-- Share of acting users with no session_start that day, by platform. Should be zero.
WITH acted AS (
  SELECT DISTINCT user_id, platform, CAST(ts AS DATE) AS day FROM events WHERE event = 'core_action'
),
sessions AS (
  SELECT DISTINCT user_id, CAST(ts AS DATE) AS day FROM events WHERE event = 'session_start'
)
SELECT a.day, a.platform, count(*) AS action_users,
       avg((s.user_id IS NULL)::INT) AS orphan_action_share
FROM acted a LEFT JOIN sessions s USING (user_id, day)
GROUP BY ALL
ORDER BY ALL;
