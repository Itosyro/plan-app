import { Context } from 'grammy';
import { PrismaClient } from '@prisma/client';
import { AiService } from '../ai/service.js';
interface BotConfig {
    miniAppUrl: string;
    groqSttModel: string;
    botToken: string;
}
export declare class BotHandlers {
    private db;
    private ai;
    private config;
    private messageHandler;
    constructor(db: PrismaClient, ai: AiService, config: BotConfig);
    start(ctx: Context): Promise<void>;
    help(ctx: Context): Promise<void>;
    settings(ctx: Context): Promise<void>;
    today(ctx: Context): Promise<void>;
    plan(ctx: Context): Promise<void>;
    add(ctx: Context): Promise<void>;
    handleText(ctx: Context): Promise<void>;
    handleVoice(ctx: Context): Promise<void>;
    handleAudio(ctx: Context): Promise<void>;
}
export {};
