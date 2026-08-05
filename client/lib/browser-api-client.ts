export async function mutate<T>(
  path: string,
  body: unknown,
  options: { method?: "POST" | "PATCH"; idempotencyKey?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  const response = await fetch(`/api/histograph${path}`, {
    method: options.method ?? "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}
