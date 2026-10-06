"""Allowlisted local tools. Memory effects remain staged until the answer commits."""
import ast
import json
import math
import re
from decimal import Decimal, localcontext

from . import documents

MAX_CALLS = 4
MAX_ROUNDS = 2
WRITE_REQUEST = re.compile(r"\b(remember|save|forget|delete|remove|ingat|simpan|hapus|lupakan)\b", re.I)
NO_FORGET = re.compile(r"(?:don't|do not|never)\s+(?:forget|delete|remove)|jangan\s+(?:hapus|lupakan)", re.I)
FORGET_REQUEST = re.compile(r"\b(forget|delete|remove|hapus|lupakan)\b", re.I)
FOLLOWUP_SAVE = re.compile(r"^(?:please\s+)?(?:save|remember|simpan|ingat)(?:\s+(?:this|that|it|me|ini|itu|saya))?(?:\s+(?:please|for future chats))?[.!?]*$", re.I)
# Detect an explicit firsthand save request for acknowledgement and required
# save planning on Laya's memory route. This does not extract or write a fact.
FIRSTHAND_SAVE = re.compile(r"^(?:please\s+)?(?:remember|save|simpan|ingat)\s+(?:that\s+)?(?:my\b|i\b|i'm\b|the\s+fact\b|nama\s+saya\b|saya\b)", re.I)
BARE_WEB_SEARCH = re.compile(
    r"^\s*(?:please\s+)?(?:search(?:\s+(?:from|on))?\s+(?:google|the\s+web|web|online)|"
    r"search\s+online|google|web\s+search|look\s+up(?:\s+online)?)\s*[?.!]*$", re.I)
WEB_SEARCH_QUERY = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"search(?:\s+(?:from|on))?\s+(?:google|the\s+web|web|online)\s+(?:for\s+)?|"
    r"search\s+(?:for\s+)?|google\s+(?:for\s+)?|look\s+up\s+(?:online\s+)?"
    r")(?P<query>\S.{0,299}?)\s*[?.!]*$", re.I)
SEARCH_FOLLOWUP_SKIP = re.compile(
    r"^\s*(?:thanks|thank\s+you|ok|okay|yes|yeah|yep|no|cancel|stop|never\s*mind)\s*[?.!]*$", re.I)
LOCAL_SEARCH_TARGET = re.compile(
    r"\b(?:my\s+)?(?:memory|memories|saved\s+facts?|profile|library|documents?|files?|attachments?|notes?|"
    r"chats?|conversations?|history)\b", re.I)
EXPLICIT_WEB_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:search(?:\s+(?:from|on))?\s+(?:google|the\s+web|web|online)|"
    r"google|look\s+up\s+online)\b", re.I)


def bare_web_search(text):
    return isinstance(text, str) and bool(BARE_WEB_SEARCH.fullmatch(text.strip()))


def explicit_web_search(text):
    if not isinstance(text, str) or bare_web_search(text):
        return None
    match = WEB_SEARCH_QUERY.fullmatch(text)
    if not match:
        return None
    if LOCAL_SEARCH_TARGET.search(text) and not EXPLICIT_WEB_PREFIX.search(text):
        return None
    query = match.group("query").strip()
    return query if query and re.search(r"\w", query) else None


def web_search_followup(text, previous):
    if not isinstance(text, str) or not bare_web_search(previous):
        return None
    query = text.strip()
    if not query or len(query) > 300 or bare_web_search(query) or SEARCH_FOLLOWUP_SKIP.fullmatch(query):
        return None
    return query if re.search(r"\w", query) else None


def explicit_name_save(text):
    """Extract only a complete, explicit name-save command; preserve its quote."""
    if NO_SAVE.search(text) or FORGET_REQUEST.search(text):
        return None
    match = re.fullmatch(
        r"(?:please\s+)?(?:remember|save)\s+(?:that\s+)?"
        r"(?P<quote>my\s+name\s+is\s+(?P<name>[^.!?\n]{1,80}))[.!]?",
        text.strip(), re.I)
    if not match:
        return None
    name = match.group('name').strip()
    words = name.split()
    if not 1 <= len(words) <= 4 or any(w.casefold() in {'and', 'or', 'then', 'but', 'dan', 'atau'} for w in words):
        return None
    if not all(c.isalpha() or c in " -'’" for c in name) or not any(c.isalpha() for c in name):
        return None
    return {'key': 'user.name', 'quote': match.group('quote').rstrip(), 'category': 'fact'}


