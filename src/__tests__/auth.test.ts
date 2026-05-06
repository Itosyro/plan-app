import { describe, it, expect } from 'vitest';
import crypto from 'crypto';
import { validateInitData } from '../api/auth.js';

const BOT_TOKEN = 'test-bot-token-123:ABC';

function createValidInitData(userData: object): string {
  const userJson = JSON.stringify(userData);
  const authDate = Math.floor(Date.now() / 1000).toString();
  const queryId = 'test-query-id';

  // Build data check string the same way validation does:
  // key=value pairs sorted alphabetically, joined with \n
  const pairs: Record<string, string> = {
    auth_date: authDate,
    query_id: queryId,
    user: userJson,
  };

  const dataCheckString = Object.entries(pairs)
    .map(([k, v]) => `${k}=${v}`)
    .sort()
    .join('\n');

  const secretKey = crypto.createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest();
  const hash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');

  // Build the query string manually the same way Telegram sends it
  // URLSearchParams encodes values, and when parsed back, decodes them
  const params = new URLSearchParams();
  params.set('auth_date', authDate);
  params.set('query_id', queryId);
  params.set('user', userJson);
  params.set('hash', hash);

  return params.toString();
}

describe('validateInitData', () => {
  it('validates correct init data', () => {
    const initData = createValidInitData({
      id: 123456,
      first_name: 'Test',
      username: 'testuser',
    });

    const result = validateInitData(initData, BOT_TOKEN);
    expect(result).not.toBeNull();
    expect(result?.id).toBe(123456);
    expect(result?.first_name).toBe('Test');
    expect(result?.username).toBe('testuser');
  });

  it('rejects invalid hash', () => {
    const result = validateInitData('user=%7B%22id%22%3A1%7D&hash=invalid&auth_date=' + Math.floor(Date.now() / 1000), BOT_TOKEN);
    expect(result).toBeNull();
  });

  it('rejects missing hash', () => {
    const result = validateInitData('user=%7B%22id%22%3A1%7D', BOT_TOKEN);
    expect(result).toBeNull();
  });

  it('rejects empty string', () => {
    const result = validateInitData('', BOT_TOKEN);
    expect(result).toBeNull();
  });

  it('rejects expired init data', () => {
    const userJson = JSON.stringify({ id: 1, first_name: 'Test' });
    const authDate = (Math.floor(Date.now() / 1000) - 100000).toString();

    const pairs: Record<string, string> = {
      auth_date: authDate,
      user: userJson,
    };

    const dataCheckString = Object.entries(pairs)
      .map(([k, v]) => `${k}=${v}`)
      .sort()
      .join('\n');

    const secretKey = crypto.createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest();
    const hash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');

    const params = new URLSearchParams();
    params.set('auth_date', authDate);
    params.set('user', userJson);
    params.set('hash', hash);

    const result = validateInitData(params.toString(), BOT_TOKEN);
    expect(result).toBeNull();
  });
});
