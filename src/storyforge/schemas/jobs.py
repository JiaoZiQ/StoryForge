"""Public, content-free contracts for asynchronous jobs and progress events."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from storyforge.enums import JobEventType, JobStatus, JobType, WorkerStatus


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_type: JobType
    project_id: int | None = Field(default=None, ge=1)
    chapter_number: int | None = Field(default=None, ge=1)
    workflow_run_id: int | None = Field(default=None, ge=1)
    operation: str = Field(default="run", min_length=1, max_length=100)
    payload: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int = Field(default=5, ge=0, le=8)


class JobAcceptedResponse(BaseModel):
    job_id: int
    status: JobStatus
    reused: bool
    status_url: str
    events_url: str


class JobResponse(BaseModel):
    id: int
    project_id: int | None
    chapter_id: int | None
    chapter_number: int | None
    workflow_run_id: int | None
    job_type: JobType
    queue_name: str
    status: JobStatus
    priority: int
    progress: int
    current_step: str | None
    attempt: int
    max_attempts: int
    result: dict[str, object]
    error_code: str | None
    error_message: str | None
    worker_id: str | None
    correlation_id: str
    available_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobEventResponse(BaseModel):
    id: int
    job_id: int
    sequence: int
    event_type: JobEventType
    status: JobStatus
    step: str | None
    progress: int
    message_code: str
    message: str
    attempt: int
    worker_id: str | None
    workflow_event_id: int | None
    created_at: datetime


class JobPageResponse(BaseModel):
    items: list[JobResponse]
    page: int
    page_size: int
    total_items: int


class JobEventPageResponse(BaseModel):
    items: list[JobEventResponse]
    page: int
    page_size: int
    total_items: int


class WorkerResponse(BaseModel):
    worker_id: str
    queue_name: str
    status: WorkerStatus
    current_job_id: int | None
    started_at: datetime
    last_heartbeat_at: datetime
    version: str


class QueueHealthResponse(BaseModel):
    mode: str
    broker_reachable: bool
    pending_jobs: int
    soft_limit_exceeded: bool
    pending_soft_limit: int
    pending_hard_limit: int
    project_pending_limit: int
    workers: list[WorkerResponse]
