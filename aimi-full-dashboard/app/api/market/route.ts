import { NextResponse } from 'next/server';
import { watchlist } from '@/lib/mock';

async function yahoo(symbol: string) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=1mo&interval=1d`;
  const res = await fetch(url, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error('market fetch failed');
  const json = await res.json();
  const result = json.chart?.result?.[0];
  const closes = result?.indicators?.quote?.[0]?.close || [];
  const times = result?.timestamp || [];
  const points = closes.map((c: number, i: number) => ({ date: new Date(times[i]*1000).toISOString().slice(5,10), close: Number(c?.toFixed?.(2) || c) })).filter((p:any)=>Number.isFinite(p.close));
  const price = points.at(-1)?.close ?? 0;
  const prev = points.at(-2)?.close ?? price;
  return { symbol, price, changePct: prev ? Number((((price-prev)/prev)*100).toFixed(2)) : 0, points, source: 'Yahoo Finance chart API' };
}

function fallback(symbol: string, idx: number) {
  const base = 80 + idx * 14;
  const points = Array.from({length: 30}, (_, i) => ({ date: `D${i+1}`, close: Number((base + Math.sin(i/3)*4 + i*.65).toFixed(2)) }));
  const price = points.at(-1)!.close; const prev = points.at(-2)!.close;
  return { symbol, price, changePct: Number((((price-prev)/prev)*100).toFixed(2)), points, source: 'Demo fallback: set live API access in deployment' };
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbols = (searchParams.get('symbols') || watchlist.join(',')).split(',').map(s=>s.trim()).filter(Boolean).slice(0,12);
  const data = await Promise.all(symbols.map((s,i)=>yahoo(s).catch(()=>fallback(s,i))));
  return NextResponse.json({ data, updatedAt: new Date().toISOString() });
}
