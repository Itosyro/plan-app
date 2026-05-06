import { FastifyInstance } from 'fastify';
import { PrismaClient } from '@prisma/client';
import { CreateTaskSchema, UpdateTaskSchema } from '../../shared/schemas.js';
import { todayStart, tomorrowStart } from '../../shared/date-utils.js';

export function registerTaskRoutes(app: FastifyInstance, db: PrismaClient) {
  app.get('/api/tasks', async (request: any) => {
    const { user } = request;
    const query = request.query as { status?: string; limit?: string; offset?: string };

    const where: any = { userId: user.id, deletedAt: null };
    if (query.status) {
      where.status = { in: query.status.split(',') };
    }

    const tasks = await db.task.findMany({
      where,
      include: { project: true, notes: true },
      orderBy: [{ sortOrder: 'asc' }, { createdAt: 'desc' }],
      take: query.limit ? parseInt(query.limit, 10) : 100,
      skip: query.offset ? parseInt(query.offset, 10) : 0,
    });
    return tasks;
  });

  app.get('/api/tasks/:id', async (request: any, reply) => {
    const { user } = request;
    const task = await db.task.findFirst({
      where: { id: request.params.id, userId: user.id, deletedAt: null },
      include: { project: true, notes: true },
    });
    if (!task) return reply.status(404).send({ error: 'Task not found', statusCode: 404 });
    return task;
  });

  app.post('/api/tasks', async (request: any, reply) => {
    const { user } = request;
    const parsed = CreateTaskSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Validation error', details: parsed.error.flatten(), statusCode: 400 });
    }
    const data = parsed.data;
    const task = await db.task.create({
      data: {
        userId: user.id,
        title: data.title,
        description: data.description,
        status: data.status || 'inbox',
        priority: data.priority || 'medium',
        energyLevel: data.energyLevel || 'medium',
        projectId: data.projectId,
        estimatedMinutes: data.estimatedMinutes,
        scheduledFor: data.scheduledFor ? new Date(data.scheduledFor) : null,
        deadlineAt: data.deadlineAt ? new Date(data.deadlineAt) : null,
      },
      include: { project: true },
    });

    await db.taskEvent.create({
      data: { userId: user.id, taskId: task.id, type: 'created', payloadJson: { title: task.title } },
    });

    return task;
  });

  app.patch('/api/tasks/:id', async (request: any, reply) => {
    const { user } = request;
    const parsed = UpdateTaskSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Validation error', details: parsed.error.flatten(), statusCode: 400 });
    }
    const data = parsed.data;

    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Task not found', statusCode: 404 });

    const updateData: any = { ...data };
    if (data.scheduledFor !== undefined) {
      updateData.scheduledFor = data.scheduledFor ? new Date(data.scheduledFor) : null;
    }
    if (data.deadlineAt !== undefined) {
      updateData.deadlineAt = data.deadlineAt ? new Date(data.deadlineAt) : null;
    }

    const task = await db.task.update({
      where: { id: request.params.id },
      data: updateData,
      include: { project: true },
    });

    await db.taskEvent.create({
      data: { userId: user.id, taskId: task.id, type: 'updated', payloadJson: { changes: Object.keys(data) } },
    });

    return task;
  });

  app.post('/api/tasks/:id/complete', async (request: any, reply) => {
    const { user } = request;
    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Task not found', statusCode: 404 });

    const task = await db.task.update({
      where: { id: request.params.id },
      data: { status: 'done', completedAt: new Date() },
      include: { project: true },
    });

    const settings = await db.userSettings.findUnique({ where: { userId: user.id } });
    if (settings?.deleteTaskOnDone) {
      await db.task.update({ where: { id: task.id }, data: { deletedAt: new Date() } });
      if (settings.deleteNotesWithTask) {
        await db.note.deleteMany({ where: { taskId: task.id } });
      }
    }

    await db.taskEvent.create({
      data: { userId: user.id, taskId: task.id, type: 'completed', payloadJson: {} },
    });

    return task;
  });

  app.post('/api/tasks/:id/reopen', async (request: any, reply) => {
    const { user } = request;
    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Task not found', statusCode: 404 });

    const task = await db.task.update({
      where: { id: request.params.id },
      data: { status: 'inbox', completedAt: null, deletedAt: null },
      include: { project: true },
    });

    await db.taskEvent.create({
      data: { userId: user.id, taskId: task.id, type: 'reopened', payloadJson: {} },
    });

    return task;
  });

  app.post('/api/tasks/:id/reschedule', async (request: any, reply) => {
    const { user } = request;
    const { status, scheduledFor } = request.body as { status?: string; scheduledFor?: string };
    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Task not found', statusCode: 404 });

    const task = await db.task.update({
      where: { id: request.params.id },
      data: {
        status: status || 'tomorrow',
        scheduledFor: scheduledFor ? new Date(scheduledFor) : tomorrowStart(),
      },
      include: { project: true },
    });

    await db.taskEvent.create({
      data: { userId: user.id, taskId: task.id, type: 'rescheduled', payloadJson: { newStatus: status } },
    });

    return task;
  });

  app.delete('/api/tasks/:id', async (request: any, reply) => {
    const { user } = request;
    const existing = await db.task.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Task not found', statusCode: 404 });

    await db.task.update({
      where: { id: request.params.id },
      data: { deletedAt: new Date() },
    });

    await db.taskEvent.create({
      data: { userId: user.id, taskId: existing.id, type: 'deleted', payloadJson: {} },
    });

    return { success: true };
  });
}
