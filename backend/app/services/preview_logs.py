from app.persistence.artifact_store import ArtifactStore
from app.services.secret_redactor import SecretRedactor


class PreviewLogService:
    MAX_BYTES = 1_000_000

    def __init__(self, artifact_store: ArtifactStore, redactor: SecretRedactor | None = None) -> None:
        self.artifact_store = artifact_store
        self.redactor = redactor or SecretRedactor()

    @staticmethod
    def key(preview_id: str) -> str:
        return f"preview-logs/{preview_id}/console.log"

    def append(self, preview_id: str, text: str, sensitive_values: list[str] | None = None) -> None:
        key = self.key(preview_id)
        try:
            current = self.artifact_store.get(key)
        except (FileNotFoundError, KeyError):
            current = b""
        safe_text = self.redactor.redact(text)
        for value in sensitive_values or []:
            if value:
                safe_text = safe_text.replace(value, self.redactor.REDACTION)
        addition = safe_text.encode("utf-8", errors="replace")
        contents = (current + addition)[-self.MAX_BYTES:]
        self.artifact_store.put(key, contents, "text/plain; charset=utf-8")

    def read(self, preview_id: str) -> tuple[str, bool]:
        try:
            contents = self.artifact_store.get(self.key(preview_id))
        except (FileNotFoundError, KeyError):
            return "", False
        return contents.decode("utf-8", errors="replace"), len(contents) >= self.MAX_BYTES
