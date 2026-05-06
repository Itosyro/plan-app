import { Context, InlineKeyboard } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { AiService } from '../ai/service.js';
import { formatSummary } from './format.js';
import { createLogger } from '../shared/logger.js';
import { parseRelativeDate, todayStart, tomorrowStart } from '../shared/date-utils.js';
import { MAX_VOICE_DURATION_SECONDS } from '../shared/constants.js';

const log = createLogger('message-handler');

interface BotConfig {
  miniAppUrl: string;
  groqSttModel: string;
  botToken: string;
}

export class MessageHandler {
  constructor(
    private db: PrismaClient,
    private ai: AiService,
    private config: BotConfig
  ) {}

  async processInput(ctx: Context, sourceType: 'text' | 'voice' | 'audio', content: string) {
    const telegramId = String(ctx.from?.id);

    try {
      const user = await this.getOrCreateUser(telegramId, ctx.from);

      const inboxEntry = await this.db.inboxEntry.create({
        data: {
          userId: user.id,
          sourceType,
          rawText: sourceType === 'text' ? content : null,
          originalTelegramFileId: sourceType !== 'text' ? content : null,
          processingStatus: 'pending',
        },
      });

      let transcriptText = content;

      if (sourceType === 'voice' || sourceType === 'audio') {
        log.info({ inboxEntryId: inboxEntry.id, sourceType }, 'Starting transcription');

        await this.db.inboxEntry.update({
          where: { id: inboxEntry.id },
          data: { processingStatus: 'transcribing' },
        });

        try {
          const file = await ctx.api.getFile(content);
          const fileUrl = `https://api.telegram.org/file/bot${this.config.botToken}/${file.file_path}`;

          transcriptText = await this.transcribe(fileUrl);
          log.info({ inboxEntryId: inboxEntry.id, transcriptLength: transcriptText.length }, 'Transcription complete');
        } catch (err) {
          log.error({ err, inboxEntryId: inboxEntry.id }, 'Transcription failed');
          await this.db.inboxEntry.update({
            where: { id: inboxEntry.id },
            data: { processingStatus: 'failed', errorMessage: String(err) },
          });
          await ctx.reply('❌ Не удалось распознать голос. Попробуйте ещё раз или напишите текстом.');
          return;
        }
      }

      await this.db.inboxEntry.update({
        where: { id: inboxEntry.id },
        data: { transcriptText, processingStatus: 'parsing' },
      });

      try {
        log.info({ inboxEntryId: inboxEntry.id }, 'Starting AI parsing');
        const result = await this.ai.parseInput(transcriptText);

        await this.db.aiRun.create({
          data: {
            userId: user.id,
            inboxEntryId: inboxEntry.id,
            type: 'parse_input',
            model: 'llama-3.3-70b-versatile',
            promptVersion: 'v1',
            inputText: transcriptText,
            outputJson: result as any,
            status: 'success',
          },
        });

        await this.createEntities(user.id, inboxEntry.id, result);

        await this.db.inboxEntry.update({
          where: { id: inboxEntry.id },
          data: { processingStatus: 'saved' },
        });

        const summary = formatSummary(result);
        const keyboard = new InlineKeyboard().webApp('📋 Открыть планер', this.config.miniAppUrl);

        await ctx.reply(summary, { reply_markup: keyboard, parse_mode: 'Markdown' });

        log.info({
          inboxEntryId: inboxEntry.id,
          tasks: result.extractedTasks?.length || 0,
          notes: result.extractedNotes?.length || 0,
        }, 'Processing complete');
      } catch (err) {
        log.error({ err, inboxEntryId: inboxEntry.id }, 'AI parsing failed');

        await this.db.aiRun.create({
          data: {
            userId: user.id,
            inboxEntryId: inboxEntry.id,
            type: 'parse_input',
            model: 'llama-3.3-70b-versatile',
            promptVersion: 'v1',
            inputText: transcriptText,
            status: 'failed',
            errorMessage: String(err),
          },
        });

        await this.db.inboxEntry.update({
          where: { id: inboxEntry.id },
          data: { processingStatus: 'failed', errorMessage: 'AI parsing failed' },
        });

        await ctx.reply('❌ Не удалось разобрать сообщение. Попробуйте переформулировать.');
      }
    } catch (err) {
      log.error({ err }, 'Message handling error');
      await ctx.reply('❌ Произошла ошибка. Попробуйте позже.');
    }
  }

