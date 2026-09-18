"""Lọc output trước khi ghi artifact; không thu thập secret để gửi server."""
import re


def safe_label(value: str) -> str:
    return re.sub(r"[^\w .-]", "_", str(value))[:100]


class Redactor:
    def __init__(self):
        self._values = set()

    def register(self, *values):
        self._values.update(str(v) for v in values if v)

    def text(self, value):
        text = str(value)
        for secret in sorted(self._values, key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)((?:password|token|otp|api[_-]?key|cookie)\s*[=:]\s*)[^\s,;]+",
                      r"\1[REDACTED]", text)
        return text

    def value(self, value):
        if isinstance(value, dict):
            return {self.text(k): self.value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.value(v) for v in value]
        return self.text(value) if isinstance(value, str) else value
