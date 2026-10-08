SELECT observation_count, vehicle_count, trip_count, speed_sample_mean_kmh,
    speed_time_weighted_mean_kmh, observed_distance_km,
    observed_speed_interval_s, gap_gt_2s_count,
    missing_speed_count::DOUBLE/observation_count AS missing_speed_fraction,
    missing_fuel_rate_count::DOUBLE/observation_count AS missing_fuel_fraction
FROM fleet_overview;
