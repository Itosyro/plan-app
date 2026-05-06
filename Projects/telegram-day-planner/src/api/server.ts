import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import { PrismaClient } from '@prisma/client';
import crypto from 'crypto';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const db = new PrismaClient();
const fastify = Fastify({ logger: true });

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN!;

// ============ AUTH ============
interface InitDataUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

function validateInitData(initData: string): InitDataUser | null {
  try {
    const params = new URLSearchParams(initData);
    const hash = params.get('hash');
    if (!hash) return null;

    params.delete('hash');
    const arr = Array.from(params.entries())
      .map(([k, v]) => `${k}=${v}`)
      .sort()
      .join('\n');

    const secretKey = crypto.createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest();
    const expectedHash = crypto.createHmac('sha256', secretKey).update(arr).digest('hex');

    if (expectedHash !== hash) return null;

    const userStr = params.get('user');
    if (!userStr) return null;

    return JSON.parse(decodeURIComponent(userStr));
  } catch {
    return null;
  }
}

async function authMiddleware(request: any, reply: any) {
  const initData = request.headers['x-init-data'];
  if (!initData) {
    return reply.status(401).send({ error: 'Unauthorized' });
  }

  const user = validateInitData(initData);
  if (!user) {
    return reply.status(401).send({ error: 'Invalid init data' });
  }

  // Get or create DB user
  let dbUser = await db.user.findUnique({
    where: { telegramId: String(user.id) },
    include: { settings: true },
  });

  if (!dbUser) {
    dbUser = await db.user.create({
      data: {
        telegramId: String(user.id),
        username: user.username,
        firstName: user.first_name,
        lastName: user.last_name,
        languageCode: user.language_code,
        settings: { create: {} },
      },
      include: { settings: true },
    });
  }

  request.user = dbUser;
}

// ============ ROUTES ============

// Health
fastify.get('/health', async () => ({ status: 'ok', time: new Date().toISOString() }));

// Serve static files from public/
fastify.register(fastifyStatic, {
  root: path.join(__dirname, '../../public'),
  prefix: '/',
});

// SPA fallback — all other routes serve index.html
fastify.setNotFoundHandler(async (request: any, reply: any) => {
  // Skip API routes — let Fastify return 404
  if (request.url.startsWith('/api/')) return;
  await reply.sendFile('index.html');
});

// Auth middleware wrapper
fastify.register(async (app) => {
  app.addHook('preHandler', authMiddleware);

  // GET /api/me
  app.get('/me', async (request: any) => {
    const { user } = request;
    return {
      id: user.id,
      telegramId: user.telegramId,
      username: user.username,
      firstName: user.firstName,
      timezone: user.timezone,
    };
  });

  // GET /api/tasks
  app.get('/tasks', async (request: any) => {
    const { user } = request;
    const tasks = await db.task.findMany({
      where: { userId: user.id, deletedAt: null },
      include: { project: true },
      orderBy: [{ priority: 'asc' }, { createdAt: 'desc' }],
    });
    return tasks;
  });

  // GET /api/tasks/:id
  app.get('/tasks/:id', async (request: any) => {
    const { user } = request;
    const task = await db.task.findFirst({
      where: { id: request.params.id, userId: user.id },
      include: { project: true, notes: true },
    });
    if (!task) return { error: 'Not found' };
    return task;
  });

  // POST /api/tasks
  app.post('/tasks', async (request: any) => {
    const { user } = request;
    const data = request.body;
    const task = await db.task.create({
      data: {
        ...data,
        userId: user.id,
        scheduledFor: data.scheduledFor ? new Date(data.scheduledFor) : null,
        deadlineAt: data.deadlineAt ? new Date(data.deadlineAt) : null,
      },
      include: { project: true },
    });
    return task;
  });

  // PATCH /api/tasks/:id
  app.patch('/tasks/:id', async (request: any) => {
    const { user } = request;
    const data = request.body;
    const task = await db.task.update({
      where: { id: request.params.id, userId: user.id },
      data: {
        ...data,
        scheduledFor: data.scheduledFor !== undefined ? (data.scheduledFor ? new Date(data.scheduledFor) : null) : undefined,
        deadlineAt: data.deadlineAt !== undefined ? (data.deadlineAt ? new Date(data.deadlineAt) : null) : undefined,
      },
      include: { project: true },
    });
    return task;
  });

  // POST /api/tasks/:id/complete
  app.post('/tasks/:id/complete', async (request: any) => {
    const { user } = request;
    const task = await db.task.update({
      where: { id: request.params.id, userId: user.id },
      data: { status: 'done', completedAt: new Date() },
    });

    // Delete if setting enabled
    const settings = await db.userSettings.findUnique({ where: { userId: user.id } });
    if (settings?.deleteTaskOnDone) {
      await db.task.update({
        where: { id: task.id },
        data: { deletedAt: new Date() },
      });
    }

    return task;
  });

  // POST /api/tasks/:id/reopen
  app.post('/tasks/:id/reopen', async (request: any) => {
    const { user } = request;
    return db.task.update({
      where: { id: request.params.id, userId: user.id },
      data: { status: 'inbox', completedAt: null },
    });
  });

  // POST /api/tasks/:id/reschedule
  app.post('/tasks/:id/reschedule', async (request: any) => {
    const { user } = request;
    const { status, scheduledFor } = request.body;
    return db.task.update({
      where: { id: request.params.id, userId: user.id },
      data: {
        status,
        scheduledFor: scheduledFor ? new Date(scheduledFor) : null,
      },
    });
  });

  // DELETE /api/tasks/:id
  app.delete('/tasks/:id', async (request: any) => {
    const { user } = request;
    await db.task.update({
      where: { id: request.params.id, userId: user.id },
      data: { deletedAt: new Date() },
    });
    return { success: true };
  });

  // GET /api/notes
  app.get('/notes', async (request: any) => {
    const { user } = request;
    return db.note.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' },
    });
  });

  // GET /api/settings
  app.get('/settings', async (request: any) => {
    const { user } = request;
    return db.userSettings.findUnique({ where: { userId: user.id } });
  });

  // PATCH /api/settings
  app.patch('/settings', async (request: any) => {
    const { user } = request;
    return db.userSettings.upsert({
      where: { userId: user.id },
      create: { userId: user.id, ...request.body },
      update: request.body,
    });
  });

  // GET /api/daily-plan/today
  app.get('/daily-plan/today', async (request: any) => {
    const { user } = request;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    return db.dailyPlan.findFirst({
      where: { userId: user.id, date: { gte: today, lt: tomorrow } },
      include: { items: { include: { task: true }, orderBy: { sortOrder: 'asc' } } },
    });
  });

  // GET /api/projects
  app.get('/projects', async (request: any) => {
    const { user } = request;
    return db.project.findMany({
      where: { userId: user.id, isArchived: false },
      orderBy: { title: 'asc' },
    });
  });
});

// ============ START ============
const PORT = Number(process.env.PORT) || 3000;

fastify.listen({ port: PORT, host: '0.0.0.0' }, (err, address) => {
  if (err) {
    console.error('Server error:', err);
    process.exit(1);
  }
  console.log(`API server running on ${address}`);
});
