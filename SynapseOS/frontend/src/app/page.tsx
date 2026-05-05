"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { Graph } from "@/components/Graph";
import { Header } from "@/components/Header";
import { Inspector } from "@/components/Inspector";
import { NoteComposer } from "@/components/NoteComposer";
import { OrphanRescue } from "@/components/OrphanRescue";
import { PathFinder } from "@/components/PathFinder";
import { SearchBar } from "@/components/SearchBar";
import { TopicPalette } from "@/components/TopicPalette";
import { api } from "@/lib/api";
import type {
  ChatTurn,
  Community,
  Graph as GraphT,
  GraphNode,
  OrphanSuggestion,
} from "@/lib/types";

const edgeKey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`);

export default function Page() {
  const [graph, setGraph] = useState<GraphT | null>(null);
  const [communities, setCommunities] = useState<Community[]>([]);
  const [orphans, setOrphans] = useState<OrphanSuggestion[]>([]);
  const [isolated, setIsolated] = useState<number | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [pathEdges, setPathEdges] = useState<Set<string> | null>(null);
  const [chatTurn, setChatTurn] = useState<ChatTurn | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshGraph = useCallback(async () => {
    try {
      // Three calls in parallel — they all read the same in-memory state
      // on the backend but each is cheap and independent.
      const [g, cs, os] = await Promise.all([
        api.graph(),
        api.communities(),
        api.orphans(),
      ]);
      setGraph(g);
      setCommunities(cs);
      setOrphans(os);
      setApiOk(true);
      setError(null);
      setSelected((prev) => {
        if (!prev) return prev;
        return g.nodes.find((n) => n.id === prev.id) ?? null;
      });
      // If the user had isolated a community that no longer exists,
      // clear the isolation so the canvas isn't stuck blank.
      setIsolated((prev) =>
        prev !== null && cs.some((c) => c.id === prev) ? prev : null,
      );
    } catch (e) {
      setApiOk(false);
      setError(e instanceof Error ? e.message : "failed to load graph");
    }
  }, []);

  useEffect(() => {
    api.health().then(() => setApiOk(true)).catch(() => setApiOk(false));
    refreshGraph();
  }, [refreshGraph]);

  const handleCreate = useCallback(
    async (payload: { title: string; body: string; tags: string[] }) => {
      const n = await api.createNote(payload);
      await refreshGraph();
      setSelected({
        id: n.id,
        title: n.title,
        body: n.body,
        tags: n.tags,
        degree: 0,
        weight: 0,
      });
    },
    [refreshGraph],
  );

  const handleDelete = useCallback(
    async (id: number) => {
      await api.deleteNote(id);
      setSelected(null);
      setPathEdges(null);
      setChatTurn(null);
      await refreshGraph();
    },
    [refreshGraph],
  );

  const nodes = useMemo(() => graph?.nodes ?? [], [graph]);

  // Derive the set of edge keys + node ids the chat panel just exercised
  // so the canvas can paint them in cyan. We also include "virtual"
  // seed→community-anchor edges as discrete highlights even when the
  // synapse graph itself has no edge between them — those are flagged
  // with `kind === "community"` and we still fold them into the node
  // halo set without claiming a synapse exists.
  const chatTraversalEdges = useMemo(() => {
    if (!chatTurn) return null;
    const out = new Set<string>();
    for (const e of chatTurn.response.traversal.expansions) {
      if (e.kind === "synapse") out.add(edgeKey(e.src, e.dst));
    }
    return out.size > 0 ? out : null;
  }, [chatTurn]);

  const chatTraversalNodes = useMemo(() => {
    if (!chatTurn) return null;
    const out = new Set<number>();
    for (const id of chatTurn.response.traversal.seeds) out.add(id);
    for (const e of chatTurn.response.traversal.expansions) {
      out.add(e.src);
      out.add(e.dst);
    }
    for (const c of chatTurn.response.citations) out.add(c.note_id);
    return out.size > 0 ? out : null;
  }, [chatTurn]);

  return (
    <main className="min-h-screen flex flex-col">
      <Header
        stats={graph?.stats ?? null}
        apiOk={apiOk}
        chatActive={chatTurn !== null}
      />

      <div className="mx-auto w-full max-w-[1600px] px-6 py-6 grid grid-cols-12 gap-6 flex-1">
        <aside className="col-span-12 lg:col-span-3 space-y-5">
          <NoteComposer onCreate={handleCreate} />
          <SearchBar onSelect={setSelected} />
          <TopicPalette
            communities={communities}
            isolated={isolated}
            onIsolate={setIsolated}
          />
          <OrphanRescue orphans={orphans} nodes={nodes} onSelect={setSelected} />
          <PathFinder
            nodes={nodes}
            onHighlight={(keys, path) => {
              setPathEdges(keys);
              if (path.length > 0) setSelected(path[path.length - 1]);
            }}
          />
          <HelpCard />
        </aside>

        <section className="col-span-12 lg:col-span-6 min-h-[640px]">
          <div className="h-[calc(100vh-9rem)] min-h-[560px]">
            <Graph
              data={graph}
              selectedId={selected?.id ?? null}
              highlightPath={pathEdges}
              chatTraversalEdges={chatTraversalEdges}
              chatTraversalNodes={chatTraversalNodes}
              isolatedCommunity={isolated}
              onSelect={(n) => setSelected(n)}
            />
          </div>
          {error && (
            <p className="mt-3 text-xs font-mono text-synapse-pink">
              {error} — start the backend with{" "}
              <span className="text-ink-100">uvicorn app.main:app --reload</span>
            </p>
          )}
        </section>

        <aside className="col-span-12 lg:col-span-3 space-y-5">
          <ChatPanel
            nodes={nodes}
            onCitationClick={(n) => setSelected(n)}
            onTraversalChange={setChatTurn}
          />
          <Inspector
            selected={selected}
            onSelect={setSelected}
            onDelete={handleDelete}
          />
        </aside>
      </div>

      <footer className="mx-auto w-full max-w-[1600px] px-6 pb-6 text-[11px] font-mono text-ink-400 flex items-center justify-between">
        <span>
          synapse := cosine(embedding<sub>a</sub>, embedding<sub>b</sub>) ≥ τ
          ∧ topK · clusters via greedy modularity · chat retrieves along
          synapses
        </span>
        <span>
          built by <span className="text-ink-200">aryan</span> · projects rotation
        </span>
      </footer>
    </main>
  );
}

function HelpCard() {
  return (
    <div className="rounded-xl bg-white/[0.015] ring-1 ring-white/5 p-4 text-xs text-ink-300 leading-relaxed">
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200 mb-2">
        how it works
      </div>
      <ol className="space-y-1.5 list-decimal list-inside marker:text-synapse-violet">
        <li>Write atomic thoughts. No folders, no hierarchy.</li>
        <li>
          SynapseOS embeds each note and links it to its closest neighbors —
          your synapses.
        </li>
        <li>
          Clusters and their names emerge automatically; isolated thoughts
          surface as &quot;orphans&quot; you can rescue.
        </li>
        <li>
          Ask the graph anything — answers cite the exact notes, and the
          retrieval traversal lights up on the canvas.
        </li>
      </ol>
    </div>
  );
}