  private async transcribe(fileUrl: string): Promise<string> {
    const response = await fetch(fileUrl);
    if (!response.ok) throw new Error(`Failed to download audio: ${response.status}`);

    const audioBuffer = await response.arrayBuffer();
    const formData = new FormData();
    formData.append('file', new Blob([audioBuffer]), 'audio.ogg');
    formData.append('model', this.config.groqSttModel);
    formData.append('language', 'ru');

    const result = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${process.env.GROQ_API_KEY}` },
      body: formData,
    });

    if (!result.ok) {
      const error = await result.text();
      throw new Error(`STT error: ${result.status} - ${error}`);
    }

    const data = await result.json() as { text?: string };
    return data.text || '';
  }

  private async getOrCreateUser(telegramId: string, from: any) {
    let user = await this.db.user.findUnique({ where: { telegramId } });

    if (!user) {
      user = await this.db.user.create({
        data: {
          telegramId,
          username: from?.username,
          firstName: from?.first_name,
          lastName: from?.last_name,
          languageCode: from?.language_code,
          settings: { create: {} },
        },
      });
    }

    return user;
  }

  private async createEntities(userId: string, inboxEntryId: string, result: any) {
    const projectMap = new Map<string, string>();
    for (const proj of result.extractedProjects || []) {
      const existing = await this.db.project.findFirst({
        where: { userId, title: { equals: proj.title, mode: 'insensitive' } },
      });
      if (existing) {
        projectMap.set(proj.title.toLowerCase(), existing.id);
      } else {
        const project = await this.db.project.create({
          data: { userId, title: proj.title, color: proj.color || null },
        });
        projectMap.set(proj.title.toLowerCase(), project.id);
      }
    }

    for (const task of result.extractedTasks || []) {
      if (task.isMaybeTask) continue;

      const status = this.mapStatus(task.statusSuggestion);
      const scheduledFor = task.dueLabel ? parseRelativeDate(task.dueLabel) : null;

      const created = await this.db.task.create({
        data: {
          userId,
          inboxEntryId,
          projectId: task.projectName ? projectMap.get(task.projectName.toLowerCase()) || null : null,
          title: task.title,
          description: task.description || null,
          status,
          priority: task.priority || 'medium',
          energyLevel: task.energyLevel || 'medium',
          estimatedMinutes: task.estimatedMinutes || null,
          scheduledFor,
          deadlineAt: task.deadlineAt ? new Date(task.deadlineAt) : null,
          sourceText: result.summary || null,
        },
      });

      await this.db.taskEvent.create({
        data: { userId, taskId: created.id, type: 'created', payloadJson: { source: 'ai_parse', title: created.title } },
      });
    }

    for (const note of result.extractedNotes || []) {
      await this.db.note.create({
        data: {
          userId,
          inboxEntryId,
          title: note.title || null,
          content: note.content,
        },
      });
    }
  }

  private mapStatus(suggestion?: string): string {
    switch (suggestion) {
      case 'today': return 'today';
      case 'tomorrow': return 'tomorrow';
      case 'upcoming': return 'upcoming';
      case 'someday': return 'someday';
      default: return 'inbox';
    }
  }

  async rebuildDayPlan(userId: string) {
    const tasks = await this.db.task.findMany({
      where: { userId, status: { in: ['inbox', 'today', 'tomorrow', 'upcoming'] }, deletedAt: null },
      orderBy: [{ priority: 'asc' }, { scheduledFor: 'asc' }],
    });

    if (tasks.length === 0) return;

    const dateStr = new Date().toISOString().split('T')[0]!;
    const result = await this.ai.buildDayPlan(
      tasks.map((t) => ({ id: t.id, title: t.title, priority: t.priority })),
      dateStr
    );

    const today = todayStart();
    const dailyPlan = await this.db.dailyPlan.upsert({
      where: { userId_date: { userId, date: today } },
      create: { userId, date: today, summary: result.concise_summary, overloadWarning: !!result.overload_warning },
      update: { summary: result.concise_summary, overloadWarning: !!result.overload_warning },
    });

    await this.db.dailyPlanItem.deleteMany({ where: { dailyPlanId: dailyPlan.id } });

    let sortOrder = 0;
    for (const item of result.ordered_plan) {
      const existing = tasks.find((t) => t.title === item.title);
      if (existing) {
        await this.db.dailyPlanItem.create({
          data: {
            dailyPlanId: dailyPlan.id,
            taskId: existing.id,
            slotLabel: result.must_do.some((m) => m.title === item.title) ? 'must_do' : 'nice_to_do',
            sortOrder: sortOrder++,
          },
        });
      }
    }
  }
}
