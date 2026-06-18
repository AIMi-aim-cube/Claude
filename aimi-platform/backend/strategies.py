"""
AIMi — Core Trading Strategies
==============================
Five institutional-grade strategies, each returning a position series
(-1 short, 0 flat, +1 long, or fractional weights) from OHLCV data.

All strategies share one interface so the backtester, signal generator
and dashboard can use them interchangeably.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class StrategyResult:
    name: str
    positions: pd.Series          # target exposure per bar
    indicators: dict = field(default_factory=dict)
    last_signal: str = "HOLD"     # BUY / SELL / HOLD
    confidence: float = 0.0       # 0..1


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> StrategyResult:
        """df: DataFrame with columns open, high, low, close, volume (DatetimeIndex)."""

    @staticmethod
    def _label(positions: pd.Series) -> tuple[str, float]:
        if len(positions) < 2:
            return "HOLD", 0.0
        cur, prev = positions.iloc[-1], positions.iloc[-2]
        if cur > prev:
            return "BUY", float(min(abs(cur), 1.0))
        if cur < prev:
            return "SELL", float(min(abs(cur - prev), 1.0))
        return ("HOLD", float(min(abs(cur), 1.0)))


class MomentumStrategy(BaseStrategy):
    """Dual moving-average crossover + rate-of-change confirmation."""
    name = "momentum"

    def __init__(self, fast: int = 20, slow: int = 50, roc_window: int = 10):
        self.fast, self.slow, self.roc = fast, slow, roc_window

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        c = df["close"]
        fast = c.rolling(self.fast).mean()
        slow = c.rolling(self.slow).mean()
        roc = c.pct_change(self.roc)
        long_sig = (fast > slow) & (roc > 0)
        short_sig = (fast < slow) & (roc < 0)
        pos = pd.Series(0.0, index=df.index)
        pos[long_sig] = 1.0
        pos[short_sig] = -1.0
        pos = pos.ffill().fillna(0.0)
        sig, conf = self._label(pos)
        return StrategyResult(self.name, pos,
                              {"sma_fast": fast, "sma_slow": slow, "roc": roc},
                              sig, conf)


class MeanReversionStrategy(BaseStrategy):
    """Bollinger-band mean reversion with RSI filter."""
    name = "mean_reversion"

    def __init__(self, window: int = 20, n_std: float = 2.0, rsi_window: int = 14):
        self.window, self.n_std, self.rsi_window = window, n_std, rsi_window

    @staticmethod
    def _rsi(close: pd.Series, window: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        c = df["close"]
        mid = c.rolling(self.window).mean()
        std = c.rolling(self.window).std()
        upper, lower = mid + self.n_std * std, mid - self.n_std * std
        rsi = self._rsi(c, self.rsi_window)

        pos = pd.Series(np.nan, index=df.index)
        pos[(c < lower) & (rsi < 30)] = 1.0    # oversold -> long
        pos[(c > upper) & (rsi > 70)] = -1.0   # overbought -> short
        pos[(c >= mid) & (pos.ffill() == 1.0)] = 0.0   # exit longs at mean
        pos[(c <= mid) & (pos.ffill() == -1.0)] = 0.0  # exit shorts at mean
        pos = pos.ffill().fillna(0.0)
        sig, conf = self._label(pos)
        return StrategyResult(self.name, pos,
                              {"bb_upper": upper, "bb_mid": mid, "bb_lower": lower, "rsi": rsi},
                              sig, conf)


class BreakoutStrategy(BaseStrategy):
    """Donchian channel breakout with ATR-scaled exposure."""
    name = "breakout"

    def __init__(self, lookback: int = 55, exit_lookback: int = 20, atr_window: int = 14):
        self.lb, self.exit_lb, self.atr_w = lookback, exit_lookback, atr_window

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        h, l, c = df["high"], df["low"], df["close"]
        upper = h.rolling(self.lb).max().shift(1)
        lower = l.rolling(self.lb).min().shift(1)
        exit_up = h.rolling(self.exit_lb).max().shift(1)
        exit_dn = l.rolling(self.exit_lb).min().shift(1)
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_w).mean()

        pos = pd.Series(np.nan, index=df.index)
        pos[c > upper] = 1.0
        pos[c < lower] = -1.0
        pos[(c < exit_dn) & (pos.ffill() == 1.0)] = 0.0
        pos[(c > exit_up) & (pos.ffill() == -1.0)] = 0.0
        pos = pos.ffill().fillna(0.0)
        # scale exposure inversely to volatility (vol targeting ~ ATR)
        vol_scale = (atr / c).rolling(5).mean()
        scale = (0.02 / vol_scale.replace(0, np.nan)).clip(0.2, 1.0).fillna(1.0)
        pos = pos * scale
        sig, conf = self._label(pos)
        return StrategyResult(self.name, pos,
                              {"donchian_up": upper, "donchian_dn": lower, "atr": atr},
                              sig, conf)


class PairsTradingStrategy(BaseStrategy):
    """Statistical-arbitrage z-score spread between two correlated assets.

    generate() expects df with columns close_a, close_b.
    """
    name = "pairs"

    def __init__(self, window: int = 60, entry_z: float = 2.0, exit_z: float = 0.5):
        self.window, self.entry_z, self.exit_z = window, entry_z, exit_z

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        a, b = np.log(df["close_a"]), np.log(df["close_b"])
        beta = a.rolling(self.window).cov(b) / b.rolling(self.window).var()
        spread = a - beta * b
        z = (spread - spread.rolling(self.window).mean()) / spread.rolling(self.window).std()

        pos = pd.Series(np.nan, index=df.index)   # +1 = long A / short B
        pos[z < -self.entry_z] = 1.0
        pos[z > self.entry_z] = -1.0
        pos[z.abs() < self.exit_z] = 0.0
        pos = pos.ffill().fillna(0.0)
        sig, conf = self._label(pos)
        return StrategyResult(self.name, pos, {"zscore": z, "hedge_beta": beta}, sig, conf)


class RiskParityStrategy(BaseStrategy):
    """Inverse-volatility weighting across a basket (multi-asset).

    generate() expects df with one close_<TICKER> column per asset.
    Returns per-asset weights in indicators['weights'].
    """
    name = "risk_parity"

    def __init__(self, vol_window: int = 30, target_vol: float = 0.10):
        self.vol_window, self.target_vol = vol_window, target_vol

    def generate(self, df: pd.DataFrame) -> StrategyResult:
        closes = df[[c for c in df.columns if c.startswith("close_")]]
        rets = closes.pct_change()
        vol = rets.rolling(self.vol_window).std() * np.sqrt(252)
        inv = 1.0 / vol.replace(0, np.nan)
        weights = inv.div(inv.sum(axis=1), axis=0).fillna(0.0)
        port_vol = (rets * weights.shift()).sum(axis=1).rolling(self.vol_window).std() * np.sqrt(252)
        leverage = (self.target_vol / port_vol).clip(0.0, 1.5).fillna(1.0)
        pos = leverage  # overall exposure dial; per-asset weights in indicators
        sig, conf = self._label(pos)
        return StrategyResult(self.name, pos, {"weights": weights, "leverage": leverage}, sig, conf)


STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    s.name: s for s in (MomentumStrategy, MeanReversionStrategy,
                        BreakoutStrategy, PairsTradingStrategy, RiskParityStrategy)
}


def get_strategy(name: str, **kwargs) -> BaseStrategy:
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[name](**kwargs)
