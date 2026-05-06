import { Context, InlineKeyboard } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { AiService } from '../ai/service.js';
import { MessageHandler } from './message-handler.js';
import { createLogger } from '../shared/logger.js';

const log = createLogger('handlers');

interface BotConfig {
  miniAppUrl: string;
  groqSttModel: string;
  botToken: string;
}

export class BotHandlers {
  private messageHandler: MessageHandler;

  constructor(
    private db: PrismaClient,
    private ai: AiService,
    private config: BotConfig
  ) {
    this.messageHandler = new MessageHandler(db, ai, config);
  }

  async start(ctx: Context) {
    const keyboard = new InlineKeyboard()
      .webApp('📋 Открыть планер', this.config.miniAppUrl);

    await ctx.reply(
      `Привет! 👋

Я помогу превратить твои мысли и голосовые в задачи и план дня.

Просто напиши мне что угодно или отправь голосовое — разберу сам.

Команды:
• /today — план на сегодня
• /plan — пересобрать план
• /settings — настройки
• /help — помощь`,
      { reply_markup: keyboard }
    );
  }

  async help(ctx: Context) {
    await ctx.reply(
      `📝 Что умею:

• Принимать текст и голосовые сообщения
• Превращать поток мыслей в задачи и заметки
• Структурировать план дня
• Напоминать о зависших задачах

Просто напиши или наговори — остальное сделаю! 🎯`
    );
  }

  async settings(ctx: Context) {
    const telegramId = String(ctx.from?.id);
    const user = await this.db.user.findUnique({
      where: { telegramId },
      include: { settings: true },
    });

    if (!user?.settings) {
      await ctx.reply('Настройки не найдены. Отправьте /start для начала.');
      return;
    }

    const s = user.settings;
    const status = `⚙️ Настройки:

• Напоминания: ${s.remindersEnabled ? '✅' : '❌'}
• Summary после обработки: ${s.postProcessingSummaryEnabled ? '✅' : '❌'}
• Ежедневный дайджест: ${s.dailyDigestEnabled ? '✅' : '❌'}${s.dailyDigestEnabled ? ` (${s.dailyDigestTime})` : ''}
• Пинг зависших задач: ${s.stuckTasksPingEnabled ? '✅' : '❌'}
• Удалять при выполнении: ${s.deleteTaskOnDone ? '✅' : '❌'}`;

    const keyboard = new InlineKeyboard()
      .webApp('⚙️ Настройки в планере', `${this.config.miniAppUrl}/settings`);

    await ctx.reply(status, { reply_markup: keyboard });
  }

  async today(ctx: Context) {
    const telegramId = String(ctx.from?.id);
    const user = await this.db.user.findUnique({ where: { telegramId } });

    if (!user) {
      await ctx.reply('Отправьте /start для начала.');
      return;
    }

    const tasks = await this.db.task.findMany({
      where: { userId: user.id, status: { in: ['today', 'inbox'] }, deletedAt: null },
      orderBy: [{ priority: 'asc' }, { createdAt: 'asc' }],
      take: 10,
    });

    if (tasks.length === 0) {
      await ctx.reply('На сегодня задач нет. Напишите или наговорите что-нибудь! 📨');
      return;
    }

    let text = '📅 *Задачи на сегодня:*\n\n';
    tasks.forEach((t, i) => {
      const priority = t.priority === 'high' ? '🔴' : t.priority === 'medium' ? '🟡' : '⚪';
      text += `${priority} ${i + 1}. ${t.title}\n`;
    });

    const keyboard = new InlineKeyboard()
      .webApp('📋 Открыть планер', this.config.miniAppUrl);

    await ctx.reply(text, { reply_markup: keyboard, parse_mode: 'Markdown' });
  }

  async plan(ctx: Context) {
    const telegramId = String(ctx.from?.id);
    const user = await this.db.user.findUnique({ where: { telegramId } });

    if (!user) {
      await ctx.reply('Отправьте /start для начала.');
      return;
    }

    const loading = await ctx.reply('🔄 Пересобираю план...');

    try {
      await this.messageHandler.rebuildDayPlan(user.id);

      await ctx.api.editMessageText(
        ctx.chat!.id,
        loading.message_id,
        '✅ План обновлён!',
        {
          reply_markup: new InlineKeyboard()
            .webApp('📋 Открыть планер', this.config.miniAppUrl),
        }
      );
    } catch (err) {
      log.error({ err }, 'Plan rebuild error');
      await ctx.api.editMessageText(
        ctx.chat!.id,
        loading.message_id,
        '❌ Не удалось пересобрать план. Попробуйте позже.'
      );
    }
  }

  async handleText(ctx: Context) {
    const text = ctx.message?.text;
    if (!text || text.startsWith('/')) return;
    await ctx.reply('🧠 Разбираю...');
    await this.messageHandler.processInput(ctx, 'text', text);
  }

  async handleVoice(ctx: Context) {
    const voice = ctx.message?.voice;
    if (!voice) return;

    if (voice.duration > 300) {
      await ctx.reply('⚠️ Голосовое слишком длинное (максимум 5 минут). Попробуйте короче.');
      return;
    }

    await ctx.reply('🎙️ Слушаю и разбираю...');
    await this.messageHandler.processInput(ctx, 'voice', voice.file_id);
  }

  async handleAudio(ctx: Context) {
    const audio = ctx.message?.audio;
    if (!audio) return;
    await ctx.reply('🎵 Слушаю и разбираю...');
    await this.messageHandler.processInput(ctx, 'audio', audio.file_id);
  }
}
