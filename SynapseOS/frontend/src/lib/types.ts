export type Note = {
  id: number;
  title: string;
  body: string;
  tags: string[];
  created_at: string;
  last_seen_at?: string | null;
};

export type GraphNode = {
  id: number;
  title: string;
  body: string;
  tags: string[];
  degree: number;
  weight: number;
  community?: number | null;
  community_color?: string | null;
};

export type GraphEdge = {
  source: number;
  target: number;
  strength: number;
  kind: "synapse";
};

export type GraphStats = {
  nodes: number;
  edges: number;
  avg_degree: number;
  threshold: number;
  top_k: number;
  communities?: number;
};

export type Community = {
  id: number;
  name: string;
  color: string;
  size: number;
  terms: string[];
  member_ids: number[];
};

export type OrphanSuggestion = {
  note_id: number;
  title: string;
  suggested_id: number | null;
  suggested_title: string | null;
  suggested_strength: number;
  suggested_threshold: number;
};

export type Graph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
};

export type Neighbor = {
  node: GraphNode;
  strength: number;
};

export type SearchHit = {
  node: GraphNode;
  score: number;
};

export type PathStep = {
  node: GraphNode;
  strength: number;
};

export type PathResult = {
  found: boolean;
  path: PathStep[];
  cost: number;
};

export type ChatRole = "seed" | "synapse" | "community";

export type ChatCitation = {
  note_id: number;
  title: string;
  snippet: string;
  score: number;
  role: ChatRole;
  via_seed_id: number | null;
  via_strength: number;
};

export type ChatExpansion = {
  src: number;
  dst: number;
  strength: number;
  kind: ChatRole;
};

export type ChatTraversal = {
  seeds: number[];
  expansions: ChatExpansion[];
};

export type ChatMode = "auto" | "extractive" | "llm";

export type ChatResponse = {
  query: string;
  answer: string;
  citations: ChatCitation[];
  traversal: ChatTraversal;
  model: string;
  mode_used: "extractive" | "llm";
  latency_ms: number;
  llm_available: boolean;
  llm_provider: string | null;
  notice: string | null;
};

export type ChatStatus = {
  llm_available: boolean;
  llm_provider: string | null;
  extractive_available: boolean;
};

export type ChatTurn = {
  id: string;       // local-only uuid for keys
  query: string;
  response: ChatResponse;
};

export type BriefReasonKind = "stale" | "central" | "orphan" | "diverse";

export type BriefReason = {
  kind: BriefReasonKind;
  text: string;
  weight: number;
};

export type BriefConnection = {
  note_id: number;
  title: string;
  strength: number;
  cluster_id: number | null;
  cluster_name: string | null;
};

export type BriefPick = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  score: number;
  reasons: BriefReason[];
  prompt: string;
  connections: BriefConnection[];
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  days_since_seen: number | null;
  is_orphan: boolean;
};

export type Brief = {
  date: string;          // YYYY-MM-DD
  k: number;
  total_notes: number;
  picks: BriefPick[];
  stats: { considered?: number; orphan_count?: number; clusters_touched?: number };
};

// ----------------------------------------------------------------- trails

export type TrailOrigin = "manual" | "path" | "chat";

export type TrailStep = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  caption: string;
  exists: boolean;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  strength_to_next: number | null;
  is_synapse_to_next: boolean;
};

export type Trail = {
  id: number;
  title: string;
  description: string;
  origin: TrailOrigin;
  created_at: string;
  updated_at: string;
  threshold: number;
  top_k: number;
  health: number;            // 0..1
  total_strength: number;
  missing_count: number;
  clusters_touched: number[];
  steps: TrailStep[];
};

export type TrailSummary = {
  id: number;
  title: string;
  description: string;
  origin: TrailOrigin;
  created_at: string;
  updated_at: string;
  step_count: number;
  health: number;
  missing_count: number;
};

export type TrailSuggestion = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  strength: number;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
};

