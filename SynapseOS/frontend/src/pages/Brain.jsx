import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Search, RefreshCw, Activity, Network, Hash } from "lucide-react";
import { toast } from "sonner";

import SynapseGraph from "@/components/SynapseGraph.jsx";
import NoteEditor   from "@/components/NoteEditor.jsx";
import { api }      from "@/lib/api";

export default function Brain() {
  const [graph, setGraph]           = useState(null);
  const [loading, setLoading]       = useState(true);
  const [selectedId, setSelected]   = useState(null);
  const [editorId, setEditorId]     = useState(undefined); // undefined = closed, null = new
  const [hoveredNode, setHovered]   = useState(null);
  const [query, setQuery]           = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const g = await api.getGraph();
      setGraph(g);
    } catch (e) {
      toast.error(`Couldn't load graph: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filteredNodes = useMemo(() => {
    if (!graph) return [];
    const q = query.trim().toLowerCase();
    if (!q) return graph.nodes;
    return graph.nodes.filter((n) =>
      n.title.toLowerCase().includes(q) ||
      n.tags.some((t) => t.toLowerCase().includes(q))
    );
  }, [graph, query]);

  const selectedNode = useMemo(
    () => graph?.nodes.find((n) => n.id === selectedId) ?? null,
    [graph, selectedId]
  );

  const neighbors = useMemo(() => {
    if (!graph || selectedId == null) return [];
    const pairs = graph.edges
      .filter((e) => e.source === selectedId || e.target === selectedId)
      .map((e) => ({
        id: e.source === selectedId ? e.target : e.source,
        strength: e.strength,
      }))
      .sort((a, b) => b.strength - a.strength);
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    return pairs
      .map((p) => ({ ...byId.get(p.id), strength: p.strength }))
      .filter(Boolean);
  }, [graph, selectedId]);

  async function rebuild() {
    try {
      const { edges } = await api.rebuild();
      toast.success(`Rewired · ${edges} synapses`);
      await load();
    } catch (e) {
      toast.error(e.message);
    }
  }

  function afterWrite() {
    setEditorId(undefined);
    load();
  }

  function afterDelete() {
    setEditorId(undefined);
    setSelected(null);
    load();
  }

  const stats = graph?.stats ?? {};

  return (
    <div className="h-[calc(100vh-56px)] grid grid-cols-[280px_1fr_420px]">
      {/* left: note list & search */}
      <div className="border-r border-white/10 bg-white/[0.02] flex flex-col">
        <div className="px-4 pt-4 pb-3 border-b border-white/10 space-y-3">
          <button
            onClick={() => { setEditorId(null); setSelected(null); }}
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-fuchsia-500/30"
          >
            <Plus className="h-4 w-4" /> Capture thought
          </button>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/40" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="search titles & tags…"
              className="w-full bg-black/30 border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white/90 placeholder:text-white/40 outline-none focus:border-fuchsia-400/50"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {loading && (
            <div className="px-4 py-8 text-center text-white/40 text-xs">
              Loading thoughts…
            </div>
          )}
          {!loading && filteredNodes.length === 0 && (
            <div className="px-4 py-8 text-center text-white/40 text-xs">
              No matches.
            </div>
          )}
          {filteredNodes.map((n) => {
            const active = n.id === selectedId;
            return (
              <button
                key={n.id}
                onClick={() => { setSelected(n.id); setEditorId(undefined); }}
                className={`w-full text-left px-4 py-2.5 border-l-2 transition-colors ${
                  active
                    ? "border-fuchsia-400 bg-fuchsia-500/10"
                    : "border-transparent hover:bg-white/5"
                }`}
              >
                <div className="text-sm text-white/90 truncate">{n.title}</div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-white/40">
                  <span className="inline-flex items-center gap-0.5">
                    <Network className="h-3 w-3" /> {n.size}
                  </span>
                  {n.tags.slice(0, 3).map((t) => (
                    <span key={t} className="inline-flex items-center gap-0.5">
                      <Hash className="h-3 w-3" /> {t}
                    </span>
                  ))}
                </div>
              </button>
            );
          })}
        </div>

        <div className="border-t border-white/10 px-4 py-3 grid grid-cols-3 gap-2 text-[10px] text-white/60">
          <Stat label="notes" value={stats.node_count ?? "—"} />
          <Stat label="synapses" value={stats.edge_count ?? "—"} />
          <Stat label="avg deg" value={stats.avg_degree ?? "—"} />
        </div>
      </div>

      {/* center: graph */}
      <div className="relative p-4">
        <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
          <button
            onClick={rebuild}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/70 hover:bg-white/10 hover:text-white transition-colors"
            title="Recompute all synapses"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            rewire
          </button>
          <div className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] text-white/60">
            <Activity className="h-3 w-3 text-emerald-300" />
            avg strength {stats.avg_strength ?? "—"}
          </div>
        </div>
        <SynapseGraph
          graph={graph}
          selectedId={selectedId}
          onSelect={(id) => { setSelected(id); setEditorId(undefined); }}
          onHover={setHovered}
          className="h-full"
        />
        {hoveredNode && (
          <div className="absolute bottom-4 left-4 right-4 md:right-auto md:max-w-md rounded-xl border border-white/10 bg-[#0a0b1c]/90 backdrop-blur-md p-3 shadow-2xl">
            <div className="text-[10px] uppercase tracking-widest text-white/40">
              Hovered
            </div>
            <div className="text-sm font-semibold text-white/95">
              {hoveredNode.title}
            </div>
            <div className="mt-1 flex gap-1 flex-wrap">
              {hoveredNode.tags?.map((t) => (
                <span key={t}
                      className="text-[10px] rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-white/60">
                  #{t}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* right: inspector / editor */}
      <div className="border-l border-white/10">
        {editorId !== undefined ? (
          <NoteEditor
            noteId={editorId}
            onClose={() => setEditorId(undefined)}
            onSaved={afterWrite}
            onDeleted={afterDelete}
          />
        ) : selectedNode ? (
          <Inspector
            node={selectedNode}
            neighbors={neighbors}
            onEdit={() => setEditorId(selectedNode.id)}
            onJumpTo={(id) => setSelected(id)}
          />
        ) : (
          <EmptyInspector onNew={() => setEditorId(null)} />
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-md bg-black/30 border border-white/5 px-2 py-1.5 text-center">
      <div className="text-white/90 text-sm font-semibold tabular-nums">
        {value}
      </div>
      <div className="text-[9px] uppercase tracking-wider text-white/40 mt-0.5">
        {label}
      </div>
    </div>
  );
}

function Inspector({ node, neighbors, onEdit, onJumpTo }) {
  return (
    <aside className="h-full flex flex-col bg-white/[0.02]">
      <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
        <div className="text-xs uppercase tracking-[0.18em] text-white/50">
          Selected
        </div>
        <button
          onClick={onEdit}
          className="text-xs text-fuchsia-300 hover:text-fuchsia-200 transition-colors"
        >
          Edit →
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <h2 className="text-xl font-semibold text-white">{node.title}</h2>
          <div className="mt-2 flex flex-wrap gap-1">
            {node.tags.map((t) => (
              <span key={t}
                    className="text-[10px] rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-white/70">
                #{t}
              </span>
            ))}
          </div>
          <div className="mt-3 text-[11px] text-white/40">
            {node.size} synapse{node.size === 1 ? "" : "s"} · created{" "}
            {new Date(node.created_at).toLocaleDateString()}
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/40 mb-2">
            Closest neighbours
          </div>
          {neighbors.length === 0 ? (
            <div className="text-xs text-white/40 italic">
              No synapses yet. Add more related notes and they'll appear here.
            </div>
          ) : (
            <ul className="space-y-2">
              {neighbors.map((nb) => (
                <li key={nb.id}>
                  <button
                    onClick={() => onJumpTo(nb.id)}
                    className="w-full text-left rounded-lg border border-white/10 bg-white/[0.03] hover:bg-white/[0.07] hover:border-white/25 transition-colors px-3 py-2"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-sm text-white/90 line-clamp-2">
                        {nb.title}
                      </div>
                      <StrengthPill strength={nb.strength} />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </aside>
  );
}

function StrengthPill({ strength }) {
  const pct = Math.round(strength * 100);
  return (
    <span className="shrink-0 text-[10px] tabular-nums rounded-full border border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-200 px-2 py-0.5">
      {pct}%
    </span>
  );
}

function EmptyInspector({ onNew }) {
  return (
    <div className="h-full grid place-items-center p-6 text-center">
      <div className="max-w-xs">
        <div className="mx-auto h-14 w-14 rounded-2xl bg-gradient-to-br from-indigo-500/30 to-fuchsia-500/30 grid place-items-center shadow-lg shadow-indigo-500/20">
          <Network className="h-6 w-6 text-fuchsia-200" />
        </div>
        <h3 className="mt-4 text-sm font-semibold text-white/90">
          Click any node to inspect it
        </h3>
        <p className="mt-1 text-xs text-white/50 leading-relaxed">
          Or start a new thought and watch SynapseOS find where it belongs.
        </p>
        <button
          onClick={onNew}
          className="mt-4 inline-flex items-center gap-2 rounded-full bg-white/5 border border-white/10 px-4 py-1.5 text-xs text-white/80 hover:bg-white/10 hover:text-white transition-colors"
        >
          <Plus className="h-3.5 w-3.5" /> Capture a thought
        </button>
      </div>
    </div>
  );
}
