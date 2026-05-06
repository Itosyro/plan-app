import {
  ParseInputResultSchema,
  BuildDayPlanResultSchema,
  DailyReviewResultSchema,
  ParseInputResult,
  BuildDayPlanResult,
  DailyReviewResult,
} from '../shared/schemas.js';
import {
  PARSE_INPUT_PROMPT,
  BUILD_DAY_PLAN_PROMPT,
  DAILY_REVIEW_PROMPT,
} from './prompts.js';

const MAX_RETRIES = 2;

interface GroqResponse {
  choices: Array<{ message: { content: string } }>;
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export class AiService {
  constructor(private apiKey: string) {}

  private async completion<T>(
    model: string,
    systemPrompt: string,
    userPrompt: string,
    schema: any,
    retries = MAX_RETRIES
  ): Promise<T> {
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ],
        temperature: 0.3,
        max_tokens: 4096,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Groq API error: ${response.status} - ${error}`);
    }

    const data: GroqResponse = await response.json();
    const content = data.choices[0]?.message?.content;

    if (!content) {
      throw new Error('Empty response from Groq');
    }

    try {
      // Try to extract JSON
      const jsonMatch = content.match(/```json\n?([\s\S]*?)\n?```/) || content.match(/\{[\s\S]*\}/);
      const jsonStr = jsonMatch ? (jsonMatch[1] || jsonMatch[0]) : content;
      const parsed = JSON.parse(jsonStr);
      return schema.parse(parsed);
    } catch (err) {
      if (retries > 0) {
        console.warn(`JSON parse failed, retrying... (${retries} left)`);
        return this.completion(model, systemPrompt, userPrompt, schema, retries - 1);
      }
      throw new Error(`Failed to parse AI response after ${MAX_RETRIES} retries`);
    }
  }

  async parseInput(text: string, model = 'llama-3.3-70b-versatile'): Promise<ParseInputResult> {
    return this.completion(model, PARSE_INPUT_PROMPT, text, ParseInputResultSchema);
  }

  async buildDayPlan(
    tasks: Array<{
      id: string;
      title: string;
      priority: string;
      estimatedMinutes?: number;
      deadlineAt?: string;
    }>,
    date: string,
    model = 'llama-3.3-70b-versatile'
  ): Promise<BuildDayPlanResult> {
    const userPrompt = `Дата: ${date}\nЗадачи:\n${JSON.stringify(tasks, null, 2)}`;
    return this.completion(model, BUILD_DAY_PLAN_PROMPT, userPrompt, BuildDayPlanResultSchema);
  }

  async generateDailyReview(
    completedTasks: Array<{ id: string; title: string }>,
    movedTasks: Array<{ id: string; title: string }>,
    overdueTasks: Array<{ id: string; title: string }>,
    stuckTasks: Array<{ id: string; title: string }>,
    model = 'llama-3.3-70b-versatile'
  ): Promise<DailyReviewResult> {
    const userPrompt = `Выполнено: ${JSON.stringify(completedTasks)}
Перенесено: ${JSON.stringify(movedTasks)}
Просрочено: ${JSON.stringify(overdueTasks)}
Зависшие: ${JSON.stringify(stuckTasks)}`;
    return this.completion(model, DAILY_REVIEW_PROMPT, userPrompt, DailyReviewResultSchema);
  }
}

export const createAiService = (apiKey: string) => new AiService(apiKey);
