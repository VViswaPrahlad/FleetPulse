-- Independent source totals: do not validate solely against intermediate Gold facts.
SELECT count(*),count(DISTINCT vehicle_id),count(DISTINCT (vehicle_id,trip_id)),
    count(speed_kmh),count(fuel_rate_lph),avg(speed_kmh),
    count(*) FILTER (WHERE gap_gt_2000ms),
    count(*) FILTER (WHERE len(quality_flags)>0),sum(len(quality_flags))
FROM silver;
