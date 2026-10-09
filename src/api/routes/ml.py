from fastapi import APIRouter,Request

from src.api.routes.analytics import Limit,Offset,FilterIdentifier
from src.api.schemas.analytics import ModelMetrics,VehicleError,Page,Split,Method
from src.api.schemas.prediction import PredictionRequest,PredictionResponse,FeatureContract,FEATURE_DEFINITIONS

router=APIRouter(tags=['Model'])


@router.get('/ml/metrics',response_model=ModelMetrics)
def metrics(request:Request):
    return request.app.state.evaluation.metrics()


@router.get('/ml/vehicle-errors',response_model=Page[VehicleError])
def errors(request:Request,limit:Limit=25,offset:Offset=0,split:Split='test',
           method:Method='hist_gradient_boosting',vehicle_id:FilterIdentifier=None):
    filters=[('split','=',split),('method','=',method)]
    if vehicle_id is not None:
        filters.append(('vehicle_id','=',vehicle_id))
    return request.app.state.analytics.page('vehicle_errors',filters,limit,offset)


@router.get('/ml/features',response_model=FeatureContract,response_model_exclude_none=True)
def features():
    """Exact feature names/units; all 31 must be present, six means allow null."""
    return {'schema_version':'ved-speed-1','history_seconds':60,'forecast_seconds':60,
        'max_sampling_gap_seconds':2,'input_kind':'prepared_past_features',
        'feature_order':[d['name'] for d in FEATURE_DEFINITIONS],'features':FEATURE_DEFINITIONS,
        'null_policy':'Only optional sensor means may be null; observed_fraction must then be zero.',
        'scope':'No raw telemetry ingestion; caller supplies fully prepared past-only features.'}


@router.post('/ml/predict',response_model=PredictionResponse)
def predict(request:Request,payload:PredictionRequest):
    """One complete prepared vector, never partial raw readings or future values."""
    predicted,identity=request.app.state.model.predict(payload.features.model_dump())
    return PredictionResponse(predicted_mean_speed_kmh=predicted,model_id=identity)
