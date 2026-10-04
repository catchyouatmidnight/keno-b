"""Bounded extractive conversation notes and lexical retrieval; no extra inference."""
import json
import re

from .documents import QUERY_STOP_WORDS

RECENT_TURNS = 4


def refresh(connection, conversation_id, timestamp):
    rows = connection.execute("SELECT user_text,assistant_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 24 OFFSET ?", (conversation_id, RECENT_TURNS)).fetchall()
    notes = [{"user_excerpt": r[0][:120], "assistant_excerpt": (r[1] or "")[:120]} for r in reversed(rows[:10])]
    text = json.dumps(notes, ensure_ascii=False)
    connection.execute("INSERT INTO conversation_summaries VALUES (?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET notes=excluded.notes,updated_at=excluded.updated_at", (conversation_id, text, timestamp))


def context(connection, conversation_id, query):
    recent = list(connection.execute("SELECT user_text,assistant_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT ?", (conversation_id, RECENT_TURNS)))
    row = connection.execute("SELECT notes FROM conversation_summaries WHERE conversation_id=?", (conversation_id,)).fetchone()
    words = set(re.findall(r"\w+", query.casefold())) - QUERY_STOP_WORDS
    older = connection.execute("SELECT user_text,assistant_text FROM turns WHERE conversation_id=? AND status='complete' ORDER BY rowid DESC LIMIT 200 OFFSET ?", (conversation_id, RECENT_TURNS)).fetchall()
    scored = [(len(words & set(re.findall(r"\w+", (r[0] + " " + (r[1] or "")).casefold()))), r) for r in older]
    matches = [{"user_excerpt": r[0][:300], "assistant_excerpt": (r[1] or "")[:500]} for score, r in sorted(scored, key=lambda item: item[0], reverse=True)[:2] if score > 0]
    return list(reversed(recent)), {"compact_notes": json.loads(row[0]) if row else [], "relevant_older_excerpts": matches}
