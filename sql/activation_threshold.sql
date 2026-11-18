-- Day-30 retention by number of core actions in the first 7 days, for January to April signups.
-- Retained = any session on days 28 to 34 after signup.
WITH cohort AS (SELECT * FROM users WHERE signup_ts < TIMESTAMP '2025-05-01'),
first_week AS (
  SELECT c.user_id, count(e.user_id) AS actions_7d
  FROM cohort c LEFT JOIN events e
    ON e.user_id = c.user_id AND e.event = 'core_action' AND e.ts < c.signup_ts + INTERVAL 7 DAYS
  GROUP BY ALL
),
d30 AS (
  SELECT DISTINCT c.user_id
  FROM cohort c JOIN events e USING (user_id)
  WHERE e.event = 'session_start' AND date_diff('day', c.signup_ts, e.ts) BETWEEN 28 AND 34
)
SELECT least(f.actions_7d, 10) AS actions_7d, c.channel,
       count(*) AS users, avg((d.user_id IS NOT NULL)::INT) AS retained_d30
FROM cohort c JOIN first_week f USING (user_id) LEFT JOIN d30 d USING (user_id)
GROUP BY ALL
ORDER BY ALL;
