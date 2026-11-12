from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from pos_api.deps import SessionDep
from pos_api.schemas import DailySummary, SalesReport, StaffPerformanceRow, TopItemRow, VoidRow
from pos_api.services import reports as service
from pos_api.services.reports import SalesGroupBy, TopItemsSort
from pos_api.timeutil import resolve_dates, today

router = APIRouter(prefix="/reports", tags=["reports"])

DateFrom = Annotated[date | None, Query(description="Local date (YYYY-MM-DD). Default: today")]
DateTo = Annotated[date | None, Query(description="Inclusive. Default: same as date_from")]


@router.get("/sales", response_model=SalesReport)
def sales(
    session: SessionDep,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    group_by: SalesGroupBy = SalesGroupBy.day,
):
    return service.sales(session, *resolve_dates(date_from, date_to), group_by)


@router.get("/top-items", response_model=list[TopItemRow])
def top_items(
    session: SessionDep,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    sort: TopItemsSort = TopItemsSort.quantity,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    category: str | None = None,
):
    return service.top_items(session, *resolve_dates(date_from, date_to), sort, limit, category)


@router.get("/staff", response_model=list[StaffPerformanceRow])
def staff(session: SessionDep, date_from: DateFrom = None, date_to: DateTo = None):
    return service.staff_performance(session, *resolve_dates(date_from, date_to))


@router.get("/voids", response_model=list[VoidRow])
def voids(session: SessionDep, date_from: DateFrom = None, date_to: DateTo = None):
    return service.voids(session, *resolve_dates(date_from, date_to))


@router.get("/daily-summary", response_model=DailySummary)
def daily_summary(session: SessionDep, day: date | None = None):
    return service.daily_summary(session, day or today())
