-- Temporary analytical facts only; immutable Silver remains the sensor/provenance source.
-- Tie order is stable Bronze provenance. Zero-duration duplicate intervals contribute no distance.
CREATE OR REPLACE TEMP TABLE interval_batch AS
WITH ordered AS (
    SELECT vehicle_id, trip_id, engine_type, day_number, elapsed_ms, speed_kmh,
        fuel_rate_lph, source_file, len(quality_flags) AS quality_flag_count,
        sampling_gap_ms AS silver_sampling_gap_ms,
        elapsed_ms - lag(elapsed_ms) OVER trip_order AS gap_ms,
        lag(speed_kmh) OVER trip_order AS previous_speed_kmh
    FROM silver_week
    WINDOW trip_order AS (PARTITION BY vehicle_id,trip_id
        ORDER BY elapsed_ms,bronze_file,bronze_row_index)
)
SELECT *, DATE '2017-11-01' + floor(day_number-1)::INTEGER AS trip_start_reference_day,
    coalesce(gap_ms>0 AND gap_ms<=2000 AND speed_kmh IS NOT NULL
        AND previous_speed_kmh IS NOT NULL AND speed_kmh>=0 AND previous_speed_kmh>=0,
        false) AS eligible_speed_interval
FROM ordered;