FIELD_FACT = re.compile(r"my (?P<field>[A-Za-z][A-Za-z ]{0,59}?) is (?P<value>[^.!?;\n]{1,300})[.!]?", re.I)


def field_fact(text):
    match = FIELD_FACT.fullmatch(text.strip())
    if not match or len(match['field'].split()) > 6 or re.search(r"\b(?:and|then|but|or)\b", match['field'] + ' ' + match['value'], re.I):
        return None
    field = ' '.join(match['field'].casefold().split())
    if field in {'name', 'creator'} or not match['value'].strip():
        return None
    return field, match['value'].strip()


def explicit_field_save(text):
    if NO_SAVE.search(text) or FORGET_REQUEST.search(text):
        return None
    match = re.fullmatch(r"(?:please\s+)?(?:remember|save)\s+(?:that\s+)?(?P<quote>my .{1,370})", text.strip(), re.I)
    fact = field_fact(match['quote']) if match else None
    if not fact:
        return None
    return {'key': 'user.fact.' + fact[0].replace(' ', '_'), 'quote': match['quote'].rstrip('.!'), 'category': 'fact'}


def explicit_calculation(text):
    match = re.fullmatch(r"\s*(?:please\s+)?calculate\s+([0-9\s.+*/()%−×÷-]{1,200})\s*[?]?", text, re.I)
    if not match:
        return None
    expression = match[1].strip().replace('×', '*').replace('÷', '/').replace('−', '-')
    try:
        calculate(expression)
    except (ValueError, SyntaxError, ArithmeticError):
        return None
    return {'expression': expression}


LOCATION = re.compile(r"(?:actually,?\s*)?(?:i live in|i (?:have )?moved to|saya tinggal di|saya pindah ke)\s+([\w][\w '’-]{0,79})[.!]?", re.I)


def location_fact(text):
    m = LOCATION.fullmatch(text.strip())
    if not m or re.search(r"\b(?:and|or|then|but|if|when|tomorrow|because|since|for|dan|atau)\b", m[1], re.I):
        return None
    return m[1].strip()


def natural_memory(text, settings):
    """Recognize only complete firsthand statements or explicit field deletion."""
    if NO_SAVE.search(text) or NO_FORGET.search(text):
        return None
    forget = re.fullmatch(r"(?:please\s+)?(?:forget|delete|remove)\s+my\s+(city|location)[.!]?", text.strip(), re.I)
    if forget:
        return ('memory_forget', {'key': 'user.location', 'quote': text.strip()})
    if not settings['automatic_memory'] or FORGET_REQUEST.search(text):
        return None
    location = location_fact(text)
    if location:
        return ('memory_save', {'key': 'user.location', 'quote': text.strip().rstrip('.!'), 'category': 'fact'})
    name = explicit_name_save('Remember that ' + text.strip())
    if name:
        return ('memory_save', name)
    return None


class ToolValidationError(ValueError):
    pass


class MemoryEvidenceError(ToolValidationError):
    pass


NO_SAVE = re.compile(r"(?:don't|do not|never)\s+(?:save|remember)|jangan\s+(?:simpan|ingat)", re.I)


def spec(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False}}}


