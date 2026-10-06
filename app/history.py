"""Bounded extractive conversation notes and lexical retrieval; no extra inference."""
import json
import re

from .documents import QUERY_STOP_WORDS
from . import context_policy

RECENT_TURNS = 4


def reply_language(connection, conversation_id, query):
    prior=connection.execute("SELECT user_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 1",(conversation_id,)).fetchone()
    chosen=context_policy.language_choice(query,prior[0] if prior else '')
    saved=connection.execute("SELECT value FROM settings WHERE key=?",('conversation_language:'+conversation_id,)).fetchone()
    if chosen:return chosen
    if saved:return json.loads(saved[0])
    # Recover explicit choices from chats made before this preference existed.
    rows=connection.execute("SELECT user_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 200",(conversation_id,)).fetchall()
    language=None;previous=''
    for row in reversed(rows):
        language=context_policy.language_choice(row[0],previous) or language
        previous=row[0]
    if language:
        connection.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('conversation_language:'+conversation_id,json.dumps(language)))
    return language


def refresh(connection, conversation_id, timestamp):
    latest=connection.execute("SELECT user_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 2",(conversation_id,)).fetchall()
    chosen=context_policy.language_choice(latest[0][0],latest[1][0] if len(latest)>1 else '') if latest else None
    if chosen:
        connection.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('conversation_language:'+conversation_id,json.dumps(chosen)))
    rows = connection.execute("SELECT user_text,assistant_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 24 OFFSET ?", (conversation_id, RECENT_TURNS)).fetchall()
    notes = [{"user_excerpt": r[0][:120], "assistant_excerpt": (r[1] or "")[:120]} for r in reversed(rows[:10])]
    text = json.dumps(notes, ensure_ascii=False)
    connection.execute("INSERT INTO conversation_summaries VALUES (?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET notes=excluded.notes,updated_at=excluded.updated_at", (conversation_id, text, timestamp))


def context(connection, conversation_id, query, recent_limit=RECENT_TURNS, retrieve_older=True):
    recent = list(connection.execute("SELECT user_text,assistant_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT ?", (conversation_id, recent_limit)))
    if not retrieve_older:
        return list(reversed(recent)), {"compact_notes": [], "relevant_older_excerpts": []}
    row = connection.execute("SELECT notes FROM conversation_summaries WHERE conversation_id=?", (conversation_id,)).fetchone()
    words = set(re.findall(r"\w+", query.casefold())) - QUERY_STOP_WORDS
    older = connection.execute("SELECT user_text,assistant_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 200 OFFSET ?", (conversation_id, RECENT_TURNS)).fetchall()
    scored = [(len(words & set(re.findall(r"\w+", r[0].casefold()))), r) for r in older]
    matches = [{"user_excerpt": r[0][:300], "assistant_excerpt": (r[1] or "")[:500]} for score, r in sorted(scored, key=lambda item: item[0], reverse=True)[:2] if score >= 2]
    return list(reversed(recent)), {"compact_notes": json.loads(row[0])[:4] if row and re.search(r"\b(?:earlier|previously|last time|before|sebelumnya|tadi)\b",query,re.I) else [], "relevant_older_excerpts": matches}
