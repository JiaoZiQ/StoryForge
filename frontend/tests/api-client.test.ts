import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { parseApiResponse, storyforgeFetch } from "@/lib/api/client";
import { ApiClientError, normalizeApiError } from "@/lib/api/errors";

afterEach(() => vi.unstubAllGlobals());

function response(status = 200, requestId = "req-1") {
  return new Response(null, {
    status,
    headers: { "x-request-id": requestId },
  });
}

describe("API client", () => {
  it("parses a valid typed response", async () => {
    const result = await parseApiResponse<{ ok: boolean }>(
      Promise.resolve({ data: { ok: true }, response: response() }),
      z.object({ ok: z.boolean() }),
    );
    expect(result).toEqual({ ok: true });
  });

  it("rejects an invalid success payload", async () => {
    await expect(
      parseApiResponse(
        Promise.resolve({ data: { status: "wrong" }, response: response() }),
        z.object({ ok: z.boolean() }),
      ),
    ).rejects.toMatchObject({ status: 500, code: "invalid_api_response" });
  });

  it("normalizes structured and unstructured server errors", async () => {
    await expect(
      parseApiResponse(
        Promise.resolve({
          error: {
            error: "version_conflict",
            message: "Try again",
            details: [],
          },
          response: response(409, "req-409"),
        }),
        z.unknown(),
      ),
    ).rejects.toMatchObject({
      status: 409,
      code: "version_conflict",
      requestId: "req-409",
    });
    expect(normalizeApiError(500, "unsafe backend exception").message).toBe(
      "StoryForge could not complete the request.",
    );
  });

  it("adds a request id and maps network failures without leaking details", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new Error("secret socket path"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      storyforgeFetch("http://storyforge.test/health"),
    ).rejects.toMatchObject({
      status: 503,
      code: "network_unavailable",
    });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).get("x-request-id")).toBeTruthy();
  });

  it("preserves generated request headers and body metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal("fetch", fetchMock);
    const request = new Request("http://storyforge.test/projects", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-contract": "generated",
      },
      body: JSON.stringify({ title: "Story" }),
    });
    await storyforgeFetch(request);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-contract")).toBe("generated");
    expect(headers.get("x-request-id")).toBeTruthy();
  });

  it("uses public messages for internal failures", () => {
    const error = new ApiClientError(504, {
      error: "provider_timeout",
      message: "raw provider traceback",
      details: [],
    });
    expect(error.message).toBe(
      "The provider did not respond before the timeout.",
    );
  });
});
