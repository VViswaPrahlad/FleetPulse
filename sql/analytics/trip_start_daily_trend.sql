-- Trip-start reference date cohort, not a wall-clock traffic-volume measure.
SELECT trip_start_reference_day,vehicle_count,trip_count,observation_count,
    speed_time_weighted_mean_kmh,observed_distance_km,gap_gt_2s_count
FROM daily_fleet ORDER BY trip_start_reference_day;