export type TrailSuggestions = {
  trail_id: number;
  threshold: number;
  suggestions: TrailSuggestion[];
};

export type TrailDraftStep = { note_id: number; caption: string };

// --------------------------------------------------------------- distill

export type AtomNeighbor = {
  note_id: number;
  title: string;
  strength: number;
  cluster_id?: number | null;
  cluster_color?: string | null;
};

export type AtomPreview = {
  temp_id: string;
  title: string;
  body: string;
  tags: string[];
  char_count: number;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  cluster_strength: number;
  neighbors: AtomNeighbor[];
  expected_synapses: number;
  llm_refined: boolean;
};

export type AtomizeMode = "auto" | "heuristic" | "llm";

export type AtomizeResponse = {
  atoms: AtomPreview[];
  total_chars: number;
  mode_used: "heuristic" | "llm";
  llm_available: boolean;
  llm_provider: string | null;
  notice: string | null;
};

export type AtomCommit = { title: string; body: string; tags: string[] };

export type AtomCommitResult = { note_id: number; title: string; synapses: number };

export type AtomizeCommitResponse = {
  created: AtomCommitResult[];
  synapses_formed: number;
};

// --------------------------------------------------------------- synthesis

export type DigestSource = {
  ref: number;
  note_id: number;
  title: string;
  centrality: number;
};

export type DigestClaim = {
  text: string;
  note_id: number;
  ref: number;
};

export type OpenThread = {
  note_id: number;
  title: string;
  text: string;
  kind: "question" | "underdeveloped";
};

export type DigestBridge = {
  note_id: number;
  title: string;
  cluster_id: number;
  cluster_name: string;
  cluster_color: string;
  strength: number;
};

export type ClusterDigest = {
  cluster_id: number;
  name: string;
  color: string;
  size: number;
  terms: string[];
  cohesion: number;
  overview: string;
  claims: DigestClaim[];
  open_threads: OpenThread[];
  bridges: DigestBridge[];
  sources: DigestSource[];
  mode_used: "extractive" | "llm";
  llm_available: boolean;
  llm_provider: string | null;
  notice: string | null;
};

// --------------------------------------------------------------- tensions

export type TensionSignalKind = "polarity" | "antonym" | "contrast" | "title";

export type TensionSignal = {
  kind: TensionSignalKind;
  weight: number;
  detail: string;
};

export type TensionEvidence = {
  note_id: number;
  title: string;
  sentence: string;
  polarity: number;
};

export type TensionKind = "internal" | "cross";

export type Tension = {
  a_id: number;
  a_title: string;
  b_id: number;
  b_title: string;
  cosine: number;
  magnitude: number;
  signals: TensionSignal[];
  evidence: TensionEvidence[];
  bridge_title: string;
  bridge_prompt: string;
  bridge_tags: string[];
  kind: TensionKind;
  cluster_a: number | null;
  cluster_a_name: string | null;
  cluster_a_color: string | null;
  cluster_b: number | null;
  cluster_b_name: string | null;
  cluster_b_color: string | null;
};

export type TensionReport = {
  threshold: number;
  floor: number;
  total_pairs_scanned: number;
  candidate_count: number;
  tension_count: number;
  tensions: Tension[];
  stats: {
    notes?: number;
    candidate_pairs?: number;
    internal?: number;
    cross?: number;
    top_magnitude?: number;
  };
};

export type NoteDraft = {
  title: string;
  body: string;
  tags: string[];
};

// ----------------------------------------------------------------- echo

export type EchoMember = {
  note_id: number;
  title: string;
  body: string;
  tags: string[];
  created_at: string;
  body_len: number;
  is_canonical: boolean;
  centrality: number;
};

export type EchoPair = {
  a_id: number;
  b_id: number;
  cosine: number;
};

export type EchoSentence = {
  text: string;
  note_ids: number[];
  is_duplicate: boolean;
  is_canonical_source: boolean;
};

