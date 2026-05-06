import { ParseInputResult, BuildDayPlanResult, DailyReviewResult } from '../shared/schemas.js';
export declare class AiService {
    private apiKey;
    constructor(apiKey: string);
    private completion;
    parseInput(text: string, model?: string): Promise<ParseInputResult>;
    buildDayPlan(tasks: Array<{
        id: string;
        title: string;
        priority: string;
        estimatedMinutes?: number;
        deadlineAt?: string;
    }>, date: string, model?: string): Promise<BuildDayPlanResult>;
    generateDailyReview(completedTasks: Array<{
        id: string;
        title: string;
    }>, movedTasks: Array<{
        id: string;
        title: string;
    }>, overdueTasks: Array<{
        id: string;
        title: string;
    }>, stuckTasks: Array<{
        id: string;
        title: string;
    }>, model?: string): Promise<DailyReviewResult>;
}
export declare const createAiService: (apiKey: string) => AiService;
