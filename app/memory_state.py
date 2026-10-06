"""Versioned memory correction history without extra inference work."""

def _normalized(value):
    return " ".join(str(value or "").casefold().split())


def archive_if_changed(connection, key, new_content, at, request_id=None, reason="superseded"):
    row = connection.execute(
        """SELECT m.*, COALESCE(mm.importance,0.5) importance, COALESCE(mm.confidence,0.8) confidence
           FROM memories m LEFT JOIN memory_meta mm ON mm.key=m.key WHERE m.key=?""",
        (key,),
    ).fetchone()
    if row is None or _normalized(row["content"]) == _normalized(new_content):
        return None
    connection.execute(
        """INSERT INTO memory_history
           (memory_key,content,category,pinned,source_conversation_id,expires_at,importance,confidence,
            replaced_at,replacement_request_id,reason)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (row["key"], row["content"], row["category"], row["pinned"], row["source_conversation_id"],
         row["expires_at"], float(row["importance"]), float(row["confidence"]), at, request_id, reason),
    )
    return dict(row)


def clear_history(connection, key):
    connection.execute("DELETE FROM memory_history WHERE memory_key=?", (key,))


def history(connection, key, limit=50):
    rows = connection.execute(
        """SELECT id,memory_key,content,category,pinned,source_conversation_id,expires_at,
                  importance,confidence,replaced_at,replacement_request_id,reason
           FROM memory_history WHERE memory_key=? ORDER BY id DESC LIMIT ?""",
        (key, limit),
    ).fetchall()
    return [dict(row) for row in rows]
