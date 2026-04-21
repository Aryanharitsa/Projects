const BASE = "/api";

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text || "(no body)"}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  listNotes:    ()                 => request("/notes"),
  getNote:      (id)               => request(`/notes/${id}`),
  createNote:   (n)                => request("/notes", {
    method: "POST", body: JSON.stringify(n),
  }),
  updateNote:   (id, n)            => request(`/notes/${id}`, {
    method: "PUT", body: JSON.stringify(n),
  }),
  deleteNote:   (id)               => request(`/notes/${id}`, {
    method: "DELETE",
  }),
  rebuild:      ()                 => request("/notes/rebuild", {
    method: "POST",
  }),
  getGraph:     ()                 => request("/graph"),
  health:       ()                 => request("/health"),
};
