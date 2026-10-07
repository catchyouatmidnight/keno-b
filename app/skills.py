"""Versioned user-authored reusable workflows over Keno's existing allowlisted tools."""
import json
import re
import time
from dataclasses import dataclass

MAX_MARKDOWN = 20_000
MAX_INSTRUCTIONS = 8_000
MAX_TRIGGERS = 24
MAX_TOOLS = 12
RISKS = {"low", "medium", "high"}
STOP = {"a","an","the","to","for","of","and","or","please","can","you","me","my","i","this","that","it"}

class SkillError(ValueError):
    pass

def _slug(value):
    value=re.sub(r"[^a-z0-9]+","-",str(value).casefold()).strip("-")
    return value[:64] or "skill"

def _norm(value):
    return " ".join(re.findall(r"[\w'-]+",str(value).casefold()))

def _words(value):
    return {w for w in re.findall(r"[\w'-]+",str(value).casefold()) if len(w)>1 and w not in STOP}

def _scalar(value):
    value=value.strip()
    if len(value)>=2 and value[0]==value[-1] and value[0] in {"'",'"'}:
        return value[1:-1]
    return value

def _frontmatter(markdown):
    text=markdown.replace("\r\n","\n").strip()
    if not text.startswith("---\n"):
        return {},text
    end=text.find("\n---\n",4)
    if end<0:
        raise SkillError("Skill front matter must end with ---")
    header,body=text[4:end],text[end+5:].strip()
    data,current={},None
    for raw in header.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.lstrip().startswith("- "):
            if current is None:
                raise SkillError("List item has no front-matter key")
            data.setdefault(current,[]).append(_scalar(raw.lstrip()[2:]))
            continue
        if ":" not in raw:
            raise SkillError("Front-matter entries must use key: value")
        key,value=raw.split(":",1); key=key.strip().casefold().replace("-","_"); value=value.strip(); current=key
        if not value:
            data[key]=[]
        elif value.startswith("[") and value.endswith("]"):
            data[key]=[_scalar(item) for item in value[1:-1].split(",") if item.strip()]
        else:
            data[key]=_scalar(value)
    return data,body

def parse(markdown, *, skill_id=None):
    if not isinstance(markdown,str) or not 1<=len(markdown)<=MAX_MARKDOWN:
        raise SkillError(f"Skill Markdown must contain 1–{MAX_MARKDOWN} characters")
    front,body=_frontmatter(markdown)
    heading=re.search(r"^#\s+(.+?)\s*$",body,re.M)
    name=str(front.get("name") or (heading.group(1) if heading else "")).strip()
    if not name or len(name)>100:
        raise SkillError("Skill name is required and must be at most 100 characters")
    description=str(front.get("description") or "").strip()
    if not description:
        paragraphs=[p.strip() for p in re.split(r"\n\s*\n",body) if p.strip() and not p.lstrip().startswith("#")]
        description=re.sub(r"\s+"," ",paragraphs[0])[:300] if paragraphs else name
    triggers=front.get("triggers") or front.get("trigger") or [name]
    if isinstance(triggers,str): triggers=[triggers]
    triggers=[str(v).strip() for v in triggers if str(v).strip()]
    triggers=list(dict.fromkeys(triggers))[:MAX_TRIGGERS]
    if not triggers: triggers=[name]
    required=front.get("requires") or front.get("required_tools") or front.get("tools") or []
    if isinstance(required,str): required=[required]
    required=[str(v).strip() for v in required if str(v).strip()]
    required=list(dict.fromkeys(required))[:MAX_TOOLS]
    risk=str(front.get("risk") or "low").strip().casefold()
    if risk not in RISKS: raise SkillError("risk must be low, medium or high")
    enabled=str(front.get("enabled","true")).casefold() not in {"false","0","no","off"}
    instructions=body.strip()
    if not instructions or len(instructions)>MAX_INSTRUCTIONS:
        raise SkillError(f"Skill instructions must contain 1–{MAX_INSTRUCTIONS} characters")
    return {"id":skill_id or _slug(name),"name":name,"description":description[:500],"triggers":triggers,
            "required_tools":required,"risk":risk,"enabled":enabled,"instructions":instructions,
            "source_markdown":markdown}

def validate_tools(skill, known_tools):
    unknown=sorted(set(skill["required_tools"])-set(known_tools))
    forbidden=[name for name in skill["required_tools"] if name.startswith(("pc.","phone.","device."))]
    if forbidden:
        raise SkillError("Device/PC capabilities are not enabled in this Keno build")
    if unknown:
        raise SkillError("Unknown required tool(s): "+", ".join(unknown))
    writes={"memory_save","memory_forget","memory_save_result"}
    if set(skill["required_tools"]) & writes and skill["risk"]!="high":
        raise SkillError("Skills that can change persistent memory must use risk: high")
    return skill

def _row(row):
    if row is None:return None
    value=dict(row)
    value["enabled"]=bool(value["enabled"])
    value["triggers"]=json.loads(value["triggers"])
    value["required_tools"]=json.loads(value["required_tools"])
    return value

