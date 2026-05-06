import cron from 'node-cron';
import { PrismaClient } from '@prisma/client';
import { Bot } from 'grammy';
import { createLogger } from '../shared/logger.js';
import type { Env } from '../shared/config.js';

const log = createLogger('cron');

export function startCronJobs(db: PrismaClient, bot: Bot, config: Env) {
  // Daily digest — every day check users with digest enabled
  cron.schedule('* * * * *', async () => {
    try {
      const now = new Date();
      const currentHour = now.getUTCHours();
      const currentMinute = now.getUTCMinutes();

      const users = await db.user.findMany({
        where: {
          settings: {
            dailyDigestEnabled: true,
            dailyDigestTime: { not: null },
          },
        },
        include: { settings: true },
      });

      for (const user of users) {
        if (!user.settings?.dailyDigestTime) continue;

        const [hours, minutes] = user.settings.dailyDigestTime.split(':').map(Number);
        // Rough timezone offset for Europe/Moscow (+3)
        const moscowHour = (currentHour + 3) % 24;

        if (moscowHour === hours && currentMinute === minutes) {
          await sendDailyDigest(db, bot, user, config);
        }
      }
    } catch (err) {
      log.error({ err }, 'Daily digest cron error');
    }
  });

  // Stuck tasks ping — every 6 hours
  cron.schedule('0 */6 * * *', async () => {
    try {
      const users = await db.user.findMany({
        where: {
          settings: { stuckTasksPingEnabled: true },
        },
        include: { settings: true },
      });

      for (const user of users) {
        await sendStuckTasksPing(db, bot, user, config);
      }
    } catch (err) {
      log.error({ err }, 'Stuck tasks ping cron error');
    }
  });

  log.info('Cron jobs started');
}

async function sendDailyDigest(db: PrismaClient, bot: Bot, user: any, config: Env) {
  try {
    const tasks = await db.task.findMany({
      where: {
        userId: user.id,
        status: { in: ['today', 'inbox'] },
        deletedAt: null,
      },
      orderBy: [{ priority: 'asc' }, { createdAt: 'asc' }],
      take: 10,
    });

    if (tasks.length === 0) return;

    let text = '📅 *Дайджест на сегодня:*\n\n';
    tasks.forEach((t: any, i: number) => {
      const priority = t.priority === 'high' ? '🔴' : t.priority === 'medium' ? '🟡' : '⚪';
      text += `${priority} ${i + 1}. ${t.title}\n`;
    });

    text += `\nВсего задач: ${tasks.length}`;

    await bot.api.sendMessage(Number(user.telegramId), text, {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [{ text: '📋 Открыть планер', web_app: { url: config.MINIAPP_URL } }],
        ],
      },
    });

    log.info({ userId: user.id }, 'Daily digest sent');
  } catch (err) {
    log.error({ err, userId: user.id }, 'Failed to send daily digest');
  }
}

async function sendStuckTasksPing(db: PrismaClient, bot: Bot, user: any, config: Env) {
  try {
    const intervalHours = user.settings?.stuckTasksPingIntervalHours || 24;
    const threshold = new Date();
    threshold.setHours(threshold.getHours() - intervalHours);

    const stuckTasks = await db.task.findMany({
      where: {
        userId: user.id,
        status: { in: ['today', 'inbox'] },
        deletedAt: null,
        updatedAt: { lt: threshold },
      },
      take: 5,
    });

    if (stuckTasks.length === 0) return;

    let text = '⏰ *Зависшие задачи:*\n\n';
    stuckTasks.forEach((t: any, i: number) => {
      text += `${i + 1}. ${t.title}\n`;
    });

    text += '\nЭти задачи давно не обновлялись. Может, стоит пересмотреть?';

    await bot.api.sendMessage(Number(user.telegramId), text, {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [{ text: '📋 Открыть планер', web_app: { url: config.MINIAPP_URL } }],
        ],
      },
    });

    log.info({ userId: user.id, count: stuckTasks.length }, 'Stuck tasks ping sent');
  } catch (err) {
    log.error({ err, userId: user.id }, 'Failed to send stuck tasks ping');
  }
}
