-- A row can have multiple flags. Counts are occurrences, not disjoint exclusions.
SELECT flag AS quality_flag, count(*)::BIGINT AS observation_count,
    count(*)::DOUBLE/(SELECT count(*) FROM silver) AS observation_fraction
FROM (SELECT unnest(quality_flags) AS flag FROM silver) AS flags
GROUP BY flag ORDER BY flag;
