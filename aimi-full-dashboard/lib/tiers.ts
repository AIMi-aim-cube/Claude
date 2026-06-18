export type Tier = 1|2|3|4|5;
export const tiers = [
  {id:1,name:'Foundation',price:'Free',features:['Plain-English market education','Ask AIMi basics','10 lessons','Daily insight summaries']},
  {id:2,name:'Investor',price:'£26/mo',features:['Conversation memory','20+ lessons','Hypothetical scenarios','Investor principles']},
  {id:3,name:'Portfolio',price:'£79/mo',features:['Illustrative allocation logic','Risk/return trade-offs','Macro impact explanations','Portfolio sync placeholder']},
  {id:4,name:'AIMi Pro',price:'£134/mo',features:['Market regime insights','AI pattern detection','Weekly briefings','Signals intelligence']},
  {id:5,name:'Quant Intelligence',price:'£199/mo',features:['FinLLAMA reasoning','Multi-strategy signals','Portfolio risk engine','Audit/replay and advisor workflows']}
] as const;
export const canAccess = (tier: Tier, required: Tier) => tier >= required;
