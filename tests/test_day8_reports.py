"""Dashboard adapters use tiny reports and existing Gold fixtures, never ETL."""
import json
import pytest
from test_day7_api import resources,client  # Reuse the small fixture only.


def write_reports(settings):
    directory=settings.root/'results/day3'
    directory.mkdir(parents=True)
    report={'input_rows':53,'retained_rows':50,'excluded_rows':3,
        'exclusion_reasons':{'negative_elapsed_ms':3},'retained_null_counts':{
            name:5 for name in ('speed_kmh','fuel_rate_lph','maf_g_s','engine_rpm',
                'absolute_load_pct','outside_air_temp_c','battery_soc_pct','hv_battery_current_a')},
        'private_path':str(settings.root)}
    (directory/'silver_quality.json').write_text(json.dumps(report))
    rows=[{'split':split,'dimension':dimension,'category':'ICE' if dimension=='powertrain' else '[0,20)',
        'method':'hist_gradient_boosting','windows':4,'vehicles':2,'mae_kmh':1.,'rmse_kmh':2.,
        'private_path':str(settings.root)} for split in ('validation','test')
        for dimension in ('powertrain','actual_target_speed_range')]
    (settings.evaluation/'cohort_metrics.json').write_text(json.dumps(rows))


def test_pipeline_reconciliation_and_safe_projection(client,resources):
    write_reports(resources)
    response=client.get('/api/v1/quality/pipeline')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['bronze_observations']==data['silver_observations']+data['quarantined_observations']==53
    assert data['gold_source_observations']==50
    assert data['gold_vehicles']==2 and data['gold_trips']==2
    assert str(resources.root) not in response.text and 'private_path' not in response.text


@pytest.mark.parametrize('split,dimension',[('test','powertrain'),('validation','actual_target_speed_range')])
def test_cohort_filtering_projection_and_bounded_page(client,resources,split,dimension):
    write_reports(resources)
    response=client.get(f'/api/v1/ml/cohorts?split={split}&dimension={dimension}')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['total']==1 and data['limit']==100
    assert data['items'][0]['split']==split and data['items'][0]['dimension']==dimension
    assert 'private_path' not in response.text


@pytest.mark.parametrize('path',['/quality/pipeline','/ml/cohorts'])
def test_missing_reports_return_safe_503(client,resources,path):
    response=client.get('/api/v1'+path)
    assert response.status_code==503 and str(resources.root) not in response.text


def test_malformed_or_unreconciled_report_returns_safe_error(client,resources):
    write_reports(resources)
    path=resources.root/'results/day3/silver_quality.json'
    report=json.loads(path.read_text()); report['retained_rows']=49
    path.write_text(json.dumps(report))
    assert client.get('/api/v1/quality/pipeline').status_code==503
    (resources.evaluation/'cohort_metrics.json').write_text('[]')
    assert client.get('/api/v1/ml/cohorts').json()['items']==[]


@pytest.mark.parametrize('query',['split=train','dimension=vehicle','dimension=powertrain&extra=1','split=test&split=validation'])
def test_invalid_or_unexpected_cohort_queries_rejected(client,query):
    assert client.get('/api/v1/ml/cohorts?'+query).status_code==422
