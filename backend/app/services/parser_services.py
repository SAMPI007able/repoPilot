import json
import os
import subprocess
from app.models.code_models import CodeClass, CodeMethod, ImportReference, ParsedFile


class ParserService:
    def __init__(self) -> None:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backend_dir = os.path.dirname(app_dir)
        self.parser_script = os.path.join(backend_dir, "parser", "parse.ts")
        self.parser_cwd = os.path.dirname(self.parser_script)

    def parse(self, file_path: str, relative_path: str | None = None) -> ParsedFile:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Cannot parse missing file: {file_path}")

        try:
            result = subprocess.run(
                ["node", "--experimental-strip-types", self.parser_script, file_path],
                cwd=self.parser_cwd,
                capture_output=True,
                text=False,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = self._decode_output(exc.stderr)
            stdout = self._decode_output(exc.stdout)
            error_message = stderr.strip() or stdout.strip() or str(exc)
            raise RuntimeError(f"Node parser failed for {file_path}: {error_message}") from exc

        try:
            raw_metadata = json.loads(self._decode_output(result.stdout))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Node parser returned invalid JSON for {file_path}: {self._decode_output(result.stdout)!r}"
            ) from exc

        return ParsedFile(
            path=relative_path or raw_metadata["file"],
            file=raw_metadata["file"],
            source_code=raw_metadata["source_code"],
            classes=[CodeClass(name=name) for name in raw_metadata.get("classes", [])],
            functions=[CodeMethod(name=name) for name in raw_metadata.get("functions", [])],
            imports=[
                ImportReference(
                    module=import_reference["module"],
                    resolved=import_reference.get("resolved"),
                    kind=import_reference["kind"],
                )
                for import_reference in raw_metadata.get("imports", [])
            ],
        )

    def _decode_output(self, output: bytes | None) -> str:
        if output is None:
            return ""

        return output.decode("utf-8", errors="replace")
