'use client';

import { create } from 'zustand';
import type { Task, Settings } from '@/types';
import { api } from './api';

interface AppState {
  tasks: Task[];
  settings: Settings | null;
  loading: boolean;
  error: string | null;
  view: 'list' | 'circles';

  fetchTasks: () => Promise<void>;
  fetchSettings: () => Promise<void>;
  completeTask: (id: string) => Promise<void>;
  reopenTask: (id: string) => Promise<void>;
  rescheduleTask: (id: string, status: string) => Promise<void>;
  deleteTask: (id: string) => Promise<void>;
  updateSettings: (data: Partial<Settings>) => Promise<void>;
  setView: (view: 'list' | 'circles') => void;
}

export const useStore = create<AppState>((set, get) => ({
  tasks: [],
  settings: null,
  loading: false,
  error: null,
  view: 'list',

  fetchTasks: async () => {
    set({ loading: true, error: null });
    try {
      const tasks = await api.getTasks();
      set({ tasks, loading: false });
    } catch (err: any) {
      set({ error: err.message, loading: false });
    }
  },

  fetchSettings: async () => {
    try {
      const settings = await api.getSettings();
      set({ settings });
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  completeTask: async (id: string) => {
    try {
      await api.completeTask(id);
      set((state) => ({
        tasks: state.tasks.map((t) =>
          t.id === id ? { ...t, status: 'done' as const, completedAt: new Date().toISOString() } : t
        ),
      }));
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  reopenTask: async (id: string) => {
    try {
      await api.reopenTask(id);
      set((state) => ({
        tasks: state.tasks.map((t) =>
          t.id === id ? { ...t, status: 'inbox' as const, completedAt: null } : t
        ),
      }));
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  rescheduleTask: async (id: string, status: string) => {
    try {
      await api.rescheduleTask(id, status);
      set((state) => ({
        tasks: state.tasks.map((t) =>
          t.id === id ? { ...t, status: status as Task['status'] } : t
        ),
      }));
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  deleteTask: async (id: string) => {
    try {
      await api.deleteTask(id);
      set((state) => ({
        tasks: state.tasks.filter((t) => t.id !== id),
      }));
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  updateSettings: async (data: Partial<Settings>) => {
    try {
      const settings = await api.updateSettings(data);
      set({ settings });
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  setView: (view) => set({ view }),
}));
