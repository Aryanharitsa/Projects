import { useEffect, useState } from "react";
import { Save, Trash2, X, Sparkles, Tag, Clock } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

export default function NoteEditor({ noteId, onClose, onSaved, onDeleted }) {
  const [loading, setLoading] = useState(false);
  const [saving,  setSaving]  = useState(false);
  const [note,    setNote]    = useState(null);
  const [title,   setTitle]   = useState("");
  const [body,    setBody]    = useState("");
  const [tags,    setTags]    = useState("");

  useEffect(() => {
    if (noteId == null) {
      setNote(null); setTitle(""); setBody(""); setTags("");
      return;
    }
    setLoading(true);
    api.getNote(noteId)
      .then((n) => {
        setNote(n);
        setTitle(n.title); setBody(n.body); setTags(n.tags);
      })
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, [noteId]);

  async function save() {
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }
    setSaving(true);
    try {
      const saved = note
        ? await api.updateNote(note.id, { title, body, tags })
        : await api.createNote({ title, body, tags });
      toast.success(note ? "Thought updated · synapses rewired" : "Thought captured · synapses forming");
      onSaved?.(saved);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function destroy() {
    if (!note) return;
    if (!confirm(`Delete "${note.title}"?`)) return;
    try {
      await api.deleteNote(note.id);
      toast.success("Thought removed · synapses rewired");
      onDeleted?.(note.id);
    } catch (e) {
      toast.error(e.message);
    }
  }

  const isNew = !note && noteId == null;

  return (
    <aside className="flex flex-col h-full bg-white/[0.02] border-l border-white/10 backdrop-blur-sm">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-white/50">
          <Sparkles className="h-3.5 w-3.5 text-fuchsia-300" />
          {isNew ? "New thought" : note ? "Editing" : "Loading…"}
        </div>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white/80 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="A crisp title for your thought…"
          disabled={loading}
          className="w-full bg-transparent text-lg font-semibold text-white placeholder:text-white/30 outline-none border-b border-white/10 pb-2 focus:border-fuchsia-400/60 transition-colors"
        />

        <div className="flex items-center gap-2 text-xs text-white/50">
          <Tag className="h-3.5 w-3.5" />
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="space separated · ml math ideas"
            className="flex-1 bg-transparent outline-none text-white/80 placeholder:text-white/30"
          />
        </div>

        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Write the thought. SynapseOS will find where it belongs."
          disabled={loading}
          rows={14}
          className="w-full bg-black/20 border border-white/10 rounded-xl px-4 py-3 text-sm text-white/90 placeholder:text-white/30 outline-none focus:border-fuchsia-400/50 resize-none"
        />

        {note && (
          <div className="flex items-center gap-4 text-[11px] text-white/40 pt-2 border-t border-white/5">
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              created {new Date(note.created_at).toLocaleString()}
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              updated {new Date(note.updated_at).toLocaleString()}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 px-4 py-3 border-t border-white/10">
        <button
          onClick={save}
          disabled={saving || loading}
          className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-fuchsia-500/30 hover:shadow-fuchsia-500/50 disabled:opacity-60 transition-shadow"
        >
          <Save className="h-4 w-4" />
          {saving ? "Saving…" : note ? "Save" : "Capture thought"}
        </button>
        {note && (
          <button
            onClick={destroy}
            className="inline-flex items-center gap-2 rounded-full border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm text-red-200 hover:bg-red-500/20 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </button>
        )}
      </div>
    </aside>
  );
}
