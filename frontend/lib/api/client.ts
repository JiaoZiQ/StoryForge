import createClient from "openapi-fetch";
import type { paths } from "./generated";
import { normalizeApiError, ApiClientError } from "./errors";
import type { z } from "zod";

const defaultTimeoutMs = 20_000;

function requestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `web-${Date.now().toString(36)}`;
}

function requestSignal(signal?: AbortSignal | null): AbortSignal {
  const timeout = AbortSignal.timeout(defaultTimeoutMs);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export async function storyforgeFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const inheritedRequest = input instanceof Request ? input : null;
  const headers = new Headers(init?.headers ?? inheritedRequest?.headers);
  headers.set("accept", "application/json");
  if (!headers.has("x-request-id")) headers.set("x-request-id", requestId());
  try {
    return await fetch(input, {
      ...init,
      headers,
      signal: requestSignal(init?.signal ?? inheritedRequest?.signal),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw normalizeApiError(504, {
        error: "request_timeout",
        message: "",
        details: [],
      });
    }
    throw normalizeApiError(503, {
      error: "network_unavailable",
      message: "",
      details: [],
    });
  }
}

export const rawApi = createClient<paths>({
  baseUrl: "/backend",
  fetch: storyforgeFetch,
});

export async function parseApiResponse<T>(
  promise: Promise<{ data?: unknown; error?: unknown; response: Response }>,
  schema: z.ZodType,
): Promise<T> {
  const { data, error, response } = await promise;
  if (!response.ok || error !== undefined) {
    throw normalizeApiError(
      response.status,
      error,
      response.headers.get("x-request-id"),
    );
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ApiClientError(
      500,
      {
        error: "invalid_api_response",
        message: "StoryForge returned an unexpected response shape.",
        details: [],
      },
      response.headers.get("x-request-id"),
    );
  }
  return parsed.data as T;
}
