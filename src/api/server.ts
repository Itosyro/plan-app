import Fastify from 'fastify';
import cors from '@fastify/cors';
import { PrismaClient } from '@prisma/client';
import { createLogger } from '../shared/logger.js';
import { getConfig } from '../shared/config.js';
import { validateInitData } from './auth.js';
import { registerTaskRoutes } from './routes/tasks.js';
import { registerNoteRoutes } from './routes/notes.js';
import { registerProjectRoutes } from './routes/projects.js';
import { registerSettingsRoutes } from './routes/settings.js';
import { registerPlanRoutes } from './routes/plan.js';
import { registerInboxRoutes } from './routes/inbox.js';

const log = createLogger('api');
const config = getConfig();
const db = new PrismaClient();

const fastify = Fastify({
  logger: false,
});

await fastify.register(cors, {
  origin: true,
  credentials: true,
});

fastify.setErrorHandler((error, _request, reply) => {
  log.error({ err: error }, 'Request error');
  const statusCode = error.statusCode || 500;
  reply.status(statusCode).send({
    error: error.message || 'Internal Server Error',
    statusCode,
  });
});

fastify.get('/health', async () => ({
  status: 'ok',
  service: 'plan-api',
  time: new Date().toISOString(),
}));

fastify.register(async (app) => {
  app.addHook('preHandler', async (request: any, reply) => {
    const initData = request.headers['x-init-data'] as string | undefined;
    if (!initData) {
      return reply.status(401).send({ error: 'Unauthorized', statusCode: 401 });
    }

    const telegramUser = validateInitData(initData, config.TELEGRAM_BOT_TOKEN);
    if (!telegramUser) {
      return reply.status(401).send({ error: 'Invalid init data', statusCode: 401 });
    }

    let dbUser = await db.user.findUnique({
      where: { telegramId: String(telegramUser.id) },
      include: { settings: true },
    });

    if (!dbUser) {
      dbUser = await db.user.create({
        data: {
          telegramId: String(telegramUser.id),
          username: telegramUser.username,
          firstName: telegramUser.first_name,
          lastName: telegramUser.last_name,
          languageCode: telegramUser.language_code,
          settings: { create: {} },
        },
        include: { settings: true },
      });
    }

    request.user = dbUser;
  });

  app.get('/api/me', async (request: any) => {
    const { user } = request;
    return {
      id: user.id,
      telegramId: user.telegramId,
      username: user.username,
      firstName: user.firstName,
      timezone: user.timezone,
      settings: user.settings,
    };
  });

  registerTaskRoutes(app, db);
  registerNoteRoutes(app, db);
  registerProjectRoutes(app, db);
  registerSettingsRoutes(app, db);
  registerPlanRoutes(app, db);
  registerInboxRoutes(app, db);
});

fastify.listen({ port: config.PORT, host: '0.0.0.0' }, (err, address) => {
  if (err) {
    log.error(err, 'Server startup failed');
    process.exit(1);
  }
  log.info(`API server running on ${address}`);
});
