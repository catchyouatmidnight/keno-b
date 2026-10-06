"""Cheap context selection; no extra model call or fabricated answer."""
import re
from .documents import QUERY_STOP_WORDS

FOLLOWUP=re.compile(r'\s*(?:which is|who is that|who exactly|what about that|tell me more|expand on that|explain further|continue|repeat(?: that)?(?: again)?|say that again|make it shorter|shorter|translate that|rewrite that|in Indonesian|in English|yea switch|yeah switch|why|how so|yes|yeah|yea|yep|ok|okay|lanjut|ulangi|kenapa)\s*[?.!]*',re.I)
ROUTINE=re.compile(r'\s*(?:hello|hi|hey|halo|hai|testing|test|how are (?:you|u)|apa kabar|thanks|thank you|terima kasih)\s*[?.!]*',re.I)
FOLLOWUP_PREFIX=re.compile(r'^\s*(?:and|what about|how about|also|then|but|dan|kalau|lalu)\b',re.I)
PAST=re.compile(r'\b(?:earlier|previously|last time|previous conversation|old chat|before|sebelumnya|tadi)\b',re.I)
STOP=QUERY_STOP_WORDS|{'hello','hi','hey','testing','test','can','do','does','u','please','help'}


def words(text):return set(re.findall(r'\w+',text.casefold()))-STOP


def plan(query,prior,attachments=False):
    if attachments:return {'mode':'documents','recent_limit':4,'older':True}
    if FOLLOWUP.fullmatch(query):return {'mode':'followup','recent_limit':4,'older':bool(PAST.search(query))}
    if FOLLOWUP_PREFIX.search(query):return {'mode':'followup','recent_limit':2,'older':bool(PAST.search(query))}
    if PAST.search(query):return {'mode':'recall','recent_limit':4,'older':True}
    if ROUTINE.fullmatch(query):return {'mode':'routine','recent_limit':0,'older':False}
    # Only USER requests establish topical relevance; do not retrieve model hallucinations.
    relevant=any(len(words(query)&words(t))>=2 for t in prior)
    personal=bool(re.search(r'\b(?:my|me|remember|save|forget|nama saya|ingat|simpan)\b',query,re.I))
    return {'mode':'related' if relevant or personal else 'standalone','recent_limit':2 if relevant or personal else 0,'older':False}


def language_choice(query,previous=''):
    names={'indonesian':'Indonesian','indonesia':'Indonesian','english':'English','inggris':'English'}
    command=re.fullmatch(r'\s*(?:please\s+)?(?:switch(?:\s+(?:to|back to))?|speak|use|in|reply in|respond in|answer in|jawab(?: dalam)?|pakai|gunakan|ganti(?: ke)?)\s+(?:bahasa\s+)?(indonesian|indonesia|english|inggris)\s*(?:please)?[.!]?\s*',query,re.I)
    if command:return names[command[1].casefold()]
    if re.fullmatch(r'\s*(?:yes|yeah|yea|yep|ok|okay|iya|ya)[, ]+switch[.!]?\s*',query,re.I):
        capability=re.fullmatch(r'\s*(?:can|could)\s+(?:you|u)\s+speak\s+(?:bahasa\s+)?(indonesian|indonesia|english|inggris)[?.!]?\s*',previous,re.I)
        if capability:return names[capability[1].casefold()]
    return None
