from datetime import timezone
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, PlainSerializer, WithJsonSchema


def _iso_z(value) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# every timestamp on the wire: ISO-8601 UTC with a trailing Z. Naive datetimes are rejected.
UtcDatetime = Annotated[
    AwareDatetime,
    PlainSerializer(_iso_z, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time", "examples": ["2026-10-12T05:30:12Z"],
                    "description": "ISO-8601 UTC, always ending in Z."}),
]


class ApiResponse(BaseModel):
    """Base for response models."""


class ApiRequest(BaseModel):
    """Base for request models: unknown fields are rejected so typos fail loudly."""
    model_config = ConfigDict(extra="forbid")


def example_of(model):
    """The first example of a model, as a validated instance (what a stub handler returns)."""
    return model.model_validate(model.model_json_schema()["examples"][0])


class Health(ApiResponse):
    """Liveness check. Not a stub."""
    status: str = "ok"
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})
