import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const maximumBodyBytes = 1_048_576;
const forwardedHeaders = [
  "accept",
  "authorization",
  "content-type",
  "last-event-id",
  "x-request-id",
];

function backendBaseUrl(): URL {
  const configured = process.env.STORYFORGE_INTERNAL_API_URL;
  const value =
    configured ??
    (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");
  if (!value) throw new Error("STORYFORGE_INTERNAL_API_URL is required");
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password
  ) {
    throw new Error(
      "STORYFORGE_INTERNAL_API_URL must be a credential-free HTTP(S) URL",
    );
  }
  return url;
}

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID();
  try {
    const base = backendBaseUrl();
    const safePath = path.map((part) => encodeURIComponent(part)).join("/");
    const target = new URL(safePath, `${base.toString().replace(/\/$/, "")}/`);
    target.search = request.nextUrl.search;

    const headers = new Headers();
    for (const name of forwardedHeaders) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set("x-request-id", requestId);

    let body: ArrayBuffer | undefined;
    if (!["GET", "HEAD"].includes(request.method)) {
      const declared = Number(request.headers.get("content-length") ?? "0");
      if (declared > maximumBodyBytes)
        return proxyError(413, "request_too_large", requestId);
      body = await request.arrayBuffer();
      if (body.byteLength > maximumBodyBytes)
        return proxyError(413, "request_too_large", requestId);
    }

    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      signal: request.signal,
    });
    const responseHeaders = new Headers();
    const contentType = response.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    for (const name of ["cache-control", "x-accel-buffering"]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    responseHeaders.set(
      "x-request-id",
      response.headers.get("x-request-id") ?? requestId,
    );
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch {
    return proxyError(503, "backend_unavailable", requestId);
  }
}

function proxyError(
  status: number,
  error: string,
  requestId: string,
): NextResponse {
  return NextResponse.json(
    {
      error,
      message:
        status === 413
          ? "The request body is too large."
          : "StoryForge API is unavailable.",
      details: [],
      request_id: requestId,
    },
    { status, headers: { "x-request-id": requestId } },
  );
}

type RouteContext = { params: Promise<{ path: string[] }> };
const handler = async (request: NextRequest, context: RouteContext) => {
  const { path } = await context.params;
  return proxy(request, path);
};

export {
  handler as DELETE,
  handler as GET,
  handler as PATCH,
  handler as POST,
  handler as PUT,
};
