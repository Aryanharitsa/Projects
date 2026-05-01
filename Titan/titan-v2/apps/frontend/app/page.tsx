import Link from "next/link";

const FEATURES = [
  {
    href: "/aml",
    title: "AML Console",
    eyebrow: "Risk",
    body: "A deterministic, explainable rule engine. Eight detectors — structuring, velocity, round-trip cycles, sanctions hits, fan-in/-out, geo, round amounts — plus a what-if simulator that re-scores live as you re-tune weights.",
    accent: "from-violet-500/30 to-violet-500/0",
    cta: "Score transactions",
  },
  {
    href: "/watchlist",
    title: "Sanctions Watchlist",
    eyebrow: "Screening",
    body: "Fuzzy-match names against the bundled OFAC/UN/EU/UK-style watchlist. Every score is a transparent blend of token-set, char-3gram, and substring containment — with a jurisdiction prior on top.",
    accent: "from-rose-400/25 via-amber-400/15 to-transparent",
    cta: "Screen names",
  },
  {
    href: "/kyc",
    title: "KYC Pipeline",
    eyebrow: "Identity",
    body: "Upload a PAN PDF. We hash it locally, pin the artefact to IPFS, then write the hash + verifier + subject wallet to the AttestationRegistry contract on-chain.",
    accent: "from-teal-400/30 to-teal-400/0",
    cta: "Run a verification",
  },
  {
    href: "/attestations",
    title: "Attestation Explorer",
    eyebrow: "On-chain",
    body: "Look up any document hash to verify whether it was attested, by whom, and when — straight from chain state. Recent attestations stream in live.",
    accent: "from-teal-400/25 via-violet-500/15 to-transparent",
    cta: "Open explorer",
  },
];

const STATS = [
  { label: "Pattern detectors", value: "8" },
  { label: "Watchlist entries", value: "30" },
  { label: "On-chain attestations", value: "live" },
  { label: "External ML deps", value: "0" },
];

export default function Home() {
  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="glass-strong overflow-hidden p-8 md:p-12">
        <div className="grid items-center gap-8 md:grid-cols-[1.4fr_1fr]">
          <div>
            <span className="pill pill-ok">v2 · explainable</span>
            <h1 className="mt-4 text-3xl font-semibold leading-[1.05] tracking-tight md:text-5xl">
              <span className="grad-text">Trusted identity</span>,{" "}
              <span className="grad-text">transparent risk</span>.
              <br />
              One pipeline.
            </h1>
            <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-white/65">
              TITAN runs KYC documents through OCR + IPFS + an on-chain attestation
              registry, and pipes the same subjects through an explainable AML rule
              engine. Every alert ships with a per-factor breakdown and a one-click
              SAR draft — no black boxes, no third-party scorer.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/kyc" className="btn-primary">
                Verify a document
                <span aria-hidden>↗</span>
              </Link>
              <Link href="/aml" className="btn">Score transactions</Link>
              <a
                href="https://github.com/Aryanharitsa/Projects/tree/main/Titan"
                target="_blank"
                className="btn-ghost"
              >
                View source
              </a>
            </div>
          </div>

          <div className="relative h-[260px] w-full">
            <FlowDiagram />
          </div>
        </div>
      </section>

      {/* Stats strip */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label} className="glass px-4 py-3">
            <div className="text-[11px] uppercase tracking-wider text-white/40">
              {s.label}
            </div>
            <div className="mt-1 text-2xl font-semibold tracking-tight grad-text">
              {s.value}
            </div>
          </div>
        ))}
      </section>

      {/* Feature cards */}
      <section className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <Link
            key={f.href}
            href={f.href}
            className="glass group relative overflow-hidden p-6 transition hover:-translate-y-0.5 hover:bg-white/[0.05]"
          >
            <div
              className={`pointer-events-none absolute -right-24 -top-24 h-56 w-56 rounded-full bg-gradient-to-br ${f.accent} blur-2xl`}
            />
            <div className="text-[11px] uppercase tracking-[0.2em] text-white/45">
              {f.eyebrow}
            </div>
            <h3 className="mt-2 text-xl font-semibold tracking-tight">
              {f.title}
            </h3>
            <p className="mt-2 text-[13.5px] leading-relaxed text-white/65">
              {f.body}
            </p>
            <div className="mt-5 inline-flex items-center gap-1.5 text-[12.5px] text-teal-400">
              {f.cta}
              <span className="transition group-hover:translate-x-0.5">→</span>
            </div>
          </Link>
        ))}
      </section>

      {/* Architecture quick-look */}
      <section className="glass p-6 md:p-8">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">How it fits together</h2>
          <span className="pill">deterministic</span>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <Card
            step="01"
            title="Ingest"
            body="PDF → SHA-256 → IPFS pin via Kubo. The artefact never leaves IPFS; only the digest is stored anywhere else."
          />
          <Card
            step="02"
            title="Anchor"
            body="The gateway signs an attest(docHash, subject, verifierId) tx. The Attested event is the verifiable receipt."
          />
          <Card
            step="03"
            title="Score"
            body="Per-account risk = Σ weighted detector contributions, capped at 100. Triggers a SAR draft at ≥60."
          />
        </div>
      </section>
    </div>
  );
}

function Card({ step, title, body }: { step: string; title: string; body: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-4">
      <div className="font-mono text-[11px] tracking-widest text-teal-400">
        STEP {step}
      </div>
      <div className="mt-1 text-[15px] font-medium">{title}</div>
      <div className="mt-1 text-[12.5px] leading-relaxed text-white/60">
        {body}
      </div>
    </div>
  );
}

/** A small inline architecture sketch — rendered via SVG, no extra deps. */
function FlowDiagram() {
  return (
    <svg viewBox="0 0 360 260" className="h-full w-full">
      <defs>
        <linearGradient id="hero-edge" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2DE1C2" />
          <stop offset="1" stopColor="#6E5BFF" />
        </linearGradient>
      </defs>

      {/* nodes */}
      {[
        { x: 30, y: 60, label: "Subject" },
        { x: 30, y: 200, label: "Analyst" },
        { x: 170, y: 130, label: "TITAN", strong: true },
        { x: 320, y: 30, label: "IPFS" },
        { x: 320, y: 130, label: "Chain" },
        { x: 320, y: 230, label: "AML" },
      ].map((n) => (
        <g key={n.label}>
          <circle
            cx={n.x}
            cy={n.y}
            r={n.strong ? 30 : 22}
            fill={n.strong ? "rgba(45,225,194,0.18)" : "rgba(255,255,255,0.05)"}
            stroke={n.strong ? "rgba(45,225,194,0.55)" : "rgba(255,255,255,0.18)"}
            strokeWidth={n.strong ? 2 : 1}
          />
          <text
            x={n.x}
            y={n.y + 4}
            textAnchor="middle"
            style={{ fontSize: 11, fontFamily: "Inter, sans-serif" }}
            className="fill-white/85"
          >
            {n.label}
          </text>
        </g>
      ))}

      {/* edges */}
      {[
        ["M52,60 Q110,90 145,118"],
        ["M52,200 Q110,170 145,142"],
        ["M198,116 Q260,80 300,42"],
        ["M200,130 L300,130"],
        ["M198,144 Q260,180 300,218"],
      ].map((p, i) => (
        <path
          key={i}
          d={p[0]}
          stroke="url(#hero-edge)"
          strokeWidth={1.6}
          fill="none"
          opacity={0.85}
        />
      ))}
    </svg>
  );
}
