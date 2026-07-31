import re


class SecretRedactor:
    REDACTION = "[REDACTED]"
    PATTERNS = (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret|private[_-]?key)"
            r"\s*[:=]\s*([^\s,;]+)"
        ),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*"),
        re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@"),
    )

    def redact(self, value: str) -> str:
        redacted = self.PATTERNS[0].sub(
            lambda match: f"{match.group(1)}={self.REDACTION}",
            value,
        )
        redacted = self.PATTERNS[1].sub(f"Bearer {self.REDACTION}", redacted)
        return self.PATTERNS[2].sub(rf"\1{self.REDACTION}@", redacted)
