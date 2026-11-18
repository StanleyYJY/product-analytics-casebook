"""Build the event log, run the SQL analyses and the monitoring, and write results/report.md.

  uv run python run_all.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib
import numpy as np
import pandas as pd

from prodkit import monitor, simulate

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent
FIG = ROOT / "results" / "figures"

# metric, how it is defined, baseline lags, log scale, minimum scale
WATCHED = [
    ("signups", "New accounts created that day", monitor.WEEKLY, True, 0.0),
    ("onboarding_rate", "Share of that day's signups finishing onboarding within 24 hours", monitor.TRAILING, False, 0.0),
    ("activation_rate_7d", "Share of that day's signups with 3+ core actions within 7 days", monitor.TRAILING, False, 0.0),
    ("dau", "Distinct users with a session_start that day", monitor.TRAILING, True, 0.0),
    ("actions_per_dau", "Core actions per daily active user", monitor.TRAILING, False, 0.0),
    ("orphan_action_share", "Data check: share of acting users with no session that day (should be 0)", monitor.TRAILING, False, 0.005),
]


def pct(x: float, d: int = 1) -> str:
    return f"{x:.{d}%}"


HEADERS = {"segment": "Segment", "signups": "Signups", "onboarded": "Onboarded", "activated": "Activated",
           "trial": "Trial", "paid": "Paid", "median_days_to_activate": "Median days to activate",
           "share_before": "Share before", "share_after": "Share after", "rate_before": "Rate before",
           "rate_after": "Rate after", "mix": "Mix effect", "rate": "Rate effect", "total": "Total"}


def table(df: pd.DataFrame, fmt: dict) -> list[str]:
    lines = ["| " + " | ".join(HEADERS.get(c, c) for c in df.columns) + " |", "|" + "---|" * len(df.columns)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt.get(c, str)(r[c]) for c in df.columns) + " |")
    return lines


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    tables = simulate.build(ROOT / "data")
    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)
    users, events = tables["users"], tables["events"]
    md = ["# Product analytics report\n",
          f"Simulated event log for a subscription productivity app, January to June 2025: {len(users):,} signups and "
          f"{len(events):,} events (signup, onboarding_complete, session_start, core_action, trial_start, "
          "subscription_paid) across iOS, Android and web and four acquisition channels. Three incidents are "
          "planted in the data so the monitoring can be graded; section 4 says what they are.\n"]

    # ---------------- metric dictionary ----------------
    md += ["## Metric definitions\n", "| Metric | Definition | Baseline |", "|---|---|---|"]
    md += [f"| `{m}` | {d} | {'same weekday, previous 4 weeks' if lags == monitor.WEEKLY else 'previous 7 days'} |"
           for m, d, lags, _, _ in WATCHED]
    md.append("\nSignups have a weekly cycle (weekends are lower), so they are compared with the same weekday. "
              "The other metrics have no weekly cycle here, and a trailing week tracks growth more closely.")

    # ---------------- funnel ----------------
    f_ch = monitor.run_sql(con, "funnel", group_by="channel")
    f_pl = monitor.run_sql(con, "funnel", group_by="platform")
    f_all = monitor.run_sql(con, "funnel", group_by="'all'")
    cols = {"segment": str, "signups": lambda v: f"{v:,}", "onboarded": pct, "activated": pct, "trial": pct,
            "paid": pct, "median_days_to_activate": lambda v: f"{v:.1f}"}
    md += ["\n## 1. Funnel (January to April signups)\n",
           "Each step must follow the previous one inside its window: onboarding within 24 hours, activation "
           "(third core action) within 7 days, trial after activation and within 30 days, then payment.\n"]
    md += table(pd.concat([f_all, f_ch, f_pl]), cols)
    worst = f_ch.sort_values("paid").iloc[0]
    best = f_ch.sort_values("paid").iloc[-1]
    md.append(f"\nThe channel gap is widest at activation: {best.segment} signups activate at "
              f"{pct(best.activated)} against {pct(worst.activated)} for {worst.segment}, and the paid rate follows "
              f"({pct(best.paid)} vs {pct(worst.paid)}). Platforms differ by up to "
              f"{(f_pl.onboarded.max() - f_pl.onboarded.min()) * 100:.0f} pts at onboarding (web is lowest) but end within "
              f"{(f_pl.activated.max() - f_pl.activated.min()) * 100:.1f} pts of each other on activation. Fixing web "
              "onboarding is worth doing only if it moves activation, which is a question for an experiment.")

    # ---------------- retention ----------------
    ret = monitor.run_sql(con, "retention", segment="channel")
    ret_all = monitor.run_sql(con, "retention", segment="'all'")
    w = (ret.assign(n=lambda d: d.cohort_size * d.retention, size=lambda d: d.cohort_size)
         .groupby(["segment", "week_k"])[["n", "size"]].sum())
    curve = (w.n / w["size"]).unstack("week_k")
    w_all = ret_all.groupby("week_k").apply(lambda g: (g.retention * g.cohort_size).sum() / g.cohort_size.sum(),
                                            include_groups=False)
    weeks = [1, 2, 4, 8, 12]
    md += ["\n## 2. Retention\n",
           "Share of each weekly signup cohort with a session in week k after signup. Only weeks that have fully "
           "elapsed are counted, and cohorts are pooled weighted by size.\n",
           "| Segment | " + " | ".join(f"Week {k}" for k in weeks) + " |", "|---|" + "---|" * len(weeks),
           "| All | " + " | ".join(pct(w_all.get(k, np.nan)) for k in weeks) + " |"]
    for seg, row in curve.iterrows():
        md.append(f"| {seg} | " + " | ".join(pct(row.get(k, np.nan)) for k in weeks) + " |")

    fig, ax = plt.subplots(figsize=(6, 3.8))
    for seg, row in curve.iterrows():
        ax.plot(row.index, row.values, marker="o", ms=3, label=seg)
    ax.set_xlabel("Weeks since signup")
    ax.set_ylabel("Share with a session")
    ax.set_title("Weekly retention by acquisition channel")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "retention_by_channel.png", dpi=150)
    plt.close(fig)

    # ---------------- activation threshold ----------------
    th = monitor.run_sql(con, "activation_threshold")
    pooled = th.groupby("actions_7d").apply(lambda g: pd.Series({
        "users": g.users.sum(), "retained": (g.users * g.retained_d30).sum() / g.users.sum()}), include_groups=False)
    by_ch = th.pivot_table(index="actions_7d", columns="channel", values="retained_d30")
    md += ["\n## 3. Is \"3 core actions in week one\" the right activation bar?\n",
           "Day-30 retention (a session on days 28 to 34) by core actions in the first 7 days:\n",
           "| Actions in week 1 | Users | Day-30 retention | Gain over one fewer action | "
           + " | ".join(by_ch.columns) + " |", "|---|---|---|---|" + "---|" * len(by_ch.columns)]
    prev = None
    for k, r in pooled.iterrows():
        gain = "" if prev is None else f"{(r.retained - prev) * 100:+.1f} pts"
        label = f"{k}+" if k == 10 else str(k)
        md.append(f"| {label} | {int(r.users):,} | {pct(r.retained)} | {gain} | "
                  + " | ".join(pct(by_ch.loc[k, c]) for c in by_ch.columns) + " |")
        prev = r.retained
    md.append("\nThere is no cliff. Each extra action is worth less, and from about the third action the gain "
              "drops below 8 points, so 3 is a reasonable bar, not a magic number. The pattern holds inside every "
              "channel, so it is not just channel mix. It is still correlation: users who were going to stay anyway "
              "also do more in week one. Before pushing users toward three actions, test it, for example with an "
              "onboarding change that makes the second and third actions easier, and measure day-30 retention.")

    # ---------------- monitoring ----------------
    daily = monitor.run_sql(con, "daily_metrics")
    daily["day"] = pd.to_datetime(daily.day)
    daily = daily.set_index("day")
    results = {}
    for m, _, lags, log, ms in WATCHED:
        s = daily[m]
        if m == "activation_rate_7d":
            s = s[daily.activation_complete]
        results[m] = monitor.detect(s, lags, log=log, min_scale=ms)

    seg = monitor.run_sql(con, "segment_daily")
    seg["day"] = pd.to_datetime(seg.day)
    plat_onb = {}
    for p, g in seg.groupby("platform"):
        g = g.groupby("day")[["onboarded_24h", "signups"]].sum()
        plat_onb[p] = monitor.detect(g.onboarded_24h / g.signups)

    inc = simulate.INCIDENTS
    in_any = pd.Series(False, index=daily.index)
    for a, b in inc.values():
        in_any |= (daily.index >= a) & (daily.index < b)
    md += ["\n## 4. Daily monitoring\n",
           "Each metric is checked every morning against a robust baseline: the median of the lagged days, with a "
           "band of 4 robust standard deviations from the previous four weeks of residuals. Flagged days are "
           "left out of later baselines. The first six weeks are a warm-up.\n",
           "The planted incidents:\n",
           "- **Android release bug, March 10 to 14:** onboarding completion on Android drops by about 45%.",
           "- **iOS tracking outage, April 22:** 70% of iOS `session_start` events are lost. Behavior is unchanged.",
           "- **Paid social campaign, May 5 to 18:** paid social signups triple, and these users engage less.\n",
           "Days flagged, by metric:\n",
           "| Metric | Android bug (5 days) | iOS outage (1 day) | Campaign (14 days) | False alarms (other days) |",
           "|---|---|---|---|---|"]
    for m, r in list(results.items()) + [("onboarding_rate, Android only", plat_onb["android"])]:
        cells = []
        for a, b in inc.values():
            win = r[(r.index >= a) & (r.index < b)]
            cells.append(f"{int(win.flag.sum())}" if len(win) else "–")
        fa = int(r.flag[~in_any.reindex(r.index, fill_value=False)].sum())
        md.append(f"| `{m}` | " + " | ".join(cells) + f" | {fa} |")
    md.append("\nThe Android bug shows in the overall onboarding rate, but it is much sharper in the Android series "
              f"(z of {plat_onb['android'].loc['2025-03-10':'2025-03-14', 'z'].min():.1f} at the worst point against "
              f"{results['onboarding_rate'].loc['2025-03-10':'2025-03-14', 'z'].min():.1f} overall). For a product "
              "with a few large segments, watching each platform costs little. Both series fire on day one here, "
              "but the Android one is far outside its band, so it would still fire for a smaller bug that the "
              "overall rate would absorb. The campaign does not trip the activation alarm: the drop is real but gradual, and "
              "section 5 shows why.")

    fig, ax = plt.subplots(figsize=(7, 3.6))
    win = slice("2025-02-15", "2025-04-10")
    for p, r in plat_onb.items():
        rr = r.loc[win]
        ax.plot(rr.index, rr.value, lw=1.2, label=p)
        ax.scatter(rr.index[rr.flag], rr.value[rr.flag], color="red", zorder=3, s=18)
    ov = results["onboarding_rate"].loc[win]
    ax.plot(ov.index, ov.value, color="black", lw=1.6, ls="--", label="all platforms")
    ax.set_ylabel("Onboarded within 24h")
    ax.set_title("Onboarding rate by platform (red = flagged)")
    ax.set_ylim(0.2, 0.85)
    ax.legend(frameon=False, ncol=2, loc="lower right")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "onboarding_by_platform.png", dpi=150)
    plt.close(fig)

    # ---------------- diagnosis ----------------
    def window_days(a, b):
        return pd.date_range(a, b - pd.Timedelta(days=1))

    def baseline_days(days, weeks=4):
        return [d for d in monitor.same_weekdays_before(days, weeks) if not in_any.get(d, False)]

    md += ["\n## 5. Diagnosis: what changed, and where\n",
           "Each incident window is compared with the same weekdays in the four weeks before it. The change in an "
           "overall rate splits exactly into a **mix** effect (a segment's share of signups moved), a **rate** "
           "effect (the segment's own rate moved), and a small interaction.\n"]
    dec_fmt = {"segment": str, "share_before": pct, "share_after": pct, "rate_before": pct, "rate_after": pct,
               "mix": lambda v: f"{v * 100:+.2f} pts", "rate": lambda v: f"{v * 100:+.2f} pts",
               "total": lambda v: f"{v * 100:+.2f} pts"}

    a, b = inc["android_onboarding_bug"]
    d_inc = window_days(a, b)
    before, after = seg[seg.day.isin(baseline_days(d_inc))], seg[seg.day.isin(d_inc)]
    dec = monitor.decompose(before, after, "platform", "onboarded_24h", "signups").reset_index(names="segment")
    md += ["### Onboarding rate, March 10 to 14, by platform\n"]
    md += table(dec[list(dec_fmt)], dec_fmt)
    md.append(f"\nOverall onboarding fell {-dec.total.sum() * 100:.1f} pts, and "
              f"{dec.set_index('segment').loc['android', 'rate'] / dec.total.sum():.0%} of that is Android's own rate. "
              "The platform mix did not move. This is a product problem on one platform: check what shipped on "
              "Android around March 10.")

    a, b = inc["ios_tracking_outage"]
    dq = monitor.run_sql(con, "data_quality_by_platform")
    dq["day"] = pd.to_datetime(dq.day)
    day = pd.Timestamp(a)
    prior = baseline_days(pd.DatetimeIndex([day]))
    md += ["\n### DAU drop on April 22: real or tracking?\n",
           "| Platform | DAU change | Users with a core action, change | Acting users with no session (that day) |",
           "|---|---|---|---|"]
    ev_day = events.assign(day=events.ts.dt.floor("D"))
    by = ev_day[ev_day.day.isin(prior + [day])].groupby(["day", "platform", "event"]).user_id.nunique().unstack("event")
    for p in simulate.PLATFORMS:
        cur = by.loc[(day, p)]
        base = by.loc[[(d, p) for d in prior]].mean()
        orphan = dq[(dq.day == day) & (dq.platform == p)].orphan_action_share.iloc[0]
        md.append(f"| {p} | {cur.session_start / base.session_start - 1:+.0%} | {cur.core_action / base.core_action - 1:+.0%} | "
                  f"{pct(orphan)} |")
    dau_chg = daily.dau.loc[day] / daily.dau.loc[prior].mean() - 1
    md.append(f"\nTotal DAU changed {dau_chg:+.0%}. Only iOS sessions dropped, while iOS users kept doing core actions at the usual rate, and many "
              "acting users have no session at all, which cannot happen in the product. The drop is a logging "
              "failure, not lost users. The right response is to annotate the dashboard and fix the iOS logging, "
              f"not to explain a {-dau_chg:.0%} fall in engagement. The orphan-action check catches this on day one.")

    a, b = inc["paid_social_campaign"]
    d_inc = window_days(a, b)
    before, after = seg[seg.day.isin(baseline_days(d_inc))], seg[seg.day.isin(d_inc)]
    dec = monitor.decompose(before, after, "channel", "activated_7d", "signups").reset_index(names="segment")
    md += ["\n### Activation rate, May 5 to 18, by channel\n"]
    md += table(dec[list(dec_fmt)], dec_fmt)
    mix, rate = dec.mix.sum(), dec.rate.sum()
    md.append(f"\nActivation fell {-dec.total.sum() * 100:.1f} pts. Mix explains {mix * 100:+.1f} pts and "
              f"within-channel rates {rate * 100:+.1f} pts. Paid social's own activation rate barely moved; there "
              "were simply many more paid social signups, and that channel always activates less. Nothing in the "
              "product broke. The question for the campaign is cost per activated user, not why activation fell.")

    (ROOT / "results" / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
