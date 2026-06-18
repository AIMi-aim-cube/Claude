import { NextResponse } from 'next/server';
import { strategySignals } from '@/lib/mock';
export async function GET() { return NextResponse.json({ signals: strategySignals, regime: { state:'Transition', riskScore:64, volatility:'Medium', updatedAt:new Date().toISOString() } }); }
