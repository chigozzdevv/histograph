import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const apiUrl = process.env.HISTOGRAPH_API_URL ?? "http://localhost:8000";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: NextRequest, context: RouteContext) {
  const token = process.env.HISTOGRAPH_API_TOKEN;
  if (!token) {
    return NextResponse.json(
      { detail: "Histograph API credentials are unavailable" },
      { status: 503 },
    );
  }
  const { path } = await context.params;
  const upstreamUrl = new URL(`${apiUrl}/v1/${path.join("/")}`);
  upstreamUrl.search = request.nextUrl.search;
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  const contentType = request.headers.get("content-type");
  const idempotencyKey = request.headers.get("idempotency-key");
  if (contentType) headers.set("Content-Type", contentType);
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  const body =
    request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  const response = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  });
  return new NextResponse(response.body, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
