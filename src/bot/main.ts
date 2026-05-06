import { Bot, session } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { createAiService } from '../ai/service.js';
import { BotHandlers } from './handlers.js';
import { getConfig } from '../shared/config.js';
import { createLogger } from '../shared/logger.js';
import { startCronJobs } from '../cron/index.js';
import * as http from 'http';

const log = createLogger('bot');
const config = getConfig();

const db = new PrismaClient();
const ai = createAiService(config.GROQ_API_KEY);
const handlers = new BotHandlers(db, ai, {
  miniAppUrl: config.MINIAPP_URL,
  groqSttModel: config.GROQ_STT_MODEL,
  botToken: config.TELEGRAM_BOT_TOKEN,
});

const bot = new Bot(config.TELEGRAM_BOT_TOKEN);

bot.use(session({ initial: () => ({}) }) as any);

bot.command('start', (ctx) => handlers.start(ctx));
bot.command('help', (ctx) => handlers.help(ctx));
bot.command('settings', (ctx) => handlers.settings(ctx));
bot.command('today', (ctx) => handlers.today(ctx));
bot.command('plan', (ctx) => handlers.plan(ctx));

bot.on('message:text', (ctx) => handlers.handleText(ctx));
bot.on('message:voice', (ctx) => handlers.handleVoice(ctx));
bot.on('message:audio', (ctx) => handlers.handleAudio(ctx));

bot.catch((err) => {
  log.error({ err: err.error }, 'Bot error');
});

log.info('Starting PLAN bot...');
bot.start();

startCronJobs(db, bot, config);

const healthPort = Number(process.env.HEALTH_PORT) || 8080;
http
  .createServer((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'plan-bot' }));
  })
  .listen(healthPort, () => {
    log.info(`Health check on port ${healthPort}`);
  });

log.info('Bot started!');
