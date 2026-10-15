import json
import os
import subprocess
import tempfile
from collections.abc import Iterable
from app.models.code_models import CodeClass, CodeMethod, ImportReference, ParsedFile
from app.services.java_source_parser import parse_java_file
from app.services.python_source_parser import parse_python_file
from app.services.source_resolution import infer_repository_root


class ParserService:
    def __init__(self) -> None:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backend_dir = os.path.dirname(app_dir)
        self.parser_script = os.path.join(backend_dir, "parser", "parse.ts")
        self.parser_cwd = os.path.dirname(self.parser_script)

    def parse(self, file_path: str, relative_path: str | None = None) -> ParsedFile:
        parsed = self.parse_many([(file_path, relative_path or os.path.basename(file_path))])
        return parsed[0]

    def parse_many(self, files: Iterable[tuple[str, str]]) -> list[ParsedFile]:
        """Parse mixed-language repositories without sending Python/Java through the TS compiler."""
        entries = []
        for file_path, relative_path in files:
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"Cannot parse missing file: {file_path}")
            entries.append(
                (
                    os.path.abspath(file_path),
                    relative_path,
                    infer_repository_root(file_path, relative_path),
                    os.path.splitext(file_path)[1].lower(),
                )
            )

        parsed: list[ParsedFile | None] = [None] * len(entries)
        typescript_batch: list[tuple[int, str, str, str]] = []
        for index, (file_path, relative_path, repository_root, extension) in enumerate(entries):
            if extension == ".py":
                parsed[index] = self._to_parsed_file(
                    parse_python_file(file_path, relative_path, repository_root),
                    relative_path,
                )
            elif extension == ".java":
                parsed[index] = self._to_parsed_file(
                    parse_java_file(file_path, relative_path, repository_root),
                    relative_path,
                )
            else:
                typescript_batch.append((index, file_path, relative_path, repository_root))

        if typescript_batch:
            for index, parsed_file in zip(
                [item[0] for item in typescript_batch],
                self._parse_typescript_batch(
                    [(file_path, relative_path, repository_root) for _, file_path, relative_path, repository_root in typescript_batch]
                ),
            ):
                parsed[index] = parsed_file

        if any(item is None for item in parsed):
            raise RuntimeError("Parser returned an incomplete mixed-language batch")
        return [item for item in parsed if item is not None]

    def _parse_typescript_batch(self, files: list[tuple[str, str, str]]) -> list[ParsedFile]:
        manifest = [
            {
                "file_path": file_path,
                "relative_path": relative_path,
                "repository_root": repository_root,
            }
            for file_path, relative_path, repository_root in files
        ]
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
