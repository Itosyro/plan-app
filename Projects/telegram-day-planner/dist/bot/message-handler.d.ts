import { Context } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { AiService } from '../ai/service.js';
interface BotConfig {
    miniAppUrl: string;
    groqSttModel: string;
    botToken: string;
}
export declare class MessageHandler {
    private db;
    private ai;
    private config;
    constructor(db: PrismaClient, ai: AiService, config: BotConfig);
    processInput(ctx: Context, sourceType: 'text' | 'voice' | 'audio', content: string): Promise<void>;
    private transcribe;
    private getOrCreateUser;
    private createEntities;
    private mapStatus;
    private parseRelativeDate;
    rebuildDayPlan(userId: string): Promise<void>;
}
export {};
