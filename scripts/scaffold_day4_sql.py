"""Development utility: materialize the reviewable Gold SQL definitions."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sql = root / 'sql/gold'
sql.mkdir(parents=True, exist_ok=True)
metrics = """count(*)::BIGINT AS observation_count,
    count(DISTINCT vehicle_id)::BIGINT AS vehicle_count,
    count(DISTINCT (vehicle_id,trip_id))::BIGINT AS trip_count,
    count(DISTINCT source_file)::BIGINT AS source_file_count,
    count(speed_kmh)::BIGINT AS speed_observation_count,
    count(*) - count(speed_kmh) AS missing_speed_count,
    count(fuel_rate_lph)::BIGINT AS fuel_rate_observation_count,
    count(*) - count(fuel_rate_lph) AS missing_fuel_rate_count,
    avg(speed_kmh) AS speed_sample_mean_kmh,
    stddev_pop(speed_kmh) AS speed_sample_stddev_kmh,
    min(speed_kmh) AS speed_min_kmh,
    quantile_cont(speed_kmh,0.5) AS speed_sample_p50_kmh,
    quantile_cont(speed_kmh,0.95) AS speed_sample_p95_kmh,
    max(speed_kmh) AS speed_max_kmh,
    count(*) FILTER (WHERE speed_kmh=0) AS stopped_observation_count,
    count(*) FILTER (WHERE quality_flag_count>0) AS flagged_observation_count,
    sum(quality_flag_count)::BIGINT AS quality_flag_occurrence_count,
    count(*) FILTER (WHERE gap_ms>2000) AS gap_gt_2s_count,
    count(*) FILTER (WHERE gap_ms>10000) AS gap_gt_10s_count,
    count(*) FILTER (WHERE gap_ms=0) AS duplicate_timestamp_count,
    max(gap_ms)/1000.0 AS max_sampling_gap_s,
    quantile_cont(gap_ms FILTER (WHERE gap_ms>0),0.5)/1000.0 AS positive_gap_p50_s,
    quantile_cont(gap_ms FILTER (WHERE gap_ms>0),0.95)/1000.0 AS positive_gap_p95_s,
    count(*) FILTER (WHERE eligible_speed_interval) AS eligible_speed_interval_count,
    sum(gap_ms/1000.0) FILTER (WHERE eligible_speed_interval) AS observed_speed_interval_s,
    sum((previous_speed_kmh+speed_kmh)*0.5*gap_ms/3600000.0)
        FILTER (WHERE eligible_speed_interval) AS observed_distance_km,
    sum(CASE WHEN previous_speed_kmh=0 AND speed_kmh=0 THEN gap_ms/1000.0 ELSE 0 END)
        FILTER (WHERE eligible_speed_interval) AS observed_stopped_interval_s,
    sum((previous_speed_kmh+speed_kmh)*0.5*gap_ms)
        FILTER (WHERE eligible_speed_interval)
        / nullif(sum(gap_ms) FILTER (WHERE eligible_speed_interval),0) AS speed_time_weighted_mean_kmh,
    min(trip_start_reference_day) AS first_trip_start_reference_day,
    max(trip_start_reference_day) AS last_trip_start_reference_day"""
# DuckDB FILTER belongs on aggregate, not its input expression.
metrics = metrics.replace('quantile_cont(gap_ms FILTER (WHERE gap_ms>0),0.5)',
    'quantile_cont(gap_ms,0.5) FILTER (WHERE gap_ms>0)').replace(
    'quantile_cont(gap_ms FILTER (WHERE gap_ms>0),0.95)',
    'quantile_cont(gap_ms,0.95) FILTER (WHERE gap_ms>0)')
groups = {
    'trip_analytics': ('vehicle_id, trip_id, engine_type', ',\n    (max(elapsed_ms)-min(elapsed_ms))/1000.0 AS elapsed_span_s,\n    count(DISTINCT day_number) AS distinct_day_number_count'),
    'vehicle_analytics': ('vehicle_id, engine_type', ''),
    'daily_fleet': ('trip_start_reference_day', ''),
    'monthly_fleet': ("date_trunc('month',trip_start_reference_day)::DATE AS trip_start_reference_month", ''),
    'powertrain_fleet': ('engine_type', ''),
    'fleet_overview': ('', ''),
}
for name, (keys, extra) in groups.items():
    grouping = keys.split(' AS ')[-1] if ' AS ' in keys else keys
    suffix = '\nGROUP BY '+grouping+'\nORDER BY '+grouping if keys else ''
    text = '-- Measured Silver observations; distance excludes missing endpoints and gaps >2s.\n'
    text += 'SELECT '+(keys+',\n    ' if keys else '')+metrics+extra+'\nFROM interval_facts'+suffix+';\n'
    (sql / (name+'.sql')).write_text(text, encoding='utf-8')