STRING = {"type": "string"}
SPECS = {
    "memory_search": spec("memory_search", "Find saved facts and their keys. Use before correcting an unknown key.",
                          {"query": STRING}, ["query"]),
    "memory_save": spec("memory_save", "Remember a lasting firsthand fact or preference stated by the user. quote must be copied verbatim from the latest user message. For an explicit follow-up such as save or remember that, quote the relevant recent USER message instead. Never quote a file or assistant answer. Reuse the existing key for corrections. Prefer user.name, user.location, user.preferred_language for those facts.",
                        {"key": STRING, "quote": STRING, "category": {"type": "string", "enum": ["fact", "preference", "project", "temporary"]}}, ["key", "quote", "category"]),
    "memory_forget": spec("memory_forget", "Forget one saved fact only when the current user explicitly asks. quote is the user's verbatim deletion request.",
                          {"key": STRING, "quote": STRING}, ["key", "quote"]),
    "document_search": spec("document_search", "Search selected uploaded files. Results include file/page citations.",
                            {"query": STRING}, ["query"]),
    "document_read": spec("document_read", "Read extracted text from specific pages of a selected file. Use its attachment_id from the supplied file list.",
                          {"attachment_id": STRING, "pages": {"type": "array", "items": {"type": "integer"}, "maxItems": 4}}, ["attachment_id", "pages"]),
    "document_overview": spec("document_overview", "Get bounded text covering every extracted page of selected files for a broad summary. Coverage reports missing/scanned pages and shortened excerpts.", {}, []),
    "calculator": spec("calculator", "Calculate arithmetic exactly using decimals. Supports + - * / // % ** and parentheses; no code or variables.",
                       {"expression": STRING}, ["expression"]),
    "weather": spec("weather", "Get current weather and today's forecast for a city explicitly supplied in the current user request. Ask for a city if none was supplied. Only the city is sent to Open-Meteo.",
                    {"city": STRING}, ["city"]),
    "web_search": spec("web_search", "Search the web for an explicit current user request. Model-generated queries must be a verbatim span of the current request. A server-validated search follow-up may reuse only the prior query already sent to search. Never send file contents, memories or assistant text. Returns snippets and links, not a full-page review.",
                       {"query": STRING}, ["query"]),
}


def catalog(family, settings, message, attachments):
    groups = {"memory": ["memory_search", "memory_save", "memory_forget"],
              "documents": ["document_search", "document_read", "document_overview"],
              "calculator": ["calculator"], "live": ["weather", "web_search"], "none": []}
    names = sum((groups[name] for name in ("memory", "documents", "calculator", "live")), []) if family == "multiple" else groups.get(family, [])
    if not attachments:
        names = [n for n in names if not n.startswith("document_")]
    if not settings["automatic_memory"] and not WRITE_REQUEST.search(message):
        names = [n for n in names if n not in {"memory_save", "memory_forget"}]
    if not settings["weather_enabled"]:
        names = [n for n in names if n != "weather"]
    if not settings["search_enabled"]:
        names = [n for n in names if n != "web_search"]
    return [SPECS[n] for n in names]


