"use client";

import { DragEvent, useCallback, useRef, useState } from "react";
import { uploadKyc } from "../../lib/api";

type Stage = "idle" | "uploading" | "ipfs" | "chain" | "done";

const STAGES: { key: Stage; title: string; body: string }[] = [
  { key: "uploading", title: "Hash & upload", body: "SHA-256 the PDF locally, stream to ai-ocr." },
  { key: "ipfs", title: "Pin to IPFS", body: "Kubo /api/v0/add returns the CID." },
  { key: "chain", title: "Anchor on-chain", body: "Sign attest(docHash, subject, verifier) and wait for the receipt." },
];

export default function KYCPage() {
  const [file, setFile] = useState<File | null>(null);
  const [wallet, setWallet] = useState("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266");
  const [verifier, setVerifier] = useState("VERIFIER-1");
  const [stage, setStage] = useState<Stage>("idle");
  const [drag, setDrag] = useState(false);
  const [resp, setResp] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  }, []);

  const submit = useCallback(async () => {
    if (!file) {
      setErr("Choose a PDF first");
      return;
    }
    setErr(null);
    setResp(null);
    setStage("uploading");
    try {
      // Stagger the visible stage updates so the timeline animates while the
      // single underlying request is in flight.
      const t1 = setTimeout(() => setStage("ipfs"), 600);
      const t2 = setTimeout(() => setStage("chain"), 1500);
      const out = await uploadKyc(file, wallet.trim(), verifier.trim() || "VERIFIER-1");
      clearTimeout(t1);
      clearTimeout(t2);
      setResp(out);
      setStage("done");
    } catch (e: any) {
      setErr(e.message || "Upload failed");
      setStage("idle");
    }
  }, [file, wallet, verifier]);

  return (
    <div className="space-y-6">
      <header>
        <span className="pill pill-ok">PDF · IPFS · on-chain</span>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
          KYC Pipeline
        </h1>
        <p className="mt-1 max-w-2xl text-[13.5px] text-white/60">
          Drop a PAN PDF and a subject wallet. The document is hashed locally,
          pinned to IPFS, and the digest is recorded on the AttestationRegistry
          contract. The PDF itself never appears on-chain.
        </p>
      </header>

      <section className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <div className="glass p-5">
          <div className="label">Subject wallet</div>
          <input
            className="input font-mono"
            value={wallet}
            onChange={(e) => setWallet(e.target.value)}
            placeholder="0x…"
          />
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <div className="label">Verifier ID</div>
              <input
                className="input font-mono"
                value={verifier}
                onChange={(e) => setVerifier(e.target.value)}
              />
            </div>
            <div>
              <div className="label">Document type</div>
              <input className="input" value="PAN (PDF)" disabled />
            </div>
          </div>

          <div className="label mt-4">Document</div>
          <div
            className={`dropzone group cursor-pointer rounded-xl p-6 text-center ${
              drag ? "dropzone-active" : ""
            }`}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
          >
            <input
              ref={fileRef}
              hidden
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <div className="text-3xl">📄</div>
            <div className="mt-2 text-sm text-white/80">
              {file ? file.name : "Drop a PDF here or click to choose"}
            </div>
            <div className="mt-1 text-[11px] text-white/40">
              {file ? `${(file.size / 1024).toFixed(1)} KB` : "Only .pdf is accepted"}
            </div>
          </div>

          <div className="mt-4 flex gap-3">
            <button className="btn-primary" onClick={submit} disabled={stage !== "idle" && stage !== "done"}>
              {stage === "idle" || stage === "done" ? "Verify & anchor" : "Working…"}
            </button>
            {file && (
              <button className="btn" onClick={() => setFile(null)}>
                Clear
              </button>
            )}
          </div>
          {err && <p className="mt-3 text-[12px] text-rose-300">{err}</p>}
        </div>

        {/* Pipeline timeline */}
        <div className="glass p-5">
          <div className="label">Pipeline</div>
          <ol className="space-y-4">
            {STAGES.map((s, i) => {
              const stageOrder: Stage[] = ["uploading", "ipfs", "chain", "done"];
              const idx = stageOrder.indexOf(stage);
              const myIdx = stageOrder.indexOf(s.key);
              const active = idx === myIdx;
              const done = idx > myIdx || stage === "done";
              return (
                <li key={s.key} className="flex items-start gap-3">
                  <span
                    className={`mt-0.5 grid h-7 w-7 place-items-center rounded-full border text-[11px] font-semibold ${
                      done
                        ? "border-teal-400/40 bg-teal-400/15 text-teal-400"
                        : active
                        ? "border-violet-400/50 bg-violet-500/15 text-violet-400 animate-pulseSoft"
                        : "border-white/10 bg-white/5 text-white/40"
                    }`}
                  >
                    {done ? "✓" : i + 1}
                  </span>
                  <div>
                    <div className={`text-[14px] ${active ? "text-white" : done ? "text-teal-400" : "text-white/55"}`}>
                      {s.title}
                    </div>
                    <div className="text-[12px] text-white/45">{s.body}</div>
                  </div>
                </li>
              );
            })}
          </ol>

          {resp && (
            <div className="mt-5 space-y-3 rounded-xl border border-teal-400/30 bg-teal-500/[0.05] p-4">
              <Row k="docHash" v={resp.docHash} mono copy />
              <Row k="ipfsCid" v={resp.ipfsCid} mono copy />
              <Row k="onchainTx" v={resp.onchainTx} mono copy />
              <Row k="block" v={String(resp.blockNumber)} mono />
              <Row k="subject" v={resp.subject} mono />
              <Row k="verifierId" v={resp.verifierId} />
              <div className="pt-1 text-[11.5px] text-white/55">
                Look this up any time at{" "}
                <a className="underline" href={`/attestations?hash=${resp.docHash}`}>
                  /attestations?hash={resp.docHash.slice(0, 10)}…
                </a>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Row({
  k,
  v,
  mono = false,
  copy = false,
}: {
  k: string;
  v: string;
  mono?: boolean;
  copy?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="w-24 text-[11px] uppercase tracking-wider text-white/40">{k}</span>
      <span
        className={`flex-1 truncate ${mono ? "font-mono" : ""} text-[12.5px] text-white/85`}
        title={v}
      >
        {v}
      </span>
      {copy && (
        <button
          className="text-[11px] text-teal-400 hover:underline"
          onClick={() => navigator.clipboard.writeText(v)}
        >
          copy
        </button>
      )}
    </div>
  );
}
