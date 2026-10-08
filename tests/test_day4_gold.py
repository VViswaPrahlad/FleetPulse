from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.analytics.build_gold import ROOT, TABLES, build_tables, connect, local, reconcile, sha256, silver_view


@pytest.fixture
def fixture_path(tmp_path):
    # pytest basetemp is explicitly project-local, matching production path rules.
    rows = []
    examples = [
        (1,1,1.25,[0,1000,2000,5000,6000,7000],[60.,60.,60.,60.,None,60.]),
        (1,2,2.0,[0,1000,3000],[0.,60.,60.]),
        (2,1,32.1,[0,1000],[None,None]),
        (3,1,32.2,[0,1000,1000,2000],[0.,0.,0.,0.]),
    ]
    for vehicle,trip,day,times,speeds in examples:
        for i,(elapsed,speed) in enumerate(zip(times,speeds)):
            gap = elapsed-times[i-1] if i else None
            flags = ([] if speed is not None else ['missing_speed_kmh']) + ['missing_fuel_rate_lph']
            if gap is not None and gap>2000:
                flags.append('irregular_gap_gt_2s')
            rows.append(dict(vehicle_id=vehicle,trip_id=trip,engine_type='ICE' if vehicle==1 else 'EV',
                day_number=day,elapsed_ms=elapsed,speed_kmh=speed,fuel_rate_lph=None,
                source_file='fixture.csv',bronze_file='fixture.parquet',bronze_row_index=len(rows),
                quality_flags=flags,sampling_gap_ms=gap,gap_gt_2000ms=bool(gap and gap>2000)))
    schema = pa.schema([('vehicle_id',pa.int64()),('trip_id',pa.int64()),('engine_type',pa.string()),
        ('day_number',pa.float64()),('elapsed_ms',pa.int64()),('speed_kmh',pa.float64()),
        ('fuel_rate_lph',pa.float64()),('source_file',pa.string()),('bronze_file',pa.string()),
        ('bronze_row_index',pa.int64()),('quality_flags',pa.list_(pa.string())),
        ('sampling_gap_ms',pa.int64()),('gap_gt_2000ms',pa.bool_())])
    path = tmp_path/'silver.parquet'
    pq.write_table(pa.Table.from_pylist(rows,schema=schema),path)
    return path


@pytest.fixture
def built(fixture_path,tmp_path):
    with connect(tmp_path/'spill') as con:
        silver_view(con,[fixture_path])
        metadata = build_tables(con,tmp_path/'gold')
        yield con,metadata,tmp_path/'gold'


def test_row_and_aggregate_reconciliation(built):
    con,metadata,_ = built
    result = reconcile(con)
    assert result['passed'] and result['silver_rows']==15
    assert result['vehicles']==3 and result['trips']==4
    assert metadata['trip_analytics']['rows']==4
    assert metadata['vehicle_analytics']['rows']==3


def test_distance_does_not_bridge_gaps_or_missing_measurements(built):
    con,_,_ = built
    got = con.execute('''SELECT observed_distance_km,observed_speed_interval_s,
        speed_time_weighted_mean_kmh,gap_gt_2s_count,elapsed_span_s
        FROM trip_analytics WHERE vehicle_id=1 AND trip_id=1''').fetchone()
    assert got == pytest.approx((60*2/3600,2,60,1,7))


def test_irregular_sample_mean_is_not_time_weighted_mean(built):
    con,_,_ = built
    got = con.execute('''SELECT speed_sample_mean_kmh,speed_time_weighted_mean_kmh,
        observed_stopped_interval_s FROM trip_analytics WHERE vehicle_id=1 AND trip_id=2''').fetchone()
    assert got == pytest.approx((40,50,0))
    # Sample mean=40; trapezoidal time mean=(30*1+60*2)/3=50.


