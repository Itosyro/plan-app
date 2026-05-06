import { describe, it, expect } from 'vitest';
import { ParseInputResultSchema, CreateTaskSchema, UpdateSettingsSchema } from '../shared/schemas.js';

describe('ParseInputResultSchema', () => {
  it('validates a correct parse result', () => {
    const data = {
      summary: 'Нужно сделать три дела',
      confidence: 0.85,
      assumptions: ['Все задачи на сегодня'],
      clarifyingQuestions: [],
      extractedProjects: [],
      extractedNotes: [{ title: 'Заметка', content: 'Текст заметки' }],
      extractedTasks: [
        {
          title: 'Сделать отчёт',
          description: null,
          statusSuggestion: 'today',
          priority: 'high',
          energyLevel: 'medium',
          estimatedMinutes: 30,
          dueLabel: null,
          deadlineAt: null,
          projectName: null,
          isMaybeTask: false,
          suggestedSubtasks: [],
        },
      ],
    };

    const result = ParseInputResultSchema.safeParse(data);
    expect(result.success).toBe(true);
  });

  it('rejects invalid confidence', () => {
    const data = {
      summary: 'test',
      confidence: 2.0,
      assumptions: [],
      clarifyingQuestions: [],
      extractedProjects: [],
      extractedNotes: [],
      extractedTasks: [],
    };

    const result = ParseInputResultSchema.safeParse(data);
    expect(result.success).toBe(false);
  });
});

describe('CreateTaskSchema', () => {
  it('validates minimal task', () => {
    const result = CreateTaskSchema.safeParse({ title: 'Test task' });
    expect(result.success).toBe(true);
  });

  it('rejects empty title', () => {
    const result = CreateTaskSchema.safeParse({ title: '' });
    expect(result.success).toBe(false);
  });

  it('validates full task', () => {
    const result = CreateTaskSchema.safeParse({
      title: 'Full task',
      description: 'With description',
      status: 'today',
      priority: 'high',
      energyLevel: 'low',
      estimatedMinutes: 60,
    });
    expect(result.success).toBe(true);
  });
});

describe('UpdateSettingsSchema', () => {
  it('validates partial update', () => {
    const result = UpdateSettingsSchema.safeParse({ remindersEnabled: false });
    expect(result.success).toBe(true);
  });

  it('validates empty update', () => {
    const result = UpdateSettingsSchema.safeParse({});
    expect(result.success).toBe(true);
  });
});
