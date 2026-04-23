"use client";

import { useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import NoteEditor from "@/components/NoteEditor";
import BacklinksPanel from "@/components/BacklinksPanel";
import GraphView from "@/components/GraphView";
import CommandPalette from "@/components/CommandPalette";
import { useStore } from "@/lib/store";

export default function Workspace() {
  const graphOpen = useStore((s) => s.graphOpen);
  const createNote = useStore((s) => s.createNote);
  const toggleGraph = useStore((s) => s.toggleGraph);

  // Workspace-level shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "n") {
        e.preventDefault();
        createNote();
      }
      if (mod && e.key.toLowerCase() === "g") {
        e.preventDefault();
        toggleGraph();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [createNote, toggleGraph]);

  return (
    <main className="h-screen w-screen flex bg-synapse-gradient bg-void-900 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex min-w-0">
        <div className="flex-1 min-w-0 flex flex-col border-r border-white/5 bg-void-800/30">
          <NoteEditor />
          <BacklinksPanel />
        </div>
        {graphOpen && (
          <div className="w-[42%] min-w-[360px] h-full">
            <GraphView />
          </div>
        )}
      </div>
      <CommandPalette />
    </main>
  );
}
