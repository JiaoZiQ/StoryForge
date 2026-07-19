import { z } from "zod";

const dateTime = z.string();
const pageMeta = z.object({
  page: z.number().int(),
  page_size: z.number().int(),
  total_items: z.number().int(),
  total_pages: z.number().int(),
});
const page = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), meta: pageMeta });

export const projectSummarySchema = z.looseObject({
  id: z.number().int(),
  title: z.string(),
  genre: z.string(),
  language: z.string(),
  status: z.string(),
  target_chapters: z.number().int(),
  target_words_per_chapter: z.number().int(),
  created_at: dateTime,
  updated_at: dateTime,
});
export const projectPageSchema = page(projectSummarySchema);
export const projectDetailSchema = projectSummarySchema.extend({
  premise: z.string(),
  tone: z.string().nullable(),
  audience: z.string().nullable(),
  additional_requirements: z.string(),
  logline: z.string().nullable(),
  themes: z.array(z.string()),
  world_summary: z.string().nullable(),
  central_conflict: z.string().nullable(),
  style_guide: z.string().nullable(),
  chapter_count: z.number().int(),
  workflow_count: z.number().int(),
});

const planCharacter = z.looseObject({
  name: z.string(),
  role: z.string(),
  description: z.string(),
  goals: z.array(z.string()),
  personality_traits: z.array(z.string()),
  speech_style: z.string(),
  current_state: z.string(),
});
const planLocation = z.looseObject({
  name: z.string(),
  description: z.string(),
  rules: z.array(z.string()),
});
const planChapter = z.looseObject({
  chapter_number: z.number().int(),
  title: z.string(),
  objective: z.string(),
  summary: z.string(),
  key_events: z.array(z.string()),
  participating_characters: z.array(z.string()),
  locations: z.array(z.string()),
  required_facts: z.array(z.string()),
  forbidden_reveals: z.array(z.string()),
});
export const planSchema = z.looseObject({
  project_id: z.number().int(),
  status: z.string(),
  themes: z.array(z.string()),
  world_summary: z.string(),
  central_conflict: z.string(),
  style_guide: z.string(),
  characters: z.array(planCharacter),
  locations: z.array(planLocation),
  chapter_plans: z.array(planChapter),
  foreshadowing: z.array(
    z.looseObject({
      id: z.number().int(),
      description: z.string(),
      setup_chapter: z.number().int(),
      expected_payoff_chapter: z.number().int(),
      status: z.string(),
      importance: z.string(),
    }),
  ),
});

export const chapterSummarySchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int(),
  chapter_number: z.number().int(),
  title: z.string(),
  objective: z.string(),
  status: z.string(),
  score: z.number().nullable(),
  has_content: z.boolean(),
  current_version_id: z.number().int().nullable(),
  accepted_version_id: z.number().int().nullable(),
  updated_at: dateTime,
});
export const chapterPageSchema = page(chapterSummarySchema);
export const chapterDetailSchema = chapterSummarySchema.extend({
  outline: z.string(),
  outline_metadata: z.record(z.string(), z.unknown()),
  summary: z.string().nullable(),
  current_version: z
    .looseObject({ id: z.number(), version: z.number(), status: z.string() })
    .nullable(),
  accepted_version: z
    .looseObject({ id: z.number(), version: z.number(), status: z.string() })
    .nullable(),
  best_version: z
    .looseObject({ id: z.number(), version: z.number(), status: z.string() })
    .nullable(),
  version_count: z.number().int(),
  conflict_count: z.number().int(),
  workflow_status: z.string().nullable(),
  content: z.string().nullable().optional(),
});
export const contextSchema = z.looseObject({
  project_id: z.number().int(),
  chapter_number: z.number().int(),
  characters: z.array(z.string()),
  locations: z.array(z.string()),
  known_fact_count: z.number().int(),
  active_foreshadowing: z.array(z.string()),
  previous_summary_count: z.number().int(),
  memory_hit_count: z.number().int(),
  metadata: z.record(z.string(), z.unknown()),
  truncated_categories: z.array(z.string()),
});
export const generationSchema = z.looseObject({
  project_id: z.number().int(),
  chapter_id: z.number().int(),
  chapter_number: z.number().int(),
  version: z.number().int(),
  status: z.string(),
  title: z.string(),
  summary: z.string(),
  fact_count: z.number().int(),
  character_update_count: z.number().int(),
  foreshadowing_update_count: z.number().int(),
});

