'use client';

import { useEffect, useMemo, useState } from 'react';
import type { PeerOffer } from '@/lib/peer_parity';
import { makePeerId } from '@/lib/peer_parity';

type Props = {
  open: boolean;
  peers: PeerOffer[];
  onClose: () => void;
  onAdd: (peer: PeerOffer) => void;
  onRemove: (peerId: string) => void;
};

export default function PeerPoolDrawer({ open, peers, onClose, onAdd, onRemove }: Props) {
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    if (!open) setShowForm(false);
  }, [open]);

  if (!open) return null;
  return (
    <div className="cc-parity-drawer fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        role="button"
        tabIndex={-1}
        aria-label="Close peer pool"
      />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-[#0c0c14] shadow-2xl">
        <header className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-white/45">Peer pool</div>
            <h3 className="text-base font-semibold">Team accepted offers ({peers.length})</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs text-white/75 hover:bg-white/10"
          >
            Close ✕
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div className="flex items-center justify-between">
            <p className="max-w-sm text-[11px] text-white/55">
              Peers shape the parity verdict. Add the offers your team has
              actually accepted; the engine fits a regression to flag drift.
            </p>
            <button
              onClick={() => setShowForm(s => !s)}
              className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs text-white hover:bg-white/10"
            >
              {showForm ? 'Cancel' : '+ Add peer'}
            </button>
          </div>

          {showForm && (
            <PeerForm
              onSubmit={p => {
                onAdd(p);
                setShowForm(false);
              }}
            />
          )}

          <div className="mt-4 space-y-2.5">
            {peers.length === 0 && (
              <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.02] p-4 text-center text-[11px] text-white/45">
                No peers yet. Add one above or publish from Offer Studio.
              </div>
            )}
            {peers.map(p => (
              <article key={p.id} className="cc-parity-peer rounded-xl border border-white/10 bg-white/[0.03] p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium">{p.candidateName}</div>
                    <div className="text-[10px] text-white/45">
                      {p.roleName} · {p.seniority} · {p.location}
                    </div>
                  </div>
                  <button
                    onClick={() => onRemove(p.id)}
                    className="rounded-md border border-rose-400/25 bg-rose-400/10 px-1.5 py-0.5 text-[10px] text-rose-200 hover:bg-rose-400/20"
                    title="Remove from peer pool"
                  >
                    Remove
                  </button>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-1.5 text-[11px]">
                  <Cell label="Composite" value={p.composite == null ? '—' : String(p.composite)} />
                  <Cell label="Base" value={`₹${p.base} LPA`} />
                  <Cell label="Equity" value={`${p.equityPct.toFixed(3)}%`} />
                  <Cell label="Sign-on" value={`₹${p.signOn} LPA`} />
                  <Cell label="Bonus" value={`${p.targetBonusPct}%`} />
                  <Cell label="Accepted" value={p.acceptedAt} />
                </div>
                {p.source && (
                  <div className="mt-1 text-[10px] uppercase tracking-wider text-white/30">
                    {p.source}
                  </div>
                )}
              </article>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/8 bg-black/20 px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-white/40">{label}</div>
      <div className="mt-0.5 truncate font-mono text-[11px] text-white">{value}</div>
    </div>
  );
}

function PeerForm({ onSubmit }: { onSubmit: (peer: PeerOffer) => void }) {
  const [name, setName] = useState('');
  const [roleName, setRoleName] = useState('');
  const [seniority, setSeniority] = useState('senior');
  const [location, setLocation] = useState('bengaluru');
  const [composite, setComposite] = useState<string>('75');
  const [base, setBase] = useState<string>('48');
  const [equity, setEquity] = useState<string>('0.15');
  const [signOn, setSignOn] = useState<string>('4');
  const [bonus, setBonus] = useState<string>('12');
  const [accepted, setAccepted] = useState<string>(new Date().toISOString().slice(0, 10));

  const valid = useMemo(() => name.trim() && Number(base) > 0, [name, base]);

  return (
    <form
      className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3"
      onSubmit={e => {
        e.preventDefault();
        if (!valid) return;
        onSubmit({
          id: makePeerId(),
          candidateName: name.trim(),
          roleName: roleName.trim() || `${seniority} engineer`,
          seniority,
          location: location.toLowerCase().trim(),
          composite: composite.trim() ? Number(composite) : null,
          base: Number(base),
          equityPct: Number(equity),
          signOn: Number(signOn),
          targetBonusPct: Number(bonus),
          acceptedAt: accepted,
          source: 'manual',
        });
      }}
    >
      <div className="grid grid-cols-2 gap-2">
        <FieldText label="Name" value={name} onChange={setName} placeholder="Candidate name" />
        <FieldText label="Role" value={roleName} onChange={setRoleName} placeholder="Senior Backend Engineer" />
        <FieldSelect
          label="Seniority"
          value={seniority}
          onChange={setSeniority}
          options={['junior', 'mid', 'senior', 'staff', 'principal', 'lead']}
        />
        <FieldText label="Location" value={location} onChange={setLocation} placeholder="bengaluru" />
        <FieldText label="Composite (0-100)" value={composite} onChange={setComposite} type="number" />
        <FieldText label="Base (LPA)" value={base} onChange={setBase} type="number" />
        <FieldText label="Equity %" value={equity} onChange={setEquity} type="number" />
        <FieldText label="Sign-on (LPA)" value={signOn} onChange={setSignOn} type="number" />
        <FieldText label="Bonus %" value={bonus} onChange={setBonus} type="number" />
        <FieldText label="Accepted" value={accepted} onChange={setAccepted} type="date" />
      </div>
      <div className="mt-3 flex justify-end">
        <button
          type="submit"
          disabled={!valid}
          className="rounded-md bg-gradient-to-r from-emerald-400 to-violet-400 px-3 py-1.5 text-xs font-semibold text-black disabled:cursor-not-allowed disabled:opacity-40"
        >
          Add to pool
        </button>
      </div>
    </form>
  );
}

function FieldText({
  label, value, onChange, placeholder, type = 'text',
}: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: 'text' | 'number' | 'date' }) {
  return (
    <label className="block">
      <div className="mb-1 text-[9px] uppercase tracking-wider text-white/40">{label}</div>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-[12px] text-white outline-none focus:border-violet-400/40"
      />
    </label>
  );
}

function FieldSelect({
  label, value, onChange, options,
}: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <label className="block">
      <div className="mb-1 text-[9px] uppercase tracking-wider text-white/40">{label}</div>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-[12px] text-white outline-none focus:border-violet-400/40"
      >
        {options.map(o => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}
