import { Bot, Context, session } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { createAiService } from '../ai/service.js';
import { BotHandlers } from './handlers.js';

const {
  TELEGRAM_BOT_TOKEN,
  GROQ_API_KEY,
  GROQ_STT_MODEL = 'whisper-large-v3-turbo',
  MINIAPP_URL = 'http://localhost:5173',
} = process.env;

if (!TELEGRAM_BOT_TOKEN || !GROQ_API_KEY) {
  console.error('Missing required env vars: TELEGRAM_BOT_TOKEN, GROQ_API_KEY');
  process.exit(1);
}

const db = new PrismaClient();
const ai = createAiService(GROQ_API_KEY);
const handlers = new BotHandlers(db, ai, { miniAppUrl: MINIAPP_URL, groqSttModel: GROQ_STT_MODEL, botToken: TELEGRAM_BOT_TOKEN });

const bot = new Bot(TELEGRAM_BOT_TOKEN);

// Session middleware
bot.use(session({
  initial: () => ({}),
}));

// Commands
bot.command('start', handlers.start.bind(handlers));
bot.command('help', handlers.help.bind(handlers));
bot.command('settings', handlers.settings.bind(handlers));
bot.command('today', handlers.today.bind(handlers));
bot.command('plan', handlers.plan.bind(handlers));
bot.command('add', handlers.add.bind(handlers));

// Message handlers
bot.on('message:text', handlers.handleText.bind(handlers));
bot.on('message:voice', handlers.handleVoice.bind(handlers));
bot.on('message:audio', handlers.handleAudio.bind(handlers));

// Error handler
bot.catch((err) => {
  console.error('Bot error:', err);
});

console.log('Starting PLAN bot...');
bot.start();

// Health check server (for Render)
import * as http from 'http';
const healthPort = Number(process.env.PORT) || Number(process.env.HEALTH_PORT) || 8080;
http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'plan-bot' }));
  } else {
    res.writeHead(404);
    res.end();
  }
}).listen(healthPort, () => {
  console.log(`Health check on port ${healthPort}`);
});
console.log('Bot started!');

// Graceful shutdown
const shutdown = async (signal: string) => {
  console.log(`Received ${signal}, shutting down...`);
  bot.stop();
  await db.$disconnect();
  process.exit(0);
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
