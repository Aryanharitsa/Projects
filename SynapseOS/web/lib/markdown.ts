import type { Note } from "./types";
import { findByTitle } from "./wikilinks";

/**
 * Tiny purpose-built markdown renderer. Keeps the bundle slim and lets us
 * wire wikilinks straight into the note store without a plugin dance.
 *
 * Supports: headings, bold/italic/code, links, lists, blockquotes, fenced
 * code, horizontal rules, inline [[wikilinks]], and #tags. Escapes HTML.
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(src: string, notes: Note[]): string {
  let out = escapeHtml(src);

  // Wikilinks: [[Target]] or [[Target|alias]]
  out = out.replace(
    /\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]/g,
    (_match, target: string, alias?: string) => {
      const label = (alias ?? target).trim();
      const resolved = findByTitle(notes, target.trim());
      const cls = resolved ? "wikilink" : "wikilink dangling";
      const dataId = resolved ? resolved.id : `dangling:${target.trim()}`;
      return `<a class="${cls}" data-wikilink="${escapeHtml(dataId)}" data-title="${escapeHtml(target.trim())}">${escapeHtml(label)}</a>`;
    },
  );

  // Inline code
  out = out.replace(/`([^`]+)`/g, (_m, code) => `<code>${code}</code>`);

  // Bold then italic (bold first to avoid _*_ tangles)
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  out = out.replace(/_([^_\n]+)_/g, "<em>$1</em>");

  // Regular links [text](url)
  out = out.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (_m, text, url) => `<a href="${url}" target="_blank" rel="noreferrer">${text}</a>`,
  );

  // Inline tags: #word — but only when preceded by whitespace or start
  out = out.replace(
    /(^|\s)#([a-zA-Z][\w-]{1,30})/g,
    (_m, pre, tag) => `${pre}<span class="tag">#${tag}</span>`,
  );

  return out;
}

export function renderMarkdown(src: string, notes: Note[]): string {
  const lines = src.split("\n");
  const out: string[] = [];
  let inCode = false;
  let codeBuf: string[] = [];
  let listStack: ("ul" | "ol")[] = [];

  const closeLists = () => {
    while (listStack.length) {
      out.push(`</${listStack.pop()}>`);
    }
  };

  for (const raw of lines) {
    const line = raw;

    // Fenced code
    if (line.trim().startsWith("```")) {
      if (inCode) {
        out.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        closeLists();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(line);
      continue;
    }

    // Horizontal rule
    if (/^\s*---\s*$/.test(line)) {
      closeLists();
      out.push("<hr />");
      continue;
    }

    // Headings
    const h = /^(#{1,6})\s+(.+?)\s*$/.exec(line);
    if (h) {
      closeLists();
      const level = h[1].length;
      out.push(`<h${level}>${renderInline(h[2], notes)}</h${level}>`);
      continue;
    }

    // Blockquote
    if (/^\s*>\s?/.test(line)) {
      closeLists();
      out.push(
        `<blockquote>${renderInline(line.replace(/^\s*>\s?/, ""), notes)}</blockquote>`,
      );
      continue;
    }

    // Unordered list
    const ul = /^\s*[-*]\s+(.*)$/.exec(line);
    if (ul) {
      if (listStack[listStack.length - 1] !== "ul") {
        closeLists();
        listStack.push("ul");
        out.push("<ul>");
      }
      out.push(`<li>${renderInline(ul[1], notes)}</li>`);
      continue;
    }

    // Ordered list
    const ol = /^\s*\d+\.\s+(.*)$/.exec(line);
    if (ol) {
      if (listStack[listStack.length - 1] !== "ol") {
        closeLists();
        listStack.push("ol");
        out.push("<ol>");
      }
      out.push(`<li>${renderInline(ol[1], notes)}</li>`);
      continue;
    }

    // Blank line closes any list
    if (/^\s*$/.test(line)) {
      closeLists();
      out.push("");
      continue;
    }

    // Paragraph
    closeLists();
    out.push(`<p>${renderInline(line, notes)}</p>`);
  }

  if (inCode) {
    // Unclosed fence — render what we have
    out.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
  }
  closeLists();

  return out.join("\n");
}
