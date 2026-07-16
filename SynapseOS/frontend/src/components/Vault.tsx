"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  VaultImportMode,
  VaultImportSummary,
  VaultSnapshot,
  VaultStats,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Called after any state-changing operation (import, restore, snapshot
   *  create) so the page can re-fetch the graph + counts. */
  onMutated?: () => void;
};

type Tab = "export" | "import" | "snapshots";

/**
 * Vault — portable import/export + local snapshots.
 *
 * Three tabs, one honest goal: your notes belong to you.
 *   - Export downloads the whole vault as JSON or a Markdown ZIP.
 *   - Import round-trips either format back, with a preview step and
 *     a hard confirmation for the destructive "replace" mode.
 *   - Snapshots are the personal Ctrl-Z: freeze a labelled JSON copy
 *     of your vault, roll back to it in one click.
 *
 * The panel is intentionally boring visually — every other surface in
 * this app is a hosted read; Vault is a *disk operation*, and the
 * confidence signal users need is "I can see what's about to happen."
 * That's why the import path forces a preview before the mutation.
 */
export function Vault({ open, onClose, onMutated }: Props) {
  const [tab, setTab] = useState<Tab>("export");
  const [stats, setStats] = useState<VaultStats | null>(null);

  // Export tab
  const [inclEmbeddings, setInclEmbeddings] = useState(true);
  const [inclTrails, setInclTrails] = useState(true);
  const [inclCompass, setInclCompass] = useState(true);
  const [inclSignal, setInclSignal] = useState(true);

  // Import tab
  const [importPayload, setImportPayload] = useState<unknown | null>(null);
  const [importSourceLabel, setImportSourceLabel] = useState<string | null>(null);
  const [importPreview, setImportPreview] = useState<VaultImportSummary | null>(null);
  const [importMode, setImportMode] = useState<Exclude<VaultImportMode, "preview">>("merge");
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState<VaultImportSummary | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Snapshots tab
  const [snapshots, setSnapshots] = useState<VaultSnapshot[]>([]);
  const [newLabel, setNewLabel] = useState("");
  const [busyRow, setBusyRow] = useState<number | null>(null);
  const [snapError, setSnapError] = useState<string | null>(null);

  const refreshStats = useCallback(async () => {
    try {
      const s = await api.vaultStats();
      setStats(s);
    } catch {
      // non-fatal: modal can render with placeholder counts
    }
  }, []);

  const refreshSnapshots = useCallback(async () => {
    try {
      const rows = await api.vaultSnapshots();
      setSnapshots(rows);
    } catch {
      setSnapshots([]);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    refreshStats();
    refreshSnapshots();
  }, [open, refreshStats, refreshSnapshots]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const clearImport = useCallback(() => {
    setImportPayload(null);
    setImportSourceLabel(null);
    setImportPreview(null);
    setImportResult(null);
    setImportError(null);
    setConfirmReplace(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const parseFile = useCallback(async (file: File) => {
    clearImport();
    setImportBusy(true);
    setImportError(null);
    try {
      if (file.name.toLowerCase().endsWith(".zip")) {
        // Client-side ZIP → find _manifest.json inside for a lossless
        // import path. The .md files carry titles/bodies but not the
        // trails/compass/signal state, so we prefer the manifest when
        // present. If the ZIP has no manifest, we fall back to error
        // and let the user try /vault/export.json instead.
        const buf = await file.arrayBuffer();
        const manifest = await extractManifestFromZip(buf);
        if (!manifest) {
          throw new Error(
            "ZIP has no _manifest.json — use the JSON export for round-trip import, or import Markdown files individually via CLI.",
          );
        }
        // Re-hydrate note bodies from the .md files inside the ZIP so a
        // ZIP import restores everything (manifest strips bodies).
        const bodies = await extractBodiesFromZip(buf);
        const notes = ((manifest as { notes?: unknown[] }).notes || []).map((raw) => {
          const n = raw as Record<string, unknown>;
          const id = Number(n.id ?? 0);
          const body = id && bodies[id] ? bodies[id] : ((n.body as string) || "(no body)");
          return { ...n, body };
        });
        setImportPayload({ ...(manifest as object), notes });
        setImportSourceLabel(`${file.name} · ${Math.round(file.size / 1024)} KB`);
      } else {
        const text = await file.text();
        const parsed = JSON.parse(text);
        setImportPayload(parsed);
        setImportSourceLabel(`${file.name} · ${Math.round(file.size / 1024)} KB`);
      }
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "unreadable file");
    } finally {
      setImportBusy(false);
    }
  }, [clearImport]);

  // Auto-preview once a payload lands
  useEffect(() => {
    if (!importPayload) {
      setImportPreview(null);
      return;
    }
    setImportBusy(true);
    api
      .vaultPreview(importPayload)
      .then((p) => setImportPreview(p))
      .catch((e) => setImportError(e instanceof Error ? e.message : "preview failed"))
      .finally(() => setImportBusy(false));
  }, [importPayload]);

  const doImport = useCallback(async () => {
    if (!importPayload) return;
    if (importMode === "replace" && !confirmReplace) {
      setConfirmReplace(true);
      return;
    }
    setImportBusy(true);
    setImportError(null);
    try {
      const summary = await api.vaultImport(importMode, importPayload);
      setImportResult(summary);
      onMutated?.();
      refreshStats();
      refreshSnapshots();
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "import failed");
    } finally {
      setImportBusy(false);
      setConfirmReplace(false);
    }
  }, [importPayload, importMode, confirmReplace, onMutated, refreshStats, refreshSnapshots]);

  const createSnap = useCallback(async () => {
    const label = newLabel.trim();
    if (!label) return;
    setSnapError(null);
    try {
      await api.vaultCreateSnapshot(label);
      setNewLabel("");
      await refreshSnapshots();
    } catch (e) {
      setSnapError(e instanceof Error ? e.message : "snapshot create failed");
    }
  }, [newLabel, refreshSnapshots]);

  const restoreSnap = useCallback(async (id: number, label: string) => {
    if (!window.confirm(`Restore snapshot "${label}"? This wipes the current vault and replaces it with the frozen copy.`)) return;
    setBusyRow(id);
    setSnapError(null);
    try {
      await api.vaultRestoreSnapshot(id);
      onMutated?.();
      refreshStats();
    } catch (e) {
      setSnapError(e instanceof Error ? e.message : "restore failed");
    } finally {
      setBusyRow(null);
    }
  }, [onMutated, refreshStats]);

  const deleteSnap = useCallback(async (id: number, label: string) => {
    if (!window.confirm(`Delete snapshot "${label}"? This cannot be undone.`)) return;
    setBusyRow(id);
    setSnapError(null);
    try {
      await api.vaultDeleteSnapshot(id);
      await refreshSnapshots();
    } catch (e) {
      setSnapError(e instanceof Error ? e.message : "delete failed");
    } finally {
      setBusyRow(null);
    }
  }, [refreshSnapshots]);

  const exportJsonUrl = useMemo(
    () => api.vaultExportJsonUrl({
      includeEmbeddings: inclEmbeddings,
      includeCompassReads: inclCompass,
      includeTrails: inclTrails,
      includeSignal: inclSignal,
    }),
    [inclEmbeddings, inclCompass, inclTrails, inclSignal],
  );
  const exportZipUrl = useMemo(
    () => api.vaultExportZipUrl({
      includeEmbeddings: inclEmbeddings,
      includeCompassReads: inclCompass,
      includeTrails: inclTrails,
      includeSignal: inclSignal,
    }),
    [inclEmbeddings, inclCompass, inclTrails, inclSignal],
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 backdrop-blur-sm p-6">
      <div className="relative w-full max-w-4xl my-6 rounded-2xl bg-gradient-to-br from-ink-800/95 via-ink-800/90 to-ink-900/95 ring-1 ring-white/10 shadow-2xl overflow-hidden">
        {/* radial accent */}
        <div
          className="absolute inset-0 pointer-events-none opacity-40"
          style={{
            background:
              "radial-gradient(600px 260px at 12% 0%, rgba(163,230,53,0.10), transparent 60%), radial-gradient(700px 300px at 90% 20%, rgba(168,85,247,0.10), transparent 65%)",
          }}
        />
        <div className="relative flex items-center justify-between px-6 pt-6 pb-4 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-synapse-lime/30 to-synapse-violet/30 ring-1 ring-white/10 flex items-center justify-center text-lg" aria-hidden>📦</div>
            <div>
              <div className="text-base font-semibold text-ink-100">Vault</div>
              <div className="text-[11px] text-ink-300 uppercase tracking-[0.18em]">portable · yours · reversible</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {stats && (
              <div className="hidden md:flex items-center gap-2 text-[11px] font-mono text-ink-300">
                <StatChip label="notes" value={stats.notes} />
                <StatChip label="trails" value={stats.trails} />
                <StatChip label="questions" value={stats.questions} />
                <StatChip label="watches" value={stats.watches} />
                <StatChip label="snapshots" value={stats.snapshots} tone="lime" />
              </div>
            )}
            <button
              onClick={onClose}
              className="text-ink-300 hover:text-ink-100 text-xl leading-none px-2"
              aria-label="close vault"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="relative px-6 pt-4 flex items-center gap-2">
          {(["export", "import", "snapshots"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-[12px] font-mono uppercase tracking-[0.14em] px-3 py-1.5 rounded-full transition ring-1 ${
                tab === t
                  ? "bg-white/8 ring-white/20 text-ink-100"
                  : "bg-white/[0.02] ring-white/8 text-ink-300 hover:text-ink-100 hover:ring-white/20"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="relative px-6 py-6 min-h-[420px]">
          {tab === "export" && (
            <ExportTab
              stats={stats}
              inclEmbeddings={inclEmbeddings}
              inclTrails={inclTrails}
              inclCompass={inclCompass}
              inclSignal={inclSignal}
              onToggleEmbeddings={() => setInclEmbeddings((v) => !v)}
              onToggleTrails={() => setInclTrails((v) => !v)}
              onToggleCompass={() => setInclCompass((v) => !v)}
              onToggleSignal={() => setInclSignal((v) => !v)}
              exportJsonUrl={exportJsonUrl}
              exportZipUrl={exportZipUrl}
            />
          )}

          {tab === "import" && (
            <ImportTab
              importPayload={importPayload}
              importSourceLabel={importSourceLabel}
              importPreview={importPreview}
              importMode={importMode}
              onModeChange={setImportMode}
              importBusy={importBusy}
              importResult={importResult}
              importError={importError}
              confirmReplace={confirmReplace}
              onCancelConfirm={() => setConfirmReplace(false)}
              onClear={clearImport}
              onFile={parseFile}
              onImport={doImport}
              fileInputRef={fileInputRef}
            />
          )}

          {tab === "snapshots" && (
            <SnapshotsTab
              snapshots={snapshots}
              newLabel={newLabel}
              onLabelChange={setNewLabel}
              onCreate={createSnap}
              onRestore={restoreSnap}
              onDelete={deleteSnap}
              busyRow={busyRow}
              error={snapError}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- tabs

function ExportTab({
  stats,
  inclEmbeddings,
  inclTrails,
  inclCompass,
  inclSignal,
  onToggleEmbeddings,
  onToggleTrails,
  onToggleCompass,
  onToggleSignal,
  exportJsonUrl,
  exportZipUrl,
}: {
  stats: VaultStats | null;
  inclEmbeddings: boolean;
  inclTrails: boolean;
  inclCompass: boolean;
  inclSignal: boolean;
  onToggleEmbeddings: () => void;
  onToggleTrails: () => void;
  onToggleCompass: () => void;
  onToggleSignal: () => void;
  exportJsonUrl: string;
  exportZipUrl: string;
}) {
  return (
    <div className="grid gap-6">
      <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/8 p-4">
        <div className="text-[11px] font-mono uppercase tracking-widest text-ink-300 mb-2">what&apos;s inside</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile label="notes" value={stats?.notes ?? "—"} tone="violet" />
          <StatTile label="trails" value={stats?.trails ?? "—"} tone="cyan" />
          <StatTile label="questions" value={stats?.questions ?? "—"} tone="pink" />
          <StatTile label="watches" value={stats?.watches ?? "—"} tone="lime" />
        </div>
        <div className="mt-3 text-[11px] font-mono text-ink-300">
          engine: <span className="text-ink-100">{stats?.engine ?? "…"}</span>
          {" · "}schema v{stats?.schema_version ?? "?"}
        </div>
      </div>

      <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/8 p-4">
        <div className="text-[11px] font-mono uppercase tracking-widest text-ink-300 mb-3">include</div>
        <div className="grid grid-cols-2 gap-2">
          <ToggleRow
            label="embeddings"
            hint="lossless synapse rebuild — needed for offline restore"
            on={inclEmbeddings}
            onToggle={onToggleEmbeddings}
          />
          <ToggleRow
            label="trails"
            hint="curated walks through the graph"
            on={inclTrails}
            onToggle={onToggleTrails}
          />
          <ToggleRow
            label="compass reads"
            hint="per-question read state + questions"
            on={inclCompass}
            onToggle={onToggleCompass}
          />
          <ToggleRow
            label="signal watches"
            hint="pinned Compass snapshots"
            on={inclSignal}
            onToggle={onToggleSignal}
          />
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <a
          href={exportJsonUrl}
          className="group rounded-xl p-5 bg-gradient-to-br from-synapse-violet/25 to-synapse-cyan/20 ring-1 ring-synapse-violet/40 hover:ring-synapse-violet/70 transition"
        >
          <div className="text-[10px] font-mono uppercase tracking-widest text-synapse-violet mb-1">
            format
          </div>
          <div className="text-lg font-semibold text-ink-100">JSON</div>
          <div className="text-[12px] text-ink-300 mt-1">
            One file. Lossless (with embeddings). Round-trips through the import tab.
          </div>
          <div className="mt-4 text-[11px] font-mono text-synapse-violet group-hover:text-ink-100 transition">
            ↓ download
          </div>
        </a>
        <a
          href={exportZipUrl}
          className="group rounded-xl p-5 bg-gradient-to-br from-synapse-lime/20 to-synapse-cyan/15 ring-1 ring-synapse-lime/40 hover:ring-synapse-lime/70 transition"
        >
          <div className="text-[10px] font-mono uppercase tracking-widest text-synapse-lime mb-1">
            format
          </div>
          <div className="text-lg font-semibold text-ink-100">Markdown ZIP</div>
          <div className="text-[12px] text-ink-300 mt-1">
            Per-note ``.md`` files with YAML frontmatter. Opens directly in Obsidian / Logseq.
          </div>
          <div className="mt-4 text-[11px] font-mono text-synapse-lime group-hover:text-ink-100 transition">
            ↓ download
          </div>
        </a>
      </div>
    </div>
  );
}

function ImportTab({
  importPayload,
  importSourceLabel,
  importPreview,
  importMode,
  onModeChange,
  importBusy,
  importResult,
  importError,
  confirmReplace,
  onCancelConfirm,
  onClear,
  onFile,
  onImport,
  fileInputRef,
}: {
  importPayload: unknown | null;
  importSourceLabel: string | null;
  importPreview: VaultImportSummary | null;
  importMode: Exclude<VaultImportMode, "preview">;
  onModeChange: (m: Exclude<VaultImportMode, "preview">) => void;
  importBusy: boolean;
  importResult: VaultImportSummary | null;
  importError: string | null;
  confirmReplace: boolean;
  onCancelConfirm: () => void;
  onClear: () => void;
  onFile: (f: File) => void;
  onImport: () => void;
  fileInputRef: React.MutableRefObject<HTMLInputElement | null>;
}) {
  const [drag, setDrag] = useState(false);
  return (
    <div className="grid gap-6">
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files[0];
          if (f) onFile(f);
        }}
        className={`rounded-xl border border-dashed p-8 text-center transition ${
          drag
            ? "border-synapse-cyan/70 bg-synapse-cyan/[0.06]"
            : "border-white/10 bg-white/[0.02]"
        }`}
      >
        <div className="text-3xl mb-2" aria-hidden>⤴︎</div>
        <div className="text-sm text-ink-100">
          Drop a <code>.json</code> or <code>.md.zip</code> export here
        </div>
        <div className="text-[11px] text-ink-300 mt-1">
          or
        </div>
        <div className="mt-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,.zip,application/json,application/zip"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
            }}
            className="hidden"
            id="vault-import-file"
          />
          <label
            htmlFor="vault-import-file"
            className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 bg-white/8 ring-1 ring-white/15 text-[12px] text-ink-100 hover:bg-white/12 cursor-pointer"
          >
            choose file
          </label>
          {Boolean(importPayload) && (
            <button
              onClick={onClear}
              className="ml-2 inline-flex items-center gap-2 rounded-full px-4 py-1.5 bg-transparent ring-1 ring-white/10 text-[12px] text-ink-300 hover:text-ink-100"
            >
              clear
            </button>
          )}
        </div>
        {importSourceLabel && (
          <div className="mt-3 text-[11px] font-mono text-ink-300">
            {importSourceLabel}
          </div>
        )}
      </div>

      {importError && (
        <div className="rounded-lg bg-rose-500/10 ring-1 ring-rose-400/40 p-3 text-[12px] text-rose-200">
          {importError}
        </div>
      )}

      {importPreview && !importResult && (
        <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/8 p-4">
          <div className="text-[11px] font-mono uppercase tracking-widest text-ink-300 mb-3">preview</div>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
            <PreviewChip label="notes" value={importPreview.total_incoming_notes} />
            <PreviewChip label="create" value={importPreview.notes_created} tone="lime" />
            <PreviewChip label="update" value={importPreview.notes_updated} tone="cyan" />
            <PreviewChip label="trails" value={importPreview.trails_imported} tone="amber" />
            <PreviewChip label="questions" value={importPreview.compass_imported} tone="pink" />
            <PreviewChip label="watches" value={importPreview.signal_imported} tone="violet" />
          </div>
          {importPreview.warnings.length > 0 && (
            <div className="mt-3 rounded-lg bg-amber-500/[0.06] ring-1 ring-amber-400/30 p-3">
              <div className="text-[11px] font-mono uppercase tracking-widest text-amber-300 mb-1">warnings ({importPreview.warnings.length})</div>
              <ul className="text-[11px] text-amber-100 list-disc pl-4 space-y-0.5 max-h-32 overflow-auto">
                {importPreview.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <div className="text-[11px] font-mono uppercase tracking-widest text-ink-300">mode</div>
            <div className="inline-flex rounded-full bg-white/[0.02] ring-1 ring-white/10 p-0.5">
              <ModeButton
                on={importMode === "merge"}
                onClick={() => onModeChange("merge")}
                tone="cyan"
                label="merge"
                hint="upsert by title"
              />
              <ModeButton
                on={importMode === "replace"}
                onClick={() => onModeChange("replace")}
                tone="rose"
                label="replace"
                hint="wipe + rebuild"
              />
            </div>

            {!confirmReplace ? (
              <button
                onClick={onImport}
                disabled={importBusy}
                className={`ml-auto inline-flex items-center gap-2 rounded-full px-4 py-2 text-[12px] font-mono ring-1 transition ${
                  importMode === "replace"
                    ? "bg-rose-500/25 ring-rose-400/50 text-rose-100 hover:bg-rose-500/35"
                    : "bg-gradient-to-r from-synapse-violet/25 to-synapse-cyan/20 ring-synapse-violet/40 text-ink-100 hover:ring-synapse-violet/70"
                } ${importBusy ? "opacity-60 cursor-not-allowed" : ""}`}
              >
                {importBusy ? "working…" : importMode === "replace" ? "review replace" : "import"}
              </button>
            ) : (
              <div className="ml-auto flex items-center gap-2">
                <span className="text-[11px] text-rose-200">
                  ⚠️ will wipe {importPreview.notes_updated + importPreview.notes_created} notes worth of state
                </span>
                <button
                  onClick={onCancelConfirm}
                  className="rounded-full px-3 py-1.5 text-[11px] font-mono ring-1 ring-white/10 text-ink-300 hover:text-ink-100"
                >
                  cancel
                </button>
                <button
                  onClick={onImport}
                  disabled={importBusy}
                  className={`rounded-full px-4 py-1.5 text-[11px] font-mono ring-1 ring-rose-400/60 bg-rose-500/30 text-rose-50 hover:bg-rose-500/50 ${
                    importBusy ? "opacity-60 cursor-not-allowed" : ""
                  }`}
                >
                  yes, replace
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {importResult && (
        <div className="rounded-xl bg-gradient-to-br from-synapse-lime/10 to-synapse-cyan/10 ring-1 ring-synapse-lime/40 p-4">
          <div className="text-[11px] font-mono uppercase tracking-widest text-synapse-lime mb-2">
            ✓ imported ({importResult.mode})
          </div>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
            <PreviewChip label="created" value={importResult.notes_created} tone="lime" />
            <PreviewChip label="updated" value={importResult.notes_updated} tone="cyan" />
            <PreviewChip label="emb." value={importResult.embeddings_restored} tone="violet" />
            <PreviewChip label="trails" value={importResult.trails_imported} tone="amber" />
            <PreviewChip label="questions" value={importResult.compass_imported} tone="pink" />
            <PreviewChip label="watches" value={importResult.signal_imported} tone="violet" />
          </div>
          {importResult.warnings.length > 0 && (
            <div className="mt-3 text-[11px] text-amber-200">
              {importResult.warnings.length} warning(s) — check the browser console.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SnapshotsTab({
  snapshots,
  newLabel,
  onLabelChange,
  onCreate,
  onRestore,
  onDelete,
  busyRow,
  error,
}: {
  snapshots: VaultSnapshot[];
  newLabel: string;
  onLabelChange: (v: string) => void;
  onCreate: () => void;
  onRestore: (id: number, label: string) => void;
  onDelete: (id: number, label: string) => void;
  busyRow: number | null;
  error: string | null;
}) {
  return (
    <div className="grid gap-4">
      <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/8 p-4">
        <div className="text-[11px] font-mono uppercase tracking-widest text-ink-300 mb-2">create snapshot</div>
        <div className="flex items-center gap-2">
          <input
            value={newLabel}
            onChange={(e) => onLabelChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newLabel.trim()) onCreate();
            }}
            placeholder="label (e.g. before-echo-merge)"
            maxLength={64}
            className="flex-1 rounded-lg bg-white/[0.03] ring-1 ring-white/10 px-3 py-2 text-[13px] text-ink-100 placeholder:text-ink-400/60 focus:ring-synapse-lime/50 outline-none"
          />
          <button
            onClick={onCreate}
            disabled={!newLabel.trim()}
            className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[12px] font-mono bg-gradient-to-r from-synapse-lime/25 to-synapse-cyan/20 ring-1 ring-synapse-lime/40 text-ink-100 hover:ring-synapse-lime/70 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            + freeze
          </button>
        </div>
        <div className="mt-2 text-[11px] text-ink-300">
          Same label overwrites the previous snapshot in place — safe to re-run.
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-rose-500/10 ring-1 ring-rose-400/40 p-3 text-[12px] text-rose-200">
          {error}
        </div>
      )}

      {snapshots.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 p-10 text-center text-[12px] text-ink-300">
          No snapshots yet. Freeze a copy before a risky operation and roll back with one click.
        </div>
      ) : (
        <ul className="grid gap-2">
          {snapshots.map((s) => (
            <li
              key={s.id}
              className="rounded-xl bg-white/[0.02] ring-1 ring-white/8 hover:ring-white/16 transition p-4 flex items-center gap-4"
            >
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-semibold text-ink-100 truncate">{s.label}</div>
                <div className="text-[11px] font-mono text-ink-300 mt-0.5">
                  {relTime(s.created_at)} · {s.note_count} notes · {kb(s.size_bytes)}
                </div>
              </div>
              <button
                onClick={() => onRestore(s.id, s.label)}
                disabled={busyRow === s.id}
                className="text-[11px] font-mono rounded-full px-3 py-1.5 ring-1 ring-synapse-cyan/45 text-synapse-cyan hover:bg-synapse-cyan/10 disabled:opacity-40"
              >
                ↺ restore
              </button>
              <button
                onClick={() => onDelete(s.id, s.label)}
                disabled={busyRow === s.id}
                className="text-[11px] font-mono rounded-full px-3 py-1.5 ring-1 ring-rose-400/40 text-rose-300 hover:bg-rose-500/10 disabled:opacity-40"
              >
                ✕ delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- atoms

function StatChip({ label, value, tone = "slate" }: { label: string; value: number | string; tone?: "slate" | "lime" }) {
  const ring = tone === "lime" ? "ring-synapse-lime/40 text-synapse-lime" : "ring-white/10 text-ink-100";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full ring-1 px-2 py-0.5 ${ring}`}>
      <span className="opacity-70">{label}</span>
      <span>{value}</span>
    </span>
  );
}

function StatTile({ label, value, tone }: { label: string; value: number | string; tone: "violet" | "cyan" | "pink" | "lime" }) {
  const ring = {
    violet: "ring-synapse-violet/40 from-synapse-violet/15 text-synapse-violet",
    cyan: "ring-synapse-cyan/40 from-synapse-cyan/15 text-synapse-cyan",
    pink: "ring-synapse-pink/40 from-synapse-pink/15 text-synapse-pink",
    lime: "ring-synapse-lime/40 from-synapse-lime/15 text-synapse-lime",
  }[tone];
  return (
    <div className={`rounded-lg bg-gradient-to-br ${ring} to-transparent ring-1 p-3`}>
      <div className="text-[10px] font-mono uppercase tracking-widest opacity-80">{label}</div>
      <div className="text-2xl font-semibold text-ink-100 mt-0.5">{value}</div>
    </div>
  );
}

function ToggleRow({ label, hint, on, onToggle }: { label: string; hint: string; on: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`text-left rounded-lg p-3 ring-1 transition flex items-start gap-3 ${
        on
          ? "bg-white/[0.04] ring-white/15"
          : "bg-white/[0.01] ring-white/8 opacity-70 hover:opacity-100"
      }`}
    >
      <span
        className={`mt-0.5 inline-flex w-8 h-4 rounded-full transition ${
          on ? "bg-synapse-lime/60" : "bg-white/10"
        }`}
      >
        <span
          className={`w-3.5 h-3.5 rounded-full bg-ink-100 shadow-sm transform transition ${
            on ? "translate-x-4" : "translate-x-0.5"
          } mt-[1px]`}
        />
      </span>
      <span>
        <span className="block text-[13px] text-ink-100">{label}</span>
        <span className="block text-[11px] text-ink-300 mt-0.5">{hint}</span>
      </span>
    </button>
  );
}

function PreviewChip({ label, value, tone = "slate" }: { label: string; value: number; tone?: "slate" | "lime" | "cyan" | "amber" | "pink" | "violet" }) {
  const ring = {
    slate: "ring-white/10 text-ink-100",
    lime: "ring-synapse-lime/40 text-synapse-lime",
    cyan: "ring-synapse-cyan/40 text-synapse-cyan",
    amber: "ring-synapse-amber/40 text-synapse-amber",
    pink: "ring-synapse-pink/40 text-synapse-pink",
    violet: "ring-synapse-violet/40 text-synapse-violet",
  }[tone];
  return (
    <div className={`rounded-lg bg-white/[0.02] ring-1 ${ring} p-2 text-center`}>
      <div className="text-[10px] font-mono uppercase tracking-widest opacity-80">{label}</div>
      <div className="text-lg font-semibold text-ink-100 mt-0.5">{value}</div>
    </div>
  );
}

function ModeButton({ on, onClick, tone, label, hint }: { on: boolean; onClick: () => void; tone: "cyan" | "rose"; label: string; hint: string }) {
  const active = tone === "cyan"
    ? "bg-synapse-cyan/25 ring-synapse-cyan/50 text-ink-100"
    : "bg-rose-500/25 ring-rose-400/50 text-rose-50";
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded-full text-[11px] font-mono ring-1 transition ${
        on ? active : "ring-transparent text-ink-300 hover:text-ink-100"
      }`}
      title={hint}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------- utils

function kb(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function relTime(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const s = Math.max(0, Math.floor((now - then) / 1000));
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------- ZIP parse
//
// Minimal ZIP central-directory reader — we only need to find
// `_manifest.json` (JSON) and every `notes/*.md` blob (UTF-8 text) inside
// an uploaded ZIP. Full spec support isn't needed; the ZIP we produce is
// stored with DEFLATE and no encryption. This avoids a JSZip dep and
// keeps first-load bytes flat.

async function extractManifestFromZip(buf: ArrayBuffer): Promise<unknown | null> {
  const entries = await readZipEntries(buf);
  const manifest = entries.find((e) => e.name === "_manifest.json");
  if (!manifest) return null;
  const text = new TextDecoder().decode(await inflateEntry(manifest));
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function extractBodiesFromZip(buf: ArrayBuffer): Promise<Record<number, string>> {
  const entries = await readZipEntries(buf);
  const out: Record<number, string> = {};
  for (const e of entries) {
    if (!e.name.startsWith("notes/") || !e.name.endsWith(".md")) continue;
    const text = new TextDecoder().decode(await inflateEntry(e));
    const idMatch = text.match(/^id:\s*(\d+)/m);
    if (!idMatch) continue;
    const id = Number(idMatch[1]);
    // strip frontmatter block
    const bodyMatch = text.match(/^---[\s\S]*?\n---\n\n?([\s\S]*)$/);
    let body = bodyMatch ? bodyMatch[1] : text;
    // strip a leading H1 (`# Title`) — we always emit one from the exporter
    body = body.replace(/^#\s.+\n\n?/, "");
    // strip `\n\n---\n\n## Related …` and everything after
    const relIdx = body.indexOf("\n\n---\n\n## Related");
    if (relIdx !== -1) body = body.slice(0, relIdx);
    out[id] = body.trim();
  }
  return out;
}

type ZipEntry = {
  name: string;
  method: number;
  compressedSize: number;
  uncompressedSize: number;
  offset: number;
  fileData: Uint8Array;
};

async function readZipEntries(buf: ArrayBuffer): Promise<ZipEntry[]> {
  const view = new DataView(buf);
  const bytes = new Uint8Array(buf);
  // Find End of Central Directory Record. Scan back up to 65k+22 bytes.
  const eocdSig = 0x06054b50;
  let eocdOff = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65558); i--) {
    if (view.getUint32(i, true) === eocdSig) {
      eocdOff = i;
      break;
    }
  }
  if (eocdOff === -1) return [];
  const cdirOffset = view.getUint32(eocdOff + 16, true);
  const cdirEntries = view.getUint16(eocdOff + 10, true);

  const entries: ZipEntry[] = [];
  let p = cdirOffset;
  for (let n = 0; n < cdirEntries; n++) {
    // Central Directory Header signature = 0x02014b50
    if (view.getUint32(p, true) !== 0x02014b50) break;
    const method = view.getUint16(p + 10, true);
    const compressedSize = view.getUint32(p + 20, true);
    const uncompressedSize = view.getUint32(p + 24, true);
    const nameLen = view.getUint16(p + 28, true);
    const extraLen = view.getUint16(p + 30, true);
    const commentLen = view.getUint16(p + 32, true);
    const localOffset = view.getUint32(p + 42, true);
    const name = new TextDecoder().decode(bytes.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extraLen + commentLen;

    // Local File Header: sig + 26 bytes header + name + extra, then data.
    if (view.getUint32(localOffset, true) !== 0x04034b50) continue;
    const lNameLen = view.getUint16(localOffset + 26, true);
    const lExtraLen = view.getUint16(localOffset + 28, true);
    const dataStart = localOffset + 30 + lNameLen + lExtraLen;
    const fileData = bytes.subarray(dataStart, dataStart + compressedSize);
    entries.push({ name, method, compressedSize, uncompressedSize, offset: localOffset, fileData });
  }
  return entries;
}

async function inflateEntry(entry: ZipEntry): Promise<Uint8Array> {
  if (entry.method === 0) return entry.fileData;
  if (entry.method === 8) {
    // Raw DEFLATE — DecompressionStream("deflate-raw") is on all modern browsers.
    if (typeof DecompressionStream !== "undefined") {
      const ds = new DecompressionStream("deflate-raw");
      const stream = new Response(entry.fileData).body!.pipeThrough(ds);
      const buf = await new Response(stream).arrayBuffer();
      return new Uint8Array(buf);
    }
  }
  throw new Error(`unsupported compression method ${entry.method}`);
}
