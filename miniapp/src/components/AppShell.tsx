'use client';

import { useEffect, useState } from 'react';
import { setInitData } from '@/lib/api';
import { BottomNav } from './BottomNav';

export function AppShell({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const tg = (window as any).Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      tg.setHeaderColor('#faf8f5');
      tg.setBackgroundColor('#faf8f5');

      const initData = tg.initData;
      if (initData) {
        setInitData(initData);
      }
    }
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 rounded-full border-2 border-[var(--accent)] border-t-transparent animate-spin" />
      </div>
    );
  }

  return (
    <>
      <main className="min-h-screen px-4 pt-2 pb-4">{children}</main>
      <BottomNav />
      <script src="https://telegram.org/js/telegram-web-app.js" />
    </>
  );
}
