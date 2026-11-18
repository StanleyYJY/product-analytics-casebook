-- Ordered funnel for users who signed up January to April (every window has closed by June 30).
-- Each step must happen after the previous one and inside its window.
WITH cohort AS (
  SELECT * FROM users WHERE signup_ts < TIMESTAMP '2025-05-01'
),
first_ts AS (
  SELECT user_id,
         min(ts) FILTER (WHERE event = 'onboarding_complete') AS onboarded_ts,
         min(ts) FILTER (WHERE event = 'trial_start') AS trial_ts,
         min(ts) FILTER (WHERE event = 'subscription_paid') AS paid_ts
  FROM events GROUP BY ALL
),
activated AS (
  SELECT user_id, ts AS activated_ts
  FROM (SELECT e.user_id, e.ts, row_number() OVER (PARTITION BY e.user_id ORDER BY e.ts) AS n
        FROM events e JOIN cohort u USING (user_id)
        WHERE e.event = 'core_action' AND e.ts < u.signup_ts + INTERVAL 7 DAYS)
  WHERE n = 3
),
steps AS (
  SELECT c.user_id, c.platform, c.channel,
         f.onboarded_ts < c.signup_ts + INTERVAL 24 HOURS AS s_onboarded,
         a.activated_ts IS NOT NULL AS s_activated,
         a.activated_ts IS NOT NULL AND f.trial_ts >= a.activated_ts
           AND f.trial_ts < c.signup_ts + INTERVAL 30 DAYS AS s_trial,
         f.paid_ts >= f.trial_ts AND f.trial_ts >= a.activated_ts
           AND f.trial_ts < c.signup_ts + INTERVAL 30 DAYS AS s_paid,
         date_diff('minute', c.signup_ts, a.activated_ts) / 1440.0 AS days_to_activate
  FROM cohort c
  LEFT JOIN first_ts f USING (user_id)
  LEFT JOIN activated a USING (user_id)
)
SELECT {group_by} AS segment,
       count(*) AS signups,
       avg(coalesce(s_onboarded, false)::INT) AS onboarded,
       avg(coalesce(s_activated, false)::INT) AS activated,
       avg(coalesce(s_trial, false)::INT) AS trial,
       avg(coalesce(s_paid, false)::INT) AS paid,
       median(days_to_activate) AS median_days_to_activate
FROM steps
GROUP BY ALL
ORDER BY signups DESC;
