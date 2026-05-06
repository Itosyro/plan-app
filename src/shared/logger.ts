import pino from 'pino';

const pinoFn = (pino as any).default || pino;

export const logger = pinoFn({
  transport:
    process.env.NODE_ENV !== 'production'
      ? { target: 'pino-pretty', options: { colorize: true } }
      : undefined,
  level: process.env.LOG_LEVEL || 'info',
});

export function createLogger(name: string) {
  return logger.child({ service: name });
}
