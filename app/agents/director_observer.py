import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from app.agents.rpc import send_rpc_to_ui_safe
from app.models import Beat, StyleState

logger = logging.getLogger(__name__)

# Load evaluation prompt template
_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "director_evaluation.yaml"


def _load_prompt_template() -> str:
    if _PROMPT_PATH.exists():
        data = yaml.safe_load(_PROMPT_PATH.read_text())
        return data.get("system_prompt", "")
    return ""


class DirectorObserver:
    """Observes actor performance and provides AI director feedback."""

    def __init__(self, session, llm):
        """
        Args:
            session: The AgentSession instance
            llm: An anthropic LLM instance (from livekit.plugins.anthropic)
        """
        self.session = session
        self.llm = llm
        self._prompt_template = _load_prompt_template()
        self._eval_history: list[dict[str, Any]] = []
        self._consecutive_narrating = 0

    async def evaluate_performance(
        self, beat: Beat, actor_text: str, style: StyleState
    ) -> dict[str, Any] | None:
        """Called by character agent after actor delivers a line.

        Builds prompt, calls LLM, returns evaluation dict, sends feedback.
        """
        try:
            expected = beat.canonical or ""
            character = beat.character or "ACTOR"

            # Build the evaluation prompt
            previous_feedback = ""
            if self._eval_history:
                last_evals = self._eval_history[-3:]
                previous_feedback = "\n".join(
                    f"- Beat {e.get('beat_id','?')}: {e.get('verdict','?')} - {e.get('director_note','')}"
                    for e in last_evals
                )

            user_prompt = (
                f"Character: {character}\n"
                f"Expected line: {expected}\n"
                f"Actor said: {actor_text}\n"
                f"Current style - tension: {style.tension:.2f}, warmth: {style.warmth:.2f}, "
                f"pace: {style.pace:.2f}\n"
                f"Consecutive 'narrating' verdicts so far: {self._consecutive_narrating}\n"
            )
            if previous_feedback:
                user_prompt += f"\nPrevious feedback:\n{previous_feedback}\n"

            user_prompt += (
                "\nEvaluate the actor's delivery. Return JSON with these fields:\n"
                '{"is_acting": bool, "is_narrating": bool, "emotional_engagement": "low"|"medium"|"high", '
                '"overall_rating": 1-10, "director_note": "brief constructive note", '
                '"should_speak_feedback": bool}\n'
            )

            # Call LLM using the chat context approach
            from livekit.agents.llm import ChatContext

            chat_ctx = ChatContext()
            if self._prompt_template:
                chat_ctx.add_message(role="system", content=self._prompt_template)
            else:
                chat_ctx.add_message(
                    role="system",
                    content=(
                        "You are an expert acting coach and theater director. "
                        "Evaluate whether an actor is truly ACTING (emotionally engaged, "
                        "making choices, inhabiting the character) or merely NARRATING/READING "
                        "(monotone, flat, just saying words without feeling). "
                        "Be encouraging but honest. Give specific, actionable feedback. "
                        "Return valid JSON only."
                    ),
                )
            chat_ctx.add_message(role="user", content=user_prompt)

            # Use the LLM to get a response
            stream = self.llm.chat(chat_ctx=chat_ctx)
            response_text = ""
            async for chunk in stream:
                try:
                    if hasattr(chunk, "choices") and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "content") and delta.content:
                            response_text += delta.content
                    elif hasattr(chunk, "content") and chunk.content:
                        response_text += chunk.content
                except (IndexError, AttributeError):
                    continue

            if not response_text.strip():
                logger.warning("Director LLM returned empty response")
                return None

            # Parse the JSON response
            evaluation = self._parse_evaluation(response_text)
            if evaluation is None:
                logger.warning(
                    "Failed to parse director evaluation: %s", response_text[:200]
                )
                return None

            evaluation["beat_id"] = beat.id
            evaluation["actor_text"] = actor_text

            # Track consecutive narrating
            if evaluation.get("is_narrating", False):
                self._consecutive_narrating += 1
            else:
                self._consecutive_narrating = 0

            # Store evaluation
            self._eval_history.append(evaluation)
            userdata = self.session.userdata
            userdata.evaluations.append(evaluation)

            # Send feedback to frontend via RPC
            await self._send_feedback_rpc(evaluation)

            # Optionally speak feedback aloud
            if evaluation.get("should_speak_feedback", False):
                note = evaluation.get("director_note", "")
                if note:
                    await self.session.say(
                        f"Director note: {note}",
                        allow_interruptions=True,
                    )

            return evaluation

        except Exception:
            logger.exception("Director evaluation failed")
            return None

    def _parse_evaluation(self, text: str) -> dict[str, Any] | None:
        """Extract JSON from LLM response text."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON in the text
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    async def _send_feedback_rpc(self, evaluation: dict[str, Any]) -> None:
        """Send director feedback to frontend via shared RPC helper."""
        userdata = self.session.userdata
        ctx = userdata.ctx
        if not ctx:
            return

        payload = {
            "beat_id": evaluation.get("beat_id", ""),
            "is_acting": evaluation.get("is_acting", False),
            "is_narrating": evaluation.get("is_narrating", True),
            "emotional_engagement": evaluation.get("emotional_engagement", "low"),
            "overall_rating": evaluation.get("overall_rating", 5),
            "director_note": evaluation.get("director_note", ""),
            "consecutive_narrating": self._consecutive_narrating,
        }

        await send_rpc_to_ui_safe(ctx, "director_feedback", payload)
