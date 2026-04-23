import type { Note } from "./types";

const now = Date.now();
const day = 86_400_000;

function note(
  id: string,
  title: string,
  body: string,
  daysAgo = 0,
  tags: string[] = [],
): Note {
  const t = now - daysAgo * day;
  return { id, title, body, tags, createdAt: t, updatedAt: t };
}

export const SEED_NOTES: Note[] = [
  note(
    "welcome",
    "Welcome to SynapseOS",
    `# Welcome to SynapseOS

**Your thoughts, connected.** This is a local-first Personal Knowledge OS where
every note is a synapse. Write freely, link with \`[[double brackets]]\`, and
watch the graph on the right wire itself up in real time.

## Start here

- Open [[Daily Log]] to jot what's on your mind today.
- Explore a core idea in [[Second Brain]].
- See how linking works in [[Wikilinks 101]].
- Browse #concept notes on [[Concepts]].

## What makes this different

Most note apps treat notes as files. SynapseOS treats them as **neurons** —
the value lives in the connections. Press \`⌘K\` to jump anywhere. Press
\`⌘G\` to zoom into the synapse graph.

> The garden, not the stream. Your notes should grow deeper the longer you tend them.
`,
    0,
    ["meta"],
  ),
  note(
    "second-brain",
    "Second Brain",
    `# Second Brain

A **second brain** is an external system for ideas you don't want to lose and
connections you couldn't make in your head alone. The core promise: *show me
what I already know that I forgot I knew.*

## Principles

1. **Capture liberally** — a note is cheap.
2. **Link aggressively** — use [[Wikilinks 101]] everywhere.
3. **Summarize in your own words** — compression is understanding.
4. **Revisit, don't archive** — ideas compound when re-entered.

Related: [[Zettelkasten]] · [[Spaced Repetition]] · [[Concepts]]

#concept
`,
    1,
    ["concept"],
  ),
  note(
    "wikilinks-101",
    "Wikilinks 101",
    `# Wikilinks 101

Typing \`[[Some Title]]\` creates a live link. If a note with that title
exists, the link is cyan. If not, it shows up **dashed magenta** — a ghost
node in the graph inviting you to create it.

Aliases: \`[[Second Brain|my exo-cortex]]\` renders the alias text but still
links to the target.

Try it:
- Link back to [[Welcome to SynapseOS]]
- Create a new one: [[Emergent Ideas]]

#concept
`,
    1,
    ["concept"],
  ),
  note(
    "zettelkasten",
    "Zettelkasten",
    `# Zettelkasten

Niklas Luhmann's slip-box method. Each note holds a single atomic idea, is
written in your own words, and links to its neighbors. Over thousands of
notes, the box becomes a thinking partner.

The SynapseOS equivalent: keep notes short, keep the title a full thought,
and let [[Wikilinks 101]] do the weaving.

See also: [[Second Brain]], [[Spaced Repetition]]

#concept
`,
    2,
    ["concept"],
  ),
  note(
    "spaced-repetition",
    "Spaced Repetition",
    `# Spaced Repetition

Review at expanding intervals — minutes, days, weeks, months — to keep facts
from decaying. In a PKM context, the trick is reviewing *connections*, not
just cards: "what does this note remind me of?"

Related: [[Second Brain]], [[Zettelkasten]]

#concept
`,
    2,
    ["concept"],
  ),
  note(
    "concepts",
    "Concepts",
    `# Concepts

Index of foundational ideas in this vault.

- [[Second Brain]]
- [[Zettelkasten]]
- [[Spaced Repetition]]
- [[Wikilinks 101]]

#index
`,
    0,
    ["index"],
  ),
  note(
    "daily-log",
    "Daily Log",
    `# Daily Log

Quick scratchpad for today. Unformatted thoughts belong here — structure
emerges from linking.

- Read something interesting about [[Zettelkasten]]
- Want to sketch a note called [[Emergent Ideas]]
- Reminder: try the \`⌘K\` palette

#journal
`,
    0,
    ["journal"],
  ),
];
