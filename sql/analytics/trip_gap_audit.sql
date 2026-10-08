SELECT vehicle_id,trip_id,engine_type,observation_count,elapsed_span_s,
    observed_speed_interval_s,
    observed_speed_interval_s/nullif(elapsed_span_s,0) AS observed_span_coverage_fraction,
    gap_gt_2s_count,max_sampling_gap_s,missing_speed_count
FROM trip_analytics
ORDER BY gap_gt_2s_count DESC,vehicle_id,trip_id LIMIT 20;
