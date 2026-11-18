"""Daily metric anomaly detection and change decomposition."""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

SQL = Path(__file__).resolve().parent.parent / "sql"


def run_sql(con: duckdb.DuckDBPyConnection, name: str, **fmt) -> pd.DataFrame:
    q = (SQL / f"{name}.sql").read_text()
    return con.execute(q.format(**fmt) if fmt else q).df()


WEEKLY = (7, 14, 21, 28)       # same weekday, previous four weeks: for metrics with a weekly cycle
TRAILING = tuple(range(1, 8))  # previous seven days: for metrics without one


def detect(x: pd.Series, lags=TRAILING, z_threshold: float = 4.0, window: int = 28, min_history: int = 42,
           min_scale: float = 0.0, log: bool = False) -> pd.DataFrame:
    """Flag days that are far from a robust baseline, one day at a time as a daily job would.

    baseline: median of the lagged days (`WEEKLY` or `TRAILING`);
    scale:    1.4826 x median absolute residual over the previous four weeks, so one outlier does not
              widen the band the way a standard deviation would. `min_scale` keeps a metric that is
              normally flat (a data check that should be zero) from dividing by zero;
    flagged days are replaced by their baseline in the history, so an incident does not become
    the baseline for the days after it.
    log=True compares counts in relative terms, so a 20% drop means the same in January and June.
    """
    v = np.log(x.astype(float).to_numpy()) if log else x.astype(float).to_numpy()
    clean = v.copy()
    resid = np.full(len(v), np.nan)
    base = np.full(len(v), np.nan)
    z = np.full(len(v), np.nan)
    flag = np.zeros(len(v), bool)
    for t in range(max(lags), len(v)):
        base[t] = np.median(clean[[t - k for k in lags]])
        hist = resid[max(0, t - window):t]
        hist = hist[~np.isnan(hist)]
        if len(hist) >= window // 2:
            scale = max(1.4826 * np.median(np.abs(hist)), min_scale)
            z[t] = (v[t] - base[t]) / scale if scale > 0 else np.nan
            flag[t] = t >= min_history and abs(z[t]) > z_threshold
        if flag[t]:
            clean[t] = base[t]
        else:
            resid[t] = v[t] - base[t]
    return pd.DataFrame({"value": x.astype(float).to_numpy(), "baseline": np.exp(base) if log else base,
                         "z": z, "flag": flag}, index=x.index)


def decompose(before: pd.DataFrame, after: pd.DataFrame, segment: str, num: str, den: str) -> pd.DataFrame:
    """Split the change in an overall rate (sum num / sum den) into mix and rate effects by segment.

    change = sum_s (w1 - w0) * r0      mix: the segment's share of the denominator moved
           + sum_s  w0 * (r1 - r0)     rate: the segment's own rate moved
           + sum_s (w1 - w0) * (r1 - r0)
    The three columns add up exactly to the change in the overall rate.
    """
    b = before.groupby(segment)[[num, den]].sum()
    a = after.groupby(segment)[[num, den]].sum()
    t = b.add_suffix("_0").join(a.add_suffix("_1"), how="outer").fillna(0)
    w0 = t[f"{den}_0"] / t[f"{den}_0"].sum()
    w1 = t[f"{den}_1"] / t[f"{den}_1"].sum()
    r0 = (t[f"{num}_0"] / t[f"{den}_0"]).fillna(0)
    r1 = (t[f"{num}_1"] / t[f"{den}_1"]).fillna(0)
    out = pd.DataFrame({"share_before": w0, "share_after": w1, "rate_before": r0, "rate_after": r1,
                        "mix": (w1 - w0) * r0, "rate": w0 * (r1 - r0), "interaction": (w1 - w0) * (r1 - r0)})
    out["total"] = out[["mix", "rate", "interaction"]].sum(axis=1)
    return out.sort_values("total")


def same_weekdays_before(days: pd.DatetimeIndex, weeks: int = 4) -> pd.DatetimeIndex:
    """The same weekdays in the `weeks` weeks before a window, used as its baseline."""
    return pd.DatetimeIndex(sorted({d - pd.Timedelta(days=7 * k) for d in days for k in range(1, weeks + 1)}))
