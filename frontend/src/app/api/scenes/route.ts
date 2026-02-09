import { NextRequest, NextResponse } from "next/server";
import { createScene, ScriptParseError } from "@/lib/scenes";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { title, script_text, ai_character_name, ai_voice_id } = body;

    if (!title || !script_text || !ai_character_name || !ai_voice_id) {
      return NextResponse.json(
        { detail: "Missing required fields." },
        { status: 400 }
      );
    }

    const scene = await createScene({
      title,
      script_text,
      ai_character_name,
      ai_voice_id,
    });

    return NextResponse.json({ scene_id: scene.scene_id });
  } catch (err) {
    if (err instanceof ScriptParseError) {
      return NextResponse.json({ detail: err.message }, { status: 400 });
    }
    const message = err instanceof Error ? err.message : "Internal error";
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}
