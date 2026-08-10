import { NextResponse } from "next/server";

import { getDemoScenarioSnapshot } from "@/lib/histograph-api";

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!uuidPattern.test(id)) {
    return NextResponse.json({ detail: "Scenario run not found" }, { status: 404 });
  }

  try {
    const snapshot = await getDemoScenarioSnapshot(id);
    if (!snapshot) {
      return NextResponse.json({ detail: "Scenario run not found" }, { status: 404 });
    }
    return NextResponse.json(snapshot, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json({ detail: "Scenario state is temporarily unavailable" }, { status: 502 });
  }
}
