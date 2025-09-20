import { NextResponse } from 'next/server';
import fs from 'node:fs/promises';
import path from 'node:path';

type Cand = {
  id: number;
  name: string;
  title: string;
  location: string;
  score: number;
  skills: string[];
};

const filePath = path.join(process.cwd(), 'src', 'data', 'custom.json');

export async function GET() {
  try {
    const buf = await fs.readFile(filePath, 'utf8');
    const arr = JSON.parse(buf);
    return NextResponse.json(arr);
  } catch {
    return NextResponse.json([], { status: 200 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { name, title, location, score, skills } = body || {};
    if (!name || !title) {
      return NextResponse.json({ error: 'name and title are required' }, { status: 400 });
    }
    const parsed: Cand = {
      id: Math.floor(Date.now()/1000),
      name: String(name).trim(),
      title: String(title).trim(),
      location: String(location || 'Unknown'),
      score: Math.max(0, Math.min(100, Number(score ?? 70))),
      skills: Array.isArray(skills) ? skills.map((s: any) => String(s)) :
              String(skills || '').split(',').map(s => s.trim()).filter(Boolean),
    };

    // read current file
    let current: Cand[] = [];
    try {
      const buf = await fs.readFile(filePath, 'utf8');
      current = JSON.parse(buf);
    } catch { current = []; }

    current.push(parsed);
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, JSON.stringify(current, null, 2), 'utf8');

    return NextResponse.json({ ok: true, id: parsed.id });
  } catch (e) {
    return NextResponse.json({ error: 'failed to save' }, { status: 500 });
  }
}
