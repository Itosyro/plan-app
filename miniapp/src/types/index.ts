export interface Task {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  energyLevel: EnergyLevel;
  projectId: string | null;
  project: Project | null;
  scheduledFor: string | null;
  deadlineAt: string | null;
  estimatedMinutes: number | null;
  completedAt: string | null;
  createdAt: string;
  notes?: Note[];
}

export type TaskStatus = 'inbox' | 'today' | 'tomorrow' | 'upcoming' | 'someday' | 'done' | 'canceled';
export type TaskPriority = 'low' | 'medium' | 'high';
export type EnergyLevel = 'low' | 'medium' | 'high';

export interface Note {
  id: string;
  title: string | null;
  content: string;
  taskId: string | null;
  createdAt: string;
}

export interface Project {
  id: string;
  title: string;
  color: string | null;
  isArchived: boolean;
}

export interface Settings {
  remindersEnabled: boolean;
  postProcessingSummaryEnabled: boolean;
  dailyDigestEnabled: boolean;
  dailyDigestTime: string | null;
  stuckTasksPingEnabled: boolean;
  stuckTasksPingIntervalHours: number | null;
  deleteTaskOnDone: boolean;
  deleteNotesWithTask: boolean;
  circlesViewEnabled: boolean;
}

export interface DailyPlan {
  id: string;
  date: string;
  summary: string | null;
  overloadWarning: boolean;
  items: DailyPlanItem[];
}

export interface DailyPlanItem {
  id: string;
  task: Task;
  slotLabel: string | null;
  sortOrder: number;
}
