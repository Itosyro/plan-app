import { FastifyInstance } from 'fastify';
import { PrismaClient } from '@prisma/client';
import { CreateNoteSchema } from '../../shared/schemas.js';

export function registerNoteRoutes(app: FastifyInstance, db: PrismaClient) {
  app.get('/api/notes', async (request: any) => {
    const { user } = request;
    return db.note.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' },
      take: 100,
    });
  });

  app.post('/api/notes', async (request: any, reply) => {
    const { user } = request;
    const parsed = CreateNoteSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Validation error', details: parsed.error.flatten(), statusCode: 400 });
    }
    return db.note.create({
      data: { userId: user.id, ...parsed.data },
    });
  });

  app.patch('/api/notes/:id', async (request: any, reply) => {
    const { user } = request;
    const { title, content } = request.body as { title?: string; content?: string };
    const existing = await db.note.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Note not found', statusCode: 404 });

    return db.note.update({
      where: { id: request.params.id },
      data: { title, content },
    });
  });

  app.delete('/api/notes/:id', async (request: any, reply) => {
    const { user } = request;
    const existing = await db.note.findFirst({ where: { id: request.params.id, userId: user.id } });
    if (!existing) return reply.status(404).send({ error: 'Note not found', statusCode: 404 });

    await db.note.delete({ where: { id: request.params.id } });
    return { success: true };
  });
}
