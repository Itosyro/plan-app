import { Context } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { AiService } from '../ai/service.js';
import { formatSummary } from './format.js';

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

  async processInput(
    ctx: Context,
    sourceType: 'text' | 'voice' | 'audio',
    content: string
  ) {
    const telegramId = String(ctx.from?.id);

    try {
      // Get or create user
      const user = await this.getOrCreateUser(telegramId, ctx.from);

      // Create inbox entry
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

      // Transcribe if voice/audio
      if (sourceType === 'voice' || sourceType === 'audio') {
        await this.db.inboxEntry.update({
          where: { id: inboxEntry.id },
          data: { processingStatus: 'transcribing' },
        });

        try {
          // Get file info and construct URL
          const file = await ctx.api.getFile(content);
          // Note: In production, store bot token securely and construct URL
          const fileUrl = `https://api.telegram.org/file/bot${this.config.botToken || ''}/${file.file_path}`;
          transcriptText = await this.transcribe(fileUrl);
        } catch (err) {
          console.error('Transcription error:', err);
          await this.db.inboxEntry.update({
            where: { id: inboxEntry.id },
            data: { processingStatus: 'failed', errorMessage: 'Transcription failed' },
          });
          await ctx.reply('❌ Не удалось распознать голос. Попробуйте ещё раз.');
          return;
        }
      }

      // Parse with AI
      await this.db.inboxEntry.update({
        where: { id: inboxEntry.id },
        data: { transcriptText, processingStatus: 'parsing' },
      });

      try {
        const result = await this.ai.parseInput(transcriptText);

        // Save AI run
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

        // Create entities
        await this.createEntities(user.id, inboxEntry.id, result);

        await this.db.inboxEntry.update({
          where: { id: inboxEntry.id },
          data: { processingStatus: 'saved' },
        });

        // Send summary
        const summary = formatSummary(result);
        const keyboard = {
          inline_keyboard: [
            [{ text: '📋 Открыть планер', web_app: { url: this.config.miniAppUrl } }],
          ],
        };

        await ctx.reply(summary, { reply_markup: keyboard, parse_mode: 'Markdown' });

      } catch (err) {
        console.error('Parsing error:', err);
        await this.db.inboxEntry.update({
          where: { id: inboxEntry.id },
          data: { processingStatus: 'failed', errorMessage: 'Parsing failed' },
        });
        await ctx.reply('❌ Не удалось разобрать сообщение. Попробуйте ещё раз.');
      }

    } catch (err) {
      console.error('Message handling error:', err);
      await ctx.reply('❌ Произошла ошибка. Попробуйте позже.');
    }
  }

  private async transcribe(fileUrl: string): Promise<string> {
    const response = await fetch(fileUrl);
    if (!response.ok) throw new Error('Failed to download audio');

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

    const data = await result.json();
    return data.text || '';
  }

  private async getOrCreateUser(telegramId: string, from: any) {
    let user = await this.db.user.findUnique({ where: { telegramId } });

    if (!user) {
      user = await this.db.user.create({
        data: {
          telegramId,
          username: from.username,
          firstName: from.first_name,
          lastName: from.last_name,
          languageCode: from.language_code,
          settings: { create: {} },
        },
      });
    }

    return user;
  }

  private async createEntities(userId: string, inboxEntryId: string, result: any) {
    // Create projects
    const projectMap = new Map<string, string>();
    for (const proj of result.extractedProjects || []) {
      const project = await this.db.project.create({
        data: { userId, title: proj.title, color: proj.color || null },
      });
      projectMap.set(proj.title.toLowerCase(), project.id);
    }

    // Create tasks
    for (const task of result.extractedTasks || []) {
      if (task.isMaybeTask) continue;

      const status = this.mapStatus(task.statusSuggestion);
      const scheduledFor = task.dueLabel ? this.parseRelativeDate(task.dueLabel) : null;

      await this.db.task.create({
        data: {
          userId,
          inboxEntryId,
          projectId: task.projectName ? projectMap.get(task.projectName.toLowerCase()) : null,
          title: task.title,
          description: task.description || null,
          status,
          priority: task.priority || 'medium',
          energyLevel: task.energyLevel || 'medium',
          estimatedMinutes: task.estimatedMinutes || null,
          scheduledFor,
          deadlineAt: task.deadlineAt ? new Date(task.deadlineAt) : null,
        },
      });
    }

    // Create notes
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

  private parseRelativeDate(label: string): Date | null {
    const now = new Date();
    const lower = label.toLowerCase();

    if (lower.includes('сегодня')) return now;
    if (lower.includes('завтра')) {
      const d = new Date(now);
      d.setDate(d.getDate() + 1);
      return d;
    }
    if (lower.includes('послезавтра')) {
      const d = new Date(now);
      d.setDate(d.getDate() + 2);
      return d;
    }
    return null;
  }

  async rebuildDayPlan(userId: string) {
    const tasks = await this.db.task.findMany({
      where: { userId, status: { in: ['inbox', 'today', 'tomorrow', 'upcoming'] }, deletedAt: null },
      orderBy: [{ priority: 'asc' }, { scheduledFor: 'asc' }],
    });

    if (tasks.length === 0) return;

    const today = new Date().toISOString().split('T')[0];
    const result = await this.ai.buildDayPlan(
      tasks.map((t) => ({ id: t.id, title: t.title, priority: t.priority })),
      today
    );

    // Create/update daily plan
    const todayDate = new Date();
    todayDate.setHours(0, 0, 0, 0);

    const dailyPlan = await this.db.dailyPlan.upsert({
      where: { userId_date: { userId, date: todayDate } },
      create: {
        userId,
        date: todayDate,
        summary: result.concise_summary,
        overloadWarning: !!result.overload_warning,
      },
      update: {
        summary: result.concise_summary,
        overloadWarning: !!result.overload_warning,
      },
    });

    // Clear old items
    await this.db.dailyPlanItem.deleteMany({ where: { dailyPlanId: dailyPlan.id } });

    // Add new items
    let sortOrder = 0;
    for (const task of result.ordered_plan) {
      const existing = tasks.find((t) => t.title === task.title);
      if (existing) {
        await this.db.dailyPlanItem.create({
          data: {
            dailyPlanId: dailyPlan.id,
            taskId: existing.id,
            slotLabel: result.must_do.some((m) => m.title === task.title) ? 'must_do' : 'nice_to_do',
            sortOrder: sortOrder++,
          },
        });
      }
    }
  }
}
