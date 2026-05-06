import { FastifyInstance } from 'fastify';
import { PrismaClient } from '@prisma/client';
import { UpdateSettingsSchema } from '../../shared/schemas.js';

export function registerSettingsRoutes(app: FastifyInstance, db: PrismaClient) {
  app.get('/api/settings', async (request: any) => {
    const { user } = request;
    return db.userSettings.findUnique({ where: { userId: user.id } });
  });

  app.patch('/api/settings', async (request: any, reply) => {
    const { user } = request;
    const parsed = UpdateSettingsSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: 'Validation error', details: parsed.error.flatten(), statusCode: 400 });
    }
    return db.userSettings.upsert({
      where: { userId: user.id },
      create: { userId: user.id, ...parsed.data },
      update: parsed.data,
    });
  });
}
