"""Read-only calendar calculations from the server clock; no inference or network."""
import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FOLLOWUP = re.compile(r'\s*(?:do that|do it|calculate (?:it|that)|yes(?: please)?|go ahead|hitung(?: itu)?|lakukan itu)\s*[.!?]*',re.I)
COUNTDOWN = re.compile(r'\s*(?:(?:how many days(?: are)?(?: left)?|days(?: left)?)\s+(?:left\s+)?(?:until|till|to|before)|berapa hari(?: lagi)?\s+(?:sampai|hingga|menuju))\s+(\d{4}(?:-\d{2}-\d{2})?)\s*[.!?]*',re.I)
TODAY = re.compile(r"\s*(?:what(?:'s| is) (?:the )?(?:date|day)(?: today)?|what is today(?:'s date)?|tanggal berapa(?: hari ini)?)\s*[.!?]*",re.I)


def current_clock():
    name=os.environ.get('KENO_TIMEZONE','UTC')
    try:zone=ZoneInfo(name)
    except ZoneInfoNotFoundError:raise ValueError('KENO_TIMEZONE must be a valid IANA timezone, for example Asia/Jakarta')
    instant=datetime.now(zone)
    return {'date':instant.date().isoformat(),'timezone':name}


def calculate(query,prior=(),clock=None):
    source=query
    if FOLLOWUP.fullmatch(query):
        # Only resolve the adjacent user request; do not guess from arbitrary old topics
        # or from an assistant's possibly incorrect response.
        for text in prior[:2]:
            if COUNTDOWN.fullmatch(text) or TODAY.fullmatch(text):source=text;break
            if not FOLLOWUP.fullmatch(text):return None
        else:return None
    match=COUNTDOWN.fullmatch(source)
    if not match and not TODAY.fullmatch(source):return None
    clock=clock or current_clock()
    result={'clock':clock,'source_request':source,'language':'Indonesian' if re.match(r'\s*(?:berapa|tanggal)',source,re.I) else None}
    if match:
        target=match[1]+'-01-01' if len(match[1])==4 else match[1]
        try:target_date=date.fromisoformat(target)
        except ValueError:return {**result,'error':'invalid_date','target':target}
        result.update(target=target_date.isoformat(),days=(target_date-date.fromisoformat(clock['date'])).days,assumed_year_start=len(match[1])==4)
    return result


def render(result,language=None):
    indonesian=(language or result['language'])=='Indonesian'
    clock=result['clock'];today=clock['date'];zone=clock['timezone']
    if result.get('error'):
        return f"{result['target']} bukan tanggal kalender yang valid." if indonesian else f"{result['target']} is not a valid calendar date."
    if 'days' not in result:return f"Hari ini {today} ({zone})." if indonesian else f"Today is {today} ({zone})."
    days=result['days'];target=result['target']
    if indonesian:
        return f"{days:,} hari lagi sampai {target}, dihitung dari {today} ({zone})." if days>=0 else f"{target} sudah lewat {-days:,} hari, dihitung dari {today} ({zone})."
    return f"{days:,} days until {target}, counting from {today} ({zone})." if days>=0 else f"{target} was {-days:,} days ago, counting from {today} ({zone})."
