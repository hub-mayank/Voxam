"""Column types that behave the same on SQLite (dev, tests) and PostgreSQL (target)."""
from datetime import timezone

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

# JSON on SQLite, JSONB on PostgreSQL; Python None is stored as SQL NULL
JsonType = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class UtcDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes. Naive values are refused on the way in; SQLite drops the zone, so it is restored on the way out."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: use a timezone-aware UTC datetime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
