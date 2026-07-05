"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Atlas } from "@/components/Atlas";
import { ChatPanel } from "@/components/ChatPanel";
import { Chronicle } from "@/components/Chronicle";
import { Compass } from "@/components/Compass";
import { DailyBrief } from "@/components/DailyBrief";
import { Distill } from "@/components/Distill";
import { Echo } from "@/components/Echo";
import { Graph } from "@/components/Graph";
import { Header } from "@/components/Header";
import { Inspector } from "@/components/Inspector";
import { NoteComposer } from "@/components/NoteComposer";
import { OrphanRescue } from "@/components/OrphanRescue";
import { PathFinder } from "@/components/PathFinder";
import { Pulse } from "@/components/Pulse";
import { Recall } from "@/components/Recall";
import { SearchBar } from "@/components/SearchBar";
import { Spark } from "@/components/Spark";
import { Synthesis } from "@/components/Synthesis";
import { Tensions } from "@/components/Tensions";
import { TopicPalette } from "@/components/TopicPalette";
import { TrailPlayer } from "@/components/TrailPlayer";
import { TrailsPanel } from "@/components/TrailsPanel";
import { api } from "@/lib/api";
import type {
  ChatTurn,
  Community,
  Graph as GraphT,
  GraphNode,
  NoteDraft,
  OrphanSuggestion,
  Trail,
  TrailDraftStep,
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
  const [briefOpen, setBriefOpen] = useState(false);
  const [briefBadge, setBriefBadge] = useState(false);
  const [distillOpen, setDistillOpen] = useState(false);
  const [distillFlash, setDistillFlash] = useState<string | null>(null);
  const [synthClusterId, setSynthClusterId] = useState<number | null>(null);
  const [tensionsOpen, setTensionsOpen] = useState(false);
  const [tensionsCount, setTensionsCount] = useState<number | null>(null);
  const [echoOpen, setEchoOpen] = useState(false);
  const [echoCount, setEchoCount] = useState<number | null>(null);
  const [atlasOpen, setAtlasOpen] = useState(false);
  const [chronicleOpen, setChronicleOpen] = useState(false);
  const [chronicleCount, setChronicleCount] = useState<number | null>(null);
  const [pulseOpen, setPulseOpen] = useState(false);
  const [pulseBadge, setPulseBadge] = useState<number | null>(null);
  const [sparkOpen, setSparkOpen] = useState(false);
  const [sparkBadge, setSparkBadge] = useState<number | null>(null);
  const [compassOpen, setCompassOpen] = useState(false);
  const [compassBadge, setCompassBadge] = useState<number | null>(null);
  const [recallOpen, setRecallOpen] = useState(false);
  const [recallBadge, setRecallBadge] = useState<number | null>(null);
  const [composerDraft, setComposerDraft] = useState<NoteDraft | null>(null);

  // Trails — the active trail (when the player is open) flows up here
  // so the canvas can paint trail mode (dim + overlay polyline) and so
  // the sidebar can highlight the active trail.
  const [trailPlayerOpen, setTrailPlayerOpen] = useState(false);
  const [trailPlayerId, setTrailPlayerId] = useState<number | null>(null);
  const [trailPlayerMode, setTrailPlayerMode] = useState<"play" | "build">(
    "play",
  );
  const [trailStarter, setTrailStarter] = useState<TrailDraftStep[] | null>(null);
  const [activeTrail, setActiveTrail] = useState<Trail | null>(null);
  const [trailFocusId, setTrailFocusId] = useState<number | null>(null);
  const [trailsListVersion, setTrailsListVersion] = useState(0);

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

  // First-paint "have they seen today's brief yet?" — drives the pulse
  // dot next to the header trigger. Cheap probe; we don't load the full
  // brief until the modal opens.
  useEffect(() => {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const seen = localStorage.getItem("synapseos:lastBriefSeen");
      setBriefBadge(seen !== today);
    } catch {
      setBriefBadge(true);
    }
  }, []);

  // Cheap probe of the tension count so the header badge reflects
  // "your second brain has N unresolved contradictions" without forcing
  // a full modal-load. Re-runs after every graph refresh so the count
  // moves when you add or delete notes.
  useEffect(() => {
    if (!graph || graph.nodes.length < 2) {
      setTensionsCount(0);
      return;
    }
    let cancelled = false;
    api
      .tensions({ limit: 50 })
      .then((r) => {
        if (!cancelled) setTensionsCount(r.tension_count);
      })
      .catch(() => {
        if (!cancelled) setTensionsCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [graph]);

  // Same idea for echoes: header badge shows "N duplicate clusters" so
  // the user knows there's PKM hygiene work waiting without having to
  // open the modal.
  useEffect(() => {
    if (!graph || graph.nodes.length < 2) {
      setEchoCount(0);
      return;
    }
    let cancelled = false;
    api
      .echo({ limit: 20 })
      .then((r) => {
        if (!cancelled) setEchoCount(r.cluster_count);
      })
      .catch(() => {
        if (!cancelled) setEchoCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [graph]);

  // Chronicle badge — count of pivoting clusters (the ones with a real
  // story to tell). Cheap probe; the full modal lazy-loads its own data
  // when opened.
  useEffect(() => {
    if (!graph || graph.nodes.length < 2) {
      setChronicleCount(0);
      return;
    }
    let cancelled = false;
    api
      .chronicle()
      .then((r) => {
        if (!cancelled)
          setChronicleCount(r.summary.pivoting_count ?? 0);
      })
      .catch(() => {
        if (!cancelled) setChronicleCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [graph]);

  // Pulse badge — sum of new notes + bridges born in the last 7d so the
  // header signals "you've shipped activity that's worth a re-read."
  // Cheap probe; the modal lazy-loads its own data when opened.
  useEffect(() => {
    if (!graph || graph.nodes.length < 1) {
      setPulseBadge(0);
      return;
    }
    let cancelled = false;
    api
      .pulse({ windowDays: 7 })
      .then((r) => {
        if (!cancelled)
          setPulseBadge((r.new_notes ?? 0) + (r.bridges_born ?? 0));
      })
      .catch(() => {
        if (!cancelled) setPulseBadge(null);
      });
    return () => {
      cancelled = true;
    };
  }, [graph]);

  // Spark badge — total queued sparks across all five kinds. Cheap
  // probe so the header pill shows "N writing prompts waiting" without
  // forcing the modal-load on every page-paint.
  useEffect(() => {
    if (!graph || graph.nodes.length < 2) {
      setSparkBadge(0);
      return;
    }
    let cancelled = false;
    api
      .spark({ limit: 16, perKind: 4 })
      .then((r) => {
        if (!cancelled) setSparkBadge(r.sparks.length);
      })
      .catch(() => {
        if (!cancelled) setSparkBadge(null);
      });
    return () => {
      cancelled = true;
    };
  }, [graph]);

  // Compass badge — count of pinned research questions. The modal
  // lazy-loads each lens on demand; the rail itself is cheap enough
  // that this single count is all the header needs.
  useEffect(() => {
    let cancelled = false;
    api
      .compassQuestions()
      .then((qs) => {
        if (!cancelled) setCompassBadge(qs.length);
      })
      .catch(() => {
        if (!cancelled) setCompassBadge(null);
      });
    return () => {
      cancelled = true;
    };
  }, [graph, compassOpen]);

  // Recall badge — count of cards currently due. Cheap summary call;
  // refreshes when the graph or the modal changes. The badge nudges
  // the user toward the modal without pushing a session on them.
  useEffect(() => {
    let cancelled = false;
    api
      .recallSummary()
      .then((s) => {
        if (!cancelled) setRecallBadge(s.due_now);
      })
      .catch(() => {
        if (!cancelled) setRecallBadge(null);
      });
    return () => {
      cancelled = true;
    };
  }, [graph, recallOpen]);

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

  // The ordered sequence Graph needs to paint the trail overlay.
  // Null whenever the player is closed or no steps exist yet so the
  // canvas reverts to its normal styling.
  const trailSequence = useMemo(() => {
    if (!trailPlayerOpen || !activeTrail) return null;
    if (activeTrail.steps.length === 0) return null;
    return activeTrail.steps.map((s) => ({
      id: s.note_id,
      isSynapseToNext: s.is_synapse_to_next,
    }));
  }, [trailPlayerOpen, activeTrail]);

  const openNewTrail = useCallback((starter?: TrailDraftStep[] | null) => {
    setTrailPlayerId(null);
    setTrailPlayerMode("build");
    setTrailStarter(starter ?? null);
    setTrailPlayerOpen(true);
  }, []);

  const openTrailForPlay = useCallback((id: number) => {
    setTrailPlayerId(id);
    setTrailPlayerMode("play");
    setTrailStarter(null);
    setTrailPlayerOpen(true);
  }, []);

  const openTrailForEdit = useCallback((id: number) => {
    setTrailPlayerId(id);
    setTrailPlayerMode("build");
    setTrailStarter(null);
    setTrailPlayerOpen(true);
  }, []);

  const handleTrailClose = useCallback(() => {
    setTrailPlayerOpen(false);
    setActiveTrail(null);
    setTrailFocusId(null);
    setTrailStarter(null);
  }, []);

  const handleTrailFocusNote = useCallback((node: GraphNode | null) => {
    setTrailFocusId(node?.id ?? null);
    if (node) setSelected(node);
  }, []);

  return (
    <main className="min-h-screen flex flex-col">
      <Header
        stats={graph?.stats ?? null}
        apiOk={apiOk}
        chatActive={chatTurn !== null}
        trailActive={trailPlayerOpen}
        onOpenBrief={() => setBriefOpen(true)}
        briefBadge={briefBadge}
        onOpenDistill={() => setDistillOpen(true)}
        onOpenTensions={() => setTensionsOpen(true)}
        tensionsBadge={tensionsCount ?? undefined}
        onOpenEcho={() => setEchoOpen(true)}
        echoBadge={echoCount ?? undefined}
        onOpenAtlas={() => setAtlasOpen(true)}
        onOpenChronicle={() => setChronicleOpen(true)}
        chronicleBadge={chronicleCount ?? undefined}
        onOpenPulse={() => setPulseOpen(true)}
        pulseBadge={pulseBadge ?? undefined}
        onOpenSpark={() => setSparkOpen(true)}
        sparkBadge={sparkBadge ?? undefined}
        onOpenCompass={() => setCompassOpen(true)}
        compassBadge={compassBadge ?? undefined}
        onOpenRecall={() => setRecallOpen(true)}
        recallBadge={recallBadge ?? undefined}
      />

      <DailyBrief
        open={briefOpen}
        onClose={() => setBriefOpen(false)}
        onSelectNote={(stub) => {
          // Resolve the stub against the loaded graph so the inspector
          // gets full body/tags/degree/weight when available, then
          // fall through to the stub on a cold-cache.
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
        onTouchedAny={() => setBriefBadge(false)}
      />

      <TrailPlayer
        open={trailPlayerOpen}
        trailId={trailPlayerId}
        initialMode={trailPlayerMode}
        startSteps={trailStarter}
        onFocusNote={handleTrailFocusNote}
        onTrailChange={setActiveTrail}
        onMutated={() => setTrailsListVersion((v) => v + 1)}
        onClose={handleTrailClose}
      />

      <Distill
        open={distillOpen}
        nodes={nodes}
        onPreviewNeighbor={setSelected}
        onCommitted={(createdIds, synapsesFormed) => {
          setDistillFlash(
            `${createdIds.length} atom${createdIds.length === 1 ? "" : "s"} added · ${synapsesFormed} synapse${synapsesFormed === 1 ? "" : "s"} formed`,
          );
          refreshGraph();
          window.setTimeout(() => setDistillFlash(null), 5500);
        }}
        onClose={() => setDistillOpen(false)}
      />

      <Synthesis
        open={synthClusterId !== null}
        clusterId={synthClusterId}
        fallbackName={
          communities.find((c) => c.id === synthClusterId)?.name ?? null
        }
        fallbackColor={
          communities.find((c) => c.id === synthClusterId)?.color ?? null
        }
        onClose={() => setSynthClusterId(null)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
      />

      <Tensions
        open={tensionsOpen}
        onClose={() => setTensionsOpen(false)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
        onReconcile={(draft) => setComposerDraft(draft)}
      />

      <Echo
        open={echoOpen}
        onClose={() => setEchoOpen(false)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
        onMutated={() => {
          refreshGraph();
        }}
      />

      <Atlas
        open={atlasOpen}
        onClose={() => setAtlasOpen(false)}
        onIsolateCluster={(id) => setIsolated(id)}
        onSynthesizeCluster={(id) => {
          setAtlasOpen(false);
          setSynthClusterId(id);
        }}
      />

      <Chronicle
        open={chronicleOpen}
        onClose={() => setChronicleOpen(false)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
        onSynthesizeCluster={(id) => {
          setChronicleOpen(false);
          setSynthClusterId(id);
        }}
        onIsolateCluster={(id) => setIsolated(id)}
      />

      <Pulse
        open={pulseOpen}
        onClose={() => setPulseOpen(false)}
        onSynthesizeCluster={(id) => {
          setPulseOpen(false);
          setSynthClusterId(id);
        }}
        onIsolateCluster={(id) => setIsolated(id)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
      />

      <Spark
        open={sparkOpen}
        onClose={() => setSparkOpen(false)}
        onUseDraft={(draft) => setComposerDraft(draft)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
        onAfterUse={() => setSparkOpen(false)}
      />

      <Compass
        open={compassOpen}
        onClose={() => setCompassOpen(false)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
          setCompassOpen(false);
        }}
      />

      <Recall
        open={recallOpen}
        onClose={() => setRecallOpen(false)}
        onSelectNote={(stub) => {
          const real = nodes.find((n) => n.id === stub.id);
          setSelected(real ?? (stub as GraphNode));
          setIsolated(null);
        }}
      />

      <div className="mx-auto w-full max-w-[1600px] px-6 py-6 grid grid-cols-12 gap-6 flex-1">
        <aside className="col-span-12 lg:col-span-3 space-y-5">
          <NoteComposer
            onCreate={handleCreate}
            draft={composerDraft}
            onDraftConsumed={() => setComposerDraft(null)}
          />
          <SearchBar onSelect={setSelected} />
          <TopicPalette
            communities={communities}
            isolated={isolated}
            onIsolate={setIsolated}
            onSynthesize={setSynthClusterId}
          />
          <OrphanRescue orphans={orphans} nodes={nodes} onSelect={setSelected} />
          <PathFinder
            nodes={nodes}
            onHighlight={(keys, path) => {
              setPathEdges(keys);
              if (path.length > 0) setSelected(path[path.length - 1]);
            }}
            onSavePath={(path) => {
              if (path.length === 0) return;
              openNewTrail(
                path.map((p) => ({ note_id: p.id, caption: "" })),
              );
            }}
          />
          <TrailsPanel
            refreshKey={trailsListVersion}
            activeTrailId={activeTrail?.id ?? null}
            onOpenPlay={openTrailForPlay}
            onOpenNew={() => openNewTrail(null)}
            onOpenEdit={openTrailForEdit}
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
              trailSequence={trailSequence}
              trailFocusId={trailFocusId}
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
            trailCanAppend={trailPlayerOpen && activeTrail !== null}
            trailCanStart={!trailPlayerOpen}
            onAddToTrail={async (id) => {
              if (!activeTrail) return;
              try {
                const updated = await api.appendTrailStep(activeTrail.id, {
                  note_id: id,
                });
                setActiveTrail(updated);
                setTrailsListVersion((v) => v + 1);
              } catch {
                /* surfaced inside the player on save */
              }
            }}
            onStartTrailHere={(id) =>
              openNewTrail([{ note_id: id, caption: "" }])
            }
          />
        </aside>
      </div>

      {distillFlash && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 px-4 py-2 rounded-full bg-gradient-to-r from-synapse-lime/20 to-synapse-cyan/20 ring-1 ring-synapse-lime/50 backdrop-blur text-xs font-mono text-synapse-lime shadow-glow flex items-center gap-2">
          <span>✓</span>
          {distillFlash}
        </div>
      )}

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