export type EchoCluster = {
  cluster_id: string;
  size: number;
  redundancy: number;
  peak_cosine: number;
  wasted_chars: number;
  chars_total: number;
  chars_unique: number;
  canonical_id: number;
  members: EchoMember[];
  pairs: EchoPair[];
  merged_title: string;
  merged_body: string;
  merged_tags: string[];
  sentences: EchoSentence[];
  overlap_ratio: number;
};

export type EchoReport = {
  threshold: number;
  total_notes: number;
  candidate_pairs: number;
  cluster_count: number;
  skipped_pair_count: number;
  clusters: EchoCluster[];
  stats: {
    notes?: number;
    pairs_above_threshold?: number;
    clusters?: number;
    wasted_chars_total?: number;
    biggest_redundancy?: number;
  };
};

export type EchoMergeResult = {
  merged_note_id: number;
  merged_title: string;
  deleted_ids: number[];
  wasted_chars_recovered: number;
  final_synapses: number;
};

export type EchoSkipEntry = {
  a_id: number;
  b_id: number;
  reason: string;
  created_at: string;
};

// ----------------------------------------------------------------- atlas

export type AtlasQuadrant = "stronghold" | "frontier" | "vault" | "drift";

export type AtlasRecommendationKind =
  | "synthesize"
  | "split"
  | "revisit"
  | "dissolve"
  | "bridge";

export type AtlasCluster = {
  id: number;
  name: string;
  color: string;
  size: number;
  terms: string[];
  cohesion: number;
  internal_density: number;
  activity: number;
  growth_velocity: number;
  last_touched_days: number | null;
  newest_age_days: number;
  mean_age_days: number;
  bridge_count: number;
  has_synapses: boolean;
  quadrant: AtlasQuadrant;
};

export type AtlasRecommendation = {
  cluster_id: number;
  cluster_name: string;
  cluster_color: string;
  kind: AtlasRecommendationKind;
  priority: number;
  headline: string;
  detail: string;
};

export type AtlasReport = {
  window_days: number;
  generated_at: string;
  total_notes: number;
  total_clusters: number;
  clusters: AtlasCluster[];
  recommendations: AtlasRecommendation[];
  summary: {
    stronghold_count?: number;
    frontier_count?: number;
    vault_count?: number;
    drift_count?: number;
    mean_cohesion?: number;
    growth_velocity?: number;
    bridge_potential?: number;
  };
};

// ------------------------------------------------------------- chronicle

export type ChronicleCategory = "calm" | "shifting" | "pivoting";

export type ChronicleChapter = {
  index: number;
  date_start: string;
  date_end: string;
  span_days: number;
  count: number;
  terms: string[];
  anchor_id: number;
  anchor_title: string;
  anchor_sentence: string;
  member_ids: number[];
  drift_in: number;
};

export type ChronicleCluster = {
  cluster_id: number;
  name: string;
  color: string;
  size: number;
  chapter_count: number;
  total_drift: number;
  peak_drift: number;
  pivot_index: number | null;
  stability: number;
  category: ChronicleCategory;
  span_days: number;
  cadence_days: number;
  emerged_terms: string[];
  faded_terms: string[];
  headline: string;
  chapters: ChronicleChapter[];
};

export type ChronicleReport = {
  generated_at: string;
  total_notes: number;
  total_clusters: number;
  eligible_clusters: number;
  target_chapters: number;
  min_cluster_notes: number;
  min_span_days: number;
  clusters: ChronicleCluster[];
  summary: {
    calm_count?: number;
    shifting_count?: number;
    pivoting_count?: number;
    mean_drift?: number;
    total_chapters?: number;
    pivots_detected?: number;
    most_pivoting?: string;
    most_stable?: string;
  };
};

// ----------------------------------------------------------------- pulse

export type PulseClusterStatus =
  | "born"
  | "emerging"
  | "hot"
  | "warm"
  | "dormant";

