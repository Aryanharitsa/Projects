// Explainable match engine.
//
// Takes a free-text job query like
//   "Senior backend (FastAPI + Postgres) in Bengaluru"
// and scores a candidate against it with a breakdown of why.
//
// Pure function, no network. Same scoring logic is mirrored on the backend
// in `app/services/match.py` so server-side results agree.

export type MatchFactor = {
  key: "skills" | "location" | "seniority" | "base";
  label: string;
  impact: number; // points this factor contributed (0..100)
};

export type MatchResult = {
  score: number; // 0..100
  matchedSkills: string[];
  missingSkills: string[];
  seniority: { wanted?: string; candidate?: string; match: boolean };
  location: { wanted?: string; match: "full" | "partial" | "none" };
  factors: MatchFactor[];
};

export type CandidateLike = {
  name?: string;
  role?: string;
  location?: string;
  tags?: string[];
  keywords?: string[];
  headline?: string;
};

export type QueryPlan = {
  text: string;
  skills: string[];
  location?: string;
  seniority?: string;
};

const ALIASES: Record<string, string> = {
  reactjs: "react",
  "react.js": "react",
  nextjs: "next.js",
  nodejs: "node.js",
  node: "node.js",
  ts: "typescript",
  js: "javascript",
  py: "python",
  postgresql: "postgres",
  psql: "postgres",
  "fast api": "fastapi",
  tailwindcss: "tailwind",
  mongo: "mongodb",
  k8s: "kubernetes",
  golang: "go",
  bangalore: "bengaluru",
};

const SKILL_VOCAB = new Set<string>([
  "react", "next.js", "vue", "svelte", "angular",
  "typescript", "javascript", "python", "go", "rust", "java", "kotlin", "swift",
  "fastapi", "flask", "django", "express", "nest.js", "spring",
  "postgres", "mysql", "mongodb", "redis", "kafka", "rabbitmq",
  "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
  "graphql", "rest", "grpc",
  "tailwind", "css", "html", "sass",
  "node.js",
  "pandas", "numpy", "pytorch", "tensorflow", "scikit-learn", "ml", "nlp", "llm",
  "prisma", "sqlalchemy",
  "cypress", "jest", "playwright", "pytest",
]);

const LOCATION_VOCAB = new Set<string>([
  "bengaluru", "mumbai", "delhi", "hyderabad", "chennai",
  "pune", "kolkata", "noida", "gurgaon", "ahmedabad", "kochi",
  "remote", "hybrid", "onsite",
]);

const SENIORITY = ["intern", "junior", "mid", "senior", "staff", "principal", "lead"];

const WEIGHTS = { skill: 0.55, loc: 0.15, sen: 0.2, base: 0.1 };

function canon(token: string): string {
  const t = token.toLowerCase().replace(/^[\W_]+|[\W_]+$/g, "");
  return ALIASES[t] ?? t;
}

function tokens(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[()[\]{},;/]/g, " ")
    .split(/\s+/)
    .map(canon)
    .filter(Boolean);
}

export function extractSkills(text: string): string[] {
  if (!text) return [];
  const out = new Set<string>();
  for (const t of tokens(text)) if (SKILL_VOCAB.has(t)) out.add(t);
  // multi-word phrase lookup
  const lower = text.toLowerCase();
  for (const skill of SKILL_VOCAB) {
    if (skill.includes(".") || skill.includes(" ")) {
      if (lower.includes(skill)) out.add(skill);
    }
  }
  // alias phrase lookup
  for (const phrase of Object.keys(ALIASES)) {
    if (phrase.includes(" ") && lower.includes(phrase)) {
      const target = ALIASES[phrase];
      if (SKILL_VOCAB.has(target)) out.add(target);
    }
  }
  return Array.from(out);
}

export function extractLocation(text: string): string | undefined {
  if (!text) return undefined;
  const m = text.match(/\bin\s+([A-Za-z][A-Za-z\s]+?)(?:$|[.,;])/i);
  if (m) {
    const loc = canon(m[1].trim());
    if (LOCATION_VOCAB.has(loc)) return loc;
  }
  for (const t of tokens(text)) if (LOCATION_VOCAB.has(t)) return t;
  return undefined;
}

