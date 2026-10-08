"""Regenerate descriptive Gold using local DuckDB SQL and Windows PyArrow IO.

No missing measurements are filled. Only project-local explicit Parquet inputs
are accepted. SQL and input/output hashes form a reproducibility manifest.
"""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import time

import duckdb
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SILVER = ROOT / 'data/silver/ved'
OUTPUT = ROOT / 'data/gold/ved'
RESULTS = ROOT / 'results/day4'
SQL = ROOT / 'sql/gold'
TABLES = ('trip_analytics', 'vehicle_analytics', 'daily_fleet', 'monthly_fleet',
          'powertrain_fleet', 'fleet_overview', 'quality_metrics')
VERSION = 'ved-gold-1'
CAP = 10_000_000_000
LOG = logging.getLogger('fleetpulse.gold')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def footprint():
    def fail(error):
        raise error
    # Path.rglob may skip inaccessible directories; never understate the budget.
    return sum((Path(folder)/name).stat().st_size
        for folder,_,names in os.walk(ROOT,onerror=fail) for name in names)


def local(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f'Path must stay inside FleetPulse: {path}')
    return path


def literal(text):
    return "'" + str(text).replace("'", "''") + "'"


def connect(temp=None):
    temp = local(temp or ROOT / 'data/tmp/duckdb-day4')
    temp.mkdir(parents=True, exist_ok=True)
    # Fixed thread count also makes floating reduction order reproducible.
    # Bundled Parquet only; do not install/load external extensions.
    return duckdb.connect(config={'threads': 1, 'memory_limit': '4GB',
        'temp_directory': str(temp), 'max_temp_directory_size': '1500MB',
        'autoinstall_known_extensions': False, 'autoload_known_extensions': False})


def silver_view(con, paths):
    paths = [local(p) for p in paths]
    if not paths:
        raise ValueError('No Silver Parquet inputs')
    names = '[' + ','.join(literal(p.as_posix()) for p in paths) + ']'
    con.execute(f'CREATE VIEW silver AS SELECT * FROM read_parquet({names}, hive_partitioning=false)')


def build_tables(con, output, paths=None):
    """Execute reviewable SQL and write stable, small Arrow Gold tables."""
    output = local(output)
    output.mkdir(parents=True, exist_ok=True)
    interval_sql = (SQL / 'interval_facts.sql').read_text(encoding='utf-8')
    if paths:
        crossing = con.execute('''SELECT count(*) FROM (
            SELECT vehicle_id,trip_id FROM silver GROUP BY vehicle_id,trip_id
            HAVING count(DISTINCT source_file)>1)''').fetchone()[0]
        if crossing:
            raise RuntimeError('Weekly batching requires complete trips; cross-file trips detected')
    batches = list(paths) if paths else [None]
    for i,path in enumerate(batches):
        source = f'read_parquet({literal(local(path).as_posix())},hive_partitioning=false)' if path else 'silver'
        con.execute(f'CREATE OR REPLACE VIEW silver_week AS SELECT * FROM {source}')
        con.execute(interval_sql)
        if i==0:
            con.execute('CREATE TEMP TABLE interval_facts AS SELECT * FROM interval_batch')
        else:
            con.execute('INSERT INTO interval_facts SELECT * FROM interval_batch')
        con.execute('DROP TABLE interval_batch')
        if i%10==0 or i==len(batches)-1:
            LOG.info('Ordered weekly intervals: %s/%s',i+1,len(batches))
    metadata = {}
    for name in TABLES:
        started = time.perf_counter()
        query = (SQL / f'{name}.sql').read_text(encoding='utf-8')
        table = con.execute(query).fetch_arrow_table()
        path = output / f'{name}.parquet'
        pq.write_table(table, path, compression='zstd', row_group_size=65536)
        if pq.ParquetFile(path).metadata.num_rows != len(table):
            raise RuntimeError(f'Write reconciliation failed: {name}')
        con.execute(f'CREATE VIEW {name} AS SELECT * FROM read_parquet({literal(path.as_posix())})')
        metadata[name] = {'rows': len(table), 'bytes': path.stat().st_size,
                          'sha256': sha256(path), 'runtime_seconds': time.perf_counter()-started}
        LOG.info('%s: %s rows, %s bytes', name, len(table), path.stat().st_size)
    return metadata


