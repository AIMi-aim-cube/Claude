import { NextResponse } from 'next/server';

export async function GET() {
  const key = process.env.FINNHUB_API_KEY;
  if (key) {
    const res = await fetch(`https://finnhub.io/api/v1/news?category=general&token=${key}`, { next: { revalidate: 600 } });
    if (res.ok) {
      const json = await res.json();
      return NextResponse.json({ source: 'Finnhub', items: json.slice(0,12).map((n:any)=>({title:n.headline,url:n.url,source:n.source,publishedAt:new Date(n.datetime*1000).toISOString(),sentiment:'neutral'})) });
    }
  }
  return NextResponse.json({ source:'Demo fallback', items:[
    {title:'AI infrastructure remains a central market theme', url:'#', source:'AIMi Intelligence', sentiment:'positive'},
    {title:'Rates, liquidity and earnings breadth drive regime uncertainty', url:'#', source:'AIMi Macro', sentiment:'neutral'},
    {title:'Volatility watch: cross-asset correlations rising', url:'#', source:'FinLLAMA Monitor', sentiment:'negative'}
  ]});
}
