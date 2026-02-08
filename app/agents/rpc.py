"""Shared RPC helpers for sending data to frontend participants."""

from __future__ import annotations

import json
import logging
from typing import Any

from livekit.agents import JobContext

logger = logging.getLogger(__name__)


async def send_rpc_to_ui_safe(
    ctx: JobContext,
    method: str,
    payload: dict[str, Any],
) -> None:
    """Send an RPC message to all remote (browser) participants.

    Iterates over every remote participant and sends individually with
    ``destination_identity``, matching the pattern used in the hackathon
    exa-deep-researcher example.  Silently swallows errors so callers
    don't need try/except.
    """
    try:
        room = ctx.room
        if room is None:
            logger.debug("No room available; skipping RPC %s", method)
            return

        remote_participants = list(room.remote_participants.values())
        if not remote_participants:
            logger.debug("No remote participants; skipping RPC %s", method)
            return

        payload_json = json.dumps(payload)

        for participant in remote_participants:
            try:
                await room.local_participant.perform_rpc(
                    destination_identity=participant.identity,
                    method=method,
                    payload=payload_json,
                )
            except Exception:
                logger.debug(
                    "Failed to send %s RPC to %s",
                    method,
                    participant.identity,
                )
    except Exception:
        logger.exception("Error in send_rpc_to_ui_safe(%s)", method)


async def stream_bytes_to_ui(
    ctx: JobContext,
    *,
    data: dict[str, Any],
    topic: str,
    filename: str = "data.json",
    attributes: dict[str, str] | None = None,
) -> None:
    """Send a large payload to the first remote participant via byte stream.

    Use this instead of RPC when the payload might exceed RPC size limits
    (e.g. locked script text).
    """
    try:
        room = ctx.room
        if room is None:
            logger.debug("No room available; skipping byte stream %s", topic)
            return

        remote_participants = list(room.remote_participants.values())
        if not remote_participants:
            logger.debug("No remote participants; skipping byte stream %s", topic)
            return

        data_json = json.dumps(data)
        data_bytes = data_json.encode("utf-8")
        dest_identities = [p.identity for p in remote_participants]

        logger.info(
            "Streaming %d bytes via byte stream (topic=%s) to %s",
            len(data_bytes),
            topic,
            dest_identities,
        )

        writer = await room.local_participant.stream_bytes(
            name=filename,
            total_size=len(data_bytes),
            mime_type="application/json",
            topic=topic,
            destination_identities=dest_identities,
            attributes=attributes or {},
        )

        await writer.write(data_bytes)
        await writer.aclose()

        logger.info("Byte stream sent successfully (topic=%s)", topic)
    except Exception:
        logger.exception("Error streaming bytes (topic=%s)", topic)
