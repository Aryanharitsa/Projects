// Small formatters shared by the Compare page and friends.

export function formatLatency(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(2)}s`;
}

export function formatCost(usd) {
  if (usd == null || Number.isNaN(usd)) return '—';
  if (usd === 0) return '$0';
  if (usd < 0.0001) return '<$0.0001';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

export function formatTokens(n) {
  if (n == null) return '—';
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

export function providerColor(provider) {
  const key = (provider || '').toLowerCase();
  if (key.startsWith('open')) return { ring: 'ring-emerald-400/60', bg: 'bg-emerald-500/10', fg: 'text-emerald-600', dot: 'bg-emerald-500' };
  if (key.startsWith('anthrop')) return { ring: 'ring-amber-400/60',   bg: 'bg-amber-500/10',   fg: 'text-amber-700',   dot: 'bg-amber-500' };
  if (key.startsWith('google') || key.startsWith('gemini')) return { ring: 'ring-sky-400/60', bg: 'bg-sky-500/10', fg: 'text-sky-700', dot: 'bg-sky-500' };
  return { ring: 'ring-zinc-400/60', bg: 'bg-zinc-500/10', fg: 'text-zinc-700', dot: 'bg-zinc-500' };
}
