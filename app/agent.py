"""Bounded native tool planning; only allowlisted functions reach execution."""
import json
import time

import httpx

from . import tools


async def plan(client, model, messages, definitions, session, metadata, check_budget):
    allowed = {d["function"]["name"] for d in definitions}
    # For a clear firsthand save on Laya's memory route, the user has already
    # selected the action. Do not let auto return a chat reply instead of a call.
    # This llama.cpp version supports string "required", not named tool objects.
    required_save = (metadata.get("route", {}).get("tool_family") == "memory"
                     and "memory_save" in allowed and not session.attachments
                     and bool(tools.FIRSTHAND_SAVE.search(session.value.message.strip()))
                     and not tools.NO_SAVE.search(session.value.message)
                     and not tools.FORGET_REQUEST.search(session.value.message))
    request_definitions = [tools.SPECS["memory_save"]] if required_save else definitions
    if required_save:
        allowed = {"memory_save"}
    metadata["tool_save_required"] = required_save
    started, count = time.monotonic(), 0
    planning_seconds, execution_seconds, rounds = 0.0, 0.0, 0
    direct_save = tools.explicit_name_save(session.value.message) if required_save else None
    metadata['tool_planning_mode'] = 'explicit_name_save' if direct_save else 'model'
    planner_thinking = bool(metadata.get('route', {}).get('thinking', False)) and not required_save
    planner_budget = metadata.get('thinking_budget', 0) if planner_thinking else 0
    metadata['tool_thinking_budget'] = planner_budget
    if direct_save:
        # Keep the normal evidence validation, staging and answer transaction.
        event = {'name': 'memory_save', 'status': 'running', 'index': 1}
        yield 'tool', event
        execution_started = time.monotonic()
        result = await session.execute('memory_save', direct_save)
        execution_seconds = time.monotonic() - execution_started
        event = {**event, 'status': 'complete', 'memory_key': result['key']}
        session.events.append(event)
        yield 'tool', event
    for round_number in range(0 if direct_save else tools.MAX_ROUNDS):
        await check_budget(messages, metadata, request_definitions)
        planning_started = time.monotonic()
        response = await client.post("/v1/chat/completions", json={
            "model": model, "messages": messages, "tools": request_definitions,
            "tool_choice": "required" if required_save else "auto",
            "parallel_tool_calls": False, "stream": False, "temperature": 0,
            "max_tokens": 512 + planner_budget, "chat_template_kwargs": {"enable_thinking": planner_thinking},
            "reasoning_budget_tokens": planner_budget, "reasoning_format": "deepseek", "cache_prompt": True})
        response.raise_for_status()
        body = response.json()
        planning_seconds += time.monotonic() - planning_started
        rounds += 1
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
            content = message.get("content")
            # A complete answer from the first pass needs no second inference.
            # This pass already honors Laya's selected effort and budget.
            # Keep it transient: generate() applies memory/weather guards first.
            if count == 0 and not required_save and choice.get("finish_reason") == "stop" and isinstance(content, str) and content.strip() and not content.lstrip().startswith(("{", "[", "```")):
                if len(content) > 100_000:
                    raise ValueError("Model output exceeded limit")
                metadata["_planner_reply"] = content
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
            execution_started = time.monotonic()
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
            execution_seconds += time.monotonic() - execution_started
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
    metadata["tool_model_seconds"] = round(planning_seconds, 3)
    metadata["tool_execution_seconds"] = round(execution_seconds, 3)
    metadata["tool_planning_rounds"] = rounds
    metadata["tool_calls"] = session.events
    metadata["memory_changes"] = [{"action": m["action"], "key": m["key"]} for m in session.mutations]
    metadata["web_sources"] = session.web_sources
    if session.sources:
        metadata["document_sources"] = list({(s["attachment_id"], s["page"], s["chunk"]): s for s in session.sources}.values())
        # Tool results now supply the document evidence; avoid sending it twice.
        for message in messages:
            if message["role"] != "user": continue
            content = message["content"]
            if isinstance(content, str) and content.startswith(session.value.message) and "\n\nSelected uploaded-file" in content:
                message["content"] = content.split("\n\nSelected uploaded-file", 1)[0]
            elif isinstance(content, list) and content and content[0].get("type") == "text" and content[0]["text"].startswith(session.value.message) and "\n\nSelected uploaded-file" in content[0]["text"]:
                content[0]["text"] = content[0]["text"].split("\n\nSelected uploaded-file", 1)[0]
    await check_budget(messages, metadata, [])
