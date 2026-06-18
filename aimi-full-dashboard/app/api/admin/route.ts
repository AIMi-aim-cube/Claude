import { NextResponse } from 'next/server';
export async function GET(){ return NextResponse.json({ usersByTier:[830,420,155,48,17], chatUsage:12840, brokerClicks:318, learningCompletion:42, moderationFlags:9, failedJobs:1, mrr: 54830 }); }