export const versionSummarySchema = z.looseObject({
  id: z.number().int(),
  chapter_id: z.number().int(),
  version: z.number().int(),
  status: z.string(),
  source: z.string(),
  parent_version_id: z.number().int().nullable(),
  score: z.number().nullable(),
  word_count: z.number().int(),
  provider: z.string(),
  model: z.string(),
  created_at: dateTime,
  accepted_at: dateTime.nullable(),
});
export const versionPageSchema = page(versionSummarySchema);
export const versionDetailSchema = versionSummarySchema.extend({
  title: z.string(),
  summary: z.string(),
  prompt_versions: z.record(z.string(), z.string()),
  changes_made: z.array(z.string()),
  content: z.string().nullable().optional(),
});
export const versionDiffSchema = z.looseObject({
  old_version_id: z.number().int(),
  new_version_id: z.number().int(),
  additions: z.number().int(),
  deletions: z.number().int(),
  changed_line_count: z.number().int(),
  word_count_delta: z.number().int(),
  changes_made: z.array(z.string()),
  unified_diff: z.string().nullable().optional(),
  truncated: z.boolean(),
});

export const evaluationSummarySchema = z.looseObject({
  id: z.number().int(),
  evaluation_version: z.number().int(),
  chapter_version_id: z.number().int(),
  status: z.string(),
  mechanical_score: z.number(),
  critic_score: z.number(),
  consistency_score: z.number(),
  final_score: z.number(),
  passed: z.boolean(),
  recommended_action: z.string(),
  created_at: dateTime,
});
export const evaluationPageSchema = page(evaluationSummarySchema);
export const evaluationDetailSchema = evaluationSummarySchema.extend({
  raw_scores: z.record(z.string(), z.number()),
  weighted_scores: z.record(z.string(), z.number()),
  mechanical_metrics: z.record(z.string(), z.unknown()),
  critic_dimensions: z.record(z.string(), z.unknown()),
  blocking_reasons: z.array(z.string()),
  issues: z.array(
    z.looseObject({
      id: z.number().int(),
      source: z.string(),
      code: z.string(),
      category: z.string(),
      severity: z.string(),
      description: z.string(),
      evidence: z.string().nullable(),
      suggestion: z.string().nullable(),
      score_penalty: z.number(),
    }),
  ),
  evaluator_versions: z.record(z.string(), z.string()),
  prompt_versions: z.record(z.string(), z.string()),
  provider: z.string(),
  model: z.string(),
});

export const conflictSchema = z.looseObject({
  id: z.number().int(),
  evaluation_id: z.number().int(),
  project_id: z.number().int(),
  chapter_id: z.number().int(),
  chapter_version_id: z.number().int(),
  conflict_type: z.string(),
  severity: z.string(),
  subject: z.string(),
  description: z.string(),
  new_evidence: z.string(),
  existing_evidence: z.string().nullable(),
  existing_fact_id: z.number().int().nullable(),
  suggested_resolution: z.string(),
  confidence: z.number(),
  rule_code: z.string(),
  status: z.string(),
  resolution_note: z.string().nullable(),
  created_at: dateTime,
  resolved_at: dateTime.nullable(),
});
export const conflictPageSchema = page(conflictSchema);

