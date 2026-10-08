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
    planning_seconds, execution_seconds, retrieval_seconds, action_seconds, rounds = 0.0, 0.0, 0.0, 0.0, 0
    successful_tool_results, duplicate_tool_calls_reused = {}, 0
    name_save = tools.explicit_name_save(session.value.message) if required_save else None
    direct_save = name_save or (tools.explicit_field_save(session.value.message) if required_save else None)
    natural = tools.natural_memory(session.value.message, session.settings) if not session.attachments else None
    natural = natural if natural and natural[0] in allowed else None
    if natural and natural[0] == 'memory_save':
        direct_save = natural[1]
    direct_forget = natural[1] if natural and natural[0] == 'memory_forget' else None
    direct_calculation = tools.explicit_calculation(session.value.message) if "calculator" in allowed and metadata.get("route", {}).get("tool_policy") == "explicit_calculation" else None
    direct_web = metadata.get("route", {}).get("web_search_query") if "web_search" in allowed and metadata.get("route", {}).get("tool_policy") in {"explicit_web_search", "web_search_followup", "explicit_web_search_and_save"} else None
    direct_web = direct_web if isinstance(direct_web, str) and direct_web.strip() else None
    metadata['tool_planning_mode'] = 'natural_memory' if natural else 'explicit_name_save' if name_save else 'explicit_field_save' if direct_save else 'explicit_calculation' if direct_calculation else 'explicit_web_search_and_save' if direct_web and metadata.get('route', {}).get('tool_policy') == 'explicit_web_search_and_save' else 'explicit_web_search' if direct_web else 'model'
    mode = metadata.get("execution_mode", metadata.get("route", {}).get("execution_mode", "balanced"))
    round_limit = 1 if mode == "fast" else 4 if mode == "deep" else tools.MAX_ROUNDS
    call_limit = 3 if mode == "fast" else 6 if mode == "deep" else tools.MAX_CALLS
    metadata["agent_step_limit"] = round_limit
    metadata["agent_call_limit"] = call_limit
    planner_thinking = bool(metadata.get('route', {}).get('thinking', False)) and not required_save and not direct_web
    required_result_save = bool(direct_web and metadata.get('route', {}).get('tool_policy') == 'explicit_web_search_and_save' and 'memory_save_result' in allowed)
    metadata['tool_result_save_required'] = required_result_save
    planner_budget = metadata.get('thinking_budget', 0) if planner_thinking else 0
    metadata['tool_thinking_budget'] = planner_budget
    if direct_save:
        # Keep the normal evidence validation, staging and answer transaction.
        event = {'name': 'memory_save', 'status': 'running', 'index': 1}
        yield 'tool', event
        execution_started = time.monotonic()
        result = await session.execute('memory_save', direct_save)
        elapsed = time.monotonic() - execution_started
        execution_seconds += elapsed
        action_seconds += elapsed
        event = {**event, 'status': 'complete', 'memory_key': result['key']}
        session.events.append(event)
        yield 'tool', event
    if direct_forget:
        event = {'name': 'memory_forget', 'status': 'running', 'index': 1}
        yield 'tool', event
        execution_started = time.monotonic()
        result = await session.execute('memory_forget', direct_forget)
        elapsed = time.monotonic() - execution_started
        execution_seconds += elapsed
        action_seconds += elapsed
        event = {**event, 'status': 'complete', 'memory_key': result['key']}
        session.events.append(event)
        yield 'tool', event
    if direct_calculation:
        event = {'name': 'calculator', 'status': 'running', 'index': 1}
        yield 'tool', event
        execution_started = time.monotonic()
        result = await session.execute('calculator', direct_calculation)
        elapsed = time.monotonic() - execution_started
        execution_seconds += elapsed
        action_seconds += elapsed
        event = {**event, 'status': 'complete'}
        session.events.append(event)
        metadata['_calculation_reply'] = f"{result['expression']} = {result['result']}."
        yield 'tool', event
    if direct_web:
        count += 1
        event = {'name': 'web_search', 'status': 'running', 'index': count}
        yield 'tool', event
        execution_started = time.monotonic()
        args = {'query': direct_web}
        try:
            result = await session.execute('web_search', args)
            status = 'complete'
        except (ValueError, TypeError, KeyError, SyntaxError, ArithmeticError, httpx.HTTPError) as error:
            detail = str(error) if isinstance(error, tools.ToolValidationError) else "Tool failed validation or is unavailable. Do not claim it succeeded."
            result = {'error': detail}
            status = 'failed'
        elapsed = time.monotonic() - execution_started
        execution_seconds += elapsed
        retrieval_seconds += elapsed
        result_event = {**event, 'status': status}
        if status == 'failed':
            result_event['detail'] = result['error']
        session.events.append(result_event)
        yield 'tool', result_event
        if status == 'complete':
            call_id = 'keno_direct_web_1'
            messages.append({'role': 'assistant', 'content': '', 'tool_calls': [{
                'id': call_id, 'type': 'function',
                'function': {'name': 'web_search', 'arguments': json.dumps(args, ensure_ascii=False)}}]})
            search_message = {'role': 'tool', 'tool_call_id': call_id, 'content': json.dumps(result, ensure_ascii=False)}
            messages.append(search_message)
            inspected_rows = set()
            inspect_count = min(3 if result.get('verification', {}).get('conflict') else 2, len(result.get('results', [])))
            for source_index in range(1, inspect_count + 1):
                if count >= call_limit - (1 if required_result_save else 0):
                    break
                count += 1
                inspect_event = {'name': 'web_inspect', 'status': 'running', 'index': count, 'source_index': source_index}
                yield 'tool', inspect_event
                inspect_started = time.monotonic()
                try:
                    inspected = await session.execute('web_inspect', {'source_index': source_index})
                    inspect_status = 'complete'
                except (ValueError, TypeError, KeyError, SyntaxError, ArithmeticError, httpx.HTTPError) as error:
                    inspected = {'error': str(error) if isinstance(error, tools.ToolValidationError) else "Inspection failed."}
                    inspect_status = 'failed'
                elapsed = time.monotonic() - inspect_started
                execution_seconds += elapsed
                retrieval_seconds += elapsed
                inspect_done = {**inspect_event, 'status': inspect_status}
                if inspect_status == 'failed':
                    inspect_done['detail'] = inspected['error']
                else:
                    inspected_rows.add(source_index)
                session.events.append(inspect_done)
                yield 'tool', inspect_done
                inspect_id = f'keno_direct_web_{count}'
                messages.append({'role': 'assistant', 'content': '', 'tool_calls': [{
                    'id': inspect_id, 'type': 'function',
                    'function': {'name': 'web_inspect', 'arguments': json.dumps({'source_index': source_index})}}]})
                messages.append({'role': 'tool', 'tool_call_id': inspect_id, 'content': json.dumps(inspected, ensure_ascii=False)})
            if inspected_rows:
                # Each inspection repeats that row's evidence and facts verbatim. Prompt
                # processing dominates search latency on CPU, so send them to the model once.
                rows = [{k: v for k, v in row.items() if k not in {'page_excerpt', 'facts'}
                         and not (k == 'snippet' and not row.get('page_excerpt'))}
                        if index in inspected_rows else row
                        for index, row in enumerate(result.get('results', []), 1)]
                search_message['content'] = json.dumps({k: v for k, v in {**result, 'results': rows}.items() if k != 'sources'}, ensure_ascii=False)
        if required_result_save and status == 'complete':
            request_definitions = [tools.SPECS['memory_save_result']]
            allowed = {'memory_save_result'}
        elif required_result_save:
            required_result_save = False
            metadata['tool_result_save_required'] = False
    skip_planner = bool(direct_save or direct_forget or direct_calculation or (direct_web and not required_result_save))
    for round_number in range(0 if skip_planner else round_limit):
        await check_budget(messages, metadata, request_definitions)
        planning_started = time.monotonic()
        response = await client.post("/v1/chat/completions", json={
            "model": model, "messages": messages, "tools": request_definitions,
            "tool_choice": "required" if required_save or required_result_save else "auto",
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
        if choice.get("finish_reason") == "length" or len(calls) > call_limit - count:
            raise ValueError("Tool call exceeded its generation or execution limit")
        normalized, results, may_continue = [], [], False
        for call in calls:
            if count >= call_limit: raise ValueError("Tool call limit reached")
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
                fingerprint = name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if fingerprint in successful_tool_results:
                    result = successful_tool_results[fingerprint]
                    status = "reused"
                    duplicate_tool_calls_reused += 1
                else:
                    result = await session.execute(name, args)
                    successful_tool_results[fingerprint] = result
                    status = "complete"
                may_continue |= name in {"memory_search", "document_search", "document_read", "document_overview", "web_search", "web_inspect"}
            except (ValueError, TypeError, KeyError, SyntaxError, ArithmeticError, httpx.HTTPError) as error:
                detail = str(error) if isinstance(error, tools.ToolValidationError) else "Tool failed validation or is unavailable. Do not claim it succeeded. Ask for missing details or retry with valid arguments."
                result = {"error": detail}
                status = "failed"
                may_continue = True
            elapsed = time.monotonic() - execution_started
            execution_seconds += elapsed
            if name in {"memory_search", "document_search", "document_read", "document_overview", "web_search", "web_inspect"}:
                retrieval_seconds += elapsed
            else:
                action_seconds += elapsed
            result_event = {**event, "status": status}
            if status == "failed": result_event["detail"] = result["error"]
            if isinstance(result, dict) and "key" in result: result_event["memory_key"] = result["key"]
            session.events.append(result_event)
            yield "tool", result_event
            results.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, ensure_ascii=False)})
        messages.append({"role": "assistant", "content": "", "tool_calls": normalized})
        messages.extend(results)
        if not may_continue or count >= call_limit:
            break
    metadata["tool_seconds"] = round(time.monotonic() - started, 3)
    metadata["tool_model_seconds"] = round(planning_seconds, 3)
    metadata["tool_execution_seconds"] = round(execution_seconds, 3)
    metadata["retrieval_seconds"] = round(retrieval_seconds, 3)
    metadata["action_tool_seconds"] = round(action_seconds, 3)
    metadata["tool_planning_rounds"] = rounds
    metadata["duplicate_tool_calls_reused"] = duplicate_tool_calls_reused
    metadata["unique_tool_executions"] = max(0, len(session.events) - duplicate_tool_calls_reused)
    metadata["tool_execution_efficiency"] = round(metadata["unique_tool_executions"] / max(1, len(session.events)), 3)
    metadata["agent_steps"] = list(session.events)
    metadata["tool_calls"] = session.events
    metadata["memory_changes"] = [{"action": m["action"], "key": m["key"]} for m in session.mutations]
    metadata["memory_conflicts"] = list(session.memory_conflicts)
    metadata["web_sources"] = session.web_sources
    metadata["web_verification"] = session.web_verification
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
