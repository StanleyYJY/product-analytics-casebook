-- Signups and 24-hour onboarding by day, platform and channel, for drilldowns.
WITH onboarded AS (
  SELECT user_id, min(ts) AS onboarded_ts FROM events WHERE event = 'onboarding_complete' GROUP BY ALL
),
third_action AS (
  SELECT user_id
  FROM (SELECT e.user_id, row_number() OVER (PARTITION BY e.user_id ORDER BY e.ts) AS n
        FROM events e JOIN users u USING (user_id)
        WHERE e.event = 'core_action' AND e.ts < u.signup_ts + INTERVAL 7 DAYS)
  WHERE n = 3
)
SELECT CAST(u.signup_ts AS DATE) AS day, u.platform, u.channel,
       count(*) AS signups,
       sum(coalesce(o.onboarded_ts < u.signup_ts + INTERVAL 24 HOURS, false)::INT) AS onboarded_24h,
       sum((a.user_id IS NOT NULL)::INT) AS activated_7d
FROM users u
LEFT JOIN onboarded o USING (user_id)
LEFT JOIN third_action a USING (user_id)
GROUP BY ALL
ORDER BY ALL;