def calculate(expression):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 200:
        raise ToolValidationError("Expression must contain 1–200 characters")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 80:
        raise ToolValidationError("Expression is too complex")
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            value = Decimal(str(node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): value = a + b
            elif isinstance(node.op, ast.Sub): value = a - b
            elif isinstance(node.op, ast.Mult): value = a * b
            elif isinstance(node.op, ast.Div): value = a / b
            elif isinstance(node.op, ast.FloorDiv): value = (a / b).to_integral_value(rounding="ROUND_FLOOR")
            elif isinstance(node.op, ast.Mod): value = a - (a / b).to_integral_value(rounding="ROUND_FLOOR") * b
            elif isinstance(node.op, ast.Pow) and b == int(b) and abs(b) <= 100: value = a ** int(b)
            else: raise ToolValidationError("Unsupported arithmetic operator or exponent")
        else:
            raise ToolValidationError("Only numbers and arithmetic operators are allowed")
        if not value.is_finite() or abs(value) > Decimal("1e100"):
            raise ToolValidationError("Arithmetic result exceeds the limit")
        return value
    with localcontext() as context:
        context.prec = 28
        result = visit(tree.body)
        return {"expression": expression, "result": format(result.normalize(), "f"), "precision_digits": 28}


class ToolSession:
    def __init__(self, value, attachments, settings, db, now, lookup, route=None):
        self.value, self.attachments, self.settings = value, attachments, settings
        self.db, self.now, self.lookup = db, now, lookup
        self.route = route or {}
        self.mutations, self.events, self.sources, self.web_sources = [], [], [], []
        self.weather_results, self.weather_city = [], None
        self.search_results = []

    def rows(self, query=""):
        with self.db() as c:
            rows = {r["key"]: dict(r) for r in c.execute("SELECT * FROM memories WHERE expires_at IS NULL OR expires_at>? ORDER BY pinned DESC,updated_at DESC LIMIT 500", (self.now(),))}
        for op in self.mutations:
            if op["action"] == "forget": rows.pop(op["key"], None)
            else: rows[op["key"]] = {"key": op["key"], "content": op["quote"], "category": op["category"]}
        words = set(re.findall(r"\w+", query.casefold()))
        ranked = sorted(rows.values(), key=lambda r: len(words & set(re.findall(r"\w+", (r["key"] + " " + r["content"]).casefold()))), reverse=True)
        return ranked[:8]

    def quote(self, value, followup=False):
        if not isinstance(value, str) or not 1 <= len(value) <= 1000:
            raise MemoryEvidenceError("Copy the user's exact fact as quote, using 1–1000 characters.")
        is_followup = followup and bool(FOLLOWUP_SAVE.fullmatch(self.value.message.strip()))
        candidates = [] if is_followup else [self.value.message]
        if is_followup:
            with self.db() as c:
                candidates += [r[0] for r in c.execute("SELECT user_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 4", (self.value.conversation_id,)) if not NO_SAVE.search(r[0]) and not FOLLOWUP_SAVE.fullmatch(r[0].strip())]
        words = re.split(r"\s+", value.strip())
        if not words or not any(words): raise MemoryEvidenceError("The quote must contain a fact, not just spaces.")
        pattern = r"\s+".join(re.escape(word) for word in words)
        for text in candidates:
            match = re.search(pattern, text, re.I)
            if match and len(match.group(0)) <= 1000:
                return match.group(0)
        raise MemoryEvidenceError("Copy the fact verbatim from a USER message, not an assistant answer. Earlier user messages are allowed only for an explicit follow-up such as save or remember that. Do not invent or paraphrase the quote.")

    async def execute(self, name, args):
        if name not in SPECS or not isinstance(args, dict):
            raise ToolValidationError("Unknown tool or invalid arguments")
        schema = SPECS[name]["function"]["parameters"]
        if set(args) != set(schema["required"]):
            raise ToolValidationError("Tool arguments do not match the schema")
        if name == "memory_search":
            query = args["query"]
            if not isinstance(query, str) or len(query) > 200: raise ToolValidationError("Memory query exceeds limit")
            return {"memories": self.rows(query)}
        if name in {"memory_save", "memory_forget"}:
            key = args["key"]
            if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", key): raise ToolValidationError("Invalid memory key")
            quote = self.quote(args["quote"], followup=name == "memory_save")
            if name == "memory_save" and NO_SAVE.search(self.value.message): raise ToolValidationError("The user requested no memory saving")
            if name == "memory_forget":
                if NO_FORGET.search(self.value.message) or not FORGET_REQUEST.search(self.value.message): raise ToolValidationError("Forgetting requires an explicit current-user request")
                if not any(r["key"] == key for r in self.rows(key)): return {"deleted": False, "key": key}
                self.mutations.append({"action": "forget", "key": key})
                return {"key": key, "deleted": True, "commits_with_answer": True}
            if not self.settings["automatic_memory"] and not WRITE_REQUEST.search(self.value.message): raise ToolValidationError("Automatic memory is disabled")
            if args["category"] not in {"fact", "preference", "project", "temporary"}: raise ToolValidationError("Invalid memory category")
            self.mutations.append({"action": "save", "key": key, "quote": quote, "category": args["category"]})
            return {"key": key, "content": quote, "saved": True, "commits_with_answer": True}
        if name.startswith("document_"):
            if not self.attachments: raise ToolValidationError("No files selected")
            if name == "document_search":
                if not isinstance(args["query"], str) or not 1 <= len(args["query"]) <= 400: raise ToolValidationError("Invalid document query")
                excerpts = documents.retrieve(self.attachments, args["query"])
                result = {"excerpts": excerpts, "coverage": "selected matching excerpts"}
            elif name == "document_overview":
                result = documents.overview(self.attachments)
                excerpts = result["excerpts"]
            else:
                attachment = next((a for a in self.attachments if a["id"] == args["attachment_id"]), None)
                if attachment is None: raise ToolValidationError("File is not selected in this conversation")
                pages = args["pages"]
                if not isinstance(pages, list) or not 1 <= len(pages) <= 4 or any(type(p) is not int or not 1 <= p <= max(1, attachment["pages"]) for p in pages): raise ToolValidationError("Select one to four valid pages")
                selected = {**attachment, "sections": [chunk for chunk in attachment["sections"] if (chunk["page"] or 1) in pages]}
                result = documents.overview([selected], budget=8000)
                excerpts = result["excerpts"]
                result["coverage"] = {"requested_pages": sorted(set(pages)), "represented_pages": sorted({e["page"] or 1 for e in excerpts}), "scope": "selected pages only"}
                result["no_extracted_text"] = not bool(excerpts)
            self.sources.extend({k: e[k] for k in ("attachment_id", "name", "page", "chunk")} for e in excerpts)
            return result
        if name == "calculator": return calculate(args["expression"])
        if name in {"weather", "web_search"}:
            enabled = self.settings["weather_enabled" if name == "weather" else "search_enabled"]
            if not enabled: raise ToolValidationError("This external lookup is disabled")
            field = "city" if name == "weather" else "query"
            text = args[field]
            if not isinstance(text, str) or not 1 <= len(text) <= 300:
                raise ToolValidationError("External lookup input must contain 1–300 characters")
            if name == "web_search":
                routed = self.route.get("web_search_query")
                allowed = isinstance(routed, str) and text.casefold() == routed.casefold()
                if not allowed and text.casefold() not in self.value.message.casefold():
                    raise ToolValidationError("Web search input must come from the current request or a validated search follow-up")
            elif text.casefold() not in self.value.message.casefold():
                raise ToolValidationError("External lookup input must be supplied in the current user request")
            if name == "weather": self.weather_city = text
            response = await self.lookup.post("/" + ("weather" if name == "weather" else "search"), json={field: text})
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict): raise ToolValidationError("Invalid lookup result")
            if name == "weather":
                if not isinstance(result.get("current"), dict): raise ToolValidationError("Invalid weather result")
                self.weather_results.append({"city": text, "result": result})
            else:
                if not isinstance(result.get("results"), list): raise ToolValidationError("Invalid web search result")
                compact = []
                for row in result["results"][:2]:
                    if not isinstance(row, dict): continue
                    compact.append({"title": str(row.get("title", ""))[:160],
                                    "url": str(row.get("url", ""))[:2000],
                                    "snippet": str(row.get("snippet", ""))[:300]})
                result = {**result, "results": compact}
                urls = {row["url"] for row in compact if row["url"]}
                result["sources"] = [source for source in result.get("sources", [])
                                     if isinstance(source, dict) and source.get("url") in urls][:2]
                result["coverage"] = "up to two search snippets only; linked pages were not fetched or verified"
                self.search_results.append({"query": text, "result": result})
            self.web_sources.extend(result.get("sources", []))
            return result
        raise ToolValidationError("Tool is not implemented")

    def commit(self, connection):
        for op in self.mutations:
            if op["action"] == "forget":
                connection.execute("DELETE FROM memories WHERE key=?", (op["key"],))
            else:
                connection.execute("INSERT INTO memories VALUES (?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET content=excluded.content,category=excluded.category,source_conversation_id=excluded.source_conversation_id,expires_at=NULL,updated_at=excluded.updated_at",
                                   (op["key"], op["quote"], op["category"], int(op["key"] in {"user.name", "user.preferred_language"}), self.value.conversation_id, None, self.now()))


