-- Chunk count and size for the main hypertable
SELECT hypertable_name, count(*) AS chunks, pg_size_pretty(sum(total_bytes)) AS size
FROM timescaledb_information.chunks c
JOIN LATERAL chunks_detailed_size(format('%I.%I', c.chunk_schema, c.chunk_name)::regclass) s ON true
WHERE hypertable_name = 'deliverability_events'
GROUP BY 1;
