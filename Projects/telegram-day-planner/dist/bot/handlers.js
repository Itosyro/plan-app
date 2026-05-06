import { InlineKeyboard } from 'grammy';
import { MessageHandler } from './message-handler.js';
export class BotHandlers {
    db;
    ai;
    config;
    messageHandler;
    constructor(db, ai, config) {
        this.db = db;
        this.ai = ai;
        this.config = config;
        this.messageHandler = new MessageHandler(db, ai, config);
    }
    async start(ctx) {
        const keyboard = new InlineKeyboard()
            .webApp('📋 Открыть планер', this.config.miniAppUrl);
        await ctx.reply(`Привет! 👋

Я помогу превратить твои мысли и голосовые в задачи и план дня.

Просто напиши мне что угодно или отправь голосовое — разберу сам.

Команды:
• /today — план на сегодня
• /plan — пересобрать план
• /settings — настройки
• /help — помощь`, { reply_markup: keyboard });
    }
    async help(ctx) {
        await ctx.reply(`📝 Что умею:

• Принимать текст и голосовые
• Превращать хаос в задачи и заметки
• Структурировать план дня

Просто напиши или наговори — остальное сделаю! 🎯`);
    }
    async settings(ctx) {
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
        const status = `⚙️ Настройки:

• Напоминания: ${s.remindersEnabled ? '✅' : '❌'}
• Summary: ${s.postProcessingSummaryEnabled ? '✅' : '❌'}
• Дайджест: ${s.dailyDigestEnabled ? '✅' : '❌'}
• Удалять при done: ${s.deleteTaskOnDone ? '✅' : '❌'}`;
        const keyboard = new InlineKeyboard()
            .webApp('⚙️ Подробнее', `${this.config.miniAppUrl}/settings`);
        await ctx.reply(status, { reply_markup: keyboard });
    }
    async today(ctx) {
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
            // Get today tasks directly
            const tasks = await this.db.task.findMany({
                where: { userId: user.id, status: 'today', deletedAt: null },
                orderBy: [{ priority: 'asc' }, { createdAt: 'asc' }],
                take: 5,
            });
            if (tasks.length === 0) {
                await ctx.reply('На сегодня задач нет. Напишите мне что-нибудь! 📨');
                return;
            }
            let text = '📅 *Задачи на сегодня:*\n\n';
            tasks.forEach((t, i) => {
                text += `${i + 1}. ${t.title}\n`;
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
            mustDo.forEach((item, i) => {
                text += `${i + 1}. ${item.task.title}\n`;
            });
            text += '\n';
        }
        if (niceToDo.length > 0) {
            text += '✨ *Если останется время:*\n';
            niceToDo.forEach((item, i) => {
                text += `${i + 1}. ${item.task.title}\n`;
            });
        }
        const keyboard = new InlineKeyboard()
            .webApp('📋 Открыть планер', this.config.miniAppUrl);
        await ctx.reply(text, { reply_markup: keyboard, parse_mode: 'Markdown' });
    }
    async plan(ctx) {
        const telegramId = String(ctx.from?.id);
        const user = await this.db.user.findUnique({ where: { telegramId } });
        if (!user) {
            await ctx.reply('Начните с /start');
            return;
        }
        const loading = await ctx.reply('🔄 Пересобираю план...');
        try {
            await this.messageHandler.rebuildDayPlan(user.id);
            await ctx.api.editMessageText(ctx.chat.id, loading.message_id, '✅ План обновлён!', {
                reply_markup: new InlineKeyboard()
                    .webApp('📋 Открыть планер', this.config.miniAppUrl),
            });
        }
        catch (err) {
            console.error('Plan rebuild error:', err);
            await ctx.api.editMessageText(ctx.chat.id, loading.message_id, '❌ Не удалось пересобрать план. Попробуйте позже.');
        }
    }
    async add(ctx) {
        await ctx.reply('📝 Напишите задачу текстом или отправьте голосовое.\n\nОтмена: /cancel');
        // Simple flow: wait for next message
        const waitingCtx = ctx;
        const handler = async (msgCtx) => {
            if (msgCtx.message?.text?.toLowerCase() === '/cancel') {
                await msgCtx.reply('✅ Отменено');
                // Remove listeners
                return;
            }
            if (msgCtx.message?.text) {
                await msgCtx.reply('🧠 Разбираю...');
                await this.messageHandler.processInput(msgCtx, 'text', msgCtx.message.text);
                return;
            }
            if (msgCtx.message?.voice) {
                await msgCtx.reply('🎙️ Слушаю...');
                await this.messageHandler.processInput(msgCtx, 'voice', msgCtx.message.voice.file_id);
                return;
            }
            if (msgCtx.message?.audio) {
                await msgCtx.reply('🎵 Слушаю...');
                await this.messageHandler.processInput(msgCtx, 'audio', msgCtx.message.audio.file_id);
                return;
            }
        };
        // This is simplified - in production use conversations plugin
        ctx.reply('Жду сообщение...');
    }
    async handleText(ctx) {
        const text = ctx.message.text;
        if (text.startsWith('/'))
            return;
        await ctx.reply('🧠 Разбираю...');
        await this.messageHandler.processInput(ctx, 'text', text);
    }
    async handleVoice(ctx) {
        const voice = ctx.message.voice;
        await ctx.reply('🎙️ Слушаю и разбираю...');
        await this.messageHandler.processInput(ctx, 'voice', voice.file_id);
    }
    async handleAudio(ctx) {
        const audio = ctx.message.audio;
        await ctx.reply('🎵 Слушаю и разбираю...');
        await this.messageHandler.processInput(ctx, 'audio', audio.file_id);
    }
}
