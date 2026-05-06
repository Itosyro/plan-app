import { FastifyInstance } from 'fastify';
import { PrismaClient } from '@prisma/client';

export function registerInboxRoutes(app: FastifyInstance, db: PrismaClient) {
  app.get('/api/inbox', async (request: any) => {
    const { user } = request;
    return db.inboxEntry.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' },
      take: 50,
    });
  });
}
