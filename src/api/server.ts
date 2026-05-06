import Fastify from 'fastify';
import fastifyStatic from '@fastify/static';
import fastifyCors from '@fastify/cors';
import { PrismaClient } from '@prisma/client';
import crypto from 'crypto';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';
import { CreateTaskSchema, UpdateTaskSchema, UpdateSettingsSchema, TaskStatusEnum } from '../shared/schemas.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const db = new PrismaClient();
const fastify = Fastify({
  logger: true,
  bodyLimit: 1024 * 256, // 256KB max body
});

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';

// CORS
fastify.register(fastifyCors, { origin: true });

// Static files — works both in dev (src/) and prod (dist/)
const publicDir = path.join(__dirname, '../../public');
fastify.register(fastifyStatic, {
  root: publicDir,
  prefix: '/',
});

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

// Global error handler
fastify.setErrorHandler(async (error, request, reply) => {
  request.log.error(error);

  // Prisma record-not-found
  if (error.message?.includes('Record to update not found') ||
      error.message?.includes('Record to delete does not exist')) {
    return reply.status(404).send({ error: 'Not found' });
  }

  return reply.status(error.statusCode || 500).send({
    error: error.message || 'Internal server error',
  });
});

// API routes with /api prefix
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
    return db.task.findMany({
      where: { userId: user.id, deletedAt: null },
      include: { project: true },
      orderBy: [{ priority: 'asc' }, { createdAt: 'desc' }],
    });
  });

  // GET /api/tasks/:id
  app.get('/tasks/:id', async (request: any, reply: any) => {
    const { user } = request;
    const task = await db.task.findFirst({
      where: { id: request.params.id, userId: user.id, deletedAt: null },
      include: { project: true, notes: true },
    });
    if (!task) return reply.status(404).send({ error: 'Not found' });
    return task;
  });

  // POST /api/tasks — validated with Zod
  app.post('/tasks', async (request: any, reply: any) => {
    const { user } = request;
    const parsed = CreateTaskSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Invalid data', details: parsed.error.flatten() });
    }

    const data = parsed.data;
    const task = await db.task.create({
      data: {
        userId: user.id,
        title: data.title,
        description: data.description || null,
        status: data.status || 'inbox',
        priority: data.priority || 'medium',
        energyLevel: data.energyLevel || 'medium',
        projectId: data.projectId || null,
        estimatedMinutes: data.estimatedMinutes || null,
        scheduledFor: data.scheduledFor ? new Date(data.scheduledFor) : null,
        deadlineAt: data.deadlineAt ? new Date(data.deadlineAt) : null,
      },
      include: { project: true },
    });
    return task;
  });

  // PATCH /api/tasks/:id — validated with Zod
  app.patch('/tasks/:id', async (request: any, reply: any) => {
    const { user } = request;
    const parsed = UpdateTaskSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Invalid data', details: parsed.error.flatten() });
    }

    const data = parsed.data;
    const updateData: any = {};
    if (data.title !== undefined) updateData.title = data.title;
    if (data.description !== undefined) updateData.description = data.description;
    if (data.status !== undefined) updateData.status = data.status;
    if (data.priority !== undefined) updateData.priority = data.priority;
    if (data.energyLevel !== undefined) updateData.energyLevel = data.energyLevel;
    if (data.projectId !== undefined) updateData.projectId = data.projectId;
    if (data.estimatedMinutes !== undefined) updateData.estimatedMinutes = data.estimatedMinutes;
    if (data.scheduledFor !== undefined) updateData.scheduledFor = data.scheduledFor ? new Date(data.scheduledFor) : null;
    if (data.deadlineAt !== undefined) updateData.deadlineAt = data.deadlineAt ? new Date(data.deadlineAt) : null;

    // Verify ownership first
    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id, deletedAt: null } });
    if (!existing) return reply.status(404).send({ error: 'Not found' });

    const task = await db.task.update({
      where: { id: request.params.id },
      data: updateData,
      include: { project: true },
    });
    return task;
  });

  // POST /api/tasks/:id/complete
  app.post('/tasks/:id/complete', async (request: any, reply: any) => {
    const { user } = request;

    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id, deletedAt: null } });
    if (!existing) return reply.status(404).send({ error: 'Not found' });

    const task = await db.task.update({
      where: { id: request.params.id },
      data: { status: 'done', completedAt: new Date() },
    });

    const settings = await db.userSettings.findUnique({ where: { userId: user.id } });
    if (settings?.deleteTaskOnDone) {
      await db.task.update({ where: { id: task.id }, data: { deletedAt: new Date() } });
    }

    return task;
  });

  // POST /api/tasks/:id/reopen
  app.post('/tasks/:id/reopen', async (request: any, reply: any) => {
    const { user } = request;

    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Not found' });

    return db.task.update({
      where: { id: request.params.id },
      data: { status: 'inbox', completedAt: null, deletedAt: null },
    });
  });

  // POST /api/tasks/:id/reschedule
  app.post('/tasks/:id/reschedule', async (request: any, reply: any) => {
    const { user } = request;
    const body = request.body || {};
    const status = TaskStatusEnum.safeParse(body.status);
    if (!status.success) {
      return reply.status(400).send({ error: 'Invalid status' });
    }

    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id, deletedAt: null } });
    if (!existing) return reply.status(404).send({ error: 'Not found' });

    return db.task.update({
      where: { id: request.params.id },
      data: {
        status: status.data,
        scheduledFor: body.scheduledFor ? new Date(body.scheduledFor) : null,
      },
    });
  });

  // DELETE /api/tasks/:id (soft delete)
  app.delete('/tasks/:id', async (request: any, reply: any) => {
    const { user } = request;

    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id, deletedAt: null } });
    if (!existing) return reply.status(404).send({ error: 'Not found' });

    await db.task.update({
      where: { id: request.params.id },
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

  // PATCH /api/settings — validated with Zod
  app.patch('/settings', async (request: any, reply: any) => {
    const { user } = request;
    const parsed = UpdateSettingsSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Invalid data', details: parsed.error.flatten() });
    }

    return db.userSettings.upsert({
      where: { userId: user.id },
      create: { userId: user.id, ...parsed.data },
      update: parsed.data,
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

  // ============ REMINDERS ============

  // GET /api/reminders
  app.get('/reminders', async (request: any) => {
    const { user } = request;
    return db.reminder.findMany({
      where: { userId: user.id, isEnabled: true },
      include: { task: true },
      orderBy: { scheduledTime: 'asc' },
    });
  });

  // POST /api/reminders
  app.post('/reminders', async (request: any, reply: any) => {
    const { user } = request;
    const body = request.body || {};

    if (!body.taskId || !body.scheduledTime) {
      return reply.status(400).send({ error: 'taskId and scheduledTime are required' });
    }

    // Verify task ownership
    const task = await db.task.findFirst({ where: { id: body.taskId, userId: user.id, deletedAt: null } });
    if (!task) return reply.status(404).send({ error: 'Task not found' });

    return db.reminder.create({
      data: {
        userId: user.id,
        taskId: body.taskId,
        type: body.type || 'scheduled',
        scheduledTime: new Date(body.scheduledTime),
        isEnabled: true,
      },
      include: { task: true },
    });
  });

  // DELETE /api/reminders/:id
  app.delete('/reminders/:id', async (request: any, reply: any) => {
    const { user } = request;
    const existing = await db.reminder.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Not found' });

    await db.reminder.delete({ where: { id: request.params.id } });
    return { success: true };
  });
}, { prefix: '/api' });

// ============ GRACEFUL SHUTDOWN ============
const shutdown = async (signal: string) => {
  fastify.log.info(`Received ${signal}, shutting down...`);
  await fastify.close();
  await db.$disconnect();
  process.exit(0);
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// ============ START ============
async function start() {
  // Run DB migrations on startup (needed for first deploy)
  try {
    console.log('Running prisma db push...');
    execSync('npx prisma db push --accept-data-loss', { stdio: 'inherit' });
    console.log('DB schema synced.');
  } catch (e) {
    console.error('prisma db push failed, continuing anyway:', (e as Error).message);
  }

  const PORT = Number(process.env.PORT) || 3000;
  fastify.listen({ port: PORT, host: '0.0.0.0' }, (err, address) => {
    if (err) {
      console.error('Server error:', err);
      process.exit(1);
    }
    console.log(`API server running on ${address}`);
  });
}

start();
