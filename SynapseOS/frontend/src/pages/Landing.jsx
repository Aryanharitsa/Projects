import { Link } from "react-router-dom";
import { ArrowRight, Brain, Network, Sparkles, Wand2, Zap } from "lucide-react";

export default function Landing() {
  return (
    <div className="mx-auto max-w-[1200px] px-6">
      <section className="pt-16 pb-24 text-center relative">
        <div
          aria-hidden
          className="absolute inset-0 -z-10
                     bg-[radial-gradient(circle_at_50%_30%,rgba(129,140,248,0.2),transparent_60%)]"
        />

        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-white/60">
          <Sparkles className="h-3.5 w-3.5 text-fuchsia-300" />
          v0.1 · a neural second brain
        </div>

        <h1 className="mt-6 text-5xl sm:text-6xl font-semibold tracking-tight leading-[1.05]">
          Your thoughts,
          <br />
          <span className="bg-gradient-to-r from-indigo-300 via-fuchsia-300 to-rose-300 bg-clip-text text-transparent">
            wired into a living graph.
          </span>
        </h1>

        <p className="mt-6 max-w-2xl mx-auto text-white/70 text-lg leading-relaxed">
          SynapseOS captures your notes and{" "}
          <em className="not-italic text-white/90">automatically</em> connects
          the ones that mean related things — no manual <code className="text-fuchsia-300">[[links]]</code>,
          no folder tax. Think of it as what Obsidian's graph view{" "}
          <span className="underline decoration-dotted">wanted</span> to be.
        </p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/brain"
            className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-6 py-3 text-sm font-semibold text-white shadow-xl shadow-fuchsia-500/30 hover:shadow-fuchsia-500/50 transition-shadow"
          >
            Open the Brain
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="https://github.com/Aryanharitsa/Projects/tree/main/SynapseOS"
            target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-6 py-3 text-sm text-white/80 hover:bg-white/10 transition-colors"
          >
            Read the README
          </a>
        </div>

        {/* ambient neural glyph */}
        <div className="mt-14 flex justify-center">
          <svg
            width="520" height="180" viewBox="0 0 520 180"
            className="glyph-pulse"
          >
            <defs>
              <radialGradient id="lg" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#c4b5fd" />
                <stop offset="100%" stopColor="#6366f1" />
              </radialGradient>
              <linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%"  stopColor="#a78bfa" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#f472b6" stopOpacity="0.8" />
              </linearGradient>
            </defs>
            {[
              [60, 90], [160, 40], [260, 90], [360, 40], [460, 90],
              [210, 140], [310, 140], [110, 140], [410, 140]
            ].map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 9 : 6} fill="url(#lg)" />
            ))}
            {[
              [60,90,160,40],[160,40,260,90],[260,90,360,40],[360,40,460,90],
              [60,90,110,140],[160,40,210,140],[260,90,310,140],[360,40,410,140],
              [110,140,210,140],[210,140,310,140],[310,140,410,140],
              [60,90,210,140],[460,90,310,140]
            ].map(([x1,y1,x2,y2], i) => (
              <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke="url(#edge)" strokeOpacity="0.5" strokeWidth="1.2" />
            ))}
          </svg>
        </div>
      </section>

      {/* features */}
      <section className="pb-24 grid grid-cols-1 md:grid-cols-3 gap-4">
        <Feature
          icon={Network}
          title="Auto-synapses"
          body="Every thought you write is vectorised with TF-IDF and compared against the rest of your brain. Similar notes grow edges — and the edges thicken with similarity."
        />
        <Feature
          icon={Brain}
          title="Graph-first UX"
          body="A canvas-rendered, force-directed layout where cluster = topic. Hover a node to highlight its neighbourhood; click to edit the note and watch the graph rewire."
        />
        <Feature
          icon={Wand2}
          title="Zero onboarding"
          body="No API keys, no OpenAI dependency, no external services. The synapse engine is 100 % local Python. Clone, `pip install`, and your first graph is already drawn."
        />
        <Feature
          icon={Zap}
          title="Fast rewire"
          body="Every create / edit / delete triggers a full synapse recompute. On personal-scale corpora (hundreds of notes) this stays sub-100ms thanks to sparse vectors."
        />
        <Feature
          icon={Sparkles}
          title="Strength-aware edges"
          body="Edges carry a cosine strength, used to tune both the layout spring length and the rendered opacity & thickness. Weak ties stay as ghost hints; strong ties are obvious."
        />
        <Feature
          icon={Brain}
          title="Built to grow"
          body="The embedder interface is pluggable — any object with `.encode(text)` works. A future day plugs in local sentence-transformers or an OpenAI embeddings provider behind the same API."
        />
      </section>
    </div>
  );
}

function Feature({ icon: Icon, title, body }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-sm p-5 hover:border-white/25 hover:bg-white/[0.05] transition-colors">
      <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-indigo-500/80 to-fuchsia-500/80 grid place-items-center shadow-lg shadow-indigo-500/20">
        <Icon className="h-4 w-4 text-white" />
      </div>
      <h3 className="mt-3 text-base font-semibold">{title}</h3>
      <p className="mt-1.5 text-sm text-white/65 leading-relaxed">{body}</p>
    </div>
  );
}
