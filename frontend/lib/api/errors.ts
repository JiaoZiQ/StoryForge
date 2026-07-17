import { z } from "zod";

const errorDetailSchema = z.looseObject({
  code: z.string(),
  message: z.string(),
  field: z.string().nullable().optional(),
  context: z.record(z.string(), z.unknown()).optional(),
});

export const apiErrorSchema = z.looseObject({
  error: z.string(),
  message: z.string(),
  details: z.array(errorDetailSchema).default([]),
  request_id: z.string().nullable().optional(),
});

export type ApiErrorPayload = z.infer<typeof apiErrorSchema>;

const publicMessages: Record<number, string> = {
  401: "Authentication is required.",
  403: "This operation is not permitted.",
  404: "The requested StoryForge resource was not found.",
  409: "The resource changed state and the operation cannot continue.",
  422: "Some submitted fields are invalid.",
  503: "StoryForge is temporarily unavailable.",
  504: "The provider did not respond before the timeout.",
  500: "StoryForge could not complete the request.",
};

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorPayload["details"];
  readonly requestId?: string;

  constructor(
    status: number,
    payload: ApiErrorPayload,
    responseRequestId?: string | null,
  ) {
    const fallback = publicMessages[status] ?? "The API request failed.";
    super(status >= 500 ? fallback : payload.message || fallback);
    this.name = "ApiClientError";
    this.status = status;
    this.code = payload.error;
    this.details = payload.details;
    this.requestId = payload.request_id ?? responseRequestId ?? undefined;
  }
}

export function normalizeApiError(
  status: number,
  payload: unknown,
  responseRequestId?: string | null,
): ApiClientError {
  const parsed = apiErrorSchema.safeParse(payload);
  return new ApiClientError(
    status,
    parsed.success
      ? parsed.data
      : {
          error: status === 504 ? "provider_timeout" : "request_failed",
          message: publicMessages[status] ?? "The API request failed.",
          details: [],
        },
    responseRequestId,
  );
}
