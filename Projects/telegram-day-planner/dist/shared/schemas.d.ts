import { z } from 'zod';
export declare const TaskStatusEnum: z.ZodEnum<["inbox", "today", "tomorrow", "upcoming", "someday", "done", "canceled"]>;
export declare const TaskPriorityEnum: z.ZodEnum<["low", "medium", "high"]>;
export declare const EnergyLevelEnum: z.ZodEnum<["low", "medium", "high"]>;
export declare const TaskSchema: z.ZodObject<{
    id: z.ZodString;
    title: z.ZodString;
    description: z.ZodNullable<z.ZodString>;
    status: z.ZodEnum<["inbox", "today", "tomorrow", "upcoming", "someday", "done", "canceled"]>;
    priority: z.ZodEnum<["low", "medium", "high"]>;
    energyLevel: z.ZodEnum<["low", "medium", "high"]>;
    projectId: z.ZodNullable<z.ZodString>;
    project: z.ZodNullable<z.ZodObject<{
        id: z.ZodString;
        title: z.ZodString;
        color: z.ZodNullable<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        id?: string;
        title?: string;
        color?: string;
    }, {
        id?: string;
        title?: string;
        color?: string;
    }>>;
    scheduledFor: z.ZodNullable<z.ZodString>;
    deadlineAt: z.ZodNullable<z.ZodString>;
    estimatedMinutes: z.ZodNullable<z.ZodNumber>;
    completedAt: z.ZodNullable<z.ZodString>;
    createdAt: z.ZodString;
}, "strip", z.ZodTypeAny, {
    id?: string;
    title?: string;
    description?: string;
    status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    projectId?: string;
    project?: {
        id?: string;
        title?: string;
        color?: string;
    };
    scheduledFor?: string;
    deadlineAt?: string;
    estimatedMinutes?: number;
    completedAt?: string;
    createdAt?: string;
}, {
    id?: string;
    title?: string;
    description?: string;
    status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    projectId?: string;
    project?: {
        id?: string;
        title?: string;
        color?: string;
    };
    scheduledFor?: string;
    deadlineAt?: string;
    estimatedMinutes?: number;
    completedAt?: string;
    createdAt?: string;
}>;
export declare const CreateTaskSchema: z.ZodObject<{
    title: z.ZodString;
    description: z.ZodOptional<z.ZodString>;
    status: z.ZodOptional<z.ZodEnum<["inbox", "today", "tomorrow", "upcoming", "someday", "done", "canceled"]>>;
    priority: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
    energyLevel: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
    projectId: z.ZodOptional<z.ZodString>;
    scheduledFor: z.ZodOptional<z.ZodString>;
    deadlineAt: z.ZodOptional<z.ZodString>;
    estimatedMinutes: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    title?: string;
    description?: string;
    status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    projectId?: string;
    scheduledFor?: string;
    deadlineAt?: string;
    estimatedMinutes?: number;
}, {
    title?: string;
    description?: string;
    status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    projectId?: string;
    scheduledFor?: string;
    deadlineAt?: string;
    estimatedMinutes?: number;
}>;
export declare const UpdateTaskSchema: z.ZodObject<{
    title: z.ZodOptional<z.ZodString>;
    description: z.ZodOptional<z.ZodOptional<z.ZodString>>;
    status: z.ZodOptional<z.ZodOptional<z.ZodEnum<["inbox", "today", "tomorrow", "upcoming", "someday", "done", "canceled"]>>>;
    priority: z.ZodOptional<z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>>;
    energyLevel: z.ZodOptional<z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>>;
    projectId: z.ZodOptional<z.ZodOptional<z.ZodString>>;
    scheduledFor: z.ZodOptional<z.ZodOptional<z.ZodString>>;
    deadlineAt: z.ZodOptional<z.ZodOptional<z.ZodString>>;
    estimatedMinutes: z.ZodOptional<z.ZodOptional<z.ZodNumber>>;
}, "strip", z.ZodTypeAny, {
    title?: string;
    description?: string;
    status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    projectId?: string;
    scheduledFor?: string;
    deadlineAt?: string;
    estimatedMinutes?: number;
}, {
    title?: string;
    description?: string;
    status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    projectId?: string;
    scheduledFor?: string;
    deadlineAt?: string;
    estimatedMinutes?: number;
}>;
export declare const NoteSchema: z.ZodObject<{
    id: z.ZodString;
    title: z.ZodNullable<z.ZodString>;
    content: z.ZodString;
    taskId: z.ZodNullable<z.ZodString>;
    createdAt: z.ZodString;
}, "strip", z.ZodTypeAny, {
    id?: string;
    title?: string;
    createdAt?: string;
    content?: string;
    taskId?: string;
}, {
    id?: string;
    title?: string;
    createdAt?: string;
    content?: string;
    taskId?: string;
}>;
export declare const CreateNoteSchema: z.ZodObject<{
    title: z.ZodOptional<z.ZodString>;
    content: z.ZodString;
    taskId: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    title?: string;
    content?: string;
    taskId?: string;
}, {
    title?: string;
    content?: string;
    taskId?: string;
}>;
export declare const ProjectSchema: z.ZodObject<{
    id: z.ZodString;
    title: z.ZodString;
    color: z.ZodNullable<z.ZodString>;
    isArchived: z.ZodBoolean;
}, "strip", z.ZodTypeAny, {
    id?: string;
    title?: string;
    color?: string;
    isArchived?: boolean;
}, {
    id?: string;
    title?: string;
    color?: string;
    isArchived?: boolean;
}>;
export declare const CreateProjectSchema: z.ZodObject<{
    title: z.ZodString;
    color: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    title?: string;
    color?: string;
}, {
    title?: string;
    color?: string;
}>;
export declare const SettingsSchema: z.ZodObject<{
    remindersEnabled: z.ZodBoolean;
    postProcessingSummaryEnabled: z.ZodBoolean;
    dailyDigestEnabled: z.ZodBoolean;
    dailyDigestTime: z.ZodNullable<z.ZodString>;
    stuckTasksPingEnabled: z.ZodBoolean;
    stuckTasksPingIntervalHours: z.ZodNullable<z.ZodNumber>;
    deleteTaskOnDone: z.ZodBoolean;
    deleteNotesWithTask: z.ZodBoolean;
    circlesViewEnabled: z.ZodBoolean;
}, "strip", z.ZodTypeAny, {
    remindersEnabled?: boolean;
    postProcessingSummaryEnabled?: boolean;
    dailyDigestEnabled?: boolean;
    dailyDigestTime?: string;
    stuckTasksPingEnabled?: boolean;
    stuckTasksPingIntervalHours?: number;
    deleteTaskOnDone?: boolean;
    deleteNotesWithTask?: boolean;
    circlesViewEnabled?: boolean;
}, {
    remindersEnabled?: boolean;
    postProcessingSummaryEnabled?: boolean;
    dailyDigestEnabled?: boolean;
    dailyDigestTime?: string;
    stuckTasksPingEnabled?: boolean;
    stuckTasksPingIntervalHours?: number;
    deleteTaskOnDone?: boolean;
    deleteNotesWithTask?: boolean;
    circlesViewEnabled?: boolean;
}>;
export declare const UpdateSettingsSchema: z.ZodObject<{
    remindersEnabled: z.ZodOptional<z.ZodBoolean>;
    postProcessingSummaryEnabled: z.ZodOptional<z.ZodBoolean>;
    dailyDigestEnabled: z.ZodOptional<z.ZodBoolean>;
    dailyDigestTime: z.ZodOptional<z.ZodNullable<z.ZodString>>;
    stuckTasksPingEnabled: z.ZodOptional<z.ZodBoolean>;
    stuckTasksPingIntervalHours: z.ZodOptional<z.ZodNullable<z.ZodNumber>>;
    deleteTaskOnDone: z.ZodOptional<z.ZodBoolean>;
    deleteNotesWithTask: z.ZodOptional<z.ZodBoolean>;
    circlesViewEnabled: z.ZodOptional<z.ZodBoolean>;
}, "strip", z.ZodTypeAny, {
    remindersEnabled?: boolean;
    postProcessingSummaryEnabled?: boolean;
    dailyDigestEnabled?: boolean;
    dailyDigestTime?: string;
    stuckTasksPingEnabled?: boolean;
    stuckTasksPingIntervalHours?: number;
    deleteTaskOnDone?: boolean;
    deleteNotesWithTask?: boolean;
    circlesViewEnabled?: boolean;
}, {
    remindersEnabled?: boolean;
    postProcessingSummaryEnabled?: boolean;
    dailyDigestEnabled?: boolean;
    dailyDigestTime?: string;
    stuckTasksPingEnabled?: boolean;
    stuckTasksPingIntervalHours?: number;
    deleteTaskOnDone?: boolean;
    deleteNotesWithTask?: boolean;
    circlesViewEnabled?: boolean;
}>;
export declare const ExtractedTaskSchema: z.ZodObject<{
    title: z.ZodString;
    description: z.ZodNullable<z.ZodString>;
    statusSuggestion: z.ZodOptional<z.ZodEnum<["inbox", "today", "tomorrow", "upcoming", "someday"]>>;
    priority: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
    energyLevel: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
    estimatedMinutes: z.ZodNullable<z.ZodNumber>;
    dueLabel: z.ZodNullable<z.ZodString>;
    deadlineAt: z.ZodNullable<z.ZodString>;
    projectName: z.ZodNullable<z.ZodString>;
    isMaybeTask: z.ZodOptional<z.ZodBoolean>;
    suggestedSubtasks: z.ZodOptional<z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        priority: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        priority?: "low" | "medium" | "high";
    }, {
        title?: string;
        priority?: "low" | "medium" | "high";
    }>, "many">>;
}, "strip", z.ZodTypeAny, {
    title?: string;
    description?: string;
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    deadlineAt?: string;
    estimatedMinutes?: number;
    statusSuggestion?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday";
    dueLabel?: string;
    projectName?: string;
    isMaybeTask?: boolean;
    suggestedSubtasks?: {
        title?: string;
        priority?: "low" | "medium" | "high";
    }[];
}, {
    title?: string;
    description?: string;
    priority?: "low" | "medium" | "high";
    energyLevel?: "low" | "medium" | "high";
    deadlineAt?: string;
    estimatedMinutes?: number;
    statusSuggestion?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday";
    dueLabel?: string;
    projectName?: string;
    isMaybeTask?: boolean;
    suggestedSubtasks?: {
        title?: string;
        priority?: "low" | "medium" | "high";
    }[];
}>;
export declare const ExtractedNoteSchema: z.ZodObject<{
    title: z.ZodNullable<z.ZodString>;
    content: z.ZodString;
}, "strip", z.ZodTypeAny, {
    title?: string;
    content?: string;
}, {
    title?: string;
    content?: string;
}>;
export declare const ExtractedProjectSchema: z.ZodObject<{
    title: z.ZodString;
    color: z.ZodNullable<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    title?: string;
    color?: string;
}, {
    title?: string;
    color?: string;
}>;
export declare const ClarifyingQuestionSchema: z.ZodObject<{
    question: z.ZodString;
    context: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    question?: string;
    context?: string;
}, {
    question?: string;
    context?: string;
}>;
export declare const ParseInputResultSchema: z.ZodObject<{
    summary: z.ZodString;
    confidence: z.ZodNumber;
    assumptions: z.ZodArray<z.ZodString, "many">;
    clarifyingQuestions: z.ZodArray<z.ZodObject<{
        question: z.ZodString;
        context: z.ZodOptional<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        question?: string;
        context?: string;
    }, {
        question?: string;
        context?: string;
    }>, "many">;
    extractedProjects: z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        color: z.ZodNullable<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        color?: string;
    }, {
        title?: string;
        color?: string;
    }>, "many">;
    extractedNotes: z.ZodArray<z.ZodObject<{
        title: z.ZodNullable<z.ZodString>;
        content: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        content?: string;
    }, {
        title?: string;
        content?: string;
    }>, "many">;
    extractedTasks: z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        description: z.ZodNullable<z.ZodString>;
        statusSuggestion: z.ZodOptional<z.ZodEnum<["inbox", "today", "tomorrow", "upcoming", "someday"]>>;
        priority: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
        energyLevel: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
        estimatedMinutes: z.ZodNullable<z.ZodNumber>;
        dueLabel: z.ZodNullable<z.ZodString>;
        deadlineAt: z.ZodNullable<z.ZodString>;
        projectName: z.ZodNullable<z.ZodString>;
        isMaybeTask: z.ZodOptional<z.ZodBoolean>;
        suggestedSubtasks: z.ZodOptional<z.ZodArray<z.ZodObject<{
            title: z.ZodString;
            priority: z.ZodOptional<z.ZodEnum<["low", "medium", "high"]>>;
        }, "strip", z.ZodTypeAny, {
            title?: string;
            priority?: "low" | "medium" | "high";
        }, {
            title?: string;
            priority?: "low" | "medium" | "high";
        }>, "many">>;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        description?: string;
        priority?: "low" | "medium" | "high";
        energyLevel?: "low" | "medium" | "high";
        deadlineAt?: string;
        estimatedMinutes?: number;
        statusSuggestion?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday";
        dueLabel?: string;
        projectName?: string;
        isMaybeTask?: boolean;
        suggestedSubtasks?: {
            title?: string;
            priority?: "low" | "medium" | "high";
        }[];
    }, {
        title?: string;
        description?: string;
        priority?: "low" | "medium" | "high";
        energyLevel?: "low" | "medium" | "high";
        deadlineAt?: string;
        estimatedMinutes?: number;
        statusSuggestion?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday";
        dueLabel?: string;
        projectName?: string;
        isMaybeTask?: boolean;
        suggestedSubtasks?: {
            title?: string;
            priority?: "low" | "medium" | "high";
        }[];
    }>, "many">;
}, "strip", z.ZodTypeAny, {
    summary?: string;
    confidence?: number;
    assumptions?: string[];
    clarifyingQuestions?: {
        question?: string;
        context?: string;
    }[];
    extractedProjects?: {
        title?: string;
        color?: string;
    }[];
    extractedNotes?: {
        title?: string;
        content?: string;
    }[];
    extractedTasks?: {
        title?: string;
        description?: string;
        priority?: "low" | "medium" | "high";
        energyLevel?: "low" | "medium" | "high";
        deadlineAt?: string;
        estimatedMinutes?: number;
        statusSuggestion?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday";
        dueLabel?: string;
        projectName?: string;
        isMaybeTask?: boolean;
        suggestedSubtasks?: {
            title?: string;
            priority?: "low" | "medium" | "high";
        }[];
    }[];
}, {
    summary?: string;
    confidence?: number;
    assumptions?: string[];
    clarifyingQuestions?: {
        question?: string;
        context?: string;
    }[];
    extractedProjects?: {
        title?: string;
        color?: string;
    }[];
    extractedNotes?: {
        title?: string;
        content?: string;
    }[];
    extractedTasks?: {
        title?: string;
        description?: string;
        priority?: "low" | "medium" | "high";
        energyLevel?: "low" | "medium" | "high";
        deadlineAt?: string;
        estimatedMinutes?: number;
        statusSuggestion?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday";
        dueLabel?: string;
        projectName?: string;
        isMaybeTask?: boolean;
        suggestedSubtasks?: {
            title?: string;
            priority?: "low" | "medium" | "high";
        }[];
    }[];
}>;
export declare const BuildDayPlanResultSchema: z.ZodObject<{
    concise_summary: z.ZodString;
    overload_warning: z.ZodNullable<z.ZodString>;
    must_do: z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        reason: z.ZodOptional<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        reason?: string;
    }, {
        title?: string;
        reason?: string;
    }>, "many">;
    nice_to_do: z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        reason: z.ZodOptional<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        reason?: string;
    }, {
        title?: string;
        reason?: string;
    }>, "many">;
    ordered_plan: z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        priority: z.ZodOptional<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        priority?: string;
    }, {
        title?: string;
        priority?: string;
    }>, "many">;
}, "strip", z.ZodTypeAny, {
    concise_summary?: string;
    overload_warning?: string;
    must_do?: {
        title?: string;
        reason?: string;
    }[];
    nice_to_do?: {
        title?: string;
        reason?: string;
    }[];
    ordered_plan?: {
        title?: string;
        priority?: string;
    }[];
}, {
    concise_summary?: string;
    overload_warning?: string;
    must_do?: {
        title?: string;
        reason?: string;
    }[];
    nice_to_do?: {
        title?: string;
        reason?: string;
    }[];
    ordered_plan?: {
        title?: string;
        priority?: string;
    }[];
}>;
export declare const DailyReviewResultSchema: z.ZodObject<{
    short_reflection: z.ZodString;
    completed_count: z.ZodNumber;
    moved_count: z.ZodNumber;
    stuck_items: z.ZodArray<z.ZodObject<{
        title: z.ZodString;
        days_stuck: z.ZodNumber;
    }, "strip", z.ZodTypeAny, {
        title?: string;
        days_stuck?: number;
    }, {
        title?: string;
        days_stuck?: number;
    }>, "many">;
    suggestion_for_tomorrow: z.ZodString;
}, "strip", z.ZodTypeAny, {
    short_reflection?: string;
    completed_count?: number;
    moved_count?: number;
    stuck_items?: {
        title?: string;
        days_stuck?: number;
    }[];
    suggestion_for_tomorrow?: string;
}, {
    short_reflection?: string;
    completed_count?: number;
    moved_count?: number;
    stuck_items?: {
        title?: string;
        days_stuck?: number;
    }[];
    suggestion_for_tomorrow?: string;
}>;
export declare const DailyPlanSchema: z.ZodObject<{
    id: z.ZodString;
    date: z.ZodString;
    summary: z.ZodNullable<z.ZodString>;
    overloadWarning: z.ZodBoolean;
    items: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        task: z.ZodObject<{
            id: z.ZodString;
            title: z.ZodString;
            description: z.ZodNullable<z.ZodString>;
            status: z.ZodEnum<["inbox", "today", "tomorrow", "upcoming", "someday", "done", "canceled"]>;
            priority: z.ZodEnum<["low", "medium", "high"]>;
            energyLevel: z.ZodEnum<["low", "medium", "high"]>;
            projectId: z.ZodNullable<z.ZodString>;
            project: z.ZodNullable<z.ZodObject<{
                id: z.ZodString;
                title: z.ZodString;
                color: z.ZodNullable<z.ZodString>;
            }, "strip", z.ZodTypeAny, {
                id?: string;
                title?: string;
                color?: string;
            }, {
                id?: string;
                title?: string;
                color?: string;
            }>>;
            scheduledFor: z.ZodNullable<z.ZodString>;
            deadlineAt: z.ZodNullable<z.ZodString>;
            estimatedMinutes: z.ZodNullable<z.ZodNumber>;
            completedAt: z.ZodNullable<z.ZodString>;
            createdAt: z.ZodString;
        }, "strip", z.ZodTypeAny, {
            id?: string;
            title?: string;
            description?: string;
            status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
            priority?: "low" | "medium" | "high";
            energyLevel?: "low" | "medium" | "high";
            projectId?: string;
            project?: {
                id?: string;
                title?: string;
                color?: string;
            };
            scheduledFor?: string;
            deadlineAt?: string;
            estimatedMinutes?: number;
            completedAt?: string;
            createdAt?: string;
        }, {
            id?: string;
            title?: string;
            description?: string;
            status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
            priority?: "low" | "medium" | "high";
            energyLevel?: "low" | "medium" | "high";
            projectId?: string;
            project?: {
                id?: string;
                title?: string;
                color?: string;
            };
            scheduledFor?: string;
            deadlineAt?: string;
            estimatedMinutes?: number;
            completedAt?: string;
            createdAt?: string;
        }>;
        slotLabel: z.ZodNullable<z.ZodString>;
        sortOrder: z.ZodNumber;
    }, "strip", z.ZodTypeAny, {
        id?: string;
        task?: {
            id?: string;
            title?: string;
            description?: string;
            status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
            priority?: "low" | "medium" | "high";
            energyLevel?: "low" | "medium" | "high";
            projectId?: string;
            project?: {
                id?: string;
                title?: string;
                color?: string;
            };
            scheduledFor?: string;
            deadlineAt?: string;
            estimatedMinutes?: number;
            completedAt?: string;
            createdAt?: string;
        };
        slotLabel?: string;
        sortOrder?: number;
    }, {
        id?: string;
        task?: {
            id?: string;
            title?: string;
            description?: string;
            status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
            priority?: "low" | "medium" | "high";
            energyLevel?: "low" | "medium" | "high";
            projectId?: string;
            project?: {
                id?: string;
                title?: string;
                color?: string;
            };
            scheduledFor?: string;
            deadlineAt?: string;
            estimatedMinutes?: number;
            completedAt?: string;
            createdAt?: string;
        };
        slotLabel?: string;
        sortOrder?: number;
    }>, "many">;
}, "strip", z.ZodTypeAny, {
    id?: string;
    date?: string;
    summary?: string;
    overloadWarning?: boolean;
    items?: {
        id?: string;
        task?: {
            id?: string;
            title?: string;
            description?: string;
            status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
            priority?: "low" | "medium" | "high";
            energyLevel?: "low" | "medium" | "high";
            projectId?: string;
            project?: {
                id?: string;
                title?: string;
                color?: string;
            };
            scheduledFor?: string;
            deadlineAt?: string;
            estimatedMinutes?: number;
            completedAt?: string;
            createdAt?: string;
        };
        slotLabel?: string;
        sortOrder?: number;
    }[];
}, {
    id?: string;
    date?: string;
    summary?: string;
    overloadWarning?: boolean;
    items?: {
        id?: string;
        task?: {
            id?: string;
            title?: string;
            description?: string;
            status?: "inbox" | "today" | "tomorrow" | "upcoming" | "someday" | "done" | "canceled";
            priority?: "low" | "medium" | "high";
            energyLevel?: "low" | "medium" | "high";
            projectId?: string;
            project?: {
                id?: string;
                title?: string;
                color?: string;
            };
            scheduledFor?: string;
            deadlineAt?: string;
            estimatedMinutes?: number;
            completedAt?: string;
            createdAt?: string;
        };
        slotLabel?: string;
        sortOrder?: number;
    }[];
}>;
export type Task = z.infer<typeof TaskSchema>;
export type Note = z.infer<typeof NoteSchema>;
export type Project = z.infer<typeof ProjectSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
export type ParseInputResult = z.infer<typeof ParseInputResultSchema>;
export type BuildDayPlanResult = z.infer<typeof BuildDayPlanResultSchema>;
export type DailyReviewResult = z.infer<typeof DailyReviewResultSchema>;
export type DailyPlan = z.infer<typeof DailyPlanSchema>;
