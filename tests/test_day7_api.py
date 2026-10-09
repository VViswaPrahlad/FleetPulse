"""Small artifact fixtures and ASGI TestClient integration; no ETL/model fit."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json

from fastapi.testclient import TestClient
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.api.main import create_app
from src.api.settings import Settings
from src.api.schemas.analytics import COUNT_FIELDS,MEASURE_FIELDS
from src.api.services.evaluation import METHODS,ERROR_FIELDS,CI_FIELDS
from src.features.speed_windows import FEATURES,past_features


class FakeModel:
    """Test-only deterministic service spy, not a real forecasting result."""
    def __init__(self):
        self.calls=0
        self.inputs=None

    def ready(self):
        return True

    def identity(self):
        return 'hgb-day6-'+'f'*12

    def predict(self,features):
        self.calls+=1
        self.inputs=features
        return features['past_speed_last_kmh'],'test-model'


def prepared():
    return {'input_kind':'prepared_past_features','feature_schema_version':'ved-speed-1',
        'history_seconds':60,'speed_unit':'km/h','acceleration_unit':'m/s^2','time_unit':'s',
        'features':past_features(np.arange(61)*1000,np.full(61,60.))}


def stats(observations):
    values={name:0 for name in COUNT_FIELDS}
    values.update({name:0. for name in MEASURE_FIELDS})
    values.update(observation_count=observations,vehicle_count=1,trip_count=1,source_file_count=1,
        speed_observation_count=observations,missing_fuel_rate_count=observations,
        flagged_observation_count=observations,quality_flag_occurrence_count=observations,
        speed_sample_mean_kmh=60.,speed_min_kmh=60.,speed_max_kmh=60.,
        speed_sample_p50_kmh=60.,speed_sample_p95_kmh=60.,speed_time_weighted_mean_kmh=60.,
        first_trip_start_reference_day=date(2017,11,1),last_trip_start_reference_day=date(2017,11,2))
    return values


@pytest.fixture
def resources(tmp_path):
    root=tmp_path/'project'
    gold=root/'data/gold/ved'
    evaluation=root/'results/day6'
    gold.mkdir(parents=True)
    evaluation.mkdir(parents=True)
    fleet=stats(50)
    fleet.update(vehicle_count=2,trip_count=2)
    a={**stats(30),'vehicle_id':1,'engine_type':'ICE'}
    b={**stats(20),'vehicle_id':2,'engine_type':'EV'}
    b.update(speed_sample_mean_kmh=None,speed_time_weighted_mean_kmh=None,observed_distance_km=None,
             speed_observation_count=0,missing_speed_count=20)
    tables={'fleet_overview':[fleet],'vehicle_analytics':[a,b],
        'trip_analytics':[{**row,'trip_id':7,'elapsed_span_s':120.,'distinct_day_number_count':1} for row in (a,b)],
        'daily_fleet':[{**stats(30),'trip_start_reference_day':date(2017,11,1)},
                       {**stats(20),'trip_start_reference_day':date(2017,11,2)}],
        'monthly_fleet':[{**fleet,'trip_start_reference_month':date(2017,11,1)}],
        'powertrain_fleet':[{**stats(30),'engine_type':'ICE'},{**stats(20),'engine_type':'EV'}],
        'quality_metrics':[{'quality_flag':'missing_fuel_rate_lph','observation_count':50,'observation_fraction':1.}]}
    for name,rows in tables.items():
        pq.write_table(pa.Table.from_pylist(rows),gold/f'{name}.parquet')
    errors=[{'method':method,'split':split,'vehicle_id':vehicle,'windows':2,'mae_kmh':1.,'rmse_kmh':2.}
            for method in METHODS for split in ('validation','test') for vehicle in (1,2)]
    pq.write_table(pa.Table.from_pylist(errors),evaluation/'vehicle_errors.parquet')
    report={'model_sha256':'f'*64,'selection':{'selected_candidate':0,'random_state':20261009,
        'selected_parameters':{'learning_rate':.05,'max_iter':200,'max_leaf_nodes':15,
                               'min_samples_leaf':20,'l2_regularization':1}},
        'metrics':{split:{method:{field:1. for field in ERROR_FIELDS} for method in METHODS}
                   for split in ('validation','test')},
        'strongest_baseline':'last_observed_speed',
        'improvement_vs_strongest_baseline':{s:{'mae_improvement_pct':20.,'rmse_improvement_pct':20.} for s in ('validation','test')},
        'vehicle_cluster_bootstrap':{s:{'seed':7,'replicates':2000,'vehicles':2,'confidence':.95,
            'intervals':{field:[1.,2.] for field in CI_FIELDS}} for s in ('validation','test')},
        'input_sha256':{str(root):'private-path-must-not-be-exposed'},'private_path':str(root)}
    (evaluation/'training_run.json').write_text(json.dumps(report))
    return Settings(root=root,cache_entries=3)


@pytest.fixture
def client(resources):
    app=create_app(resources)
    app.state.model=FakeModel()
    with TestClient(app,raise_server_exceptions=False) as value:
        yield value


def test_live_ready_openapi_and_exact_prepared_feature_schema(client):
    assert client.get('/api/v1/health').status_code==200
    ready=client.get('/api/v1/ready')
    assert ready.status_code==200 and ready.json()['ready']
    spec=client.get('/openapi.json').json()
    assert len(spec['components']['schemas']['PreparedFeatures']['required'])==31
    assert spec['components']['schemas']['PreparedFeatures']['additionalProperties'] is False
    contract=client.get('/api/v1/ml/features').json()
    assert contract['feature_order']==list(FEATURES)
    assert sum(d['nullable'] for d in contract['features'])==6


@pytest.mark.parametrize('endpoint',[
    '/fleet/overview','/vehicles','/vehicles/1','/trips','/vehicles/1/trips/7',
    '/trends/daily','/trends/monthly','/fleet/powertrains','/quality/summary',
    '/ml/metrics','/ml/vehicle-errors'])
def test_read_endpoints_and_no_private_path_leakage(client,resources,endpoint):
    response=client.get('/api/v1'+endpoint)
    assert response.status_code==200,response.text
    assert str(resources.root) not in response.text
    assert 'private_path' not in response.text and 'input_sha256' not in response.text


def test_pagination_filters_trip_scoping_and_null_semantics(client):
    first=client.get('/api/v1/vehicles?limit=1').json()
    second=client.get('/api/v1/vehicles?limit=1&offset=1').json()
    assert first['total']==2 and len(first['items'])==1
    assert first['items'][0]['vehicle_id']==1 and second['items'][0]['vehicle_id']==2
    assert second['items'][0]['observed_distance_km'] is None
    trips=client.get('/api/v1/trips?vehicle_id=2&trip_id=7').json()
    assert trips['total']==1 and trips['items'][0]['vehicle_id']==2
    assert client.get('/api/v1/vehicles?powertrain=ICE').json()['total']==1
    assert client.get('/api/v1/vehicles/99').status_code==404
    assert client.get('/api/v1/vehicles/1/trips/99').status_code==404


@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','offset=100001',
    'powertrain=ICE%27%20OR%201%3D1','limit=one'])
def test_bounded_query_validation(client,query):
    response=client.get('/api/v1/vehicles?'+query)
    assert response.status_code==422 and response.json()['error']['code']=='invalid_request'


def test_inclusive_date_filters_and_inverted_or_invalid_dates(client):
    assert client.get('/api/v1/trends/daily?start_date=2017-11-02&end_date=2017-11-02').json()['total']==1
    assert client.get('/api/v1/trends/monthly?start_date=2017-11-01&end_date=2017-11-01').json()['total']==1
    assert client.get('/api/v1/trends/daily?start_date=2018-01-01&end_date=2017-01-01').status_code==422
    assert client.get('/api/v1/trends/daily?start_date=bad-date').status_code==422


def test_complete_prediction_nullable_means_and_no_units_conversion(client):
    response=client.post('/api/v1/ml/predict',json=prepared())
    assert response.status_code==200,response.text
    assert response.json()['predicted_mean_speed_kmh']==60
    assert response.json()['forecast_seconds']==60
    assert client.app.state.model.inputs['past_engine_rpm_sample_mean'] is None


@pytest.mark.parametrize('kind',['missing_feature','extra_feature','extra_top','wrong_units',
    'string_number','boolean_number','null_required','fraction','noninteger_count',
    'gap','soc','availability','extrema','raw_telemetry'])
def test_invalid_prediction_never_reaches_model(client,kind):
    body=prepared()
    if kind=='missing_feature':
        del body['features'][FEATURES[0]]
    elif kind=='extra_feature':
        body['features']['vehicle_id']=1
    elif kind=='extra_top':
        body['target_mean_speed_kmh']=999
    elif kind=='wrong_units':
        body['speed_unit']='mph'
    elif kind=='string_number':
        body['features'][FEATURES[0]]='60'
    elif kind=='boolean_number':
        body['features'][FEATURES[0]]=True
    elif kind=='null_required':
        body['features'][FEATURES[0]]=None
    elif kind=='fraction':
        body['features']['past_stop_sample_fraction']=1.5
    elif kind=='noninteger_count':
        body['features']['past_sample_count']=61.5
    elif kind=='gap':
        body['features']['past_gap_max_s']=3
    elif kind=='soc':
        body['features']['past_battery_soc_pct_sample_mean']=101
        body['features']['past_battery_soc_pct_observed_fraction']=1
    elif kind=='availability':
        body['features']['past_engine_rpm_sample_mean']=700
    elif kind=='extrema':
        body['features']['past_speed_min_kmh']=100
    else:
        body={'speed_kmh':60,'timestamp':1000}
    response=client.post('/api/v1/ml/predict',json=body)
    assert response.status_code==422,response.text
    assert client.app.state.model.calls==0


def test_nonfinite_json_input_is_rejected_without_echoing_it(client):
    encoded=json.dumps(prepared()).replace('60.0','NaN',1)
    response=client.post('/api/v1/ml/predict',content=encoded,headers={'Content-Type':'application/json'})
    assert response.status_code==422 and 'NaN' not in response.text


def test_signed_sensors_and_advisory_load_above_100_remain_valid(client):
    body=prepared()
    for sensor,value in [('hv_battery_current_a',-5),('outside_air_temp_c',-20),('absolute_load_pct',150)]:
        body['features'][f'past_{sensor}_sample_mean']=value
        body['features'][f'past_{sensor}_observed_fraction']=1
    assert client.post('/api/v1/ml/predict',json=body).status_code==200


def test_body_size_bound_covers_declared_and_chunked_payloads(client):
    assert client.post('/api/v1/ml/predict',content=b' '*70000).status_code==413
    assert client.post('/api/v1/ml/predict',content=iter([b' '*40000,b' '*40000])).status_code==413


def test_analytics_cache_is_bounded_and_invalidates_after_file_change(client,resources):
    service=client.app.state.analytics
    client.get('/api/v1/fleet/overview')
    count=service.query_count
    client.get('/api/v1/fleet/overview')
    assert service.query_count==count
    path=resources.gold/'fleet_overview.parquet'
    changed=stats(99)
    pq.write_table(pa.Table.from_pylist([changed]),path)
    assert client.get('/api/v1/fleet/overview').json()['observation_count']==99
    for offset in range(8):
        client.get(f'/api/v1/vehicles?offset={offset}')
    assert len(service._cache)<=3


def test_missing_or_corrupt_artifacts_are_unavailable_and_live_still_works(client,resources):
    (resources.gold/'fleet_overview.parquet').unlink()
    assert client.get('/api/v1/fleet/overview').status_code==503
    assert client.get('/api/v1/ready').status_code==503
    assert client.get('/api/v1/health').status_code==200
    (resources.evaluation/'training_run.json').write_text('not json')
    response=client.get('/api/v1/ml/metrics')
    assert response.status_code==503 and str(resources.root) not in response.text


def test_missing_real_model_has_safe_503(resources):
    with TestClient(create_app(resources),raise_server_exceptions=False) as client:
        response=client.post('/api/v1/ml/predict',json=prepared())
        assert response.status_code==503 and response.json()['error']['code']=='model_unavailable'
        assert str(resources.root) not in response.text


def test_internal_exception_and_request_errors_do_not_echo_paths(client,resources):
    def fail(*args,**kwargs):
        raise RuntimeError(str(resources.root)+' SECRET internal traceback')
    client.app.state.analytics.one=fail
    response=client.get('/api/v1/fleet/overview')
    assert response.status_code==500 and 'SECRET' not in response.text
    assert str(resources.root) not in response.text
    body=prepared()
    body['features'][FEATURES[0]]=str(resources.root)
    response=client.post('/api/v1/ml/predict',json=body)
    assert response.status_code==422 and str(resources.root) not in response.text


def test_local_cors_allowed_origin_and_other_origin_rejected(client):
    headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'}
    allowed=client.options('/api/v1/ml/predict',headers=headers)
    assert allowed.status_code==200 and allowed.headers['access-control-allow-origin']=='http://localhost:5173'
    headers['Origin']='https://example.org'
    rejected=client.options('/api/v1/ml/predict',headers=headers)
    assert rejected.status_code==400 and 'access-control-allow-origin' not in rejected.headers


def test_concurrent_queries_have_independent_duckdb_connections(client):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda v:client.get(f'/api/v1/trips?vehicle_id={v}'),[1,2]*4))
    assert all(response.status_code==200 for response in results)
    assert [response.json()['items'][0]['vehicle_id'] for response in results]==[1,2]*4


def test_model_evaluation_identity_mismatch_is_not_ready(client):
    client.app.state.model.identity=lambda:'wrong-model'
    response=client.get('/api/v1/ready')
    assert response.status_code==503 and not response.json()['components']['model_evaluation_match']


def test_corrupt_vehicle_error_schema_is_not_ready(client,resources):
    (resources.evaluation/'vehicle_errors.parquet').write_bytes(b'broken parquet')
    assert client.get('/api/v1/ready').status_code==503
    assert client.get('/api/v1/ml/vehicle-errors').status_code==503


def test_impossible_sampling_statistics_are_rejected(client):
    body=prepared()
    body['features']['past_sample_count']=31
    body['features']['past_gap_max_s']=1
    assert client.post('/api/v1/ml/predict',json=body).status_code==422


def test_stationary_fraction_rounding_is_accepted_without_clipping(client):
    body=prepared()
    body['features']=past_features(np.arange(61)*1000,np.zeros(61))
    body['features']['past_stop_interval_fraction']=1.0000000000000002
    assert client.post('/api/v1/ml/predict',json=body).status_code==200
    assert client.app.state.model.inputs['past_stop_interval_fraction']==1.0000000000000002


@pytest.mark.parametrize('query',['unknown=1','limit=1&limit=2','powertrain=ICE&powertrain=EV'])
def test_unexpected_or_duplicate_query_fields_are_rejected(client,query):
    assert client.get('/api/v1/vehicles?'+query).status_code==422


def test_internal_errors_have_cors_for_the_approved_local_client(client):
    def fail(*args,**kwargs):
        raise RuntimeError('internal only')
    client.app.state.analytics.one=fail
    response=client.get('/api/v1/fleet/overview',headers={'Origin':'http://localhost:5173'})
    assert response.status_code==500
    assert response.headers['access-control-allow-origin']=='http://localhost:5173'
