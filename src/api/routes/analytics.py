from datetime import date
from typing import Annotated

from fastapi import APIRouter,Path,Query,Request

from src.api.errors import ApiError
from src.api.services.dashboard_reports import PipelineReport,pipeline
from src.api.schemas.analytics import (AnalyticsMetrics,VehicleAnalytics,TripAnalytics,
    DailyAnalytics,MonthlyAnalytics,PowertrainAnalytics,Page,Powertrain,QualitySummary)

router=APIRouter(tags=['Fleet analytics'])
Limit=Annotated[int,Query(ge=1,le=100)]
Offset=Annotated[int,Query(ge=0,le=100_000)]
Identifier=Annotated[int,Path(ge=0,le=2_147_483_647)]
FilterIdentifier=Annotated[int|None,Query(ge=0,le=2_147_483_647)]


@router.get('/fleet/overview',response_model=AnalyticsMetrics)
def overview(request:Request):
    return request.app.state.analytics.one('fleet_overview')


@router.get('/vehicles',response_model=Page[VehicleAnalytics])
def vehicles(request:Request,limit:Limit=25,offset:Offset=0,powertrain:Powertrain|None=None):
    filters=[('engine_type','=',powertrain)] if powertrain else []
    return request.app.state.analytics.page('vehicle_analytics',filters,limit,offset)


@router.get('/vehicles/{vehicle_id}',response_model=VehicleAnalytics)
def vehicle(request:Request,vehicle_id:Identifier):
    return request.app.state.analytics.one('vehicle_analytics',[('vehicle_id','=',vehicle_id)])


@router.get('/trips',response_model=Page[TripAnalytics])
def trips(request:Request,limit:Limit=25,offset:Offset=0,vehicle_id:FilterIdentifier=None,
          trip_id:FilterIdentifier=None,powertrain:Powertrain|None=None):
    filters=[]
    for name,value in (('vehicle_id',vehicle_id),('trip_id',trip_id),('engine_type',powertrain)):
        if value is not None:
            filters.append((name,'=',value))
    return request.app.state.analytics.page('trip_analytics',filters,limit,offset)


@router.get('/vehicles/{vehicle_id}/trips/{trip_id}',response_model=TripAnalytics)
def trip(request:Request,vehicle_id:Identifier,trip_id:Identifier):
    """Trip ID is scoped by vehicle; do not assume fleet-wide trip-ID uniqueness."""
    return request.app.state.analytics.one('trip_analytics',[
        ('vehicle_id','=',vehicle_id),('trip_id','=',trip_id)])


def trend_page(service,table,column,limit,offset,start_date,end_date):
    if start_date and end_date and start_date>end_date:
        raise ApiError(422,'invalid_request','Start date must not be after end date.')
    filters=[]
    if start_date:
        filters.append((column,'>=',start_date))
    if end_date:
        filters.append((column,'<=',end_date))
    return service.page(table,filters,limit,offset)


@router.get('/trends/daily',response_model=Page[DailyAnalytics])
def daily(request:Request,limit:Limit=25,offset:Offset=0,start_date:date|None=None,end_date:date|None=None):
    """Whole-trip cohorts by dataset-reference trip-start day; timezone unspecified."""
    return trend_page(request.app.state.analytics,'daily_fleet','trip_start_reference_day',
                      limit,offset,start_date,end_date)


@router.get('/trends/monthly',response_model=Page[MonthlyAnalytics])
def monthly(request:Request,limit:Limit=25,offset:Offset=0,start_date:date|None=None,end_date:date|None=None):
    """Filters are inclusive against the stored month-start date."""
    return trend_page(request.app.state.analytics,'monthly_fleet','trip_start_reference_month',
                      limit,offset,start_date,end_date)


@router.get('/fleet/powertrains',response_model=Page[PowertrainAnalytics])
def powertrains(request:Request,limit:Limit=25,offset:Offset=0):
    return request.app.state.analytics.page('powertrain_fleet',limit=limit,offset=offset)


@router.get('/quality/summary',response_model=QualitySummary)
def quality(request:Request):
    service=request.app.state.analytics
    return {'overview':service.one('fleet_overview'),
            'flags':service.page('quality_metrics',limit=100)}


@router.get('/quality/pipeline',response_model=PipelineReport)
def pipeline_report(request:Request):
    """Reconciled historical pipeline counts from the existing small Day 3 report."""
    return pipeline(request.app.state.settings,request.app.state.analytics)
