import duckdb
import numpy as np
import pandas as pd

from prodkit import monitor


def _con(users, events):
    con = duckdb.connect()
    u = pd.DataFrame(users, columns=["user_id", "signup_ts", "channel", "platform"])
    u["signup_ts"] = pd.to_datetime(u.signup_ts)
    e = pd.DataFrame(events, columns=["user_id", "ts", "event"])
    e["ts"] = pd.to_datetime(e.ts)
    e["platform"] = e.user_id.map(u.set_index("user_id").platform)
    con.register("users", u)
    con.register("events", e)
    return con


USERS = [(1, "2025-01-06 09:00", "organic", "ios"), (2, "2025-01-06 10:00", "referral", "android")]


def test_funnel_requires_order_and_windows():
    events = [
        # user 1: onboarded, 3 actions inside 7 days, trial after activation, then paid
        (1, "2025-01-06 09:05", "onboarding_complete"),
        *[(1, f"2025-01-0{d} 12:00", "core_action") for d in (6, 7, 8)],
        (1, "2025-01-09 12:00", "trial_start"), (1, "2025-01-23 12:00", "subscription_paid"),
        # user 2: onboards late (after 24h), third action on day 8 is outside the window, trial before activation
        (2, "2025-01-08 10:00", "onboarding_complete"),
        (2, "2025-01-06 11:00", "core_action"), (2, "2025-01-07 11:00", "core_action"),
        (2, "2025-01-06 12:00", "trial_start"),
        (2, "2025-01-14 11:00", "core_action"),
    ]
    f = monitor.run_sql(_con(USERS, events), "funnel", group_by="channel").set_index("segment")
    assert f.loc["organic", ["onboarded", "activated", "trial", "paid"]].tolist() == [1, 1, 1, 1]
    assert f.loc["referral", ["onboarded", "activated", "trial", "paid"]].tolist() == [0, 0, 0, 0]


def test_retention_counts_each_user_once_per_week():
    events = [(1, "2025-01-06 09:00", "session_start"), (1, "2025-01-06 18:00", "session_start"),
              (1, "2025-01-14 09:00", "session_start"), (2, "2025-01-06 10:00", "session_start")]
    r = monitor.run_sql(_con(USERS, events), "retention", segment="'all'").set_index("week_k")
    assert r.loc[0, "retention"] == 1.0 and r.loc[1, "retention"] == 0.5


def test_detector_flags_step_and_ignores_weekly_cycle():
    days = pd.date_range("2025-01-01", periods=120)
    rng = np.random.default_rng(0)
    x = pd.Series(1000 * np.where(days.day_of_week >= 5, 0.8, 1.0) * rng.normal(1, 0.01, len(days)), index=days)
    assert not monitor.detect(x, monitor.WEEKLY, log=True).flag.any()
    x.iloc[80:83] *= 0.7
    flagged = monitor.detect(x, monitor.WEEKLY, log=True).flag
    assert flagged.iloc[80:83].all() and flagged.sum() == 3      # flagged days do not poison later baselines


def test_detector_min_scale_for_flat_check():
    x = pd.Series(np.zeros(80), index=pd.date_range("2025-01-01", periods=80))
    x.iloc[60] = 0.2
    r = monitor.detect(x, min_scale=0.005)
    assert r.flag.sum() == 1 and r.flag.iloc[60]


def test_decomposition_adds_up_and_separates_mix_from_rate():
    before = pd.DataFrame({"seg": ["a", "b"], "num": [50, 10], "den": [100, 100]})
    after = pd.DataFrame({"seg": ["a", "b"], "num": [50, 30], "den": [100, 300]})  # b grows, its rate stays 10%
    d = monitor.decompose(before, after, "seg", "num", "den")
    change = 80 / 400 - 60 / 200
    assert abs(d.total.sum() - change) < 1e-12
    assert abs(d.rate.sum()) < 1e-12 and d.mix.sum() < 0
