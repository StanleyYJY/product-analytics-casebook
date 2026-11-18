-- Weekly cohort retention: share of each signup-week cohort with a session in week k after signup.
-- Cells whose week has not fully elapsed by the end of the data are left out.
WITH cohort AS (
  SELECT user_id, signup_ts, date_trunc('week', signup_ts) AS cohort_week, {segment} AS segment FROM users
),
activity AS (
  SELECT DISTINCT c.user_id, c.cohort_week, c.segment,
         date_diff('day', c.signup_ts, e.ts) // 7 AS week_k
  FROM events e JOIN cohort c USING (user_id)
  WHERE e.event = 'session_start'
),
sizes AS (
  SELECT cohort_week, segment, count(*) AS cohort_size FROM cohort GROUP BY ALL
)
SELECT a.cohort_week, a.segment, a.week_k, any_value(s.cohort_size) AS cohort_size,
       count(*) / any_value(s.cohort_size) AS retention
FROM activity a JOIN sizes s USING (cohort_week, segment)
WHERE a.cohort_week + INTERVAL 7 DAYS * (a.week_k + 2) <= TIMESTAMP '2025-07-01'
  AND a.week_k <= 12
GROUP BY ALL
ORDER BY ALL;
