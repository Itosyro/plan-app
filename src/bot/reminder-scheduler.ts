import { Bot } from 'grammy';
import { PrismaClient } from '@prisma/client';

const CHECK_INTERVAL_MS = 30_000; // check every 30 seconds

export class ReminderScheduler {
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private db: PrismaClient,
    private bot: Bot
  ) {}

  start() {
    console.log('Reminder scheduler started');
    this.timer = setInterval(() => this.check(), CHECK_INTERVAL_MS);
    // Run once immediately
    this.check();
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private async check() {
    try {
      const now = new Date();

      // Find all due reminders
      const reminders = await this.db.reminder.findMany({
        where: {
          isEnabled: true,
          scheduledTime: { lte: now },
        },
        include: {
          task: true,
          user: true,
        },
      });

      for (const reminder of reminders) {
        try {
          const chatId = reminder.user.telegramId;
          const taskTitle = reminder.task?.title || 'Напоминание';

          let text = `🔔 *Напоминание*\n\n`;
          if (reminder.task) {
            text += `📌 ${taskTitle}`;
            if (reminder.task.description) {
              text += `\n${reminder.task.description}`;
            }
          } else {
            text += taskTitle;
          }

          await this.bot.api.sendMessage(chatId, text, { parse_mode: 'Markdown' });

          // Disable the reminder after sending (one-shot)
          await this.db.reminder.update({
            where: { id: reminder.id },
            data: { isEnabled: false },
          });
        } catch (err) {
          console.error(`Failed to send reminder ${reminder.id}:`, err);
        }
      }
    } catch (err) {
      console.error('Reminder check error:', err);
    }
  }
}
