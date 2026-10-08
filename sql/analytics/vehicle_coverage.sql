-- Null eligible-distance means no supported intervals, unlike measured zero.
SELECT vehicle_id, engine_type, trip_count, observation_count,
    speed_time_weighted_mean_kmh, observed_distance_km, gap_gt_2s_count,
    missing_speed_count::DOUBLE/observation_count AS missing_speed_fraction,
    missing_fuel_rate_count::DOUBLE/observation_count AS missing_fuel_fraction
FROM vehicle_analytics ORDER BY observed_distance_km DESC NULLS LAST, vehicle_id LIMIT 20;
