'use client';
import {useEffect,useState} from 'react';

export default function ThemeToggle() {
  const [mounted,setMounted]=useState(false);
  const [dark,setDark]=useState(false);

  useEffect(()=>{
    const pref = (localStorage.getItem('theme') ?? 'system');
    const sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = pref === 'dark' || (pref === 'system' && sysDark);
    setDark(isDark);
    document.documentElement.classList.toggle('dark', isDark);
    setMounted(true);
  },[]);

  if(!mounted) return null;

  const toggle=()=>{
    const next=!dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
  };

  return (
    <button onClick={toggle}
      className="rounded-lg border px-3 py-1.5 text-sm transition
                 border-neutral-200 bg-white hover:bg-neutral-50
                 dark:border-neutral-700 dark:bg-neutral-800 dark:hover:bg-neutral-700"
      aria-label="Toggle theme">
      {dark ? '☀️ Light' : '🌙 Dark'}
    </button>
  );
}