export const bookRunAcceptedSchema = z.looseObject({
  book_run_id: z.number().int(),
  job_id: z.number().int(),
  reused: z.boolean(),
  status: z.string(),
  status_url: z.string(),
  events_url: z.string(),
});
export const bookRunSchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int(),
  job_id: z.number().int().nullable(),
  status: z.string(),
  mode: z.string(),
  total_chapters: z.number().int(),
  completed_chapters: z.number().int(),
  accepted_chapters: z.number().int(),
  failed_chapters: z.number().int(),
  needs_review_chapters: z.number().int(),
  current_chapter_number: z.number().int().nullable(),
  current_global_revision_round: z.number().int(),
  max_global_revision_rounds: z.number().int(),
  current_node: z.string(),
  progress: z.number().int(),
  book_snapshot_id: z.number().int().nullable(),
  best_snapshot_id: z.number().int().nullable(),
  blocking_reasons: z.array(z.string()),
  chapter_status: z.record(z.string(), z.string()),
  periodic_checks: z.array(z.record(z.string(), z.unknown())),
  spent_cost: z.string(),
  remaining_cost: z.string(),
  used_tokens: z.number().int(),
  remaining_tokens: z.number().int(),
  provider_calls: z.number().int(),
  remaining_provider_calls: z.number().int(),
  started_at: dateTime.nullable(),
  updated_at: dateTime,
  finished_at: dateTime.nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
});
export const bookRunPageSchema = z.object({
  items: z.array(bookRunSchema),
  page: z.number().int(),
  page_size: z.number().int(),
  total_items: z.number().int(),
  total_pages: z.number().int(),
});
export const bookSnapshotSchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int(),
  book_run_id: z.number().int(),
  snapshot_number: z.number().int(),
  status: z.string(),
  chapter_version_map: z.record(z.string(), z.number().int()),
  total_words: z.number().int(),
  chapter_count: z.number().int(),
  accepted_chapter_count: z.number().int(),
  content_hash: z.string(),
  evaluation_summary: z.record(z.string(), z.unknown()),
  created_at: dateTime,
  accepted_at: dateTime.nullable(),
});
export const bookSnapshotPageSchema = z.object({
  items: z.array(bookSnapshotSchema),
  total_items: z.number().int(),
});
export const bookEvaluationSchema = z.looseObject({
  id: z.number().int(),
  book_snapshot_id: z.number().int(),
  evaluation_version: z.number().int(),
  final_score: z.number(),
  passed: z.boolean(),
  dimension_scores: z.record(z.string(), z.number()),
  blocking_reasons: z.array(z.string()),
  recommended_action: z.string(),
  priority_chapters: z.array(z.number().int()),
  global_issues: z.array(z.record(z.string(), z.unknown())),
  evaluator_versions: z.record(z.string(), z.string()),
  prompt_versions: z.record(z.string(), z.string()),
  created_at: dateTime,
});
export const bookAnalysisSchema = z.looseObject({
  snapshot_id: z.number().int(),
  kind: z.string(),
  score: z.number().nullable(),
  summary: z.record(z.string(), z.unknown()),
  items: z.array(z.record(z.string(), z.unknown())),
});
export const timelinePageSchema = z.object({
  items: z.array(z.record(z.string(), z.unknown())),
  page: z.number().int(),
  page_size: z.number().int(),
  total_items: z.number().int(),
  total_pages: z.number().int(),
});
export const bookRevisionPlanSchema = z.looseObject({
  id: z.number().int(),
  book_snapshot_id: z.number().int(),
  revision_round: z.number().int(),
  status: z.string(),
  global_objectives: z.array(z.string()),
  tasks: z.array(z.record(z.string(), z.unknown())),
  dependency_order: z.array(z.number().int()),
  must_preserve: z.array(z.string()),
  global_constraints: z.array(z.string()),
  estimated_calls: z.number().int(),
  estimated_tokens: z.number().int(),
  estimated_cost: z.string(),
});
export const factSchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int(),
  chapter_id: z.number().int(),
  chapter_number: z.number().int(),
  chapter_version_id: z.number().int(),
  subject: z.string(),
  predicate: z.string(),
  object: z.string(),
  fact_type: z.string(),
  valid_from_chapter: z.number().int(),
  valid_to_chapter: z.number().int().nullable(),
  confidence: z.number(),
  source_quote: z.string(),
  status: z.literal("accepted"),
});
export const factPageSchema = page(factSchema);

export const workflowSchema = z.looseObject({
  workflow_run_id: z.number().int(),
  thread_id: z.string(),
  project_id: z.number().int(),
  chapter_id: z.number().int(),
  chapter_number: z.number().int(),
  current_node: z.string(),
  status: z.string(),
  original_version_id: z.number().nullable(),
  current_version_id: z.number().nullable(),
  best_version_id: z.number().nullable(),
  accepted_version_id: z.number().nullable(),
  original_version: z.number().nullable(),
  current_version: z.number().nullable(),
  best_version: z.number().nullable(),
  accepted_version: z.number().nullable(),
  revision_attempt: z.number().int(),
  max_revision_attempts: z.number().int(),
  latest_score: z.number().nullable(),
  blocking_reasons: z.array(z.string()),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  started_at: dateTime,
  updated_at: dateTime,
  finished_at: dateTime.nullable(),
});
export const workflowPageSchema = page(workflowSchema);
export const workflowEventPageSchema = page(
  z.looseObject({
    id: z.number().int(),
    node: z.string(),
    event_type: z.string(),
    attempt: z.number().int(),
    status: z.string(),
    duration_ms: z.number().int(),
    version_id: z.number().nullable(),
    evaluation_id: z.number().nullable(),
    error_code: z.string().nullable(),
    created_at: dateTime,
  }),
);

