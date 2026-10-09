"""FleetPulse local REST API. Import/startup does not process telemetry or fit ML."""
import logging
import re

from fastapi import FastAPI,Request,Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from src.api.errors import ApiError
from src.api.settings import Settings
from src.api.schemas.analytics import ErrorResponse
from src.api.services.analytics import AnalyticsService
from src.api.services.model import ModelService
from src.api.services.evaluation import EvaluationService
from src.api.routes import health,analytics,ml

LOG=logging.getLogger('fleetpulse.api')


def error(status,code,message,details=None):
    body={'error':{'code':code,'message':message}}
    if details:
        body['error']['details']=details
    return JSONResponse(body,status_code=status)


class BodyLimitMiddleware:
    """Bound JSON request memory including chunked requests, before decoding."""
    def __init__(self,app,max_bytes):
        self.app,self.max_bytes=app,max_bytes

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method']!='POST':
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        try:
            if int(headers.get(b'content-length',b'0'))>self.max_bytes:
                return await error(413,'request_too_large','Request body exceeds 64 KiB.')(scope,receive,send)
        except ValueError:
            return await error(400,'invalid_request','Invalid content length.')(scope,receive,send)
        chunks=[]
        size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            body=message.get('body',b'')
            size+=len(body)
            if size>self.max_bytes:
                return await error(413,'request_too_large','Request body exceeds 64 KiB.')(scope,receive,send)
            chunks.append(body)
            if not message.get('more_body',False):
                break
        sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)


def create_app(settings=None):
    settings=settings or Settings()
    app=FastAPI(title='FleetPulse API',version='1.0.0',debug=False,
        description='Local analytics and next-minute speed inference from prepared past-only features. No raw telemetry processing.',
        responses={422:{'model':ErrorResponse},503:{'model':ErrorResponse},500:{'model':ErrorResponse}})
    app.state.settings=settings
    app.state.analytics=AnalyticsService(settings)
    app.state.model=ModelService(settings)
    app.state.evaluation=EvaluationService(settings)
    app.add_middleware(BodyLimitMiddleware,max_bytes=settings.max_body_bytes)
    app.add_middleware(CORSMiddleware,allow_origins=list(settings.cors_origins),
        allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Content-Type'])

    @app.exception_handler(ApiError)
    async def api_error(request,exc):
        return error(exc.status,exc.code,exc.message)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,exc):
        # Do not echo inputs, exception context, arbitrary field names or paths.
        details=[]
        for item in exc.errors()[:16]:
            location='.'.join(str(part) if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',str(part)) else 'field'
                              for part in item['loc'])
            details.append({'field':location,'code':item['type']})
        return error(422,'invalid_request','Request does not match the documented contract.',details)

    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        return error(exc.status_code,'not_found' if exc.status_code==404 else 'http_error',
                     'Route not found.' if exc.status_code==404 else 'Request could not be completed.')

    @app.exception_handler(Exception)
    async def unexpected(request,exc):
        LOG.error('Unhandled API request failure',exc_info=exc)
        response=error(500,'internal_error','Request could not be completed.')
        # ServerErrorMiddleware emits this outside ordinary CORS middleware.
        origin=request.headers.get('origin')
        if origin in settings.cors_origins:
            response.headers['Access-Control-Allow-Origin']=origin
            response.headers['Vary']='Origin'
        return response

    def strict_query(request:Request):
        allowed={parameter.alias for parameter in request.scope['route'].dependant.query_params}
        if any(name not in allowed or len(request.query_params.getlist(name))!=1
               for name in request.query_params):
            raise ApiError(422,'invalid_request','Unexpected or repeated query parameter.')

    for router in (health.router,analytics.router,ml.router):
        app.include_router(router,prefix='/api/v1',dependencies=[Depends(strict_query)])
    return app


app=create_app()
