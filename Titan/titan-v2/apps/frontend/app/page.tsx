export default function Home() {
  return (
    <section className="grid gap-6 md:grid-cols-2">
      <div className="rounded-xl border bg-white p-6">
        <h2 className="text-lg font-medium mb-2">KYC</h2>
        <p className="text-sm text-gray-600 mb-4">Upload PAN → IPFS hash → on-chain attestation.</p>
        <a
          href="http://localhost:8000/docs#/"
          target="_blank"
          className="inline-block rounded bg-black px-4 py-2 text-white"
        >
          Open KYC API
        </a>
      </div>
      <div className="rounded-xl border bg-white p-6">
        <h2 className="text-lg font-medium mb-2">AML Engine (Fintrace)</h2>
        <p className="text-sm text-gray-600 mb-4">
          Score a batch of transactions now (stub), or open Fintrace console.
        </p>
        <div className="flex gap-3">
          <a href="/aml" className="rounded border px-4 py-2">Open AML UI</a>
          <a href="http://localhost:8002/docs" target="_blank" className="rounded bg-black px-4 py-2 text-white">Fintrace Docs</a>
        </div>
      </div>
    </section>
  );
}
