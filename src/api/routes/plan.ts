import { FastifyInstance } from 'fastify';
import { PrismaClient } from '@prisma/client';
import { todayStart, tomorrowStart } from '../../shared/date-utils.js';
import { createAiService } from '../../ai/service.js';
import { getConfig } from '../../shared/config.js';

export function registerPlanRoutes(app: FastifyInstance, db: PrismaClient) {
  app.get('/api/daily-plan/today', async (request: any) => {
    const { user } = request;
    const today = todayStart(user.timezone);
    const tomorrow = tomorrowStart(user.timezone);

    const plan = await db.dailyPlan.findFirst({
      where: { userId: user.id, date: { gte: today, lt: tomorrow } },
      include: {
        items: {
          include: { task: { include: { project: true } } },
          orderBy: { sortOrder: 'asc' },
        },
      },
    });

    return plan || { items: [], summary: null, overloadWarning: false };
  });

  app.post('/api/daily-plan/rebuild', async (request: any) => {
    const { user } = request;
    const config = getConfig();
    const ai = createAiService(config.GROQ_API_KEY);

    const tasks = await db.task.findMany({
      where: {
        userId: user.id,
        status: { in: ['inbox', 'today', 'tomorrow', 'upcoming'] },
        deletedAt: null,
      },
      orderBy: [{ priority: 'asc' }, { scheduledFor: 'asc' }],
    });

    if (tasks.length === 0) {
      return { items: [], summary: 'Нет активных задач', overloadWarning: false };
    }

    const dateStr = new Date().toISOString().split('T')[0];
    const result = await ai.buildDayPlan(
      tasks.map((t) => ({
        id: t.id,
        title: t.title,
        priority: t.priority,
        estimatedMinutes: t.estimatedMinutes ?? undefined,
        deadlineAt: t.deadlineAt?.toISOString(),
      })),
      dateStr!
    );

    const today = todayStart(user.timezone);
    const dailyPlan = await db.dailyPlan.upsert({
      where: { userId_date: { userId: user.id, date: today } },
      create: {
        userId: user.id,
        date: today,
        summary: result.concise_summary,
        overloadWarning: !!result.overload_warning,
      },
      update: {
        summary: result.concise_summary,
        overloadWarning: !!result.overload_warning,
      },
    });

    await db.dailyPlanItem.deleteMany({ where: { dailyPlanId: dailyPlan.id } });

    let sortOrder = 0;
    for (const planItem of result.ordered_plan) {
      const matchingTask = tasks.find((t) => t.title === planItem.title);
      if (matchingTask) {
        await db.dailyPlanItem.create({
          data: {
            dailyPlanId: dailyPlan.id,
            taskId: matchingTask.id,
            slotLabel: result.must_do.some((m) => m.title === planItem.title) ? 'must_do' : 'nice_to_do',
            sortOrder: sortOrder++,
          },
        });
      }
    }

    await db.aiRun.create({
      data: {
        userId: user.id,
        type: 'build_day_plan',
        model: config.GROQ_MODEL,
        promptVersion: 'v1',
        inputText: JSON.stringify(tasks.map((t) => t.title)),
        outputJson: result as any,
        status: 'success',
      },
    });

    return db.dailyPlan.findFirst({
      where: { id: dailyPlan.id },
      include: {
        items: {
          include: { task: { include: { project: true } } },
          orderBy: { sortOrder: 'asc' },
        },
      },
    });
  });
}
