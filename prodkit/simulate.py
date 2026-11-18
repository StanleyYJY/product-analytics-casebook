"""Simulated event log for a subscription productivity app, January to June 2025.

Each user has a latent engagement level that depends on acquisition channel. Signups go through
onboarding, then activation (3+ core actions in the first 7 days), daily activity that decays over
time, a trial, and a paid subscription.

Three incidents are planted so the monitoring can be graded:
  android_onboarding_bug  Mar 10-14: an Android release breaks a step, onboarding completion drops on Android
  ios_tracking_outage     Apr 22: 70% of iOS session_start events are lost; behavior is unchanged
  paid_social_campaign    May 5-18: paid social signups triple, and these users engage less
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

START = pd.Timestamp("2025-01-01")
DAYS = 181
HORIZON = 90  # days of activity simulated per user
CHANNELS = ["organic", "paid_search", "paid_social", "referral"]
CHANNEL_SHARE = np.array([0.40, 0.25, 0.20, 0.15])
CHANNEL_MU = dict(zip(CHANNELS, [0.0, -0.2, -0.6, 0.4]))
PLATFORMS = ["ios", "android", "web"]
PLATFORM_SHARE = np.array([0.45, 0.40, 0.15])
PLATFORM_ONBOARD = dict(zip(PLATFORMS, [0.2, 0.0, -0.3]))

INCIDENTS = {
    "android_onboarding_bug": (pd.Timestamp("2025-03-10"), pd.Timestamp("2025-03-15")),
    "ios_tracking_outage": (pd.Timestamp("2025-04-22"), pd.Timestamp("2025-04-23")),
    "paid_social_campaign": (pd.Timestamp("2025-05-05"), pd.Timestamp("2025-05-19")),
}


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _users(rng) -> pd.DataFrame:
    day = np.arange(DAYS)
    dates = START + pd.to_timedelta(day, unit="D")
    dow = np.where(dates.day_of_week >= 5, 0.8, 1.0)
    base = 400 * (1 + 0.15 * day / DAYS) * dow
    n_base = rng.poisson(base)
    camp = (dates >= INCIDENTS["paid_social_campaign"][0]) & (dates < INCIDENTS["paid_social_campaign"][1])
    n_extra = np.where(camp, rng.poisson(base * CHANNEL_SHARE[2] * 2), 0)

    d_base = np.repeat(day, n_base)
    ch_base = rng.choice(len(CHANNELS), size=len(d_base), p=CHANNEL_SHARE)
    d = np.r_[d_base, np.repeat(day, n_extra)]
    ch = np.r_[ch_base, np.full(n_extra.sum(), 2)]
    n = len(d)
    hour = rng.choice(24, size=n, p=_hour_p())
    signup_ts = START + pd.to_timedelta(d, unit="D") + pd.to_timedelta(hour * 3600 + rng.integers(0, 3600, n), unit="s")
    channel = np.array(CHANNELS)[ch]
    users = pd.DataFrame({
        "signup_ts": signup_ts, "channel": channel,
        "platform": np.array(PLATFORMS)[rng.choice(3, size=n, p=PLATFORM_SHARE)],
        "engagement": rng.normal(np.vectorize(CHANNEL_MU.get)(channel), 1.0),
    }).sort_values("signup_ts", kind="stable").reset_index(drop=True)
    users.insert(0, "user_id", np.arange(n))
    return users


def _hour_p():
    w = np.array([1, .5, .3, .3, .3, .6, 1.2, 2, 3, 3.5, 3.5, 3.5, 4, 3.5, 3.5, 3.5, 3.5, 4, 4.5, 5, 5, 4, 3, 2])
    return w / w.sum()


def build(out_dir: Path, seed: int = 11) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    u = _users(rng)
    n = len(u)
    e = u.engagement.to_numpy()
    end = START + pd.Timedelta(days=DAYS)

    # onboarding
    p_onb = sigmoid(0.9 + 0.6 * e + np.vectorize(PLATFORM_ONBOARD.get)(u.platform))
    bug0, bug1 = INCIDENTS["android_onboarding_bug"]
    bug = (u.platform == "android").to_numpy() & (u.signup_ts >= bug0).to_numpy() & (u.signup_ts < bug1).to_numpy()
    p_onb = np.where(bug, p_onb * 0.55, p_onb)
    onboarded = rng.random(n) < p_onb
    onb_ts = u.signup_ts + pd.to_timedelta(rng.exponential(600, n), unit="s")

    # daily activity over the first 90 days (day 0 is the signup day)
    first_week_lambda = np.exp(0.2 + 0.7 * e + 0.6 * onboarded)
    days = np.arange(HORIZON)
    act_logit = (-0.6 + 0.9 * e[:, None] + 0.8 * onboarded[:, None] - 0.55 * np.log1p(days)[None, :])
    active = rng.random((n, HORIZON)) < sigmoid(act_logit)
    active[:, 0] = True
    signup_day = ((u.signup_ts - START).dt.days).to_numpy()
    active &= (signup_day[:, None] + days[None, :]) < DAYS
    ui, di = np.nonzero(active)
    base_day = u.signup_ts.dt.floor("D").to_numpy()[ui] + pd.to_timedelta(di, unit="D").to_numpy()
    k_sessions = 1 + rng.poisson(0.5, len(ui))
    lam = np.where(di < 7, first_week_lambda[ui] / 3, np.exp(-0.3 + 0.5 * e[ui]))
    k_actions = rng.poisson(lam)

    def stamp(rep_ui, rep_day, k):
        idx = np.repeat(np.arange(len(rep_ui)), k)
        t = pd.to_datetime(rep_day[idx]) + pd.to_timedelta(rng.choice(24, size=len(idx), p=_hour_p()) * 3600
                                                            + rng.integers(0, 3600, len(idx)), unit="s")
        return rep_ui[idx], t

    s_u, s_t = stamp(ui, base_day, k_sessions)
    a_u, a_t = stamp(ui, base_day, k_actions)
    # the signup-day session starts at signup
    first = np.r_[True, s_u[1:] != s_u[:-1]] if len(s_u) else np.array([], bool)
    s_t = np.where(first, u.signup_ts.to_numpy()[s_u], np.maximum(s_t, u.signup_ts.to_numpy()[s_u]))
    ok = a_t >= u.signup_ts.to_numpy()[a_u]
    a_u, a_t = a_u[ok], a_t[ok]

    # activation, trial, paid
    a_df = pd.DataFrame({"u": a_u, "t": a_t})
    wk = a_df[a_df.t < u.signup_ts.to_numpy()[a_df.u] + np.timedelta64(7, "D")]
    activated = np.bincount(wk.u, minlength=n) >= 3
    trial = activated & (rng.random(n) < sigmoid(-0.8 + 0.8 * e))
    trial_ts = u.signup_ts + pd.to_timedelta(rng.uniform(1, 10, n), unit="D")
    paid = trial & (rng.random(n) < sigmoid(-0.4 + 0.6 * e))
    paid_ts = trial_ts + pd.Timedelta(days=14)

    plat = u.platform.to_numpy()
    ev = [
        pd.DataFrame({"user_id": u.user_id, "ts": u.signup_ts, "event": "signup"}),
        pd.DataFrame({"user_id": u.user_id[onboarded], "ts": onb_ts[onboarded], "event": "onboarding_complete"}),
        pd.DataFrame({"user_id": s_u, "ts": s_t, "event": "session_start"}),
        pd.DataFrame({"user_id": a_u, "ts": a_t, "event": "core_action"}),
        pd.DataFrame({"user_id": u.user_id[trial], "ts": trial_ts[trial], "event": "trial_start"}),
        pd.DataFrame({"user_id": u.user_id[paid], "ts": paid_ts[paid], "event": "subscription_paid"}),
    ]
    events = pd.concat(ev, ignore_index=True)
    events = events[events.ts < end]
    events["platform"] = plat[events.user_id.to_numpy()]

    # logging outage: lose most iOS session_start events for one day
    o0, o1 = INCIDENTS["ios_tracking_outage"]
    hit = ((events.event == "session_start") & (events.platform == "ios") & (events.ts >= o0) & (events.ts < o1)
           & (rng.random(len(events)) < 0.7))
    events = events[~hit].sort_values(["ts", "user_id"], kind="stable").reset_index(drop=True)

    users = u.drop(columns="engagement")
    out_dir.mkdir(parents=True, exist_ok=True)
    users.to_parquet(out_dir / "users.parquet", index=False)
    events.to_parquet(out_dir / "events.parquet", index=False)
    return {"users": users, "events": events}
