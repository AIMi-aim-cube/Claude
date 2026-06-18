import { NextResponse } from 'next/server';
import { GoogleGenerativeAI } from '@google/generative-ai';

export async function POST(req: Request) {
  const { message, tier = 1, riskProfile = 'Balanced' } = await req.json();
  const compliance = 'Educational information only. AIMi does not execute trades, hold funds, or provide personalised investment advice.';
  const key = process.env.GOOGLE_GENERATIVE_AI_API_KEY;
  const system = `You are AIMi, Dr Ana Armstrong's AI investment guide. User tier ${tier}; risk profile ${riskProfile}. Be educational, tier-aware, compliance-safe. No personalised advice, no trade execution, no guarantees. For Tier 1 avoid asset-specific trade discussion. For Tier 4-5 discuss market intelligence as non-personalised decision support.`;
  if (key) {
    try {
      const genAI = new GoogleGenerativeAI(key);
      const model = genAI.getGenerativeModel({ model: process.env.GEMINI_MODEL || 'gemini-1.5-flash' });
      const result = await model.generateContent(`${system}\n\nUser: ${message}\n\nInclude one short compliance note.`);
      return NextResponse.json({ answer: result.response.text(), source:'Gemini API', compliance });
    } catch (e) {}
  }
  return NextResponse.json({ answer: `AIMi view: ${message ? 'I can help you understand this in plain English and show the relevant learning path, market context, and tier-appropriate intelligence.' : 'Ask me about markets, risk, lessons, or AIMi features.'}\n\n${compliance}`, source:'Demo fallback', compliance });
}
