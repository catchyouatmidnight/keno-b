"""Bounded, private Laya decisions. This module never generates chat responses."""
import math
import time

import httpx
from fastapi import HTTPException

QUESTIONS = {
    "thinking": {"type": "choice", "instructions": "Choose effort for latest_request only. Earlier requests are context for follow-ups, not tasks to repeat. Prefer quick for routine help. A list of instructions is not by itself complex reasoning.",
                 "criteria": {"quick": "greeting, casual chat, straightforward fact, routine device settings or how-to instructions, simple extraction or brief summary",
                              "deep": "requires substantive multi-step inference: comparing conflicting evidence, resolving contradictions, complex analysis or planning with constraints"}},
    "source": {"type": "choice", "instructions": "Choose the evidence needed for the latest request, considering available attachments.",
               "criteria": {"text": "answer from conversation or extracted document text; no visual inspection required",
                            "vision": "inspect photos, screenshots, scanned pages, charts, diagrams or page layout"}},
    "document_scope": {"type": "choice", "instructions": "Choose how to select document excerpts for the latest request.",
                       "criteria": {"overview": "general explanation such as 'tell me about this', summarize or review the document broadly; use excerpts spread across it",
                                    "focused": "answer a specific question; retrieve matching passages"}},
    "tool_family": {"type": "choice", "instructions": "Choose tools necessary to fulfill latest_request only. Routine instructions or explanations need none. Mentioning a device or personal detail inside a question is not a request to save it. Earlier requests are only follow-up context; do not repeat their actions. Save firsthand lasting user facts in introductions, declarations and corrections, never facts from attachments or assistant replies.",
                    "criteria": {"none": "casual chat, general knowledge, routine device settings or how-to advice; explain steps without performing an action",
                                 "memory": "user declares a lasting personal fact/preference, introduces themselves, explicitly saves, asks what is remembered, corrects or forgets a saved fact",
                                 "documents": "explain, summarize, search or read selected uploaded files",
                                 "calculator": "arithmetic calculation",
                                 "live": "current weather, news or explicit web search",
                                 "multiple": "request needs more than one tool family"}},
}


async def decide(client, message, history, attachments):
    start = time.monotonic()
    state = {"latest_request": message[:2400], "request_truncated": len(message) > 2400,
             "earlier_user_requests": history[-600:],
             "attachments": [{k: a[k] for k in ("id", "name", "kind", "pages", "characters")} for a in attachments]}
    # Plain chat needs effort and tool-family decisions only.
    # Laya still decides quick/deep for every request; this is not a keyword router.
    questions = QUESTIONS if attachments else {k: QUESTIONS[k] for k in ("thinking", "tool_family")}
    try:
        response = await client.post("/v1/systemone", json={"state": state, "questions": questions,
                                    "model": "multilingual", "max_len": 1024, "head_max_len": 256})
        response.raise_for_status()
        result = response.json()
        answers = result["answers"]
        decisions = {}
        for key, options in (("thinking", {"quick", "deep"}), ("source", {"text", "vision"}),
                             ("document_scope", {"overview", "focused"}),
                             ("tool_family", {"none", "memory", "documents", "calculator", "live", "multiple"})):
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
        # Latency policy: require a confident deep choice. Preserve Laya's raw
        # decision for inspection; uncertain short requests default to quick.
        thinking = (decisions["thinking"]["choice"] == "deep"
                    and decisions["thinking"]["confidence"] >= 0.65) or state["request_truncated"]
        vision = bool(attachments) and (decisions["source"]["choice"] == "vision" or
                 any(a["kind"] == "image" or not a["characters"] for a in attachments))
        return {"engine": "laya", "thinking": thinking, "vision": vision,
                "document_scope": decisions["document_scope"]["choice"] if attachments else "focused",
                "question_count": len(questions),
                "tool_family": decisions["tool_family"]["choice"],
                "uncertain": uncertain, "decisions": decisions,
                "effort_policy": "truncated_deep" if state["request_truncated"] else
                                 "uncertain_quick" if uncertain else "laya_choice",
                "seconds": round(time.monotonic() - start, 3)}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Local Laya router unavailable or returned an invalid decision; check laya logs")
