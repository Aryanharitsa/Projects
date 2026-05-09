'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  buildCalendar,
  downloadIcs,
  formatSlotLabel,
  proposeSlots,
  type SlotInput,
} from '@/lib/ics';

type Props = {
  candidateName: string;
  candidateEmail?: string;
  roleName: string;
  defaultSummary?: string;
  defaultDescription?: string;
  defaultLocation?: string;
  durationMin?: number;
};

export default function SlotProposer(props: Props) {
  const {
    candidateName,
    candidateEmail,
    roleName,
    defaultSummary,
    defaultDescription,
    defaultLocation = 'Google Meet (link to follow)',
    durationMin = 60,
  } = props;

  const [slots, setSlots] = useState<number[]>([]);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [duration, setDuration] = useState(durationMin);
  const [summary, setSummary] = useState(
    defaultSummary ?? `${roleName} interview — ${candidateName}`,
  );
  const [description, setDescription] = useState(
    defaultDescription ??
      `Hi ${candidateName.split(' ')[0]} — please pick the slot that works best for you. Reply with your choice and I'll confirm with the panel.`,
  );
  const [location, setLocation] = useState(defaultLocation);
  const [organizerEmail, setOrganizerEmail] = useState('');

  // Hydrate proposed slots once on mount (client-only — Date is local).
  useEffect(() => {
    const next = proposeSlots({ daysAhead: 10, hours: [10, 14, 16], slotsPerDay: 2, maxSlots: 6 });
    setSlots(next);
    setPicked(new Set(next.slice(0, 3)));
  }, []);

  const pickedList = useMemo(
    () => [...picked].sort((a, b) => a - b),
    [picked],
  );

  const toggle = (ms: number) => {
    setPicked(prev => {
      const next = new Set(prev);
      if (next.has(ms)) next.delete(ms);
      else next.add(ms);
      return next;
    });
  };

  const regenerate = () => {
    const next = proposeSlots({ daysAhead: 10, hours: [10, 14, 16], slotsPerDay: 2, maxSlots: 6 });
    setSlots(next);
    setPicked(new Set(next.slice(0, 3)));
  };

  const onDownload = () => {
    if (pickedList.length === 0) return;
    const slotInputs: SlotInput[] = pickedList.map((startMs, i) => ({
      startUtcMs: startMs,
      durationMin: duration,
      summary: pickedList.length > 1
        ? `${summary} — option ${i + 1} of ${pickedList.length}`
        : summary,
      description,
      location,
      organizer: organizerEmail
        ? { name: 'Recruiter', email: organizerEmail.trim() }
        : undefined,
      attendees: candidateEmail
        ? [{ name: candidateName, email: candidateEmail.trim() }]
        : undefined,
    }));
    const ics = buildCalendar(slotInputs);
    const safe = `${candidateName}_${roleName}`
      .replace(/[^a-z0-9]+/gi, '_')
      .replace(/^_+|_+$/g, '') || 'interview';
    downloadIcs(`${safe}.ics`, ics);
  };

  return (
    <div className="cc-slots rounded-xl border border-white/10 bg-white/[0.04] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Schedule interview
          </div>
          <div className="text-sm font-medium text-white">{candidateName}</div>
        </div>
        <button
          type="button"
          onClick={regenerate}
          className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10"
          title="Regenerate proposed slots"
        >
          ↻ refresh slots
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {slots.map(ms => {
          const isOn = picked.has(ms);
          return (
            <button
              type="button"
              key={ms}
              onClick={() => toggle(ms)}
              className={`cc-slot rounded-lg border px-2.5 py-2 text-left text-[11px] transition ${
                isOn
                  ? 'border-violet-400/60 bg-violet-400/15 text-violet-100'
                  : 'border-white/10 bg-white/5 text-white/70 hover:bg-white/10'
              }`}
            >
              <span className="font-medium">{formatSlotLabel(ms)}</span>
              <span className="mt-0.5 block font-mono text-[10px] opacity-70">
                {duration} min
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-4 space-y-2">
        <label className="block text-[10px] uppercase tracking-wider text-white/45">
          Summary
        </label>
        <input
          value={summary}
          onChange={e => setSummary(e.target.value)}
          className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white focus:border-indigo-400/60 focus:outline-none"
        />
        <label className="block pt-2 text-[10px] uppercase tracking-wider text-white/45">
          Description
        </label>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white/85 focus:border-indigo-400/60 focus:outline-none"
        />
        <div className="grid gap-2 pt-2 md:grid-cols-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-white/45">
              Location
            </label>
            <input
              value={location}
              onChange={e => setLocation(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white focus:border-indigo-400/60 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-white/45">
              Duration
            </label>
            <select
              value={duration}
              onChange={e => setDuration(Number(e.target.value))}
              className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white focus:border-indigo-400/60 focus:outline-none"
            >
              {[30, 45, 60, 75, 90].map(m => (
                <option key={m} value={m}>{m} min</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-white/45">
              Organizer email
            </label>
            <input
              type="email"
              placeholder="optional"
              value={organizerEmail}
              onChange={e => setOrganizerEmail(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white focus:border-indigo-400/60 focus:outline-none"
            />
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="text-[11px] text-white/55">
          {pickedList.length === 0
            ? 'Pick at least one slot to export.'
            : `${pickedList.length} slot${pickedList.length === 1 ? '' : 's'} → one .ics file with ${pickedList.length} VEVENT${pickedList.length === 1 ? '' : 's'}.`}
        </div>
        <button
          type="button"
          disabled={pickedList.length === 0}
          onClick={onDownload}
          className="rounded-lg bg-gradient-to-r from-teal-400 to-violet-400 px-3.5 py-2 text-sm font-semibold text-black shadow-md disabled:cursor-not-allowed disabled:from-white/10 disabled:to-white/10 disabled:text-white/40"
        >
          Download .ics
        </button>
      </div>
    </div>
  );
}
