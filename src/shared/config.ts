import { z } from 'zod';

const EnvSchema = z.object({
  DATABASE_URL: z.string().min(1),
  TELEGRAM_BOT_TOKEN: z.string().min(1),
  GROQ_API_KEY: z.string().min(1),
  GROQ_MODEL: z.string().default('llama-3.3-70b-versatile'),
  GROQ_STT_MODEL: z.string().default('whisper-large-v3-turbo'),
  MINIAPP_URL: z.string().default('http://localhost:3000'),
  PORT: z.coerce.number().default(3001),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  JWT_SECRET: z.string().default('dev-secret-change-me'),
  WEBHOOK_URL: z.string().optional(),
  NEXT_PUBLIC_API_URL: z.string().default('http://localhost:3001'),
});

export type Env = z.infer<typeof EnvSchema>;

let _config: Env | null = null;

export function getConfig(): Env {
  if (!_config) {
    const result = EnvSchema.safeParse(process.env);
    if (!result.success) {
      console.error('Invalid environment variables:', result.error.flatten().fieldErrors);
      process.exit(1);
    }
    _config = result.data;
  }
  return _config;
}