def reconcile(con):
    """Independent direct-Silver aggregates, compared to the published summaries."""
    source = con.execute((ROOT/'sql/validation/silver_totals.sql').read_text(encoding='utf-8')).fetchone()
    checks = {}
    for name in TABLES[:5]:
        got = con.execute(f'''SELECT sum(observation_count),sum(speed_observation_count),
            sum(fuel_rate_observation_count),sum(gap_gt_2s_count),
            sum(flagged_observation_count),sum(quality_flag_occurrence_count),
            sum(speed_sample_mean_kmh*speed_observation_count)/sum(speed_observation_count)
            FROM {name}''').fetchone()
        expected = (source[0],source[3],source[4],source[6],source[7],source[8])
        if got[:6] != expected or (source[5] is not None and abs(got[6]-source[5])>1e-9):
            raise RuntimeError(f'{name} aggregate reconciliation failed: {got}, source={source}')
        checks[name] = {'observations': got[0], 'speed_observations': got[1],
            'fuel_rate_observations': got[2], 'gap_gt_2s': got[3],
            'flagged_observations': got[4], 'quality_flag_occurrences': got[5],
            'weighted_sample_mean_kmh': got[6]}
    overview = con.execute('SELECT observation_count,vehicle_count,trip_count FROM fleet_overview').fetchone()
    if overview != source[:3]:
        raise RuntimeError('Fleet distinct counts differ from Silver')
    trip_stats = con.execute('''SELECT count(*) FILTER (WHERE distinct_day_number_count<>1),
        count(*) FILTER (WHERE observed_speed_interval_s > elapsed_span_s+1e-8),
        max(source_file_count) FROM trip_analytics''').fetchone()
    gap_mismatch = con.execute('''SELECT count(*) FROM interval_facts
        WHERE gap_ms IS DISTINCT FROM silver_sampling_gap_ms''').fetchone()[0]
    if trip_stats[0] or trip_stats[1] or gap_mismatch:
        raise RuntimeError(f'Trip/time invariants failed: {trip_stats}, gap mismatches={gap_mismatch}')
    quality = con.execute('SELECT sum(observation_count) FROM quality_metrics').fetchone()[0]
    if (quality or 0) != source[8]:
        raise RuntimeError('Quality occurrence reconciliation failed')
    return {'passed': True, 'silver_rows':source[0], 'vehicles':source[1],
        'trips':source[2], 'tables':checks, 'sampling_gap_mismatches':gap_mismatch,
        'max_source_files_per_trip':trip_stats[2], 'quality_occurrences':quality}


def snapshot(paths):
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def run(force=False):
    started = time.perf_counter()
    RESULTS.mkdir(parents=True, exist_ok=True)
    paths = sorted(SILVER.rglob('*.parquet'))
    bronze = sorted((ROOT / 'data/bronze/ved').rglob('*.parquet'))
    used = footprint()
    # Spill is capped to 1.5 GB; reserve that plus 100 MB of staged Gold.
    if used+1_600_000_000 >= CAP or shutil.disk_usage(ROOT).free < 1_700_000_000:
        raise RuntimeError('Storage/free-space gate failed before Gold execution')
    input_hashes = snapshot(paths)
    bronze_hashes = snapshot(bronze)
    config = {'version':VERSION,'duckdb':duckdb.__version__,'threads':1,'memory_limit':'4GB',
        'gap_limit_ms':2000,'time_basis':'trip_start_dataset_reference_day_timezone_unspecified',
        'code_sha256':sha256(Path(__file__)),
        'sql_sha256': {p.relative_to(ROOT/'sql').as_posix():sha256(p)
                       for p in sorted((ROOT/'sql').rglob('*.sql'))}}
    manifest_path = RESULTS / 'gold_manifest.json'
    if manifest_path.exists() and not force:
        previous = json.loads(manifest_path.read_text())
        if (previous['inputs']==input_hashes and previous['config']==config
            and previous['bronze_hashes']==bronze_hashes and set(previous['tables'])==set(TABLES)) and all(
            (OUTPUT/f'{n}.parquet').exists() and sha256(OUTPUT/f'{n}.parquet')==m['sha256']
            for n,m in previous['tables'].items()):
            return {'cached':True,'runtime_seconds':time.perf_counter()-started,
                'tables':previous['tables'],'project_bytes':footprint()}
    stage = local(ROOT / 'data/tmp/gold-day4-stage')
    stage.mkdir(parents=True,exist_ok=True)
    con = connect()
    try:
        silver_view(con, paths)
        compute_start = time.perf_counter()
        tables = build_tables(con, stage, paths)
        compute_seconds = time.perf_counter()-compute_start
        validation_start = time.perf_counter()
        validation = reconcile(con)
        validation_seconds = time.perf_counter()-validation_start
    finally:
        con.close()
    if snapshot(paths)!=input_hashes or snapshot(bronze)!=bronze_hashes:
        raise RuntimeError('Immutable source hashes changed during Gold execution')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for name in TABLES:
        os.replace(stage/f'{name}.parquet', OUTPUT/f'{name}.parquet')
    stage.rmdir()
    result = {'cached':False,'version':VERSION,'config':config,'inputs':input_hashes,
        'bronze_hashes':bronze_hashes, 'tables':tables,'reconciliation':validation,
        'bronze_silver_unchanged':True,'compute_seconds':compute_seconds,
        'validation_seconds':validation_seconds,'runtime_seconds':time.perf_counter()-started,
        'gold_bytes':sum(x['bytes'] for x in tables.values()),'project_bytes':footprint()}
    manifest_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force',action='store_true',help='Regenerate instead of using verified hash cache')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    result = run(args.force)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
