'use client';
import Link from 'next/link';
import ThemeToggle from './theme-toggle';

export default function Nav(){
  return (
    <nav className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur
                    dark:bg-neutral-900/80 dark:border-neutral-800">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl
                           bg-gradient-to-br from-indigo-500 to-violet-600 text-white
                           dark:from-indigo-400 dark:to-violet-500 text-base font-semibold">
            F
          </span>
          <span className="text-2xl font-extrabold tracking-tight
                           text-neutral-950 dark:text-white">
            Credicrew
          </span>
        </Link>
        <div className="flex items-center gap-2 text-sm">
          <Link href="/" className="rounded-md px-3 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800">Discover</Link>
          <Link href="/pipeline" className="rounded-md px-3 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800">Pipeline</Link>
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
