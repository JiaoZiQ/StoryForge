"""Bounded Milestone 10 offline demonstration projections."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DemoM10ScenarioA(BaseModel):
    status: str
    provider_calls: int
    tokens: int
    estimated_cost: Decimal


class DemoM10ScenarioB(BaseModel):
    attempts: int
    retry_reason: str
    status: str


class DemoM10ScenarioC(BaseModel):
    primary: str
    fallback: str
    fallback_count: int


class DemoM10ScenarioD(BaseModel):
    circuit: str
    fallback_used: bool


class DemoM10ScenarioE(BaseModel):
    budget_status: str
    provider_calls_made: int


class DemoM10ScenarioF(BaseModel):
    calls_before_resume: int
    calls_after_resume: int
    duplicate_calls: int
    duplicate_cost_records: int


class DemoM10Response(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_backend: Literal["PostgreSQL"]
    project_id: int
    profile: str
    privacy_policy: str
    scenario_a: DemoM10ScenarioA
    scenario_b: DemoM10ScenarioB
    scenario_c: DemoM10ScenarioC
    scenario_d: DemoM10ScenarioD
    scenario_e: DemoM10ScenarioE
    scenario_f: DemoM10ScenarioF
