-- Domains whose last 3 days look like they are burning
SELECT d.name, s.day, s.sent, s.bounces, round(s.bounces::numeric / nullif(s.sent, 0), 4) AS bounce_rate,
       s.inbox_placement, s.warmup_score
FROM domain_daily_stats s
JOIN domains d ON d.id = s.domain_id
WHERE s.day > now() - INTERVAL '3 days'
  AND (s.bounces::numeric / nullif(s.sent, 0) > 0.03 OR s.inbox_placement < 0.7)
ORDER BY bounce_rate DESC NULLS LAST;
