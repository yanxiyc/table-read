import { AccessToken, RoomAgentDispatch, RoomConfiguration } from "livekit-server-sdk";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { sceneId } = await req.json();

  if (!sceneId) {
    return NextResponse.json({ error: "sceneId is required" }, { status: 400 });
  }

  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const livekitUrl = process.env.LIVEKIT_URL || "ws://localhost:7880";

  if (!apiKey || !apiSecret) {
    return NextResponse.json(
      { error: "LiveKit credentials not configured" },
      { status: 500 }
    );
  }

  const roomName = `table-read-${sceneId}`;
  const identity = `actor-${sceneId.slice(0, 8)}`;

  const agentDispatch = new RoomAgentDispatch({ agentName: "table-read-agent" });
  const roomConfig = new RoomConfiguration({ agents: [agentDispatch] });

  const at = new AccessToken(apiKey, apiSecret, {
    identity,
    ttl: "1h",
  });
  at.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
  });
  at.roomConfig = roomConfig;

  const token = await at.toJwt();

  return NextResponse.json({
    token,
    serverUrl: livekitUrl,
    room: roomName,
  });
}
