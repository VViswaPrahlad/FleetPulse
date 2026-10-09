from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse

from src.api.schemas.analytics import Health,Readiness

router=APIRouter(tags=['Health'])


@router.get('/health',response_model=Health)
def health():
    """Process liveness; no artifact loading or telemetry scan."""
    return Health()


@router.get('/ready',response_model=Readiness,responses={503:{'model':Readiness}})
def ready(request:Request):
    """Full-demo readiness; missing components do not prevent process liveness."""
    components={'analytics':request.app.state.analytics.ready(),
        'model':request.app.state.model.ready(),'evaluation':request.app.state.evaluation.ready()}
    try:
        components['model_evaluation_match']=bool(components['model'] and components['evaluation']
            and request.app.state.model.identity()==request.app.state.evaluation.metrics().model_id)
    except Exception:
        components['model_evaluation_match']=False
    body=Readiness(ready=all(components.values()),components=components)
    return JSONResponse(body.model_dump(),status_code=200 if body.ready else 503)
