"""
AIMi — Portfolio Builder & Risk Analytics
=========================================
PortfolioBuilder : max-Sharpe / min-volatility / risk-parity / equal-weight
                   allocation from historical returns, mapped to the user's
                   risk profile (conservative → aggressive).
RiskAnalyzer     : VaR, CVaR, Sharpe, Sortino, max drawdown, beta,
                   volatility, correlation matrix — the same metrics that
                   underpin institutional mandates.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

TRADING_DAYS = 252
RISK_FREE = 0.04  # annual

RISK_PROFILES = {
    # profile        target_vol  max_single_weight  method
    "conservative": {"target_vol": 0.06, "max_weight": 0.20, "method": "min_vol"},
    "balanced":     {"target_vol": 0.10, "max_weight": 0.30, "method": "risk_parity"},
    "growth":       {"target_vol": 0.15, "max_weight": 0.40, "method": "max_sharpe"},
    "aggressive":   {"target_vol": 0.22, "max_weight": 0.60, "method": "max_sharpe"},
}


# ------------------------------------------------------------------ risk
@dataclass
class RiskReport:
    ann_return: float
    ann_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    var_95: float          # 1-day historical VaR (as positive loss %)
    cvar_95: float
    beta: float | None
    calmar: float
    correlation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


class RiskAnalyzer:
    @staticmethod
    def analyze(returns: pd.Series, benchmark: pd.Series | None = None,
                asset_returns: pd.DataFrame | None = None) -> RiskReport:
        r = returns.dropna()
        ann_ret = float((1 + r).prod() ** (TRADING_DAYS / max(len(r), 1)) - 1)
        ann_vol = float(r.std() * np.sqrt(TRADING_DAYS))
        downside = r[r < 0].std() * np.sqrt(TRADING_DAYS)
        sharpe = (ann_ret - RISK_FREE) / ann_vol if ann_vol else 0.0
        sortino = (ann_ret - RISK_FREE) / downside if downside else 0.0

        equity = (1 + r).cumprod()
        dd = (equity / equity.cummax() - 1)
        max_dd = float(dd.min())

        var_95 = float(-np.percentile(r, 5))
        tail = r[r <= -var_95]
        cvar_95 = float(-tail.mean()) if len(tail) else var_95

        beta = None
        if benchmark is not None:
            b = benchmark.reindex(r.index).dropna()
            joined = pd.concat([r, b], axis=1).dropna()
            if len(joined) > 10 and joined.iloc[:, 1].var() > 0:
                beta = float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / joined.iloc[:, 1].var())

        corr = {}
        if asset_returns is not None and asset_returns.shape[1] > 1:
            corr = asset_returns.corr().round(3).to_dict()

        calmar = ann_ret / abs(max_dd) if max_dd else 0.0
        return RiskReport(ann_ret, ann_vol, float(sharpe), float(sortino),
                          max_dd, var_95, cvar_95, beta, float(calmar), corr)


# ------------------------------------------------------------- optimiser
class PortfolioBuilder:
    """Long-only allocation via random-portfolio search with constraints —
    robust, dependency-free, and good enough for 5–30 asset universes.
    Swap in scipy.optimize/cvxpy for production exact solutions."""

    def __init__(self, n_samples: int = 20000, seed: int = 7):
        self.n_samples, self.seed = n_samples, seed

    def build(self, prices: pd.DataFrame, risk_profile: str = "balanced",
              benchmark: pd.Series | None = None) -> dict:
        profile = RISK_PROFILES.get(risk_profile, RISK_PROFILES["balanced"])
        rets = prices.pct_change().dropna()
        if rets.empty or rets.shape[1] == 0:
            raise ValueError("No usable price data")

        method = profile["method"]
        if method == "risk_parity":
            weights = self._risk_parity(rets)
        else:
            weights = self._search(rets, method, profile["max_weight"])

        weights = self._cap(weights, profile["max_weight"])
        port_rets = (rets * weights).sum(axis=1)
        report = RiskAnalyzer.analyze(port_rets, benchmark, rets)

        return {
            "risk_profile": risk_profile,
            "method": method,
            "weights": {t: round(float(w), 4) for t, w in weights.items() if w > 0.001},
            "risk": report.to_dict(),
            "equity_curve": ((1 + port_rets).cumprod()).round(4).to_dict(),
        }

    # -- methods -------------------------------------------------------------
    def _search(self, rets: pd.DataFrame, objective: str, max_w: float) -> pd.Series:
        rng = np.random.default_rng(self.seed)
        n = rets.shape[1]
        mu = rets.mean().values * TRADING_DAYS
        cov = rets.cov().values * TRADING_DAYS

        W = rng.dirichlet(np.ones(n), size=self.n_samples)
        W = np.minimum(W, max_w)
        W = W / W.sum(axis=1, keepdims=True)

        port_ret = W @ mu
        port_vol = np.sqrt(np.einsum("ij,jk,ik->i", W, cov, W))
        port_vol[port_vol == 0] = 1e-9

        if objective == "min_vol":
            best = int(np.argmin(port_vol))
        else:  # max_sharpe
            best = int(np.argmax((port_ret - RISK_FREE) / port_vol))
        return pd.Series(W[best], index=rets.columns)

    @staticmethod
    def _risk_parity(rets: pd.DataFrame) -> pd.Series:
        vol = rets.std() * np.sqrt(TRADING_DAYS)
        inv = 1.0 / vol.replace(0, np.nan)
        return (inv / inv.sum()).fillna(0.0)

    @staticmethod
    def _cap(weights: pd.Series, cap: float) -> pd.Series:
        w = weights.clip(upper=cap)
        return w / w.sum()
