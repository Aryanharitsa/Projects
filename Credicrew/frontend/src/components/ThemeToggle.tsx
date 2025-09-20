'use client';
import { useEffect, useState } from 'react';

export default function ThemeToggle() {
  const [mode, setMode] = useState<'light'|'dark'>('dark');

  useEffect(() => {
    const isDark = document.documentElement.classList.contains('dark');
    setMode(isDark ? 'dark' : 'light');
  }, []);

  const toggle = () => {
    const root = document.documentElement;
    const next = mode === 'dark' ? 'light' : 'dark';
    root.classList.toggle('dark', next === 'dark');
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch {}
    setMode(next);
  };

  return (
    <button
      onClick={toggle}
      className="inline-flex items-center gap-2 rounded-lg border border-neutral-700/50 px-3 py-1.5 text-sm
                 bg-neutral-900 hover:bg-neutral-800 text-neutral-200
                 dark:bg-neutral-900 dark:hover:bg-neutral-800"
      aria-label="Toggle theme"
    >
      {mode === 'dark' ? '🌞 Light' : '🌙 Dark'}
    </button>
  );
}
