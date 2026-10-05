"""Bounded removal of a question-restating how-to preamble, without inference."""
import re

from .documents import QUERY_STOP_WORDS


class OpeningFilter:
    LIMIT = 512

    def __init__(self, request, enabled=True):
        self.active = enabled and bool(re.match(r'^\s*how\s+(?:can|do|does|to)\b', request, re.I))
        if re.search(r'\b(?:verbatim|quote|translate|translation|json|code)\b', request, re.I):
            self.active = False
        self.words = set(re.findall(r'\w+', request.casefold())) - QUERY_STOP_WORDS - {'can', 'do', 'does'}
        self.buffer = ''
        self.removed = False

    def push(self, text, final=False):
        if not self.active:
            return text
        self.buffer += text
        stripped = self.buffer.lstrip()
        # Only a possible "To ... follow these steps:" opening needs buffering.
        if stripped and not ('to '.startswith(stripped.casefold()) or stripped.casefold().startswith('to ')):
            return self.release()
        if '\n' in stripped:
            line, rest = stripped.split('\n', 1)
            match = re.fullmatch(r'To\s+(.{1,400}?),?\s+follow\s+(?:these|the)\s+steps\s*:', line.strip(), re.I)
            if match and rest.strip():
                topic = set(re.findall(r'\w+', match.group(1).casefold())) - QUERY_STOP_WORDS
                # Remove only a repeated topic, not a new condition or warning.
                if len(topic) >= 2 and topic.issubset(self.words):
                    self.buffer = rest.lstrip()
                    self.removed = True
                return self.release()
            if not match:
                return self.release()
        if final or len(self.buffer) >= self.LIMIT:
            return self.release()
        return ''

    def release(self):
        text, self.buffer, self.active = self.buffer, '', False
        return text


class ClosingFilter:
    """Hold only a potential stock closing at a line boundary, not the answer."""
    PREFIXES = ("let me know", "if you're still having trouble")
    STOCK = re.compile(r"(?:Let me know if you (?:need (?:any )?(?:further assistance|more help)|have (?:any )?(?:other |further )?questions)|If you're still having trouble, let me know and I can guide you further)[.!]?", re.I)

    def __init__(self, enabled=True):
        self.enabled, self.start, self.buffer = enabled, True, ''
        self.content_seen, self.removed = False, False

    def push(self, text, final=False):
        if not self.enabled:
            return text
        output = ''
        for char in text:
            if self.start and self.content_seen:
                self.buffer += char
                candidate = self.buffer.strip().casefold()
                possible = not candidate or any(p.startswith(candidate) or candidate.startswith(p) for p in self.PREFIXES)
                if possible and (char != '\n' or self.STOCK.fullmatch(self.buffer.strip())) and len(self.buffer) <= 256:
                    continue
                output += self.buffer
                self.content_seen |= bool(self.buffer.strip())
                self.buffer = ''
                self.start = char == '\n'
            else:
                output += char
                self.content_seen |= bool(char.strip())
                self.start = char == '\n'
        if final and self.buffer:
            if self.STOCK.fullmatch(self.buffer.strip()):
                self.removed = True
            else:
                output += self.buffer
            self.buffer = ''
        return output


class ResponseFilter:
    def __init__(self, request, enabled=True):
        self.opening = OpeningFilter(request, enabled)
        safe = enabled and not re.search(r'\b(?:verbatim|quote|translate|translation|json|code|html|python)\b', request, re.I)
        self.closing = ClosingFilter(safe)

    @property
    def removed(self):
        return self.opening.removed

    def push(self, text, final=False):
        return self.closing.push(self.opening.push(text, final), final)