def weather_reply(session, metadata):
    """Guard simple live-weather questions; never infer a city or fabricate data.

    This is an answer safeguard, not a replacement for Laya/tool selection.
    Broader comparisons, files and conceptual weather questions keep the model path.
    """
    text = session.value.message.strip()
    direct = len(text) <= 300 and not session.attachments and bool(re.search(
        r"\b(weather|cuaca)\b", text, re.I)) and bool(re.search(
        r"\b(today|now|currently|current|tonight|in|at|sekarang|hari ini|malam ini|di)\b", text, re.I))
    if not direct or re.search(r"\b(compare|explain|code|build|api|html|document|how.*work|bandingkan|jelaskan)\b", text, re.I):
        return None
    if not session.settings['weather_enabled']:
        return "Weather lookups are off. Enable Weather in Tools, then tell me which city to check."
    if not session.weather_results:
        if session.weather_city:
            return f"I couldn't retrieve weather for {session.weather_city}. Check that the lookup service is running and try again."
        return "Which city should I check? I haven't retrieved any weather data yet."
    replies = []
    for item in session.weather_results:
        result = item['result']
        location = result.get('location') or {}
        city = ', '.join(str(location[k]) for k in ('name', 'admin1', 'country') if location.get(k)) or item['city']
        current = result['current']
        units = result.get('current_units') or {}
        temperature = current.get('temperature_2m')
        if type(temperature) not in {int, float} or not math.isfinite(temperature):
            return "The weather lookup returned incomplete data. Please try again."
        unit = str(units.get('temperature_2m', ''))
        reply = f"{city}: {temperature}{unit}"
        feels = current.get('apparent_temperature')
        if type(feels) in {int, float} and math.isfinite(feels):
            reply += f", feels like {feels}{units.get('apparent_temperature', unit)}"
        reply += "."
        timestamp = current.get('time')
        if timestamp: reply += f" Forecast time: {timestamp} ({result.get('timezone') or 'provider local time'})."
        reply += " Source: Open-Meteo. Model-based weather estimate."
        replies.append(reply)
    return '\n'.join(replies)


