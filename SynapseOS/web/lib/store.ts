"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Note } from "./types";
import { SEED_NOTES } from "./seed";
import { extractTags, findByTitle, slugify } from "./wikilinks";

type State = {
  notes: Note[];
  activeId: string | null;
  commandOpen: boolean;
  graphOpen: boolean;
  query: string;

  // actions
  setQuery: (q: string) => void;
  setActive: (id: string | null) => void;
  openCommand: (v?: boolean) => void;
  toggleGraph: () => void;

  createNote: (title?: string) => Note;
  createFromTitle: (title: string) => Note;
  updateNote: (id: string, patch: Partial<Pick<Note, "title" | "body">>) => void;
  deleteNote: (id: string) => void;

  openOrCreate: (title: string) => void;
};

const freshId = () => {
  const rand = Math.random().toString(36).slice(2, 8);
  return `n-${Date.now().toString(36)}-${rand}`;
};

export const useStore = create<State>()(
  persist(
    (set, get) => ({
      notes: SEED_NOTES,
      activeId: SEED_NOTES[0]?.id ?? null,
      commandOpen: false,
      graphOpen: true,
      query: "",

      setQuery: (q) => set({ query: q }),
      setActive: (id) => set({ activeId: id }),
      openCommand: (v) =>
        set((s) => ({ commandOpen: typeof v === "boolean" ? v : !s.commandOpen })),
      toggleGraph: () => set((s) => ({ graphOpen: !s.graphOpen })),

      createNote: (title) => {
        const n: Note = {
          id: freshId(),
          title: title?.trim() || "Untitled",
          body: `# ${title?.trim() || "Untitled"}\n\n`,
          tags: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        set((s) => ({ notes: [n, ...s.notes], activeId: n.id }));
        return n;
      },

      createFromTitle: (title) => {
        const trimmed = title.trim() || "Untitled";
        const existing = findByTitle(get().notes, trimmed);
        if (existing) {
          set({ activeId: existing.id });
          return existing;
        }
        const n: Note = {
          id: `n-${slugify(trimmed)}-${Math.random().toString(36).slice(2, 5)}`,
          title: trimmed,
          body: `# ${trimmed}\n\n`,
          tags: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        set((s) => ({ notes: [n, ...s.notes], activeId: n.id }));
        return n;
      },

      updateNote: (id, patch) =>
        set((s) => ({
          notes: s.notes.map((n) =>
            n.id === id
              ? {
                  ...n,
                  ...patch,
                  tags: patch.body ? extractTags(patch.body) : n.tags,
                  updatedAt: Date.now(),
                }
              : n,
          ),
        })),

      deleteNote: (id) =>
        set((s) => {
          const notes = s.notes.filter((n) => n.id !== id);
          const activeId =
            s.activeId === id ? (notes[0]?.id ?? null) : s.activeId;
          return { notes, activeId };
        }),

      openOrCreate: (title) => {
        const existing = findByTitle(get().notes, title);
        if (existing) {
          set({ activeId: existing.id });
        } else {
          get().createFromTitle(title);
        }
      },
    }),
    {
      name: "synapseos:v1",
      partialize: (s) => ({ notes: s.notes, activeId: s.activeId }),
    },
  ),
);
