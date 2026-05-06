import type { Task, Note, Project, Settings, DailyPlan } from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

let initData = '';

export function setInitData(data: string) {
  initData = data;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'x-init-data': initData,
      ...options.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `HTTP ${res.status}`);
  }

  return res.json();
}

// Tasks
export const api = {
  getTasks: (status?: string) =>
    request<Task[]>(`/api/tasks${status ? `?status=${status}` : ''}`),

  getTask: (id: string) =>
    request<Task>(`/api/tasks/${id}`),

  createTask: (data: Partial<Task>) =>
    request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify(data) }),

  updateTask: (id: string, data: Partial<Task>) =>
    request<Task>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  completeTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/complete`, { method: 'POST' }),

  reopenTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/reopen`, { method: 'POST' }),

  rescheduleTask: (id: string, status: string, scheduledFor?: string) =>
    request<Task>(`/api/tasks/${id}/reschedule`, {
      method: 'POST',
      body: JSON.stringify({ status, scheduledFor }),
    }),

  deleteTask: (id: string) =>
    request<{ success: boolean }>(`/api/tasks/${id}`, { method: 'DELETE' }),

  // Notes
  getNotes: () => request<Note[]>('/api/notes'),
  createNote: (data: { title?: string; content: string; taskId?: string }) =>
    request<Note>('/api/notes', { method: 'POST', body: JSON.stringify(data) }),

  // Projects
  getProjects: () => request<Project[]>('/api/projects'),
  createProject: (data: { title: string; color?: string }) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),

  // Settings
  getSettings: () => request<Settings>('/api/settings'),
  updateSettings: (data: Partial<Settings>) =>
    request<Settings>('/api/settings', { method: 'PATCH', body: JSON.stringify(data) }),

  // Daily Plan
  getDailyPlan: () => request<DailyPlan>('/api/daily-plan/today'),
  rebuildPlan: () => request<DailyPlan>('/api/daily-plan/rebuild', { method: 'POST' }),

  // Me
  getMe: () => request<{ id: string; firstName: string; timezone: string }>('/api/me'),
};
