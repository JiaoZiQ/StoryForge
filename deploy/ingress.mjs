import { createServer, request } from "node:http";

const hopByHopHeaders = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function safeHeaders(headers) {
  return Object.fromEntries(
    Object.entries(headers).filter(([name]) => !hopByHopHeaders.has(name.toLowerCase())),
  );
}

function proxy(upstream) {
  return createServer((incoming, outgoing) => {
    const target = new URL(incoming.url ?? "/", upstream);
    const headers = safeHeaders(incoming.headers);
    headers.host = target.host;
    headers["x-forwarded-host"] = incoming.headers.host ?? "localhost";
    headers["x-forwarded-proto"] = "http";
    const forwarded = request(
      target,
      { method: incoming.method, headers },
      (response) => {
        outgoing.writeHead(response.statusCode ?? 502, safeHeaders(response.headers));
        response.pipe(outgoing);
      },
    );
    forwarded.setTimeout(120_000, () => forwarded.destroy(new Error("upstream timeout")));
    forwarded.on("error", () => {
      if (!outgoing.headersSent) {
        outgoing.writeHead(502, { "content-type": "application/json" });
      }
      outgoing.end(
        JSON.stringify({
          error: "upstream_unavailable",
          message: "StoryForge is temporarily unavailable.",
          details: [],
        }),
      );
    });
    incoming.pipe(forwarded);
  });
}

proxy("http://frontend:3000").listen(3000, "0.0.0.0");
proxy("http://api:8000").listen(8000, "0.0.0.0");