export const retrievalSchema = z.looseObject({
  query: z.string(),
  hits: z.array(
    z.looseObject({
      id: z.number().int(),
      source_type: z.string(),
      content: z.string(),
      score: z.number(),
      sources: z.array(z.string()),
      chapter_number: z.number().nullable(),
      version_id: z.number().nullable(),
      entity_names: z.array(z.string()),
      relation_path: z.array(z.string()),
      explanation: z.string(),
    }),
  ),
  total_candidates: z.number().int(),
  keyword_candidates: z.number().int(),
  vector_candidates: z.number().int(),
  fact_candidates: z.number().int(),
  graph_candidates: z.number().int(),
  deduplicated_count: z.number().int(),
  omitted_count: z.number().int(),
  estimated_chars: z.number().int(),
  retrieval_version: z.string(),
  filters_applied: z.array(z.string()),
  degraded: z.boolean(),
  degraded_reasons: z.array(z.string()),
});

export const memorySummarySchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int(),
  chapter_id: z.number().nullable(),
  chapter_version_id: z.number().nullable(),
  source_type: z.string(),
  source_id: z.string(),
  chunk_index: z.number().int(),
  content_preview: z.string(),
  content_hash: z.string(),
  token_estimate: z.number().int(),
  character_count: z.number().int(),
  embedding_provider: z.string(),
  embedding_model: z.string(),
  embedding_dimensions: z.number().int(),
  status: z.literal("accepted"),
  valid_from_chapter: z.number().int(),
  valid_to_chapter: z.number().nullable(),
  created_at: dateTime,
});
export const memoryPageSchema = page(memorySummarySchema);
export const memoryStatusPageSchema = page(
  z.looseObject({
    id: z.number().int(),
    project_id: z.number().int(),
    chapter_version_id: z.number().int(),
    status: z.string(),
    attempt_count: z.number().int(),
    chunk_count: z.number().int(),
    graph_entity_count: z.number().int(),
    graph_relation_count: z.number().int(),
    embedding_provider: z.string(),
    embedding_model: z.string(),
    embedding_dimensions: z.number().int(),
    error_code: z.string().nullable(),
  }),
);
export const reindexSchema = z.looseObject({
  project_id: z.number().int(),
  results: z.array(
    z.looseObject({
      chapter_version_id: z.number().int(),
      status: z.string(),
      chunk_count: z.number().int(),
      graph_entity_count: z.number().int(),
      graph_relation_count: z.number().int(),
      degraded: z.boolean(),
    }),
  ),
});

export const graphEntitySchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int(),
  entity_type: z.string(),
  canonical_name: z.string(),
  description: z.string().nullable(),
  aliases: z.array(z.string()),
  confidence: z.number(),
  status: z.literal("accepted"),
  source_chapter_id: z.number().nullable(),
  source_version_id: z.number().nullable(),
});
export const graphEntityPageSchema = page(graphEntitySchema);
export const graphRelationSchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int(),
  subject_entity_id: z.number().int(),
  subject_name: z.string(),
  predicate: z.string(),
  object_entity_id: z.number().int(),
  object_name: z.string(),
  confidence: z.number(),
  valid_from_chapter: z.number().int(),
  valid_to_chapter: z.number().nullable(),
  status: z.literal("accepted"),
  evidence: z.string(),
  source_version_id: z.number().nullable(),
});
export const graphRelationPageSchema = page(graphRelationSchema);
export const graphNeighborsSchema = z.looseObject({
  project_id: z.number().int(),
  entity_id: z.number().int(),
  current_chapter: z.number().int(),
  max_hops: z.union([z.literal(1), z.literal(2)]),
  entities: z.array(graphEntitySchema),
  relations: z.array(graphRelationSchema),
});

export const healthSchema = z.looseObject({
  status: z.literal("ok"),
  service: z.literal("storyforge"),
  version: z.string(),
  environment: z.string(),
});
export const readinessSchema = z.looseObject({
  status: z.literal("ready"),
  database: z.literal("ok"),
  migration_revision: z.string(),
  provider: z.string(),
});

