'use client';

import { useState } from 'react';
import type { RaterStat } from '@/lib/calibration';
import { ARCHETYPE_LABEL, type Archetype } from '@/lib/panel_seed';

const BAND_PILL: Record<string, string> = {
  calibrated: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  lenient: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  severe: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
};

type Props = {
  open: boolean;
  onClose: () => void;
  raters: RaterStat[];
  onRemove: (interviewerId: string) => void;
  onAdd: (name: string, title: string, archetype: Archetype) => void;
  onReset: () => void;
};

export default function PanelDrawer({ open, onClose, raters, onRemove, onAdd, onReset }: Props) {
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [archetype, setArchetype] = useState<Archetype>('calibrated');

  if (!open) return null;

  const submit = () => {
    if (!name.trim()) return;
    onAdd(name.trim(), title.trim(), archetype);
    setName('');
    setTitle('');
    setArchetype('calibrated');
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <aside className="cc-cal-drawer relative h-full w-full max-w-md overflow-y-auto border-l border-white/10 bg-[#0b0b12] p-5 shadow-2xl">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-fuchsia-300/80">Panel</div>
            <h2 className="text-lg font-semibold text-white">Manage interviewers</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-sm text-white/70 hover:bg-white/10"
          >
            Close
          </button>
        </div>

        {/* current panel */}
        <div className="mt-4 space-y-2">
          {raters.length === 0 && (
            <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-4 text-center text-sm text-white/50">
              No interviewers yet.
            </div>
          )}
          {raters.map(r => (
            <div key={r.interviewerId} className="flex items-center justify-between rounded-xl border border-white/8 bg-white/[0.03] p-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-white">{r.name}</div>
                <div className="truncate text-[11px] text-white/45">
                  {r.title || 'Interviewer'} · {r.count} ratings
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${BAND_PILL[r.band]}`}>
                  {r.band}
                </span>
                <button
                  onClick={() => onRemove(r.interviewerId)}
                  className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/60 hover:border-rose-400/40 hover:text-rose-200"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* add form */}
        <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <div className="text-[11px] uppercase tracking-wider text-white/45">Add interviewer</div>
          <div className="mt-2 space-y-2">
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Name"
              className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder-white/30 focus:border-fuchsia-400/60 focus:outline-none"
            />
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Title (e.g. Senior Engineer)"
              className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder-white/30 focus:border-fuchsia-400/60 focus:outline-none"
            />
            <div>
              <label className="text-[10px] uppercase tracking-wider text-white/40">
                Seed their scores as
              </label>
              <select
                value={archetype}
                onChange={e => setArchetype(e.target.value as Archetype)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-fuchsia-400/60 focus:outline-none"
              >
                {(Object.keys(ARCHETYPE_LABEL) as Archetype[]).map(a => (
                  <option key={a} value={a} className="bg-[#0b0b12]">
                    {ARCHETYPE_LABEL[a]}
                  </option>
                ))}
              </select>
              <div className="mt-1 text-[10px] text-white/40">
                New interviewers are auto-scored on every shortlisted candidate so the
                audit stays populated; edit any cell in the grid to override.
              </div>
            </div>
            <button
              onClick={submit}
              disabled={!name.trim()}
              className="w-full rounded-lg bg-gradient-to-r from-fuchsia-400 to-sky-400 px-3 py-2 text-sm font-semibold text-black hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Add to panel
            </button>
          </div>
        </div>

        <button
          onClick={onReset}
          className="mt-4 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/60 hover:bg-white/10"
        >
          Reset panel to seed
        </button>
      </aside>
    </div>
  );
}
