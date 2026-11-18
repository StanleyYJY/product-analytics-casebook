-- One row per day: the metrics a product team watches every morning.
-- Cohort metrics (onboarding, activation) are keyed to the signup day.
WITH days AS (
  SELECT CAST(range AS DATE) AS day FROM range(DATE '2025-01-01', DATE '2025-07-01', INTERVAL 1 DAY)
),
onboarded AS (
  SELECT user_id, min(ts) AS onboarded_ts FROM events WHERE event = 'onboarding_complete' GROUP BY ALL
),
third_action AS (  -- activation = third core action within 7 days of signup
  SELECT user_id, ts AS activated_ts
  FROM (SELECT e.user_id, e.ts, row_number() OVER (PARTITION BY e.user_id ORDER BY e.ts) AS n
        FROM events e JOIN users u USING (user_id)
        WHERE e.event = 'core_action' AND e.ts < u.signup_ts + INTERVAL 7 DAYS)
  WHERE n = 3
),
cohort AS (
  SELECT CAST(u.signup_ts AS DATE) AS day,
         count(*) AS signups,
         avg(coalesce(o.onboarded_ts < u.signup_ts + INTERVAL 24 HOURS, false)::INT) AS onboarding_rate,
         avg((a.activated_ts IS NOT NULL)::INT) AS activation_rate_7d
  FROM users u
  LEFT JOIN onboarded o USING (user_id)
  LEFT JOIN third_action a USING (user_id)
  GROUP BY ALL
),
activity AS (
  SELECT CAST(ts AS DATE) AS day,
         count(DISTINCT user_id) FILTER (WHERE event = 'session_start') AS dau,
         count(DISTINCT user_id) FILTER (WHERE event = 'core_action') AS action_users,
         count(*) FILTER (WHERE event = 'core_action') AS core_actions
  FROM events GROUP BY ALL
),
orphans AS (  -- data check: a user who acted on a day must have started a session that day
  SELECT CAST(a.ts AS DATE) AS day, count(DISTINCT a.user_id) AS orphan_action_users
  FROM events a
  WHERE a.event = 'core_action'
    AND NOT EXISTS (SELECT 1 FROM events s
                    WHERE s.event = 'session_start' AND s.user_id = a.user_id
                      AND CAST(s.ts AS DATE) = CAST(a.ts AS DATE))
  GROUP BY ALL
)
SELECT d.day, c.signups, c.onboarding_rate, c.activation_rate_7d,
       ac.dau, ac.action_users, ac.core_actions / ac.dau AS actions_per_dau,
       coalesce(o.orphan_action_users, 0) / ac.action_users AS orphan_action_share,
       d.day <= DATE '2025-07-01' - INTERVAL 7 DAYS AS activation_complete
FROM days d
JOIN cohort c USING (day)
JOIN activity ac USING (day)
LEFT JOIN orphans o USING (day)
ORDER BY d.day;
