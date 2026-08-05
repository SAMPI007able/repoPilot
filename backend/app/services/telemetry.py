import os
from typing import Any


class Telemetry:
    def __init__(self) -> None:
        self._api_key = os.getenv("POSTHOG_API_KEY", "").strip()
        self._enabled = bool(self._api_key)

    def capture(self, distinct_id: str, event_name: str, properties: dict[str, Any] | None = None) -> None:
        if not self._enabled or not distinct_id:
            return

        try:
            from posthog import Posthog
        except Exception:
            return

        try:
            client = Posthog(project_api_key=self._api_key, host=os.getenv("POSTHOG_HOST", "https://us.i.posthog.com"))
            client.capture(distinct_id, event_name, properties=properties or {})
        except Exception:
            return

    def identify(self, distinct_id: str, properties: dict[str, Any] | None = None) -> None:
        if not self._enabled or not distinct_id:
            return

        try:
            from posthog import Posthog
        except Exception:
            return

        try:
            client = Posthog(project_api_key=self._api_key, host=os.getenv("POSTHOG_HOST", "https://us.i.posthog.com"))
            client.identify(distinct_id, properties=properties or {})
        except Exception:
            return
