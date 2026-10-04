"""Bounded, private Laya decisions. This module never generates chat responses."""
import math
import time

import httpx
from fastapi import HTTPException

QUESTIONS = {
    "thinking": {"type": "choice", "instructions": "Choose effort for latest_request only. Earlier requests are context for follow-ups, not tasks to repeat. A greeting after a complex task is still quick.",
                 "criteria": {"quick": "greeting, casual chat, straightforward fact, simple extraction or brief summary",
                              "deep": "multi-step reasoning, calculations, comparing evidence, contradictions, complex analysis or planning"}},
    "source": {"type": "choice", "instructions": "Choose the evidence needed for the latest request, considering available attachments.",
               "criteria": {"text": "answer from conversation or extracted document text; no visual inspection required",
                            "vision": "inspect photos, screenshots, scanned pages, charts, diagrams or page layout"}},
    "document_scope": {"type": "choice", "instructions": "Choose how to select document excerpts for the latest request.",
                       "criteria": {"overview": "summarize or review the document broadly; use excerpts spread across it",
                                    "focused": "answer a specific question; retrieve matching passages"}},
}


async def decide(client, message, history, attachments):
    start = time.monotonic()
    state = {"latest_request": message[:2400], "request_truncated": len(message) > 2400,
             "earlier_user_requests": history[-600:],
             "attachments": [{k: a[k] for k in ("id", "name", "kind", "pages", "characters")} for a in attachments]}
    # With no attached evidence, only the effort decision requires inference.
    # Laya still decides quick/deep for every request; this is not a keyword router.
    questions = QUESTIONS if attachments else {"thinking": QUESTIONS["thinking"]}
    try:
        response = await client.post("/v1/systemone", json={"state": state, "questions": questions,
                                    "model": "multilingual", "max_len": 1024, "head_max_len": 256})
        response.raise_for_status()
        result = response.json()
        answers = result["answers"]
        decisions = {}
        for key, options in (("thinking", {"quick", "deep"}), ("source", {"text", "vision"}),
                             ("document_scope", {"overview", "focused"})):
            if key not in questions:
                continue
            answer = answers[key]
            choice = answer["choice"]
            if choice not in options:
                raise ValueError("Invalid routing choice")
            # Prefer calibrated chosen-answer confidence, never entropy confidence.
            raw = answer.get("answer_confidence")
            if raw is None:
                probs = answer["probabilities"]
                raw = probs[choice] if isinstance(probs, dict) else None
            confidence = float(raw)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Invalid routing confidence")
            decisions[key] = {"choice": choice, "confidence": round(confidence, 4)}
        uncertain = decisions["thinking"]["confidence"] < 0.65 or state["request_truncated"]
        # Honor Laya's effort choice. Low confidence alone is not evidence that
        # a quick request needs hidden reasoning. Keep uncertainty in metadata.
        thinking = decisions["thinking"]["choice"] == "deep" or state["request_truncated"]
        vision = bool(attachments) and (decisions["source"]["choice"] == "vision" or
                 any(a["kind"] == "image" or not a["characters"] for a in attachments))
        return {"engine": "laya", "thinking": thinking, "vision": vision,
                "document_scope": decisions["document_scope"]["choice"] if attachments else "focused",
                "question_count": len(questions),
                "uncertain": uncertain, "decisions": decisions,
                "seconds": round(time.monotonic() - start, 3)}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Local Laya router unavailable or returned an invalid decision; check laya logs")