def web_search_reply(session, metadata=None):
    policy = (metadata or {}).get("route", {}).get("tool_policy")
    if policy == "web_search_needs_query":
        return "What would you like me to search for?"
    if policy not in {"explicit_web_search", "web_search_followup"}:
        return None
    if not session.settings["search_enabled"]:
        return "Web search is off. Enable Search in Tools, then tell me what to look up."
    if not session.search_results:
        return "I couldn't retrieve web search results. Check that the lookup service is running and try again."
    if not any(item["result"].get("results") for item in session.search_results):
        return "I couldn't find any web results for that search."
    return None


def memory_reply(session, metadata=None):
    """Ground explicit save acknowledgements and memory capability in server state."""
    text = session.value.message.strip()
    forgot = [op['key'] for op in session.mutations if op['action'] == 'forget']
    if forgot:
        return "Forgot the saved " + ("name" if forgot[0] == 'user.name' else "location" if forgot[0] == 'user.location' else "fact") + "."
    if (metadata or {}).get('tool_planning_mode') == 'natural_memory' and session.events and session.events[-1]['name'] == 'memory_forget':
        return "I don't have that fact saved."
    memory_save_turn = (metadata or {}).get("route", {}).get("tool_family") == "memory" and any(event["name"] == "memory_save" for event in session.events)
    explicit_save = bool(FIRSTHAND_SAVE.search(text)) and not NO_SAVE.search(text)
    if FOLLOWUP_SAVE.fullmatch(text) or memory_save_turn or explicit_save:
        saved = [op["quote"] for op in session.mutations if op["action"] == "save"]
        if saved:
            return "Saved: " + "; ".join(dict.fromkeys(saved)) + ". These facts will be available in future chats on this Keno server."
        return "I couldn't save a fact. Please repeat the detail you want me to remember. It hasn't been saved for future chats."
    if len(text) <= 200 and re.search(r"\b(?:can|will|do)\s+(?:you|u)\s+(?:remember|have memory)\b", text, re.I) and re.search(r"\b(me|chats?|conversations?|memory)\b", text, re.I):
        mode = "Automatic memory is enabled." if session.settings['automatic_memory'] else "Automatic memory is off; ask me explicitly to save a fact."
        return "Yes. Facts saved in Memories persist across chats on this Keno server. " + mode + " You can review, edit or delete them in Memories. This does not mean I retain every detail from every chat."
    return None
