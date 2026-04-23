"use client";

import { useMemo } from "react";
import { FileText, ArrowLeftRight } from "lucide-react";
import { useStore } from "@/lib/store";
import { backlinksOf, extractWikilinks } from "@/lib/wikilinks";

export default function BacklinksPanel() {
  const notes = useStore((s) => s.notes);
  const activeId = useStore((s) => s.activeId);
  const setActive = useStore((s) => s.setActive);

  const active = notes.find((n) => n.id === activeId);
  const backlinks = useMemo(
    () => (active ? backlinksOf(active.id, notes) : []),
    [active, notes],
  );
  const outbound = useMemo(() => {
    if (!active) return [];
    const titles = extractWikilinks(active.body);
    return titles.map((t) => {
      const hit = notes.find((n) => n.title.toLowerCase() === t.toLowerCase());
      return { title: t, id: hit?.id, dangling: !hit };
    });
  }, [active, notes]);

  if (!active) return null;

  return (
    <div className="p-4 border-t border-white/5 bg-void-800/30">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-ink-400 mb-2">
        <ArrowLeftRight className="w-3 h-3" />
        Connections
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Panel title={`Backlinks · ${backlinks.length}`} tint="text-synapse-violet">
          {backlinks.length === 0 ? (
            <Empty>No notes link here yet.</Empty>
          ) : (
            <ul className="space-y-1">
              {backlinks.map((b) => (
                <li key={b.id}>
                  <button
                    onClick={() => setActive(b.id)}
                    className="flex items-center gap-1.5 text-[12px] text-ink-200 hover:text-synapse-violet transition w-full text-left truncate"
                  >
                    <FileText className="w-3 h-3 shrink-0" />
                    <span className="truncate">{b.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={`Outbound · ${outbound.length}`} tint="text-synapse-cyan">
          {outbound.length === 0 ? (
            <Empty>Add [[link]]s to connect ideas.</Empty>
          ) : (
            <ul className="space-y-1">
              {outbound.map((o) => (
                <li key={o.title}>
                  <button
                    onClick={() => o.id && setActive(o.id)}
                    disabled={o.dangling}
                    className="flex items-center gap-1.5 text-[12px] w-full text-left truncate disabled:cursor-not-allowed"
                  >
                    <FileText className="w-3 h-3 shrink-0" />
                    <span
                      className={
                        o.dangling
                          ? "text-synapse-magenta/80 border-b border-dashed border-synapse-magenta/40"
                          : "text-ink-200 hover:text-synapse-cyan transition"
                      }
                    >
                      {o.title}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Panel({
  title,
  tint,
  children,
}: {
  title: string;
  tint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg bg-void-700/40 border border-white/5 p-3">
      <div className={`text-[10px] uppercase tracking-wider mb-1.5 ${tint}`}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] text-ink-400 italic">{children}</div>;
}
