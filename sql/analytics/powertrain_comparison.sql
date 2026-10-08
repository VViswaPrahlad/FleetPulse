SELECT engine_type,vehicle_count,trip_count,observation_count,
    speed_sample_p50_kmh,speed_sample_p95_kmh,speed_time_weighted_mean_kmh,
    fuel_rate_observation_count::DOUBLE/observation_count AS fuel_rate_presence_fraction,
    observed_distance_km,gap_gt_2s_count
FROM powertrain_fleet ORDER BY engine_type;
