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
