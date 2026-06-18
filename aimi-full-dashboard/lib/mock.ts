export const watchlist = ['SPY','QQQ','NVDA','TSLA','PLTR','BTC-USD','ETH-USD','GLD','USO'];
export const strategySignals = [
 {asset:'NVDA',strategy:'Momentum',direction:'Long bias',confidence:82,risk:'Medium',entry:'Above 146',horizon:'Swing',impact:'AI beta exposure',regime:'Risk-On'},
 {asset:'SPY',strategy:'Breakout',direction:'Neutral → Long',confidence:68,risk:'Low',entry:'Break above range',horizon:'Short',impact:'Broad market beta',regime:'Transition'},
 {asset:'GLD',strategy:'Relative Value',direction:'Long bias',confidence:74,risk:'Medium',entry:'Pullback zone',horizon:'Medium',impact:'Defensive diversifier',regime:'Risk-Off'},
 {asset:'BTC-USD',strategy:'Volatility',direction:'Watch',confidence:61,risk:'High',entry:'After vol compression',horizon:'Short',impact:'High volatility sleeve',regime:'Transition'}
];
export const lessons = [
 {title:'Financial Freedom Number',tier:1,progress:90,type:'Video'}, {title:'Compounding without the jargon',tier:1,progress:72,type:'Lesson'},
 {title:'Risk, volatility and drawdowns',tier:2,progress:30,type:'Quiz'}, {title:'Portfolio diversification intuition',tier:3,progress:15,type:'Workshop'},
 {title:'Market regimes and factors',tier:4,progress:0,type:'Briefing'}, {title:'FinLLAMA Quant Signals',tier:5,progress:0,type:'Lab'}
];
export const auditLogs = [
 'Disclosure v1.0 acknowledged', 'Tier entitlement checked: signals', 'AIMi refusal logged: personal advice boundary', 'Broker hand-off confirmation shown', 'Signal approval status: human-reviewed'
];