export type PulseRecommendationKind =
  | "synthesize"
  | "name"
  | "revisit"
  | "bridge"
  | "hub";

export type PulseDay = {
  date: string;        // YYYY-MM-DD
  created: number;
  revisited: number;
};

export type PulseCluster = {
  cluster_id: number;
  name: string;
  color: string;
  size: number;
  new_count: number;
  revisits_count: number;
  share_new: number;
  momentum: number;
  centroid_drift: number | null;
  status: PulseClusterStatus;
  last_touched_days: number | null;
  new_terms: string[];
  hot_titles: string[];
};

export type PulseBridge = {
  source_id: number;
  source_title: string;
  target_id: number;
  target_title: string;
  source_cluster_id: number;
  source_cluster_name: string;
  source_cluster_color: string;
  target_cluster_id: number;
  target_cluster_name: string;
  target_cluster_color: string;
  strength: number;
  source_is_new: boolean;
  target_is_new: boolean;
};

export type PulseHub = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  degree: number;
  weight: number;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  days_old: number;
};

export type PulseRecommendation = {
  kind: PulseRecommendationKind;
  headline: string;
  detail: string;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  note_id: number | null;
  priority: number;
};

export type PulseReport = {
  window_days: number;
  generated_at: string;
  window_start: string;
  headline: string;
  total_notes: number;
  new_notes: number;
  revisited_notes: number;
  words_written: number;
  streak_days: number;
  synapses_total: number;
  bridges_born: number;
  hubs_born: number;
  clusters_total: number;
  clusters_hot: number;
  clusters_emerging: number;
  clusters_dormant: number;
  activity: PulseDay[];
  clusters: PulseCluster[];
  bridges: PulseBridge[];
  hubs: PulseHub[];
  emerged_terms: string[];
  faded_terms: string[];
  recommendations: PulseRecommendation[];
  summary: {
    new_notes?: number;
    revisited_notes?: number;
    words_written?: number;
    streak_days?: number;
    bridges_born?: number;
    hubs_born?: number;
    clusters_hot?: number;
    clusters_emerging?: number;
    clusters_dormant?: number;
    synapses_total?: number;
    avg_degree?: number;
  };
};

// ----------------------------------------------------------------- spark

export type SparkKind = "bridge" | "distill" | "counter" | "frontier" | "revive";

export type SparkEvidence = {
  note_id: number;
  title: string;
  snippet: string;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
};

export type SparkPredictedSynapse = {
  note_id: number;
  title: string;
  strength: number;
};

export type Spark = {
  id: string;
  kind: SparkKind;
  priority: number;
  title: string;
  body: string;
  tags: string[];
  rationale: string;
  headline: string;
  cited_evidence: SparkEvidence[];
  predicted_cluster_id: number | null;
  predicted_cluster_name: string | null;
  predicted_cluster_color: string | null;
  predicted_cluster_strength: number;
  predicted_synapses: SparkPredictedSynapse[];
  expected_synapse_count: number;
  bridge_cluster_a_id: number | null;
  bridge_cluster_a_name: string | null;
  bridge_cluster_a_color: string | null;
  bridge_cluster_b_id: number | null;
  bridge_cluster_b_name: string | null;
  bridge_cluster_b_color: string | null;
  bridge_centroid_cosine: number;
};

export type SparkReport = {
  generated_at: string;
  total_notes: number;
  total_clusters: number;
  sparks: Spark[];
  summary: {
    bridge_count?: number;
    distill_count?: number;
    counter_count?: number;
    frontier_count?: number;
    revive_count?: number;
    mean_predicted_synapses?: number;
    highest_priority?: number;
  };
};

// ----------------------------------------------------------------- compass

export type LensNote = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  relevance: number;
  info_gain: number;
  cosine: number;
  lexical: number;
  title_hit: boolean;
  read: boolean;
  read_at: string | null;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
};

export type CompassCitation = {
  ref: number;
  note_id: number;
  title: string;
  excerpt: string;
  relevance: number;
};

