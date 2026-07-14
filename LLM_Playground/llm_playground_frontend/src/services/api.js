// API service for connecting to the Flask backend
const API_BASE_URL = 'http://localhost:5050/api';

class ApiService {
  async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || 'API request failed');
      }
      
      return data;
    } catch (error) {
      console.error('API request error:', error);
      throw error;
    }
  }

  // Get available providers
  async getProviders() {
    return this.request('/providers');
  }

  // Get models for a specific provider
  async getModels(provider) {
    const res = await this.request(`/models/${provider}`);
    return res.models || [];
  }

  // Get parameters for a specific provider
  async getParameters(provider) {
    return this.request(`/parameters/${provider}`);
  }

  // Send chat request and extract debug_info
  async sendChat(chatData) {
    // Send request to backend
    const data = await this.request('/chat', {
      method: 'POST',
      body: JSON.stringify(chatData),
    });
    console.log('[ApiService] raw /chat payload:', data);

    // If the backend returned structured debug_info, use it directly
    const dbg = data.debug_info || {};
    const inputTokens  = dbg.input_tokens  ?? 0;
    const outputTokens = dbg.output_tokens ?? 0;
    const totalTokens  = dbg.total_tokens  ?? (inputTokens + outputTokens);
    const latency      = dbg.latency       ?? null;
    const requestId    = dbg.id            ?? dbg.request_id ?? '';
    const timeStamp    = dbg.timestamp     ?? new Date().toISOString();

    const isAugust = chatData.pkey != null;

    // Return assistant content and structured debug info
    return {
      success: data.success ?? true,
      content: data.response,
      debug_info: {
        provider:      dbg.provider     ?? chatData.provider,
        model:         dbg.model        ?? chatData.model,
        // August mode fields
        ...(isAugust && {
          pkey:        chatData.pkey,
          pvariables:  chatData.pvariables
        }),
        input_tokens:  inputTokens,
        output_tokens: outputTokens,
        total_tokens:  totalTokens,
        latency:       latency,
        id:            requestId,
        status:        dbg.status       ?? 'success',
        timestamp:     timeStamp,
        model_version: dbg.model_version ?? chatData.model
      }
    };
  }

  // Run the same prompt against N {provider, model} candidates in parallel.
  // Returns { success, results: [...], winners: { fastest, cheapest, most_verbose }, wall_latency }.
  async compare(payload) {
    return this.request('/compare', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // Published per-1M-token pricing for each supported model family.
  async getPricing() {
    const res = await this.request('/pricing');
    return res.pricing || {};
  }

  // Default LLM-as-judge rubric (criteria + weights).
  async getRubric() {
    const res = await this.request('/rubric');
    return res.rubric || [];
  }

  // Score a finished Arena run with an LLM judge.
  // Payload: { prompt, system_prompt, candidates:[{provider,model,response,status}],
  //            judge:{provider,model}, rubric:[{name,description,weight}] }
  async judge(payload) {
    return this.request('/judge', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // Score a finished Arena run with a *panel* of K judges in parallel.
  // Returns a consensus leaderboard with mean ± std composites, inter-judge
  // agreement (Fleiss' kappa per criterion + overall), and per-judge breakdown.
  // Payload: { prompt, system_prompt, candidates:[...],
  //            judges:[{provider,model}, ...], rubric:[...], run_id? }
  async judgeConsensus(payload) {
    return this.request('/judge/consensus', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Run History ──────────────────────────────────────────────────────────
  // Every Arena run is auto-persisted server-side; these endpoints power the
  // History tab (list / detail / tag / star / delete / stats / diff).

  // List runs with optional filter object: { q, model, provider, judged,
  // starred, tag, since, before, limit, offset } — all keys are optional.
  async listHistory(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '' || v === false) return;
      qs.set(k, v === true ? '1' : String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/history${suffix}`);
  }

  async getRun(runId) {
    return this.request(`/history/${encodeURIComponent(runId)}`);
  }

  async deleteRun(runId) {
    return this.request(`/history/${encodeURIComponent(runId)}`, { method: 'DELETE' });
  }

  async setRunMeta(runId, meta) {
    return this.request(`/history/${encodeURIComponent(runId)}/meta`, {
      method: 'POST',
      body: JSON.stringify(meta),
    });
  }

  async historyStats() {
    return this.request('/history/stats');
  }

  async diffRuns(a, b) {
    return this.request('/history/diff', {
      method: 'POST',
      body: JSON.stringify({ a, b }),
    });
  }

  // ─── Personal Chatbot Arena ───────────────────────────────────────────────
  // Blind A/B voting → ELO leaderboard. Pairs are sampled from the persisted
  // run history, votes feed an ELO replay, and judge-vs-human agreement is
  // surfaced server-side from the same vote log.

  // Sample a blind pair. `runId` deeplinks to a specific run; otherwise the
  // sampler walks recent runs and biases toward under-played pairings.
  async arenaPair({ runId, excludeA, excludeB } = {}) {
    const qs = new URLSearchParams();
    if (runId)    qs.set('run_id', runId);
    if (excludeA) qs.set('exclude_a', excludeA);
    if (excludeB) qs.set('exclude_b', excludeB);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/arena/pair${suffix}`);
  }

  async arenaVote(payload) {
    return this.request('/arena/vote', { method: 'POST', body: JSON.stringify(payload) });
  }

  async arenaUndo(voteId) {
    return this.request(`/arena/vote/${encodeURIComponent(voteId)}`, { method: 'DELETE' });
  }

  async arenaLeaderboard({ k, prior, since, minGames } = {}) {
    const qs = new URLSearchParams();
    if (k != null)     qs.set('k', k);
    if (prior != null) qs.set('prior', prior);
    if (since != null) qs.set('since', since);
    if (minGames)      qs.set('min_games', minGames);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/arena/leaderboard${suffix}`);
  }

  async arenaMatrix({ topN = 8 } = {}) {
    return this.request(`/arena/matrix?top_n=${topN}`);
  }

  async arenaAgreement({ minVotes = 1 } = {}) {
    return this.request(`/arena/agreement?min_votes=${minVotes}`);
  }

  async arenaRecent({ limit = 20 } = {}) {
    return this.request(`/arena/recent?limit=${limit}`);
  }

  async arenaStats() {
    return this.request('/arena/stats');
  }

  // ─── Prompt Library ──────────────────────────────────────────────────────
  // Versioned prompts linked back to Arena runs. Each prompt has a chain of
  // versions; running a version from Arena attaches the resulting run to it.

  async listPrompts(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '' || v === false) return;
      qs.set(k, v === true ? '1' : String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/prompts${suffix}`);
  }

  async createPrompt(payload) {
    return this.request('/prompts', { method: 'POST', body: JSON.stringify(payload) });
  }

  async getPrompt(promptId) {
    return this.request(`/prompts/${encodeURIComponent(promptId)}`);
  }

  async deletePrompt(promptId) {
    return this.request(`/prompts/${encodeURIComponent(promptId)}`, { method: 'DELETE' });
  }

  async setPromptMeta(promptId, meta) {
    return this.request(`/prompts/${encodeURIComponent(promptId)}/meta`, {
      method: 'POST',
      body: JSON.stringify(meta),
    });
  }

  async addPromptVersion(promptId, payload) {
    return this.request(`/prompts/${encodeURIComponent(promptId)}/versions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async diffPromptVersions(a, b) {
    return this.request('/prompts/diff', {
      method: 'POST',
      body: JSON.stringify({ a, b }),
    });
  }

  async promptStats() {
    return this.request('/prompts/stats');
  }

  async runsForVersion(promptId, versionId, { limit = 50 } = {}) {
    return this.request(
      `/prompts/${encodeURIComponent(promptId)}/versions/${encodeURIComponent(versionId)}/runs?limit=${limit}`
    );
  }

  // ─── Eval Suites ───────────────────────────────────────────────────────────
  // Reproducible test batteries — define a fixed list of cases, fan them out
  // against any model, watch pass-rate + judge composite move when you change
  // the prompt or swap the model. Round-8 move.

  async listSuites(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '' || v === false) return;
      qs.set(k, v === true ? '1' : String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/suites${suffix}`);
  }

  async createSuite(payload) {
    return this.request('/suites', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedSmokeSuite() {
    return this.request('/suites/seed', { method: 'POST' });
  }

  async getSuite(suiteId) {
    return this.request(`/suites/${encodeURIComponent(suiteId)}`);
  }

  async deleteSuite(suiteId) {
    return this.request(`/suites/${encodeURIComponent(suiteId)}`, { method: 'DELETE' });
  }

  async setSuiteMeta(suiteId, meta) {
    return this.request(`/suites/${encodeURIComponent(suiteId)}/meta`, {
      method: 'POST',
      body: JSON.stringify(meta),
    });
  }

  async addSuiteCase(suiteId, payload) {
    return this.request(`/suites/${encodeURIComponent(suiteId)}/cases`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async updateSuiteCase(suiteId, caseId, payload) {
    return this.request(
      `/suites/${encodeURIComponent(suiteId)}/cases/${encodeURIComponent(caseId)}`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  }

  async deleteSuiteCase(suiteId, caseId) {
    return this.request(
      `/suites/${encodeURIComponent(suiteId)}/cases/${encodeURIComponent(caseId)}`,
      { method: 'DELETE' },
    );
  }

  async runSuite(suiteId, payload) {
    return this.request(`/suites/${encodeURIComponent(suiteId)}/runs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async listSuiteRuns(suiteId, { limit = 50, offset = 0 } = {}) {
    const qs = new URLSearchParams();
    if (limit) qs.set('limit', limit);
    if (offset) qs.set('offset', offset);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/suites/${encodeURIComponent(suiteId)}/runs${suffix}`);
  }

  async getSuiteRun(runId) {
    return this.request(`/suites/runs/${encodeURIComponent(runId)}`);
  }

  async deleteSuiteRun(runId) {
    return this.request(`/suites/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' });
  }

  async compareSuiteRuns(a, b) {
    return this.request('/suites/runs/compare', {
      method: 'POST',
      body: JSON.stringify({ a, b }),
    });
  }

  async suitesStats() {
    return this.request('/suites/stats');
  }

  // ─── Rubrics Studio ────────────────────────────────────────────────────────
  // First-class versioned judge rubrics: anchor-driven dimensions, per-dim
  // scores + rationales, weighted composite computed server-side. Round-9.

  async listRubrics(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '' || v === false) return;
      qs.set(k, v === true ? '1' : String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/rubrics${suffix}`);
  }

  async createRubric(payload) {
    return this.request('/rubrics', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedRubrics() {
    return this.request('/rubrics/seed', { method: 'POST' });
  }

  async rubricsStats() {
    return this.request('/rubrics/stats');
  }

  async getRubric(rubricId) {
    return this.request(`/rubrics/${encodeURIComponent(rubricId)}`);
  }

  async deleteRubric(rubricId) {
    return this.request(`/rubrics/${encodeURIComponent(rubricId)}`, { method: 'DELETE' });
  }

  async setRubricMeta(rubricId, meta) {
    return this.request(`/rubrics/${encodeURIComponent(rubricId)}/meta`, {
      method: 'POST',
      body: JSON.stringify(meta),
    });
  }

  async saveRubricRevision(rubricId, payload) {
    return this.request(`/rubrics/${encodeURIComponent(rubricId)}/revisions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async restoreRubricRevision(rubricId, revisionNum, payload = {}) {
    return this.request(
      `/rubrics/${encodeURIComponent(rubricId)}/revisions/${encodeURIComponent(revisionNum)}/restore`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  }

  async testRubric(rubricId, payload) {
    return this.request(`/rubrics/${encodeURIComponent(rubricId)}/test`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async listRubricJudgements(rubricId, { limit = 50, offset = 0 } = {}) {
    const qs = new URLSearchParams();
    if (limit) qs.set('limit', limit);
    if (offset) qs.set('offset', offset);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/rubrics/${encodeURIComponent(rubricId)}/judgements${suffix}`);
  }

  async deleteRubricJudgement(judgementId) {
    return this.request(`/rubrics/judgements/${encodeURIComponent(judgementId)}`, {
      method: 'DELETE',
    });
  }

  // ─── Optimizer Studio ──────────────────────────────────────────────────────
  // Automated prompt evolution against a Rubrics rubric. Each generation
  // mutates the elites + base prompt, scores every variant on every test
  // case, persists the lineage. Round-10.

  async listOptimizations(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/optimize${suffix}`);
  }

  async createOptimization(payload) {
    return this.request('/optimize', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedOptimization() {
    return this.request('/optimize/seed', { method: 'POST' });
  }

  async optimizerStats() {
    return this.request('/optimize/stats');
  }

  async getOptimization(optId) {
    return this.request(`/optimize/${encodeURIComponent(optId)}`);
  }

  async deleteOptimization(optId) {
    return this.request(`/optimize/${encodeURIComponent(optId)}`, { method: 'DELETE' });
  }

  async advanceOptimization(optId) {
    return this.request(`/optimize/${encodeURIComponent(optId)}/advance`, { method: 'POST' });
  }

  async runOptimization(optId, payload = {}) {
    return this.request(`/optimize/${encodeURIComponent(optId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async promoteVariant(optId, variantId) {
    return this.request(
      `/optimize/${encodeURIComponent(optId)}/promote/${encodeURIComponent(variantId)}`,
      { method: 'POST' },
    );
  }

  async optimizerMutations() {
    return this.request('/optimize/mutations');
  }

  async optimizerPreview(payload) {
    return this.request('/optimize/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Adversary Lab ─────────────────────────────────────────────────────────
  // Prompt robustness tester. An audit runs the base prompt against a catalog
  // of perturbations (typographic / structural / distractor / injection) and
  // scores each one against the same rubric the clean baseline used. The
  // composite Robustness score blends a degradation axis (how much the
  // composite drops under noise) with a safety axis (what fraction of
  // injection vectors leak a marker). Round-11.

  async listAudits(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/adversary${suffix}`);
  }

  async createAudit(payload) {
    return this.request('/adversary', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedAudit() {
    return this.request('/adversary/seed', { method: 'POST' });
  }

  async adversaryStats() {
    return this.request('/adversary/stats');
  }

  async getAudit(auditId) {
    return this.request(`/adversary/${encodeURIComponent(auditId)}`);
  }

  async deleteAudit(auditId) {
    return this.request(`/adversary/${encodeURIComponent(auditId)}`, { method: 'DELETE' });
  }

  async runAudit(auditId, payload = {}) {
    return this.request(`/adversary/${encodeURIComponent(auditId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async adversaryPerturbations() {
    return this.request('/adversary/perturbations');
  }

  async adversaryPreview(payload) {
    return this.request('/adversary/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Showdown Arena ────────────────────────────────────────────────────────
  // Paired A/B test of two prompts ("Champion" vs "Challenger") across a
  // shared set of test cases. Surfaces mean Δ, 95% bootstrap CI, sign-test
  // p-value, Cohen's d, win rate, and a ship/keep/no-decision verdict.
  // Round-13.

  async listShowdowns(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/showdown${suffix}`);
  }

  async createShowdown(payload) {
    return this.request('/showdown', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedShowdown() {
    return this.request('/showdown/seed', { method: 'POST' });
  }

  async showdownStats() {
    return this.request('/showdown/stats');
  }

  async getShowdown(showdownId) {
    return this.request(`/showdown/${encodeURIComponent(showdownId)}`);
  }

  async deleteShowdown(showdownId) {
    return this.request(`/showdown/${encodeURIComponent(showdownId)}`, { method: 'DELETE' });
  }

  async runShowdown(showdownId, payload = {}) {
    return this.request(`/showdown/${encodeURIComponent(showdownId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Drift Lab ─────────────────────────────────────────────────────────────
  // Output stability tester. Replays the same prompt against the same model
  // N times and rolls the bag into a composite Stability Score (lexical +
  // length + latency axes) plus a pairwise similarity matrix, cluster
  // summary, medoid pick, and variance-type verdict. Round-14.

  async listDrifts(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/drift${suffix}`);
  }

  async createDrift(payload) {
    return this.request('/drift', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedDrift() {
    return this.request('/drift/seed', { method: 'POST' });
  }

  async driftStats() {
    return this.request('/drift/stats');
  }

  async driftDefaults() {
    return this.request('/drift/defaults');
  }

  async getDrift(driftId) {
    return this.request(`/drift/${encodeURIComponent(driftId)}`);
  }

  async deleteDrift(driftId) {
    return this.request(`/drift/${encodeURIComponent(driftId)}`, { method: 'DELETE' });
  }

  async runDrift(driftId, payload = {}) {
    return this.request(`/drift/${encodeURIComponent(driftId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Prompt Surgeon ────────────────────────────────────────────────────────
  // Section-level ablation & attribution. Parses a prompt into sections,
  // ablates each one, and bands every section as critical / supporting /
  // dead-weight / harmful — then ships a trimmed "lean" prompt + dollar
  // savings projection. Round-15.

  async listSurgeons(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/surgeon${suffix}`);
  }

  async createSurgeon(payload) {
    return this.request('/surgeon', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedSurgeon() {
    return this.request('/surgeon/seed', { method: 'POST' });
  }

  async surgeonStats() {
    return this.request('/surgeon/stats');
  }

  async surgeonDefaults() {
    return this.request('/surgeon/defaults');
  }

  async surgeonParse(systemPrompt) {
    return this.request('/surgeon/parse', {
      method: 'POST',
      body: JSON.stringify({ system_prompt: systemPrompt || '' }),
    });
  }

  async getSurgeon(surgeonId) {
    return this.request(`/surgeon/${encodeURIComponent(surgeonId)}`);
  }

  async deleteSurgeon(surgeonId) {
    return this.request(`/surgeon/${encodeURIComponent(surgeonId)}`, { method: 'DELETE' });
  }

  async runSurgeon(surgeonId, payload = {}) {
    return this.request(`/surgeon/${encodeURIComponent(surgeonId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Frontier — Cost/Quality Pareto Explorer ──────────────────────────────
  // Round-16. For a prompt + candidate roster, computes each model's
  // quality vs cost, keeps the Pareto-frontier set, and kneedles the
  // elbow. Returns default / quality-floor / budget-ceiling picks so
  // "which model do I ship?" has a data-backed answer.

  async listFrontiers(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/frontier${suffix}`);
  }

  async createFrontier(payload) {
    return this.request('/frontier', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedFrontier() {
    return this.request('/frontier/seed', { method: 'POST' });
  }

  async frontierStats() {
    return this.request('/frontier/stats');
  }

  async frontierDefaults() {
    return this.request('/frontier/defaults');
  }

  async getFrontier(frontierId) {
    return this.request(`/frontier/${encodeURIComponent(frontierId)}`);
  }

  async deleteFrontier(frontierId) {
    return this.request(`/frontier/${encodeURIComponent(frontierId)}`, { method: 'DELETE' });
  }

  async runFrontier(frontierId, payload = {}) {
    return this.request(`/frontier/${encodeURIComponent(frontierId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async recommendFrontier(frontierId, payload = {}) {
    return this.request(`/frontier/${encodeURIComponent(frontierId)}/recommend`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Studio Relay — Cascade Router Designer ────────────────────────────
  // Given a prompt + a cost-ordered roster + a gate rule, Relay simulates a
  // cheap→expensive cascade: how much traffic terminates at each level, the
  // expected cost / quality / latency, and three recommended shapes
  // (balanced, cost_min, latency_capped).
  async listRelays(filters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/relay${suffix}`);
  }

  async createRelay(payload) {
    return this.request('/relay', { method: 'POST', body: JSON.stringify(payload) });
  }

  async seedRelay() {
    return this.request('/relay/seed', { method: 'POST' });
  }

  async relayStats() {
    return this.request('/relay/stats');
  }

  async relayDefaults() {
    return this.request('/relay/defaults');
  }

  async getRelay(relayId) {
    return this.request(`/relay/${encodeURIComponent(relayId)}`);
  }

  async deleteRelay(relayId) {
    return this.request(`/relay/${encodeURIComponent(relayId)}`, { method: 'DELETE' });
  }

  async runRelay(relayId, payload = {}) {
    return this.request(`/relay/${encodeURIComponent(relayId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async previewRelay(relayId, payload = {}) {
    return this.request(`/relay/${encodeURIComponent(relayId)}/preview`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ─── Studio Sentinel — Prompt Injection Defense (Day 83) ───────────────────
  // Deterministic engine — every response is a pure function of the request.
  // No persistence, no keys required; the demo lights up on first load.
  async sentinelDefaults() {
    return this.request('/sentinel/defaults');
  }
  async sentinelAttacks() {
    return this.request('/sentinel/attacks');
  }
  async sentinelDefenses() {
    return this.request('/sentinel/defenses');
  }
  async sentinelScan(input) {
    return this.request('/sentinel/scan', {
      method: 'POST',
      body: JSON.stringify({ input }),
    });
  }
  async sentinelMatrix(defenseIds = null) {
    return this.request('/sentinel/matrix', {
      method: 'POST',
      body: JSON.stringify(defenseIds ? { defense_ids: defenseIds } : {}),
    });
  }
  async sentinelSimulate(payload) {
    return this.request('/sentinel/simulate', {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
  }
  async sentinelSuggest(payload = {}) {
    return this.request('/sentinel/suggest', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }
  async sentinelCompile(payload) {
    return this.request('/sentinel/compile', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }
  async sentinelSeed() {
    return this.request('/sentinel/seed');
  }

  // ─── Studio Insights ───────────────────────────────────────────────────────
  // Cross-cutting analytics over the whole run history: model scorecards, the
  // quality/cost efficiency frontier, spend timeline, and provider roll-up.
  async insights({ minAppearances = 1 } = {}) {
    const qs = new URLSearchParams();
    if (minAppearances && minAppearances > 1) qs.set('min_appearances', minAppearances);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/insights${suffix}`);
  }

  // Upload August JSON file
  async uploadAugustJson(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    return this.request('/august/upload', {
      method: 'POST',
      headers: {}, // Remove Content-Type to let browser set it for FormData
      body: formData,
    });
  }

  // Export chat data
  async exportChat(chatData) {
    return this.request('/export', {
      method: 'POST',
      body: JSON.stringify(chatData),
    });
  }

  // Health check
  async healthCheck() {
    return this.request('/health');
  }

  // Get masked key status and "active" flag for all API keys
  async getKeyStatus() {
    return this.request('/key-status');
  }

  // Save updated API keys (object: {OPENAI_API_KEY, GEMINI_API_KEY, ...})
  async saveKeys(keysObj) {
    return this.request('/save-keys', {
      method: 'POST',
      body: JSON.stringify(keysObj),
    });
  }
}

export default new ApiService();
