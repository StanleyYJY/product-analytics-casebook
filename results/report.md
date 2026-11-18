# Product analytics report

Simulated event log for a subscription productivity app, January to June 2025: 75,442 signups and 2,437,192 events (signup, onboarding_complete, session_start, core_action, trial_start, subscription_paid) across iOS, Android and web and four acquisition channels. Three incidents are planted in the data so the monitoring can be graded; section 4 says what they are.

## Metric definitions

| Metric | Definition | Baseline |
|---|---|---|
| `signups` | New accounts created that day | same weekday, previous 4 weeks |
| `onboarding_rate` | Share of that day's signups finishing onboarding within 24 hours | previous 7 days |
| `activation_rate_7d` | Share of that day's signups with 3+ core actions within 7 days | previous 7 days |
| `dau` | Distinct users with a session_start that day | previous 7 days |
| `actions_per_dau` | Core actions per daily active user | previous 7 days |
| `orphan_action_share` | Data check: share of acting users with no session that day (should be 0) | previous 7 days |

Signups have a weekly cycle (weekends are lower), so they are compared with the same weekday. The other metrics have no weekly cycle here, and a trailing week tracks growth more closely.

## 1. Funnel (January to April signups)

Each step must follow the previous one inside its window: onboarding within 24 hours, activation (third core action) within 7 days, trial after activation and within 30 days, then payment.

| Segment | Signups | Onboarded | Activated | Trial | Paid | Median days to activate |
|---|---|---|---|---|---|---|
| all | 47,161 | 68.7% | 33.4% | 12.5% | 7.1% | 2.5 |
| organic | 18,876 | 70.0% | 36.5% | 13.8% | 7.8% | 2.5 |
| paid_search | 11,770 | 67.5% | 30.3% | 10.6% | 5.7% | 2.7 |
| paid_social | 9,445 | 62.9% | 19.5% | 6.4% | 3.4% | 2.9 |
| referral | 7,070 | 74.7% | 49.2% | 20.7% | 12.5% | 2.0 |
| ios | 21,258 | 72.2% | 33.7% | 12.4% | 7.2% | 2.5 |
| android | 18,718 | 66.9% | 33.2% | 12.8% | 7.0% | 2.5 |
| web | 7,185 | 63.0% | 33.3% | 12.2% | 7.1% | 2.4 |

The channel gap is widest at activation: referral signups activate at 49.2% against 19.5% for paid_social, and the paid rate follows (12.5% vs 3.4%). Platforms differ by up to 9 pts at onboarding (web is lowest) but end within 0.5 pts of each other on activation. Fixing web onboarding is worth doing only if it moves activation, which is a question for an experiment.

## 2. Retention

Share of each weekly signup cohort with a session in week k after signup. Only weeks that have fully elapsed are counted, and cohorts are pooled weighted by size.

| Segment | Week 1 | Week 2 | Week 4 | Week 8 | Week 12 |
|---|---|---|---|---|---|
| All | 70.8% | 64.3% | 56.9% | 48.6% | 40.2% |
| organic | 73.6% | 67.2% | 60.5% | 50.8% | 42.4% |
| paid_search | 69.9% | 63.1% | 54.5% | 46.7% | 37.9% |
| paid_social | 59.5% | 52.8% | 45.7% | 36.3% | 29.8% |
| referral | 82.3% | 76.8% | 69.5% | 62.3% | 52.4% |

## 3. Is "3 core actions in week one" the right activation bar?

Day-30 retention (a session on days 28 to 34) by core actions in the first 7 days:

| Actions in week 1 | Users | Day-30 retention | Gain over one fewer action | organic | paid_search | paid_social | referral |
|---|---|---|---|---|---|---|---|
| 0 | 17,200 | 34.3% |  | 36.6% | 32.8% | 29.8% | 42.3% |
| 1 | 8,747 | 51.2% | +16.9 pts | 53.7% | 48.8% | 46.5% | 56.4% |
| 2 | 5,440 | 62.9% | +11.7 pts | 63.5% | 62.9% | 58.4% | 66.6% |
| 3 | 3,655 | 70.8% | +7.9 pts | 71.8% | 70.6% | 65.3% | 73.8% |
| 4 | 2,540 | 77.5% | +6.7 pts | 79.0% | 77.9% | 69.8% | 79.5% |
| 5 | 1,907 | 82.3% | +4.8 pts | 84.9% | 80.0% | 79.8% | 81.0% |
| 6 | 1,440 | 86.7% | +4.4 pts | 86.7% | 85.8% | 83.8% | 89.6% |
| 7 | 1,105 | 89.3% | +2.6 pts | 88.1% | 88.8% | 87.7% | 93.4% |
| 8 | 910 | 92.6% | +3.3 pts | 92.5% | 92.4% | 89.5% | 94.3% |
| 9 | 713 | 92.7% | +0.1 pts | 94.9% | 89.2% | 89.1% | 93.3% |
| 10+ | 3,504 | 97.1% | +4.4 pts | 97.3% | 96.3% | 96.8% | 97.4% |

