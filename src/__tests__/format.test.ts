import { describe, it, expect } from 'vitest';
import { formatSummary } from '../bot/format.js';

describe('formatSummary', () => {
  it('formats tasks and notes', () => {
    const result = {
      summary: 'Три задачи на сегодня',
      extractedTasks: [
        { title: 'Задача 1', statusSuggestion: 'today', priority: 'high' },
        { title: 'Задача 2', statusSuggestion: 'tomorrow', priority: 'medium' },
      ],
      extractedNotes: [{ title: 'Заметка', content: 'Текст' }],
      extractedProjects: [],
      clarifyingQuestions: [],
    };

    const text = formatSummary(result);
    expect(text).toContain('2 задачи');
    expect(text).toContain('1 заметка');
    expect(text).toContain('Задача 1');
  });

  it('handles empty result', () => {
    const result = {
      extractedTasks: [],
      extractedNotes: [],
    };

    const text = formatSummary(result);
    expect(text).toContain('Не удалось выделить');
  });

  it('shows clarifying questions', () => {
    const result = {
      summary: 'Непонятно',
      extractedTasks: [{ title: 'Задача', statusSuggestion: 'inbox', priority: 'medium' }],
      extractedNotes: [],
      clarifyingQuestions: [{ question: 'Что именно имелось в виду?' }],
    };

    const text = formatSummary(result);
    expect(text).toContain('Что именно');
  });
});