def list_skills(connection):
    return [_row(r) for r in connection.execute("SELECT * FROM skills ORDER BY enabled DESC,updated_at DESC,name")]

def get(connection, skill_id):
    return _row(connection.execute("SELECT * FROM skills WHERE id=?",(skill_id,)).fetchone())

def save(connection, skill, stamp):
    current=connection.execute("SELECT * FROM skills WHERE id=?",(skill["id"],)).fetchone()
    version=(current["version"]+1) if current else 1
    created_at=current["created_at"] if current else stamp
    use_count=current["use_count"] if current else 0
    last_used_at=current["last_used_at"] if current else None
    if current:
        connection.execute("""INSERT OR REPLACE INTO skill_versions
          (skill_id,version,name,description,enabled,risk,triggers,required_tools,instructions,source_markdown,archived_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
          (current["id"],current["version"],current["name"],current["description"],current["enabled"],current["risk"],
           current["triggers"],current["required_tools"],current["instructions"],current["source_markdown"],stamp))
    connection.execute("""INSERT INTO skills
      (id,name,description,enabled,version,risk,triggers,required_tools,instructions,source_markdown,created_at,updated_at,use_count,last_used_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,enabled=excluded.enabled,
      version=excluded.version,risk=excluded.risk,triggers=excluded.triggers,required_tools=excluded.required_tools,
      instructions=excluded.instructions,source_markdown=excluded.source_markdown,updated_at=excluded.updated_at""",
      (skill["id"],skill["name"],skill["description"],int(skill["enabled"]),version,skill["risk"],json.dumps(skill["triggers"]),
       json.dumps(skill["required_tools"]),skill["instructions"],skill["source_markdown"],created_at,stamp,use_count,last_used_at))
    return get(connection,skill["id"])

def history(connection, skill_id):
    return [_row(r) for r in connection.execute("""SELECT skill_id id,name,description,enabled,version,risk,triggers,required_tools,
      instructions,source_markdown,archived_at updated_at,0 use_count,NULL last_used_at,archived_at created_at
      FROM skill_versions WHERE skill_id=? ORDER BY version DESC""",(skill_id,))]

def restore(connection, skill_id, version, stamp):
    row=connection.execute("SELECT * FROM skill_versions WHERE skill_id=? AND version=?",(skill_id,version)).fetchone()
    if row is None: raise SkillError("Skill version not found")
    skill={"id":skill_id,"name":row["name"],"description":row["description"],"enabled":bool(row["enabled"]),"risk":row["risk"],
           "triggers":json.loads(row["triggers"]),"required_tools":json.loads(row["required_tools"]),
           "instructions":row["instructions"],"source_markdown":row["source_markdown"]}
    return save(connection,skill,stamp)

def set_enabled(connection, skill_id, enabled, stamp):
    if not connection.execute("UPDATE skills SET enabled=?,updated_at=? WHERE id=?",(int(enabled),stamp,skill_id)).rowcount:
        raise SkillError("Skill not found")
    return get(connection,skill_id)

def record_use(connection, skill_id, stamp):
    connection.execute("UPDATE skills SET use_count=use_count+1,last_used_at=? WHERE id=?",(stamp,skill_id))

def _score(query, skill):
    q=_norm(query); qw=_words(query)
    best=0.0; reason=""
    for trigger in skill["triggers"]:
        t=_norm(trigger); tw=_words(trigger)
        if not t: continue
        if q==t: return 1.0,"exact trigger"
        if len(t)>=4 and re.search(r"(?<!\w)"+re.escape(t)+r"(?!\w)",q):
            score=.93 if len(tw)>=2 else .82
        elif tw and qw:
            overlap=len(tw&qw); coverage=overlap/max(1,len(tw)); precision=overlap/max(1,len(qw))
            score=.68*coverage+.22*precision
            if overlap>=2:score+=.06
        else:score=0
        if score>best:best,reason=score,"trigger similarity"
    meta=_words(skill["name"]+" "+skill["description"])
    if meta and qw:
        overlap=len(meta&qw)
        meta_score=.45*(overlap/max(1,len(qw)))+.2*(overlap/max(1,len(meta)))
        if meta_score>best:best,reason=meta_score,"name/description similarity"
    return min(1.0,best),reason

def match(connection, query, threshold=.68):
    started=time.monotonic(); ranked=[]
    for row in list_skills(connection):
        if not row["enabled"]:continue
        score,reason=_score(query,row)
        if score>0: ranked.append((score,reason,row))
    ranked.sort(key=lambda item:(item[0],item[2]["version"],item[2]["updated_at"]),reverse=True)
    if not ranked or ranked[0][0]<threshold:
        return None,round(time.monotonic()-started,6),[{"id":r["id"],"score":round(s,3)} for s,_,r in ranked[:3]]
    score,reason,skill=ranked[0]
    explicit=bool(re.fullmatch(r"\s*run\s+skill\s+"+re.escape(_norm(skill["name"]))+r"\s*[.!]?\s*",_norm(query)))
    return {**skill,"score":round(score,3),"match_reason":reason,"explicit_invocation":explicit},round(time.monotonic()-started,6),[{"id":r["id"],"score":round(s,3)} for s,_,r in ranked[:3]]