export function extractSeniority(text: string): string | undefined {
  if (!text) return undefined;
  const lower = text.toLowerCase();
  for (const s of SENIORITY) if (new RegExp(`\\b${s}\\b`).test(lower)) return s;
  return undefined;
}

export function planQuery(text: string): QueryPlan {
  return {
    text,
    skills: extractSkills(text),
    location: extractLocation(text),
    seniority: extractSeniority(text),
  };
}

export function matchCandidate(plan: QueryPlan, c: CandidateLike): MatchResult {
  const bag = new Set<string>(
    [
      ...(c.tags ?? []),
      ...(c.keywords ?? []),
      ...((c.role ?? "").split(/\s+/)),
    ]
      .map(canon)
      .filter(Boolean)
  );
  const candLoc = canon((c.location ?? "").split(/[(),]/)[0]);

  const matched: string[] = [];
  const missing: string[] = [];
  for (const s of plan.skills) {
    if (bag.has(s)) matched.push(s);
    else missing.push(s);
  }
  const skillCov =
    plan.skills.length === 0 ? 0.8 : matched.length / plan.skills.length;

  let locState: "full" | "partial" | "none";
  if (!plan.location) locState = "full";
  else if (candLoc === plan.location || plan.location === "remote")
    locState = "full";
  else if (candLoc === "remote" || candLoc.includes("hybrid"))
    locState = "partial";
  else locState = "none";
  const locScore = locState === "full" ? 1 : locState === "partial" ? 0.5 : 0;

  const candSen = extractSeniority([c.role ?? "", c.headline ?? ""].join(" "));
  const senMatch = plan.seniority ? candSen === plan.seniority : true;
  const senScore = !plan.seniority
    ? 1
    : senMatch
    ? 1
    : candSen
    ? 0.3
    : 0.6;

  const raw =
    WEIGHTS.skill * skillCov +
    WEIGHTS.loc * locScore +
    WEIGHTS.sen * senScore +
    WEIGHTS.base;
  const score = Math.round(Math.max(0, Math.min(1, raw)) * 100);

  const factors: MatchFactor[] = [];
  factors.push({
    key: "base",
    label: "Baseline fit",
    impact: Math.round(WEIGHTS.base * 100),
  });
  if (plan.skills.length) {
    factors.push({
      key: "skills",
      label: `${matched.length}/${plan.skills.length} required skill${
        plan.skills.length === 1 ? "" : "s"
      }`,
      impact: Math.round(WEIGHTS.skill * 100 * skillCov),
    });
  } else {
    factors.push({
      key: "skills",
      label: "No specific skills requested",
      impact: Math.round(WEIGHTS.skill * 100 * skillCov),
    });
  }
  if (plan.location) {
    const label =
      locState === "full"
        ? `Location · ${plan.location}`
        : locState === "partial"
        ? `Location · ${c.location ?? candLoc} (flex)`
        : `Location · ${c.location ?? "unknown"} (mismatch)`;
    factors.push({
      key: "location",
      label,
      impact: Math.round(WEIGHTS.loc * 100 * locScore),
    });
  }
  if (plan.seniority) {
    factors.push({
      key: "seniority",
      label: senMatch
        ? `Seniority · ${plan.seniority}`
        : `Seniority · ${candSen ?? "unspecified"} (wanted ${plan.seniority})`,
      impact: Math.round(WEIGHTS.sen * 100 * senScore),
    });
  }

  return {
    score,
    matchedSkills: matched,
    missingSkills: missing,
    seniority: { wanted: plan.seniority, candidate: candSen, match: senMatch },
    location: { wanted: plan.location, match: locState },
    factors,
  };
}

export function scoreBand(score: number): "strong" | "solid" | "weak" {
  if (score >= 80) return "strong";
  if (score >= 60) return "solid";
  return "weak";
}