export type CompassSubquestion = {
  term: string;
  note_count: number;
  covered: number;
  coverage_pct: number;
  sample_note_id: number;
};

export type CompassLens = {
  question_id: number;
  question_text: string;
  created_at: string;
  archived_at: string | null;
  generated_at: string;
  total_notes: number;
  in_lens: number;
  relevance_mass_total: number;
  relevance_mass_read: number;
  coverage_pct: number;
  notes: LensNote[];
  frontiers: LensNote[];
  subquestions: CompassSubquestion[];
  working_answer: string;
  citations: CompassCitation[];
  stats: {
    total_in_lens?: number;
    read_in_lens?: number;
    top_relevance?: number;
    answered_subquestions?: number;
    frontiers_count?: number;
  };
};

export type CompassQuestionSummary = {
  id: number;
  text: string;
  created_at: string;
  archived_at: string | null;
  reads_count: number;
  last_read_at: string | null;
  coverage_pct: number;
};

// ----------------------------------------------------------------- recall

export type RecallCardKind = "cloze" | "prompt" | "neighbor";

export type RecallNeighborChoice = {
  note_id: number;
  title: string;
  is_correct: boolean;
  cluster_id: number | null;
  cluster_color: string | null;
};

export type RecallCard = {
  id: string;
  kind: RecallCardKind;
  note_id: number;
  title: string;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  prompt_text: string;
  answer_text: string;
  cloze_answer: string;
  body_before: string;
  body_after: string;
  body_snippet: string;
  choices: RecallNeighborChoice[];
  correct_choice_id: number | null;
  ease: number;
  interval_hours: number;
  next_due: string;
  streak: number;
  reviews: number;
  lapses: number;
  days_overdue: number;
  days_since_seen: number | null;
  reasons: string[];
};

export type RecallSession = {
  generated_at: string;
  session_id: string;
  total_notes: number;
  eligible_notes: number;
  k: number;
  cards: RecallCard[];
  streak_days: number;
  due_now: number;
  stats: {
    reviewed_notes?: number;
    mean_ease?: number;
    cloze_count?: number;
    prompt_count?: number;
    neighbor_count?: number;
  };
};

export type RecallGrade = 0 | 1 | 2 | 3;

export type RecallGradeResult = {
  note_id: number;
  grade: number;
  ease: number;
  interval_hours: number;
  next_due: string;
  streak: number;
  reviews: number;
  lapses: number;
  next_due_phrase: string;
};

export type RecallClusterMastery = {
  cluster_id: number;
  cluster_name: string;
  cluster_color: string;
  size: number;
  reviewed: number;
  known: number;
  mastery: number;
  mean_ease: number;
  due_now: number;
};

export type RecallSummary = {
  generated_at: string;
  total_notes: number;
  reviewed_notes: number;
  due_now: number;
  streak_days: number;
  mean_ease: number;
  total_reviews: number;
  mastery_overall: number;
  clusters: RecallClusterMastery[];
};

export type RecallClozeCheck = {
  is_correct: boolean;
  similarity: number;
};

// ----------------------------------------------------------------- signal

export type SignalStatus = "new" | "grown" | "shrunk" | "stable" | "fresh";

export type SignalLensNoteSummary = {
  note_id: number;
  title: string;
  snippet: string;
  relevance: number;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
};

export type SignalCitationDelta = {
  note_id: number;
  title: string;
  excerpt: string;
  relevance: number;
};

export type SignalSubqDelta = {
  term: string;
  note_count_now: number;
  note_count_pinned: number;
  covered_now: number;
  covered_pinned: number;
  coverage_pct_now: number;
  coverage_pct_pinned: number;
  coverage_pct_delta: number;
  sample_note_id: number;
};

