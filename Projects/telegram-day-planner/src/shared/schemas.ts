import { z } from 'zod';

// Task schemas
export const TaskStatusEnum = z.enum(['inbox', 'today', 'tomorrow', 'upcoming', 'someday', 'done', 'canceled']);
export const TaskPriorityEnum = z.enum(['low', 'medium', 'high']);
export const EnergyLevelEnum = z.enum(['low', 'medium', 'high']);

export const TaskSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  status: TaskStatusEnum,
  priority: TaskPriorityEnum,
  energyLevel: EnergyLevelEnum,
  projectId: z.string().nullable(),
  project: z.object({ id: z.string(), title: z.string(), color: z.string().nullable() }).nullable(),
  scheduledFor: z.string().nullable(),
  deadlineAt: z.string().nullable(),
  estimatedMinutes: z.number().nullable(),
  completedAt: z.string().nullable(),
  createdAt: z.string(),
});

export const CreateTaskSchema = z.object({
  title: z.string().min(1),
  description: z.string().optional(),
  status: TaskStatusEnum.optional(),
  priority: TaskPriorityEnum.optional(),
  energyLevel: EnergyLevelEnum.optional(),
  projectId: z.string().optional(),
  scheduledFor: z.string().optional(),
  deadlineAt: z.string().optional(),
  estimatedMinutes: z.number().optional(),
});

export const UpdateTaskSchema = CreateTaskSchema.partial();

// Note schemas
export const NoteSchema = z.object({
  id: z.string(),
  title: z.string().nullable(),
  content: z.string(),
  taskId: z.string().nullable(),
  createdAt: z.string(),
});

export const CreateNoteSchema = z.object({
  title: z.string().optional(),
  content: z.string().min(1),
  taskId: z.string().optional(),
});

// Project schemas
export const ProjectSchema = z.object({
  id: z.string(),
  title: z.string(),
  color: z.string().nullable(),
  isArchived: z.boolean(),
});

export const CreateProjectSchema = z.object({
  title: z.string().min(1),
  color: z.string().optional(),
});

// Settings schemas
export const SettingsSchema = z.object({
  remindersEnabled: z.boolean(),
  postProcessingSummaryEnabled: z.boolean(),
  dailyDigestEnabled: z.boolean(),
  dailyDigestTime: z.string().nullable(),
  stuckTasksPingEnabled: z.boolean(),
  stuckTasksPingIntervalHours: z.number().nullable(),
  deleteTaskOnDone: z.boolean(),
  deleteNotesWithTask: z.boolean(),
  circlesViewEnabled: z.boolean(),
});

export const UpdateSettingsSchema = SettingsSchema.partial();

// AI Parsing schemas
export const ExtractedTaskSchema = z.object({
  title: z.string(),
  description: z.string().nullable(),
  statusSuggestion: z.enum(['inbox', 'today', 'tomorrow', 'upcoming', 'someday']).optional(),
  priority: TaskPriorityEnum.optional(),
  energyLevel: EnergyLevelEnum.optional(),
  estimatedMinutes: z.number().nullable(),
  dueLabel: z.string().nullable(),
  deadlineAt: z.string().nullable(),
  projectName: z.string().nullable(),
  isMaybeTask: z.boolean().optional(),
  suggestedSubtasks: z.array(z.object({
    title: z.string(),
    priority: TaskPriorityEnum.optional(),
  })).optional(),
});

export const ExtractedNoteSchema = z.object({
  title: z.string().nullable(),
  content: z.string(),
});

export const ExtractedProjectSchema = z.object({
  title: z.string(),
  color: z.string().nullable(),
});

export const ClarifyingQuestionSchema = z.object({
  question: z.string(),
  context: z.string().optional(),
});

export const ParseInputResultSchema = z.object({
  summary: z.string(),
  confidence: z.number().min(0).max(1),
  assumptions: z.array(z.string()),
  clarifyingQuestions: z.array(ClarifyingQuestionSchema),
  extractedProjects: z.array(ExtractedProjectSchema),
  extractedNotes: z.array(ExtractedNoteSchema),
  extractedTasks: z.array(ExtractedTaskSchema),
});

export const BuildDayPlanResultSchema = z.object({
  concise_summary: z.string(),
  overload_warning: z.string().nullable(),
  must_do: z.array(z.object({ title: z.string(), reason: z.string().optional() })),
  nice_to_do: z.array(z.object({ title: z.string(), reason: z.string().optional() })),
  ordered_plan: z.array(z.object({ title: z.string(), priority: z.string().optional() })),
});

export const DailyReviewResultSchema = z.object({
  short_reflection: z.string(),
  completed_count: z.number(),
  moved_count: z.number(),
  stuck_items: z.array(z.object({ title: z.string(), days_stuck: z.number() })),
  suggestion_for_tomorrow: z.string(),
});

// Daily Plan schemas
export const DailyPlanSchema = z.object({
  id: z.string(),
  date: z.string(),
  summary: z.string().nullable(),
  overloadWarning: z.boolean(),
  items: z.array(z.object({
    id: z.string(),
    task: TaskSchema,
    slotLabel: z.string().nullable(),
    sortOrder: z.number(),
  })),
});

// Types
export type Task = z.infer<typeof TaskSchema>;
export type Note = z.infer<typeof NoteSchema>;
export type Project = z.infer<typeof ProjectSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
export type ParseInputResult = z.infer<typeof ParseInputResultSchema>;
export type BuildDayPlanResult = z.infer<typeof BuildDayPlanResultSchema>;
export type DailyReviewResult = z.infer<typeof DailyReviewResultSchema>;
export type DailyPlan = z.infer<typeof DailyPlanSchema>;
