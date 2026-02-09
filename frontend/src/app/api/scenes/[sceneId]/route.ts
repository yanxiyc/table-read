import { NextRequest, NextResponse } from "next/server";
import { loadScene } from "@/lib/scenes";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ sceneId: string }> }
) {
  const { sceneId } = await params;

  try {
    const scene = await loadScene(sceneId);
    return NextResponse.json(scene);
  } catch {
    return NextResponse.json(
      { detail: `Scene '${sceneId}' not found.` },
      { status: 404 }
    );
  }
}