export type SignalDelta = {
  question_id: number;
  question_text: string;
  pinned_at: string;
  last_refreshed_at: string | null;
  generated_at: string;
  coverage_now: number;
  coverage_pinned: number;
  coverage_delta: number;
  in_lens_now: number;
  in_lens_pinned: number;
  reads_new_count: number;
  reads_new: SignalLensNoteSummary[];
  joined_since_count: number;
  joined_since: SignalLensNoteSummary[];
  left_since_count: number;
  left_since: SignalLensNoteSummary[];
  citations_added: SignalCitationDelta[];
  citations_removed: SignalCitationDelta[];
  subquestion_progress: SignalSubqDelta[];
  working_answer_changed: boolean;
  working_answer: string;
  status: SignalStatus;
  headline: string;
  stats: {
    joined_ids_count?: number;
    left_ids_count?: number;
    new_reads_count?: number;
    citations_added_count?: number;
    citations_removed_count?: number;
    subquestion_moves?: number;
    top_relevance_now?: number;
  };
};

export type SignalReport = {
  generated_at: string;
  watch_count: number;
  grown_count: number;
  shrunk_count: number;
  stable_count: number;
  new_count: number;
  watches: SignalDelta[];
};

// ---------------------------------------------------------------- vault

export type VaultStats = {
  notes: number;
  trails: number;
  questions: number;
  watches: number;
  snapshots: number;
  engine: string;
  schema_version: number;
};

export type VaultImportSummary = {
  mode: string;
  dry_run: boolean;
  notes_created: number;
  notes_updated: number;
  notes_skipped: number;
  notes_removed: number;
  trails_imported: number;
  compass_imported: number;
  signal_imported: number;
  embeddings_restored: number;
  warnings: string[];
  total_incoming_notes: number;
};

export type VaultSnapshot = {
  id: number;
  label: string;
  created_at: string;
  note_count: number;
  size_bytes: number;
};

export type VaultImportMode = "merge" | "replace" | "preview";

// ---------------------------------------------------------------- prism

export type PrismLensId =
  | "skeptic"
  | "empiricist"
  | "historian"
  | "futurist"
  | "practitioner"
  | "contrarian"
  | "systems"
  | "first_principles";

export type PrismLensFamily = "critical" | "empirical" | "narrative" | "generative";

export type PrismStance = "reinforce" | "challenge" | "neutral" | "thin";

export type PrismLensSpec = {
  id: PrismLensId;
  label: string;
  color: string; // css color name (rose, sky, amber, violet, emerald, fuchsia, cyan, lime)
  icon: string;
  tagline: string;
  family: PrismLensFamily;
  vocab_size: number;
};

export type PrismPick = {
  note_id: number;
  title: string;
  cluster_id?: number | null;
  cluster_color?: string | null;
  similarity: number;
  lexicon_score: number;
  score: number;
  quote: string;
  tags: string[];
  is_top: boolean;
};

export type PrismLensResult = {
  id: PrismLensId;
  label: string;
  color: string;
  icon: string;
  tagline: string;
  family: PrismLensFamily;
  coverage: number;
  stance: PrismStance;
  weakness: string | null;
  picks: PrismPick[];
};

export type PrismTargetKind = "note" | "cluster" | "query";

export type PrismTarget = {
  kind: PrismTargetKind;
  id: number | null;
  label: string;
  excerpt: string;
  cluster_id?: number | null;
  cluster_color?: string | null;
};

export type PrismReport = {
  target: PrismTarget;
  lenses: PrismLensResult[];
  weakest_lens: PrismLensId | null;
  strongest_lens: PrismLensId | null;
  stance_distribution: Record<PrismStance, number>;
  dominant_family: PrismLensFamily | null;
  spark_suggestion: string | null;
  prism_id: string;
  config: Record<string, unknown>;
  stats: Record<string, number>;
};

export type PrismComputeInput = {
  target_kind: PrismTargetKind;
  target_id?: number | null;
  query?: string | null;
  top_k_per_lens?: number;
  floor_sim?: number;
  lens_ids?: PrismLensId[] | null;
};
