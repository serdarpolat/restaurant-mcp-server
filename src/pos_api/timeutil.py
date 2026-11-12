"""Time helpers. The DB stores UTC; the API speaks the restaurant's local time."""

from datetime import UTC, date, datetime, time, timedelta

from pos_api.db.database import RESTAURANT_TZ


def now() -> datetime:
    return datetime.now(RESTAURANT_TZ).replace(microsecond=0)


def today() -> date:
    return now().date()


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(RESTAURANT_TZ)


def day_range(start: date, end: date) -> tuple[datetime, datetime]:
    """[start 00:00, end+1 00:00) in local time."""
    return (
        datetime.combine(start, time.min, tzinfo=RESTAURANT_TZ),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=RESTAURANT_TZ),
    )


def resolve_dates(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Default to today; a single bound means a single day."""
    if date_from is None and date_to is None:
        return today(), today()
    date_from = date_from or date_to
    date_to = date_to or date_from
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to
