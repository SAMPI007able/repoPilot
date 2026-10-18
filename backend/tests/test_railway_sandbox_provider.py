import json
import os
import unittest
from unittest.mock import MagicMock, patch

from app.models.preview_models import PreviewStatus
from app.services.railway_sandbox_provider import RailwaySandboxProvider


class RailwaySandboxProviderTests(unittest.TestCase):
    def test_bridge_events_are_forwarded_without_exposing_configuration(self):
        process = MagicMock()
        process.stdin = MagicMock()
        process.stdout = iter([
            json.dumps({
                "type": "transition", "status": "cloning", "message": "Cloning",
                "state": {"sandboxId": "sandbox-1"},
            }) + "\n",
            json.dumps({"type": "log", "text": "installed"}) + "\n",
            json.dumps({
                "type": "result", "previewUrl": "https://preview.example",
                "providerState": {"sandboxId": "sandbox-1"},
            }) + "\n",
        ])
        process.wait.return_value = 0
        transitions = []
        logs = []
        environment = {
            "RAILWAY_API_TOKEN": "secret",
            "RAILWAY_SANDBOX_ENVIRONMENT_ID": "isolated-environment",
            "PREVIEW_RAILWAY_ACKNOWLEDGE_DEDICATED_ENVIRONMENT": "true",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "app.services.railway_sandbox_provider.subprocess.Popen", return_value=process,
        ):
            provider = RailwaySandboxProvider("/bridge.mjs")
            result = provider._run_bridge(
                {"action": "cleanup", "providerState": {}},
                lambda status, message, state: transitions.append((status, message, state)),
                logs.append,
            )

        self.assertEqual(result["previewUrl"], "https://preview.example")
        self.assertEqual(transitions[0][0], PreviewStatus.CLONING)
        self.assertEqual(logs, ["installed"])
        submitted = process.stdin.write.call_args.args[0]
        self.assertNotIn("secret", submitted)


if __name__ == "__main__":
    unittest.main()