There is no cliff. Each extra action is worth less, and from about the third action the gain drops below 8 points, so 3 is a reasonable bar, not a magic number. The pattern holds inside every channel, so it is not just channel mix. It is still correlation: users who were going to stay anyway also do more in week one. Before pushing users toward three actions, test it, for example with an onboarding change that makes the second and third actions easier, and measure day-30 retention.

## 4. Daily monitoring

Each metric is checked every morning against a robust baseline: the median of the lagged days, with a band of 4 robust standard deviations from the previous four weeks of residuals. Flagged days are left out of later baselines. The first six weeks are a warm-up.

The planted incidents:

- **Android release bug, March 10 to 14:** onboarding completion on Android drops by about 45%.
- **iOS tracking outage, April 22:** 70% of iOS `session_start` events are lost. Behavior is unchanged.
- **Paid social campaign, May 5 to 18:** paid social signups triple, and these users engage less.

Days flagged, by metric:

| Metric | Android bug (5 days) | iOS outage (1 day) | Campaign (14 days) | False alarms (other days) |
|---|---|---|---|---|
| `signups` | 0 | 0 | 11 | 0 |
| `onboarding_rate` | 5 | 0 | 0 | 0 |
| `activation_rate_7d` | 0 | 0 | 0 | 0 |
| `dau` | 0 | 1 | 0 | 0 |
| `actions_per_dau` | 0 | 1 | 0 | 0 |
| `orphan_action_share` | 0 | 1 | 0 | 0 |
| `onboarding_rate, Android only` | 5 | 0 | 0 | 0 |

The Android bug shows in the overall onboarding rate, but it is much sharper in the Android series (z of -11.1 at the worst point against -6.6 overall). For a product with a few large segments, watching each platform costs little. Both series fire on day one here, but the Android one is far outside its band, so it would still fire for a smaller bug that the overall rate would absorb. The campaign does not trip the activation alarm: the drop is real but gradual, and section 5 shows why.

## 5. Diagnosis: what changed, and where

Each incident window is compared with the same weekdays in the four weeks before it. The change in an overall rate splits exactly into a **mix** effect (a segment's share of signups moved), a **rate** effect (the segment's own rate moved), and a small interaction.

### Onboarding rate, March 10 to 14, by platform

| Segment | Share before | Share after | Rate before | Rate after | Mix effect | Rate effect | Total |
|---|---|---|---|---|---|---|---|
| android | 39.6% | 39.2% | 67.6% | 37.9% | -0.25 pts | -11.77 pts | -11.90 pts |
| web | 15.1% | 15.0% | 62.9% | 60.7% | -0.02 pts | -0.33 pts | -0.34 pts |
| ios | 45.3% | 45.7% | 72.2% | 71.6% | +0.28 pts | -0.26 pts | +0.02 pts |

Overall onboarding fell 12.2 pts, and 96% of that is Android's own rate. The platform mix did not move. This is a product problem on one platform: check what shipped on Android around March 10.

### DAU drop on April 22: real or tracking?

| Platform | DAU change | Users with a core action, change | Acting users with no session (that day) |
|---|---|---|---|
| ios | -62% | -1% | 62.3% |
| android | +1% | +0% | 0.0% |
| web | +2% | +1% | 0.0% |

Total DAU changed -28%. Only iOS sessions dropped, while iOS users kept doing core actions at the usual rate, and many acting users have no session at all, which cannot happen in the product. The drop is a logging failure, not lost users. The right response is to annotate the dashboard and fix the iOS logging, not to explain a 28% fall in engagement. The orphan-action check catches this on day one.

### Activation rate, May 5 to 18, by channel

| Segment | Share before | Share after | Rate before | Rate after | Mix effect | Rate effect | Total |
|---|---|---|---|---|---|---|---|
| organic | 39.6% | 28.7% | 36.4% | 36.7% | -3.99 pts | +0.14 pts | -3.89 pts |
| referral | 15.2% | 10.6% | 48.1% | 48.2% | -2.21 pts | +0.01 pts | -2.21 pts |
| paid_search | 24.8% | 17.9% | 31.2% | 32.1% | -2.15 pts | +0.24 pts | -1.98 pts |
| paid_social | 20.4% | 42.9% | 19.2% | 20.8% | +4.31 pts | +0.33 pts | +5.01 pts |

Activation fell 3.1 pts. Mix explains -4.0 pts and within-channel rates +0.7 pts. Paid social's own activation rate barely moved; there were simply many more paid social signups, and that channel always activates less. Nothing in the product broke. The question for the campaign is cost per activated user, not why activation fell.
