"""
AIMi — Backtesting Engine
=========================
Vectorised backtester for any BaseStrategy. Models:
  • next-bar execution (no look-ahead: positions shift one bar)
  • transaction costs + slippage on turnover
  • full risk report via RiskAnalyzer
  • trade log extraction

Usage:
    from strategies import get_strategy
    from scraper import market_data
    bt = Backtester()
    result = bt.run(get_strategy("momentum"), market_data.history("AAPL", "2y"))
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from strategies import BaseStrategy, StrategyResult
from portfolio import RiskAnalyzer


@dataclass
class BacktestResult:
    strategy: str
    ticker: str
    start: str
    end: str
    initial_capital: float
    final_equity: float
    total_return: float
    n_trades: int
    win_rate: float
    risk: dict
    equity_curve: pd.Series = field(repr=False, default=None)
    drawdown_curve: pd.Series = field(repr=False, default=None)
    trades: list = field(default_factory=list)

    def to_dict(self, include_curves: bool = True) -> dict:
        d = {
            "strategy": self.strategy, "ticker": self.ticker,
            "start": self.start, "end": self.end,
            "initial_capital": self.initial_capital,
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return * 100, 2),
            "n_trades": self.n_trades,
            "win_rate_pct": round(self.win_rate * 100, 1),
            "risk": self.risk,
            "trades": self.trades[-50:],
        }
        if include_curves and self.equity_curve is not None:
            d["equity_curve"] = {str(k.date()): round(float(v), 2)
                                 for k, v in self.equity_curve.items()}
            d["drawdown_curve"] = {str(k.date()): round(float(v), 4)
                                   for k, v in self.drawdown_curve.items()}
        return d


class Backtester:
    def __init__(self, initial_capital: float = 100_000.0,
                 commission_bps: float = 5.0, slippage_bps: float = 2.0):
        self.capital = initial_capital
        self.cost = (commission_bps + slippage_bps) / 10_000.0

    def run(self, strategy: BaseStrategy, df: pd.DataFrame,
            ticker: str = "ASSET") -> BacktestResult:
        res: StrategyResult = strategy.generate(df)
        pos = res.positions.reindex(df.index).fillna(0.0)

        # next-bar execution: today's signal earns tomorrow's return
        exec_pos = pos.shift(1).fillna(0.0)
        asset_rets = df["close"].pct_change().fillna(0.0)

        turnover = exec_pos.diff().abs().fillna(exec_pos.abs())
        strat_rets = exec_pos * asset_rets - turnover * self.cost

        equity = self.capital * (1 + strat_rets).cumprod()
        drawdown = equity / equity.cummax() - 1

        trades = self._extract_trades(exec_pos, df["close"])
        wins = sum(1 for t in trades if t["pnl_pct"] > 0)
        risk = RiskAnalyzer.analyze(strat_rets, benchmark=asset_rets).to_dict()

        return BacktestResult(
            strategy=strategy.name,
            ticker=ticker,
            start=str(df.index[0].date()),
            end=str(df.index[-1].date()),
            initial_capital=self.capital,
            final_equity=float(equity.iloc[-1]),
            total_return=float(equity.iloc[-1] / self.capital - 1),
            n_trades=len(trades),
            win_rate=wins / len(trades) if trades else 0.0,
            risk=risk,
            equity_curve=equity,
            drawdown_curve=drawdown,
            trades=trades,
        )

    def compare(self, strategies: list[BaseStrategy], df: pd.DataFrame,
                ticker: str = "ASSET") -> dict:
        """Run several strategies on the same data, plus buy & hold benchmark."""
        out = {s.name: self.run(s, df, ticker).to_dict(include_curves=False)
               for s in strategies}
        bh = self.capital * (df["close"] / df["close"].iloc[0])
        out["buy_and_hold"] = {
            "final_equity": round(float(bh.iloc[-1]), 2),
            "total_return_pct": round(float(bh.iloc[-1] / self.capital - 1) * 100, 2),
            "risk": RiskAnalyzer.analyze(df["close"].pct_change()).to_dict(),
        }
        return out

    @staticmethod
    def _extract_trades(pos: pd.Series, close: pd.Series) -> list[dict]:
        trades, entry_i = [], None
        sign = np.sign(pos)
        for i in range(1, len(sign)):
            prev, cur = sign.iloc[i - 1], sign.iloc[i]
            if prev == 0 and cur != 0:
                entry_i = i
            elif prev != 0 and cur != prev:  # exit or flip
                if entry_i is not None:
                    e_px, x_px = float(close.iloc[entry_i]), float(close.iloc[i])
                    direction = float(prev)
                    trades.append({
                        "entry": str(close.index[entry_i].date()),
                        "exit": str(close.index[i].date()),
                        "side": "LONG" if direction > 0 else "SHORT",
                        "entry_price": round(e_px, 2),
                        "exit_price": round(x_px, 2),
                        "pnl_pct": round(direction * (x_px / e_px - 1) * 100, 2),
                    })
                entry_i = i if cur != 0 else None
        return trades