export const providerCapabilitySchema = z.looseObject({
  provider: z.string(),
  model: z.string(),
  model_type: z.enum(["chat", "embedding"]),
  context_window: z.number().int(),
  max_output_tokens: z.number().int(),
  supports_structured_output: z.boolean(),
  supports_json_schema: z.boolean(),
  supports_embeddings: z.boolean(),
  embedding_dimensions: z.number().int().nullable(),
  enabled: z.boolean(),
  pricing_available: z.boolean(),
});
export const providerHealthSchema = z.looseObject({
  provider: z.string(),
  model: z.string(),
  enabled: z.boolean(),
  health_status: z.string(),
  circuit_status: z.enum(["closed", "open", "half_open"]),
  pricing_available: z.boolean(),
  capabilities: z.array(z.string()),
});
export const usageSummarySchema = z.looseObject({
  calls: z.number().int(),
  succeeded: z.number().int(),
  failures: z.number().int(),
  input_tokens: z.number().int(),
  output_tokens: z.number().int(),
  cached_input_tokens: z.number().int(),
  total_tokens: z.number().int(),
  estimated_cost: z.string().nullable(),
  billed_cost: z.string().nullable(),
  fallback_count: z.number().int(),
  timeout_count: z.number().int(),
  rate_limit_count: z.number().int(),
  average_latency_ms: z.string(),
  currency: z.string(),
});
export const providerCallSchema = z.looseObject({
  id: z.number().int(),
  task_type: z.string(),
  provider: z.string(),
  model: z.string(),
  status: z.string(),
  attempt: z.number().int(),
  fallback_index: z.number().int(),
  input_tokens: z.number().int(),
  output_tokens: z.number().int(),
  total_tokens: z.number().int(),
  usage_source: z.string(),
  estimated_cost: z.string().nullable(),
  billed_cost: z.string().nullable(),
  currency: z.string(),
  latency_ms: z.number().int(),
  created_at: dateTime,
});
export const providerCallPageSchema = page(providerCallSchema);
export const projectBudgetSchema = z.looseObject({
  project_id: z.number().int(),
  currency: z.string(),
  soft_limit: z.string(),
  hard_limit: z.string(),
  period: z.string(),
  spent_estimated: z.string(),
  spent_billed: z.string(),
  reserved_estimated: z.string(),
  enabled: z.boolean(),
  remaining_estimated: z.string(),
});
export const modelSettingsSchema = z.looseObject({
  project_id: z.number().int(),
  model_profile: z.enum(["offline", "economy", "balanced", "quality"]),
  privacy_policy: z.enum(["offline", "strict", "standard"]),
});
export const modelProfileOptionSchema = z.looseObject({
  name: z.enum(["offline", "economy", "balanced", "quality"]),
  description: z.string(),
  external_allowed: z.boolean(),
});

export const jobSchema = z.looseObject({
  id: z.number().int(),
  project_id: z.number().int().nullable(),
  chapter_id: z.number().int().nullable(),
  chapter_number: z.number().int().nullable(),
  workflow_run_id: z.number().int().nullable(),
  job_type: z.string(),
  queue_name: z.string(),
  status: z.string(),
  priority: z.number().int(),
  progress: z.number().int(),
  current_step: z.string().nullable(),
  attempt: z.number().int(),
  max_attempts: z.number().int(),
  result: z.record(z.string(), z.unknown()),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  worker_id: z.string().nullable(),
  correlation_id: z.string(),
  available_at: dateTime,
  queued_at: dateTime.nullable(),
  started_at: dateTime.nullable(),
  finished_at: dateTime.nullable(),
  created_at: dateTime,
  updated_at: dateTime,
});
export const jobAcceptedSchema = z.object({
  job_id: z.number().int(),
  status: z.string(),
  reused: z.boolean(),
  status_url: z.string(),
  events_url: z.string(),
});
export const jobPageSchema = z.object({
  items: z.array(jobSchema),
  page: z.number().int(),
  page_size: z.number().int(),
  total_items: z.number().int(),
});
export const jobEventSchema = z.looseObject({
  id: z.number().int(),
  job_id: z.number().int(),
  sequence: z.number().int(),
  event_type: z.string(),
  status: z.string(),
  step: z.string().nullable(),
  progress: z.number().int(),
  message_code: z.string(),
  message: z.string(),
  attempt: z.number().int(),
  worker_id: z.string().nullable(),
  workflow_event_id: z.number().int().nullable(),
  created_at: dateTime,
});
export const jobEventPageSchema = z.object({
  items: z.array(jobEventSchema),
  page: z.number().int(),
  page_size: z.number().int(),
  total_items: z.number().int(),
});
export const workerSchema = z.looseObject({
  worker_id: z.string(),
  queue_name: z.string(),
  status: z.string(),
  current_job_id: z.number().int().nullable(),
  started_at: dateTime,
  last_heartbeat_at: dateTime,
  version: z.string(),
});
export const queueHealthSchema = z.looseObject({
  mode: z.string(),
  broker_reachable: z.boolean(),
  pending_jobs: z.number().int(),
  soft_limit_exceeded: z.boolean(),
  pending_soft_limit: z.number().int(),
  pending_hard_limit: z.number().int(),
  project_pending_limit: z.number().int(),
  workers: z.array(workerSchema),
});