def test_all_missing_speed_is_null_not_zero(built):
    con,_,_ = built
    got = con.execute('''SELECT speed_sample_mean_kmh,observed_distance_km,
        observed_speed_interval_s,speed_time_weighted_mean_kmh,missing_speed_count,
        fuel_rate_observation_count FROM trip_analytics WHERE vehicle_id=2''').fetchone()
    assert got == (None,None,None,None,2,0)


def test_measured_stationary_distance_is_zero(built):
    con,_,_ = built
    got = con.execute('''SELECT observed_distance_km,observed_speed_interval_s,
        duplicate_timestamp_count FROM trip_analytics WHERE vehicle_id=3''').fetchone()
    assert got == (0.,2.,1)


def test_reference_dates_are_trip_start_dates(built):
    con,_,_ = built
    assert con.execute('SELECT trip_start_reference_day FROM daily_fleet ORDER BY 1').fetchall()==[
        (date(2017,11,1),),(date(2017,11,2),),(date(2017,12,2),)]
    assert con.execute('SELECT count(*) FROM monthly_fleet').fetchone()[0]==2


def test_parquet_readability_schema_and_primary_keys(built):
    con,metadata,output = built
    for name in TABLES:
        table = pq.read_table(output/f'{name}.parquet')
        assert len(table)==metadata[name]['rows']
        assert 'observation_count' in table.column_names
        assert pa.types.is_int64(table.schema.field('observation_count').type)
    assert con.execute('SELECT count(*) FROM (SELECT vehicle_id,trip_id FROM trip_analytics GROUP BY ALL)').fetchone()[0]==4


def test_fresh_runs_are_byte_reproducible_and_silver_unchanged(fixture_path,tmp_path):
    before = sha256(fixture_path)
    snapshots = []
    for i in range(2):
        with connect(tmp_path/f'spill{i}') as con:
            silver_view(con,[fixture_path])
            snapshots.append({n:m['sha256'] for n,m in build_tables(con,tmp_path/f'gold{i}').items()})
    assert snapshots[0]==snapshots[1]
    assert sha256(fixture_path)==before


def test_detects_corrupted_sampling_gap(built):
    con,_,_ = built
    con.execute('UPDATE interval_facts SET silver_sampling_gap_ms=999 WHERE gap_ms=1000')
    with pytest.raises(RuntimeError,match='invariants'):
        reconcile(con)


def test_outside_project_paths_rejected():
    with pytest.raises(ValueError,match='inside FleetPulse'):
        local(ROOT.parent/'unrelated.parquet')


@pytest.mark.parametrize('query',[
    'fleet_overview','vehicle_coverage','trip_gap_audit','powertrain_comparison',
    'trip_start_daily_trend','quality_flags'])
def test_reusable_demo_sql_executes_against_gold(built,query):
    con,_,_ = built
    sql=(ROOT/'sql/analytics'/f'{query}.sql').read_text(encoding='utf-8')
    assert len(con.execute(sql).fetchall())>0


def test_weekly_batches_match_whole_fixture(fixture_path,tmp_path):
    snapshots=[]
    for i,paths in enumerate((None,[fixture_path])):
        with connect(tmp_path/f'batchspill{i}') as con:
            silver_view(con,[fixture_path])
            snapshots.append({n:m['sha256'] for n,m in build_tables(con,tmp_path/f'batchgold{i}',paths).items()})
    assert snapshots[0]==snapshots[1]


def test_cross_file_trip_guard(fixture_path,tmp_path):
    other=tmp_path/'second.parquet'
    table=pq.read_table(fixture_path)
    idx=table.schema.get_field_index('source_file')
    table=table.set_column(idx,'source_file',pa.array(['second.csv']*len(table)))
    pq.write_table(table,other)
    with connect(tmp_path/'guardspill') as con:
        silver_view(con,[fixture_path,other])
        with pytest.raises(RuntimeError,match='cross-file'):
            build_tables(con,tmp_path/'guardgold',[fixture_path,other])
