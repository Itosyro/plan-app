import { describe, it, expect } from 'vitest';
import { parseRelativeDate } from '../shared/date-utils.js';

describe('parseRelativeDate', () => {
  it('parses "сегодня"', () => {
    const result = parseRelativeDate('сегодня');
    expect(result).not.toBeNull();
    expect(result!.getHours()).toBe(0);
    expect(result!.getMinutes()).toBe(0);
  });

  it('parses "завтра"', () => {
    const today = parseRelativeDate('сегодня')!;
    const tomorrow = parseRelativeDate('завтра')!;
    expect(tomorrow.getTime() - today.getTime()).toBe(86400000);
  });

  it('parses "послезавтра"', () => {
    const today = parseRelativeDate('сегодня')!;
    const dayAfter = parseRelativeDate('послезавтра')!;
    expect(dayAfter.getTime() - today.getTime()).toBe(172800000);
  });

  it('returns null for unknown labels', () => {
    expect(parseRelativeDate('когда-нибудь')).toBeNull();
    expect(parseRelativeDate('')).toBeNull();
    expect(parseRelativeDate('random text')).toBeNull();
  });
});
