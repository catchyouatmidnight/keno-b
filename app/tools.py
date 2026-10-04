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
FORGET_REQUEST = re.compile(r"\b(forget|delete|remove|hapus|lupakan)\b", re.I)
NO_SAVE = re.compile(r"(?:don't|do not|never)\s+(?:save|remember)|jangan\s+(?:simpan|ingat)", re.I)


def spec(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False}}}


STRING = {"type": "string"}
SPECS = {
    "memory_search": spec("memory_search", "Find saved facts and their keys. Use before correcting an unknown key.",
                          {"query": STRING}, ["query"]),
    "memory_save": spec("memory_save", "Remember a lasting firsthand fact or preference stated by the user. quote must be copied verbatim from the latest user message, never a file or assistant answer. Reuse the existing key for corrections. Prefer user.name, user.location, user.preferred_language for those facts.",
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
    "web_search": spec("web_search", "Search the web for an explicit current user request. query must be a verbatim span of the current request; never send file contents, memories or chat history. Returns snippets and links, not a full-page review.",
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
        raise ValueError("Expression must contain 1–200 characters")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 80:
        raise ValueError("Expression is too complex")
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
            else: raise ValueError("Unsupported arithmetic operator or exponent")
        else:
            raise ValueError("Only numbers and arithmetic operators are allowed")
        if not value.is_finite() or abs(value) > Decimal("1e100"):
            raise ValueError("Arithmetic result exceeds the limit")
        return value
    with localcontext() as context:
        context.prec = 28
        result = visit(tree.body)
        return {"expression": expression, "result": format(result.normalize(), "f"), "precision_digits": 28}


class ToolSession:
    def __init__(self, value, attachments, settings, db, now, lookup):
        self.value, self.attachments, self.settings = value, attachments, settings
        self.db, self.now, self.lookup = db, now, lookup
        self.mutations, self.events, self.sources, self.web_sources = [], [], [], []
        self.weather_results, self.weather_city = [], None

    def rows(self, query=""):
        with self.db() as c:
            rows = {r["key"]: dict(r) for r in c.execute("SELECT * FROM memories WHERE expires_at IS NULL OR expires_at>? ORDER BY pinned DESC,updated_at DESC LIMIT 500", (self.now(),))}
        for op in self.mutations:
            if op["action"] == "forget": rows.pop(op["key"], None)
            else: rows[op["key"]] = {"key": op["key"], "content": op["quote"], "category": op["category"]}
        words = set(re.findall(r"\w+", query.casefold()))
        ranked = sorted(rows.values(), key=lambda r: len(words & set(re.findall(r"\w+", (r["key"] + " " + r["content"]).casefold()))), reverse=True)
        return ranked[:8]

    def quote(self, value):
        if not isinstance(value, str) or not 1 <= len(value) <= 1000 or value not in self.value.message:
            raise ValueError("Evidence must be a verbatim span of the current user message")
        return value

    async def execute(self, name, args):
        if name not in SPECS or not isinstance(args, dict):
            raise ValueError("Unknown tool or invalid arguments")
        schema = SPECS[name]["function"]["parameters"]
        if set(args) != set(schema["required"]):
            raise ValueError("Tool arguments do not match the schema")
        if name == "memory_search":
            query = args["query"]
            if not isinstance(query, str) or len(query) > 200: raise ValueError("Memory query exceeds limit")
            return {"memories": self.rows(query)}
        if name in {"memory_save", "memory_forget"}:
            key = args["key"]
            if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", key): raise ValueError("Invalid memory key")
            quote = self.quote(args["quote"])
            if name == "memory_save" and NO_SAVE.search(self.value.message): raise ValueError("The user requested no memory saving")
            if name == "memory_forget":
                if not FORGET_REQUEST.search(self.value.message): raise ValueError("Forgetting requires an explicit current-user request")
                if not any(r["key"] == key for r in self.rows(key)): return {"deleted": False, "key": key}
                self.mutations.append({"action": "forget", "key": key})
                return {"key": key, "deleted": True, "commits_with_answer": True}
            if not self.settings["automatic_memory"] and not WRITE_REQUEST.search(self.value.message): raise ValueError("Automatic memory is disabled")
            if args["category"] not in {"fact", "preference", "project", "temporary"}: raise ValueError("Invalid memory category")
            self.mutations.append({"action": "save", "key": key, "quote": quote, "category": args["category"]})
            return {"key": key, "content": quote, "saved": True, "commits_with_answer": True}
        if name.startswith("document_"):
            if not self.attachments: raise ValueError("No files selected")
            if name == "document_search":
                if not isinstance(args["query"], str) or not 1 <= len(args["query"]) <= 400: raise ValueError("Invalid document query")
                excerpts = documents.retrieve(self.attachments, args["query"])
                result = {"excerpts": excerpts, "coverage": "selected matching excerpts"}
            elif name == "document_overview":
                result = documents.overview(self.attachments)
                excerpts = result["excerpts"]
            else:
                attachment = next((a for a in self.attachments if a["id"] == args["attachment_id"]), None)
                if attachment is None: raise ValueError("File is not selected in this conversation")
                pages = args["pages"]
                if not isinstance(pages, list) or not 1 <= len(pages) <= 4 or any(type(p) is not int or not 1 <= p <= max(1, attachment["pages"]) for p in pages): raise ValueError("Select one to four valid pages")
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
            if not enabled: raise ValueError("This external lookup is disabled")
            field = "city" if name == "weather" else "query"
            text = args[field]
            if not isinstance(text, str) or not 1 <= len(text) <= 300 or text.casefold() not in self.value.message.casefold():
                raise ValueError("External lookup input must be supplied in the current user request")
            if name == "weather": self.weather_city = text
            response = await self.lookup.post("/" + ("weather" if name == "weather" else "search"), json={field: text})
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict): raise ValueError("Invalid lookup result")
            if name == "weather":
                if not isinstance(result.get("current"), dict): raise ValueError("Invalid weather result")
                self.weather_results.append({"city": text, "result": result})
            self.web_sources.extend(result.get("sources", []))
            return result
        raise ValueError("Tool is not implemented")

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
