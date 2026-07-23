import Link from 'next/link';

export default function Navbar() {
  return (
    <header className="sticky top-0 z-30 border-b border-white/5 bg-neutral-950/80 backdrop-blur supports-[backdrop-filter]:bg-neutral-950/60">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold text-white">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 text-xs font-bold">
            C
          </span>
          <span className="text-lg">Credicrew</span>
        </Link>

        <nav className="flex items-center gap-1">
          <Link href="/" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Discover</Link>
          <Link href="/roles" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Roles</Link>
          <Link href="/hq" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Command Center</Link>
          <Link href="/compass" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Compass</Link>
          <Link
            href="/anchor"
            className="relative rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white"
          >
            Anchor
            <span className="ml-1 inline-block rounded-full bg-gradient-to-br from-fuchsia-400 via-rose-400 to-amber-400 px-1.5 py-[1px] text-[9px] font-bold uppercase tracking-widest text-neutral-950">
              NEW
            </span>
          </Link>
          <Link href="/sources" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Channels</Link>
          <Link href="/cadence" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Cadence</Link>
          <Link href="/crosswind" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Crosswind</Link>
          <Link href="/revive" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Revive</Link>
          <Link href="/hindsight" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Hindsight</Link>
          <Link href="/verdict" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Verdict</Link>
          <Link href="/brief" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Brief</Link>
          <Link href="/reference" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Reference</Link>
          <Link href="/pipeline" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Pipeline</Link>
          <Link href="/submit" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Submit</Link>
        </nav>
      </div>
    </header>
  );
}
