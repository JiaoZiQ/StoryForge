"""Typed graph extraction and neighbor projections."""

from pydantic import BaseModel, ConfigDict, Field

from storyforge.enums import GraphEntityType, GraphPredicate


class ExtractedGraphEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: GraphEntityType
    canonical_name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(min_length=1, max_length=500)


class ExtractedGraphRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=200)
    predicate: GraphPredicate
    object: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(min_length=1, max_length=500)
    valid_from_chapter: int = Field(gt=0)
    valid_to_chapter: int | None = Field(default=None, gt=0)


class GraphExtractionResult(BaseModel):
    entities: list[ExtractedGraphEntity] = Field(default_factory=list)
    relations: list[ExtractedGraphRelation] = Field(default_factory=list)


class GraphPath(BaseModel):
    entity_ids: list[int]
    entity_names: list[str]
    predicates: list[str]
    explanation: str
