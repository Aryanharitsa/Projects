import Link from 'next/link';
import { candidates } from '@/data/candidates';

export default function CV({ params }: { params: { id: string } }) {
  const person = candidates.find(c => String(c.id) === params.id);
  if (!person) {
    return (
      <main className="min-h-screen bg-black text-white grid place-items-center">
        <div className="text-center">
          <p className="mb-4">CV not found.</p>
          <Link href="/" className="text-indigo-400 hover:underline">Back</Link>
        </div>
      </main>
    );
  }
  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="max-w-3xl mx-auto px-4 py-10">
        <Link href="/" className="text-indigo-400 hover:underline">← Back</Link>
        <h1 className="text-3xl font-semibold mt-4">{person.name}</h1>
        <p className="text-white/60 mt-1">{person.headline}</p>
        <div className="prose prose-invert mt-6 whitespace-pre-wrap">{person.cv}</div>
      </div>
    </main>
  );
}
