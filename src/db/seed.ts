import { PrismaClient } from '@prisma/client';

const db = new PrismaClient();

async function main() {
  console.log('Seeding database...');

  const user = await db.user.upsert({
    where: { telegramId: '000000000' },
    update: {},
    create: {
      telegramId: '000000000',
      username: 'testuser',
      firstName: 'Test',
      lastName: 'User',
      languageCode: 'ru',
      settings: {
        create: {
          remindersEnabled: true,
          postProcessingSummaryEnabled: true,
          dailyDigestEnabled: false,
          dailyDigestTime: '09:00',
        },
      },
    },
  });

  console.log('Created test user:', user.id);

  const project = await db.project.create({
    data: {
      userId: user.id,
      title: 'Личное',
      color: '#4CAF50',
    },
  });

  const tasks = [
    { title: 'Разобрать входящие', status: 'today', priority: 'high' },
    { title: 'Написать план на неделю', status: 'today', priority: 'medium' },
    { title: 'Прочитать статью о продуктивности', status: 'tomorrow', priority: 'low' },
    { title: 'Подготовить отчёт', status: 'upcoming', priority: 'high', estimatedMinutes: 60 },
    { title: 'Купить продукты', status: 'today', priority: 'medium', energyLevel: 'low' },
  ];

  for (const task of tasks) {
    await db.task.create({
      data: {
        userId: user.id,
        projectId: project.id,
        title: task.title,
        status: task.status,
        priority: task.priority,
        energyLevel: (task as any).energyLevel || 'medium',
        estimatedMinutes: (task as any).estimatedMinutes || null,
      },
    });
  }

  await db.note.create({
    data: {
      userId: user.id,
      title: 'Идея для проекта',
      content: 'Сделать интеграцию с Google Calendar для автоматического планирования.',
    },
  });

  console.log('Seed complete!');
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => db.$disconnect());
