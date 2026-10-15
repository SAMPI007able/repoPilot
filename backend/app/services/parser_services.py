import json
import os
import subprocess
import tempfile
from collections.abc import Iterable
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

        return self._to_parsed_file(raw_metadata, relative_path)

    def parse_many(self, files: Iterable[tuple[str, str]]) -> list[ParsedFile]:
        """Parse a repository with one Node process instead of one process per file."""
        manifest = []
        for file_path, relative_path in files:
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"Cannot parse missing file: {file_path}")
            repository_root = os.path.abspath(file_path)
            for _ in relative_path.replace("\\", "/").split("/"):
                repository_root = os.path.dirname(repository_root)
            manifest.append(
                {
                    "file_path": os.path.abspath(file_path),
                    "relative_path": relative_path,
                    "repository_root": repository_root,
                }
            )

        if not manifest:
            return []

        manifest_path = ""
        process: subprocess.Popen[str] | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                delete=False,
            ) as manifest_file:
                json.dump(manifest, manifest_file)
                manifest_path = manifest_file.name

            process = subprocess.Popen(
                ["node", "--experimental-strip-types", self.parser_script, "--batch", manifest_path],
                cwd=self.parser_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            parsed_files: list[ParsedFile] = []
            assert process.stdout is not None
            for line in process.stdout:
                if not line.strip():
                    continue
                try:
                    result = json.loads(line)
                except json.JSONDecodeError as exc:
                    process.kill()
                    raise RuntimeError(f"Node batch parser returned invalid JSON: {line[:200]!r}") from exc
                parsed_files.append(self._to_parsed_file(result, result.pop("relative_path")))

            stderr = process.stderr.read() if process.stderr is not None else ""
            return_code = process.wait()
            if return_code != 0:
                raise RuntimeError(f"Node batch parser failed: {stderr.strip() or f'exit code {return_code}'}")
            if len(parsed_files) != len(manifest):
                raise RuntimeError(
                    f"Node batch parser returned {len(parsed_files)} of {len(manifest)} files"
                )
            return parsed_files
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
            if manifest_path:
                try:
                    os.unlink(manifest_path)
                except OSError:
                    pass

    def _to_parsed_file(self, raw_metadata: dict, relative_path: str | None = None) -> ParsedFile:
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
            complexity=max(int(raw_metadata.get("complexity", 1)), 1),
        )

    def _decode_output(self, output: bytes | None) -> str:
        if output is None:
            return ""

        return output.decode("utf-8", errors="replace")
