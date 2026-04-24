"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Graph } from "@/components/Graph";
import { Header } from "@/components/Header";
import { Inspector } from "@/components/Inspector";
import { NoteComposer } from "@/components/NoteComposer";
import { PathFinder } from "@/components/PathFinder";
import { SearchBar } from "@/components/SearchBar";
import { api } from "@/lib/api";
import type { Graph as GraphT, GraphNode } from "@/lib/types";

export default function Page() {
  const [graph, setGraph] = useState<GraphT | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [pathEdges, setPathEdges] = useState<Set<string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshGraph = useCallback(async () => {
    try {
      const g = await api.graph();
      setGraph(g);
      setApiOk(true);
      setError(null);
      // Keep the selected node in sync with the latest server state
      setSelected((prev) => {
        if (!prev) return prev;
        return g.nodes.find((n) => n.id === prev.id) ?? null;
      });
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
      await refreshGraph();
    },
    [refreshGraph],
  );

  const nodes = useMemo(() => graph?.nodes ?? [], [graph]);

  return (
    <main className="min-h-screen flex flex-col">
      <Header stats={graph?.stats ?? null} apiOk={apiOk} />

      <div className="mx-auto w-full max-w-[1600px] px-6 py-6 grid grid-cols-12 gap-6 flex-1">
        <aside className="col-span-12 lg:col-span-3 space-y-5">
          <NoteComposer onCreate={handleCreate} />
          <SearchBar onSelect={setSelected} />
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

        <aside className="col-span-12 lg:col-span-3">
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
          ∧ topK
        </span>
        <span>
          built by <span className="text-ink-200">aryan</span> · day 4 of the
          projects rotation
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
        <li>Write an atomic thought. No folders, no hierarchy.</li>
        <li>
          SynapseOS embeds it and links to the most similar existing notes —
          your synapses.
        </li>
        <li>Drag, zoom, search, and trace paths between ideas.</li>
      </ol>
    </div>
  );
}
