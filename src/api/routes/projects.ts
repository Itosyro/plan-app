import { FastifyInstance } from 'fastify';
import { PrismaClient } from '@prisma/client';
import { CreateProjectSchema } from '../../shared/schemas.js';

export function registerProjectRoutes(app: FastifyInstance, db: PrismaClient) {
  app.get('/api/projects', async (request: any) => {
    const { user } = request;
    return db.project.findMany({
      where: { userId: user.id, isArchived: false },
      include: { _count: { select: { tasks: true } } },
      orderBy: { title: 'asc' },
    });
  });

  app.post('/api/projects', async (request: any, reply) => {
    const { user } = request;
    const parsed = CreateProjectSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Validation error', details: parsed.error.flatten(), statusCode: 400 });
    }
    return db.project.create({
      data: { userId: user.id, ...parsed.data },
    });
  });

  app.patch('/api/projects/:id', async (request: any, reply) => {
    const { user } = request;
    const { title, color, isArchived } = request.body as { title?: string; color?: string; isArchived?: boolean };
    const existing = await db.project.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Project not found', statusCode: 404 });

    return db.project.update({
      where: { id: request.params.id },
      data: { title, color, isArchived },
    });
  });
}
