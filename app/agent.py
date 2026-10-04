"""Bounded native tool planning; only allowlisted functions reach execution."""
import json
import time

import httpx

from . import tools


async def plan(client, model, messages, definitions, session, metadata, check_budget):
    allowed = {d["function"]["name"] for d in definitions}
    started, count = time.monotonic(), 0
    for round_number in range(tools.MAX_ROUNDS):
        await check_budget(messages, metadata, definitions)
        response = await client.post("/v1/chat/completions", json={
            "model": model, "messages": messages, "tools": definitions, "tool_choice": "auto",
            "parallel_tool_calls": False, "stream": False, "temperature": 0,
            "max_tokens": 512, "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_budget_tokens": 0, "reasoning_format": "deepseek", "cache_prompt": True})
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("Model returned invalid tool choices")
        choice = choices[0]
        message = choice.get("message", {})
        if not isinstance(message, dict):
            raise ValueError("Model returned an invalid tool message")
        calls = message.get("tool_calls") or []
        if not isinstance(calls, list) or any(not isinstance(call, dict) or not isinstance(call.get("function"), dict) for call in calls):
            raise ValueError("Model returned malformed tool calls")
        if not calls:
            break
        if choice.get("finish_reason") == "length" or len(calls) > tools.MAX_CALLS - count:
            raise ValueError("Tool call exceeded its generation or execution limit")
        normalized, results, may_continue = [], [], False
        for call in calls:
            if count >= tools.MAX_CALLS: raise ValueError("Tool call limit reached")
            count += 1
            function = call.get("function", {})
            name = function.get("name", "")
            if not isinstance(name, str) or not 1 <= len(name) <= 80:
                raise ValueError("Model returned an invalid tool name")
            call_id = f"keno_call_{round_number}_{count}"
            raw = function.get("arguments", "{}")
            normalized.append({"id": call_id, "type": "function", "function": {"name": name, "arguments": raw if isinstance(raw, str) else json.dumps(raw)}})
            event = {"name": name, "status": "running", "index": count}
            yield "tool", event
            try:
                if name not in allowed: raise ValueError("Tool was not allowed for this request")
                if not isinstance(raw, str) or len(raw) > 8000: raise ValueError("Tool arguments exceed limit")
                args = json.loads(raw)
                result = await session.execute(name, args)
                status = "complete"
                may_continue |= name in {"memory_search", "document_search"}
            except (ValueError, TypeError, KeyError, SyntaxError, ArithmeticError, httpx.HTTPError) as error:
                detail = str(error) if isinstance(error, tools.ToolValidationError) else "Tool failed validation or is unavailable. Do not claim it succeeded. Ask for missing details or retry with valid arguments."
                result = {"error": detail}
                status = "failed"
                may_continue = True
            result_event = {**event, "status": status}
            if status == "failed": result_event["detail"] = result["error"]
            if isinstance(result, dict) and "key" in result: result_event["memory_key"] = result["key"]
            session.events.append(result_event)
            yield "tool", result_event
            results.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, ensure_ascii=False)})
        messages.append({"role": "assistant", "content": "", "tool_calls": normalized})
        messages.extend(results)
        if not may_continue or count >= tools.MAX_CALLS:
            break
    metadata["tool_seconds"] = round(time.monotonic() - started, 3)
    metadata["tool_calls"] = session.events
    metadata["memory_changes"] = [{"action": m["action"], "key": m["key"]} for m in session.mutations]
    metadata["web_sources"] = session.web_sources
    if session.sources:
        metadata["document_sources"] = list({(s["attachment_id"], s["page"], s["chunk"]): s for s in session.sources}.values())
        # Tool results now supply the document evidence; avoid sending it twice.
        for message in messages:
            if message["role"] != "user": continue
            content = message["content"]
            if isinstance(content, str) and content.startswith(session.value.message + "\n\nSelected uploaded-file"):
                message["content"] = session.value.message
            elif isinstance(content, list) and content and content[0].get("type") == "text" and content[0]["text"].startswith(session.value.message + "\n\nSelected uploaded-file"):
                content[0]["text"] = session.value.message
    messages[0]["content"] += "\nTool phase is complete. Answer the user's request using successful results. Do not request more tools."
    await check_budget(messages, metadata, [])
