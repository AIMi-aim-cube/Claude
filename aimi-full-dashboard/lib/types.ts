export type MarketPoint = { date: string; close: number };
export type MarketQuote = { symbol: string; price: number; changePct: number; points: MarketPoint[]; source: string };
export type NewsItem = { title: string; url: string; source: string; publishedAt?: string; sentiment?: 'positive'|'neutral'|'negative' };
