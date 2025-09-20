import Link from 'next/link';
import ThemeToggle from '@/components/ThemeToggle';

export default function Navbar() {
  return (
    <header className="sticky top-0 z-30 border-b border-neutral-800/60 bg-neutral-950/80 backdrop-blur supports-[backdrop-filter]:bg-neutral-950/60">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold text-white">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500 text-sm">F</span>
          <span className="text-lg">Credicrew</span>
        </Link>

        <nav className="flex items-center gap-2">
          <Link href="/" className="rounded-lg px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800/60">Discover</Link>
          <Link href="/pipeline" className="rounded-lg px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800/60">Pipeline</Link>
          <Link href="/submit" className="rounded-lg px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800/60">Submit</Link>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
