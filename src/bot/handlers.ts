import { Bot, Context, InlineKeyboard } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { AiService } from '../ai/service.js';
import { MessageHandler } from './message-handler.js';

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
• /remind — поставить напоминание
• /settings — настройки
• /help — помощь`,
      { reply_markup: keyboard }
    );
  }

  async help(ctx: Context) {
    await ctx.reply(
      `📝 Что умею:

• Принимать текст и голосовые → превращать в задачи
• Структурировать план дня
• /remind — поставить напоминание на задачу (бот пришлёт в нужное время)
• Mini App — управление задачами, drag-and-drop колонки

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
      await ctx.reply('Настройки не найдены. Напишите /start');
      return;
    }

    const s = user.settings;
    const keyboard = new InlineKeyboard()
      .text(s.remindersEnabled ? '🔔 Напоминания: ВКЛ' : '🔕 Напоминания: ВЫКЛ', 'toggle_reminders').row()
      .text(s.dailyDigestEnabled ? '📬 Дайджест: ВКЛ' : '📭 Дайджест: ВЫКЛ', 'toggle_digest').row()
      .text(s.deleteTaskOnDone ? '🗑 Удалять при done: ВКЛ' : '📦 Удалять при done: ВЫКЛ', 'toggle_delete_on_done').row()
      .text(s.columnViewEnabled ? '📊 Колонки: ВКЛ' : '📋 Колонки: ВЫКЛ', 'toggle_columns').row()
      .webApp('⚙️ Все настройки', this.config.miniAppUrl);

    await ctx.reply('⚙️ *Настройки:*', { reply_markup: keyboard, parse_mode: 'Markdown' });
  }

  async today(ctx: Context) {
    const telegramId = String(ctx.from?.id);
    const user = await this.db.user.findUnique({ where: { telegramId } });

    if (!user) {
      await ctx.reply('Начните с /start');
      return;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    const plan = await this.db.dailyPlan.findFirst({
      where: { userId: user.id, date: { gte: today, lt: tomorrow } },
      include: { items: { include: { task: true }, orderBy: { sortOrder: 'asc' } } },
    });

    if (!plan || plan.items.length === 0) {
      const tasks = await this.db.task.findMany({
        where: { userId: user.id, status: 'today', deletedAt: null },
        orderBy: [{ priority: 'asc' }, { createdAt: 'asc' }],
        take: 10,
      });

      if (tasks.length === 0) {
        await ctx.reply('На сегодня задач нет. Напишите мне что-нибудь! 📨');
        return;
      }

      let text = '📅 *Задачи на сегодня:*\n\n';
      tasks.forEach((t, i) => {
        const pri = t.priority === 'high' ? '🔴' : t.priority === 'medium' ? '🟡' : '🟢';
        text += `${pri} ${t.title}\n`;
      });

      const keyboard = new InlineKeyboard()
        .webApp('📋 Открыть планер', this.config.miniAppUrl);

      await ctx.reply(text, { reply_markup: keyboard, parse_mode: 'Markdown' });
      return;
    }

    const mustDo = plan.items.filter((i) => i.slotLabel === 'must_do');
    const niceToDo = plan.items.filter((i) => i.slotLabel === 'nice_to_do');

    let text = '📅 *План на сегодня:*\n\n';

    if (mustDo.length > 0) {
      text += '🔥 *Критично:*\n';
      mustDo.forEach((item) => {
        text += `• ${item.task.title}\n`;
      });
      text += '\n';
    }

    if (niceToDo.length > 0) {
      text += '✨ *Если останется время:*\n';
      niceToDo.forEach((item) => {
        text += `• ${item.task.title}\n`;
      });
    }

    const keyboard = new InlineKeyboard()
      .webApp('📋 Открыть планер', this.config.miniAppUrl);

    await ctx.reply(text, { reply_markup: keyboard, parse_mode: 'Markdown' });
  }

  async plan(ctx: Context) {
    const telegramId = String(ctx.from?.id);
    const user = await this.db.user.findUnique({ where: { telegramId } });

    if (!user) {
      await ctx.reply('Начните с /start');
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
      console.error('Plan rebuild error:', err);
      await ctx.api.editMessageText(
        ctx.chat!.id,
        loading.message_id,
        '❌ Не удалось пересобрать план. Попробуйте позже.'
      );
    }
  }

  async add(ctx: Context) {
    await ctx.reply(
      '📝 Напишите задачу текстом или отправьте голосовое — я разберу и добавлю.'
    );
  }

  async remind(ctx: Context) {
    const telegramId = String(ctx.from?.id);
    const user = await this.db.user.findUnique({ where: { telegramId } });

    if (!user) {
      await ctx.reply('Начните с /start');
      return;
    }

    // Get active tasks
    const tasks = await this.db.task.findMany({
      where: { userId: user.id, status: { not: 'done' }, deletedAt: null },
      orderBy: { createdAt: 'desc' },
      take: 10,
    });

    if (tasks.length === 0) {
      await ctx.reply('У вас нет активных задач. Напишите что-нибудь, и я создам задачу!');
      return;
    }

    let text = '🔔 *Выберите задачу для напоминания:*\n\n';
    const keyboard = new InlineKeyboard();

    tasks.forEach((task, i) => {
      const pri = task.priority === 'high' ? '🔴' : task.priority === 'medium' ? '🟡' : '🟢';
      text += `${i + 1}. ${pri} ${task.title}\n`;
      keyboard.text(`${i + 1}. ${task.title.slice(0, 30)}`, `remind_task:${task.id}`).row();
    });

    await ctx.reply(text, { reply_markup: keyboard, parse_mode: 'Markdown' });
  }

  async handleCallback(ctx: Context) {
    const data = ctx.callbackQuery?.data;
    if (!data) return;

    const telegramId = String(ctx.from?.id);
    const user = await this.db.user.findUnique({
      where: { telegramId },
      include: { settings: true },
    });

    if (!user) {
      await ctx.answerCallbackQuery({ text: 'Начните с /start' });
      return;
    }

    // Settings toggles
    if (data.startsWith('toggle_')) {
      await this.handleSettingsToggle(ctx, user, data);
      return;
    }

    // Remind task — show time options
    if (data.startsWith('remind_task:')) {
      const taskId = data.replace('remind_task:', '');
      await this.showReminderTimeOptions(ctx, taskId);
      return;
    }

    // Remind time selected
    if (data.startsWith('remind_time:')) {
      const [, taskId, minutes] = data.split(':');
      await this.createReminder(ctx, user.id, taskId, parseInt(minutes));
      return;
    }

    await ctx.answerCallbackQuery();
  }

  private async handleSettingsToggle(ctx: Context, user: any, data: string) {
    const settings = user.settings;
    if (!settings) {
      await ctx.answerCallbackQuery({ text: 'Настройки не найдены' });
      return;
    }

    const toggleMap: Record<string, string> = {
      toggle_reminders: 'remindersEnabled',
      toggle_digest: 'dailyDigestEnabled',
      toggle_delete_on_done: 'deleteTaskOnDone',
      toggle_columns: 'columnViewEnabled',
    };

    const field = toggleMap[data];
    if (!field) {
      await ctx.answerCallbackQuery();
      return;
    }

    const newValue = !(settings as any)[field];
    await this.db.userSettings.update({
      where: { userId: user.id },
      data: { [field]: newValue },
    });

    await ctx.answerCallbackQuery({ text: `${newValue ? 'Включено' : 'Выключено'}` });

    // Refresh settings view
    await this.settings(ctx);
  }

  private async showReminderTimeOptions(ctx: Context, taskId: string) {
    const keyboard = new InlineKeyboard()
      .text('⏰ 15 мин', `remind_time:${taskId}:15`)
      .text('⏰ 30 мин', `remind_time:${taskId}:30`).row()
      .text('⏰ 1 час', `remind_time:${taskId}:60`)
      .text('⏰ 2 часа', `remind_time:${taskId}:120`).row()
      .text('⏰ Завтра 9:00', `remind_time:${taskId}:tomorrow`).row();

    await ctx.answerCallbackQuery();
    await ctx.editMessageText('⏰ *Через сколько напомнить?*', {
      reply_markup: keyboard,
      parse_mode: 'Markdown',
    });
  }

  private async createReminder(ctx: Context, userId: string, taskId: string, minutes: number) {
    let scheduledTime: Date;

    if (isNaN(minutes)) {
      // "tomorrow" case
      scheduledTime = new Date();
      scheduledTime.setDate(scheduledTime.getDate() + 1);
      scheduledTime.setHours(9, 0, 0, 0);
    } else {
      scheduledTime = new Date(Date.now() + minutes * 60 * 1000);
    }

    await this.db.reminder.create({
      data: {
        userId,
        taskId,
        type: 'scheduled',
        scheduledTime,
        isEnabled: true,
      },
    });

    const timeStr = scheduledTime.toLocaleString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      day: 'numeric',
      month: 'short',
    });

    await ctx.answerCallbackQuery({ text: `Напоминание установлено на ${timeStr}` });
    await ctx.editMessageText(`🔔 Напомню в *${timeStr}*`, { parse_mode: 'Markdown' });
  }

  async handleText(ctx: Context) {
    const text = ctx.message.text;
    if (text.startsWith('/')) return;
    await ctx.reply('🧠 Разбираю...');
    await this.messageHandler.processInput(ctx, 'text', text);
  }

  async handleVoice(ctx: Context) {
    const voice = ctx.message.voice;
    await ctx.reply('🎙️ Слушаю и разбираю...');
    await this.messageHandler.processInput(ctx, 'voice', voice.file_id);
  }

  async handleAudio(ctx: Context) {
    const audio = ctx.message.audio;
    await ctx.reply('🎵 Слушаю и разбираю...');
    await this.messageHandler.processInput(ctx, 'audio', audio.file_id);
  }
}
