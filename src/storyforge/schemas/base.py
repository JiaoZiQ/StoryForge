"""Shared Pydantic v2 schema configuration and constrained field types."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

EntityId = Annotated[int, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Score = Annotated[float, Field(ge=0, le=100)]
Confidence = Annotated[float, Field(ge=0, le=1)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]
CategoryText = Annotated[str, Field(min_length=1, max_length=100)]
LongText = Annotated[str, Field(min_length=1)]


class RequestModel(BaseModel):
    """Strict base for create and update request payloads."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ORMResponseModel(BaseModel):
    """Base that validates response data from SQLAlchemy attributes."""

    model_config = ConfigDict(from_attributes=True)
