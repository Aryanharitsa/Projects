import Link from "next/link";
import {
  ArrowRight,
  Brain,
  Command,
  Github,
  Keyboard,
  Lock,
  Network,
  Sparkles,
  Zap,
} from "lucide-react";
import HeroGraph from "@/components/HeroGraph";

export default function Landing() {
  return (
    <main className="min-h-screen bg-void-900 text-ink-100 overflow-x-hidden">
      {/* Ambient background */}
      <div className="bg-ambient" />

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-6 md:px-10 py-5">
        <div className="flex items-center gap-2">
          <Mark />
          <span className="font-semibold tracking-tight">SynapseOS</span>
          <span className="text-[10px] uppercase tracking-[0.18em] text-ink-400 ml-1 hidden md:inline">
            · Your thoughts, connected
          </span>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="https://github.com/Aryanharitsa/Projects/tree/main/SynapseOS"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-sm text-ink-300 hover:text-ink-100"
          >
            <Github className="w-4 h-4" /> GitHub
          </a>
          <Link
            href="/workspace"
            className="flex items-center gap-1.5 text-sm px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-synapse-cyan/25 to-synapse-violet/25 border border-synapse-cyan/25 hover:from-synapse-cyan/40 hover:to-synapse-violet/40 transition-all"
          >
            Open workspace
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative z-10 px-6 md:px-10 pt-10 md:pt-16 pb-20 grid md:grid-cols-[1.05fr,1fr] gap-10 items-center max-w-6xl mx-auto">
        <div>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-synapse-cyan/25 bg-synapse-cyan/5 text-[11px] uppercase tracking-[0.18em] text-synapse-cyan mb-5 animate-fade-up">
            <Sparkles className="w-3 h-3" /> Local-first PKM
          </div>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-[1.05] animate-fade-up">
            Your thoughts,
            <br />
            <span className="bg-gradient-to-r from-synapse-cyan via-synapse-violet to-synapse-magenta bg-clip-text text-transparent">
              connected.
            </span>
          </h1>
          <p className="text-ink-300 text-lg mt-5 leading-relaxed max-w-xl animate-fade-up">
            SynapseOS is a Personal Knowledge OS where every note is a synapse.
            Write in Markdown, link with <span className="font-mono text-synapse-cyan">[[double brackets]]</span>,
            and watch your ideas form a living graph — instantly, in your
            browser, with no server.
          </p>
          <div className="mt-7 flex items-center gap-3 animate-fade-up">
            <Link
              href="/workspace"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-synapse-cyan to-synapse-violet text-void-900 font-semibold shadow-glow hover:brightness-110 transition"
            >
              Launch SynapseOS
              <ArrowRight className="w-4 h-4" />
            </Link>
            <KeyHint />
          </div>
          <div className="mt-8 flex items-center gap-5 text-[11px] uppercase tracking-[0.2em] text-ink-400">
            <span className="flex items-center gap-1.5">
              <Lock className="w-3 h-3" /> 100% local
            </span>
            <span className="flex items-center gap-1.5">
              <Zap className="w-3 h-3" /> No signup
            </span>
            <span className="flex items-center gap-1.5">
              <Brain className="w-3 h-3" /> Open source
            </span>
          </div>
        </div>

        {/* Hero visual */}
        <div className="relative aspect-[5/4] rounded-2xl overflow-hidden surface shadow-glowViolet">
          <HeroGraph />
          <div className="absolute inset-0 bg-gradient-to-t from-void-900/60 via-transparent to-void-900/20" />
          <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between text-[11px] text-ink-300">
            <span className="flex items-center gap-1.5">
              <Network className="w-3 h-3 text-synapse-cyan" /> Live synapse graph
            </span>
            <span className="font-mono text-ink-400">26 nodes · 40 links</span>
          </div>
        </div>
      </section>

      {/* Feature grid */}
      <section className="relative z-10 px-6 md:px-10 pb-20 max-w-6xl mx-auto">
        <div className="divider-neon mb-14" />
        <h2 className="text-2xl md:text-3xl font-semibold tracking-tight mb-2">
          A notes app that <span className="text-synapse-cyan">thinks in connections.</span>
        </h2>
        <p className="text-ink-300 max-w-2xl mb-10">
          Most tools treat notes as files in folders. SynapseOS treats them as
          neurons — the value lives in the edges between ideas.
        </p>
        <div className="grid md:grid-cols-3 gap-4">
          <Feature
            icon={<Network className="w-5 h-5" />}
            title="Force-directed synapse graph"
            body="Pan, zoom, drag nodes. Active notes glow. Ghost nodes hint at links you haven't written yet."
          />
          <Feature
            icon={<Brain className="w-5 h-5" />}
            title="Live backlinks & outbound"
            body="Every note shows who links to it and where it points. Break a link and it turns dashed magenta."
          />
          <Feature
            icon={<Command className="w-5 h-5" />}
            title="⌘K command palette"
            body="Fuzzy-jump to any note, or type a brand-new title and hit enter to create it on the spot."
          />
          <Feature
            icon={<Lock className="w-5 h-5" />}
            title="Local-first, private"
            body="Your vault lives in your browser. No accounts, no cloud. Exportable, yours forever."
          />
          <Feature
            icon={<Keyboard className="w-5 h-5" />}
            title="Keyboard-driven"
            body="⌘N new note, ⌘G toggle graph, ⌘K palette. Optimized for flow, not clicks."
          />
          <Feature
            icon={<Sparkles className="w-5 h-5" />}
            title="Gorgeous dark UI"
            body="Neon synapse accents, glass surfaces, crisp typography. Presentation matters."
          />
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 px-6 md:px-10 py-10 border-t border-white/5 text-sm text-ink-400 flex items-center justify-between max-w-6xl mx-auto">
        <div className="flex items-center gap-2">
          <Mark small />
          <span>SynapseOS</span>
          <span className="text-ink-500">· MIT</span>
        </div>
        <div className="flex items-center gap-4">
          <a
            href="https://github.com/Aryanharitsa/Projects/tree/main/SynapseOS"
            target="_blank"
            rel="noreferrer"
            className="hover:text-ink-100"
          >
            Source
          </a>
          <Link href="/workspace" className="hover:text-ink-100">
            Workspace
          </Link>
        </div>
      </footer>
    </main>
  );
}

function Feature({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="surface surface-hover rounded-2xl p-5 transition-all">
      <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-synapse-cyan/15 to-synapse-violet/15 border border-white/5 flex items-center justify-center text-synapse-cyan mb-3">
        {icon}
      </div>
      <h3 className="font-semibold mb-1">{title}</h3>
      <p className="text-sm text-ink-300 leading-relaxed">{body}</p>
    </div>
  );
}

function KeyHint() {
  return (
    <span className="text-[11px] text-ink-400 flex items-center gap-1.5">
      or press
      <kbd className="px-1.5 py-0.5 rounded border border-white/10 bg-void-700/60 font-mono text-ink-200">
        ⌘K
      </kbd>
      inside
    </span>
  );
}

function Mark({ small }: { small?: boolean }) {
  const s = small ? "w-6 h-6" : "w-8 h-8";
  return (
    <div className={`relative ${s}`}>
      <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-synapse-cyan via-synapse-violet to-synapse-magenta opacity-90" />
      <div className="absolute inset-[2px] rounded-[7px] bg-void-900 flex items-center justify-center">
        <svg viewBox="0 0 24 24" className={small ? "w-3 h-3" : "w-4 h-4"} fill="none">
          <circle cx="6" cy="6" r="2" fill="#22e4ff" />
          <circle cx="18" cy="6" r="2" fill="#9a5bff" />
          <circle cx="12" cy="18" r="2" fill="#ff4fd8" />
          <path
            d="M6 6 L12 18 M18 6 L12 18 M6 6 L18 6"
            stroke="url(#glanding)"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
          <defs>
            <linearGradient id="glanding" x1="0" y1="0" x2="24" y2="24">
              <stop offset="0" stopColor="#22e4ff" />
              <stop offset="1" stopColor="#ff4fd8" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
  );
}
