import json
import os
import tempfile
import unittest
from threading import Barrier
from unittest.mock import Mock

from app.models.code_models import ParsedFile
from app.services.graph_services import GraphService
from app.services.parser_services import ParserService
from app.services.repository_indexer_service import RepositoryIndexerService
from app.services.repository_services import RepositoryService


class ParserServiceTests(unittest.TestCase):
    def test_parse_many_parses_all_files_in_one_batch(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            first_path = os.path.join(repo_path, "first.ts")
            second_path = os.path.join(repo_path, "second.ts")
            with open(first_path, "w", encoding="utf-8") as source_file:
                source_file.write("export function first() { return 1; }")
            with open(second_path, "w", encoding="utf-8") as source_file:
                source_file.write("export class Second {}")

            parsed_files = ParserService().parse_many(
                [(first_path, "first.ts"), (second_path, "second.ts")]
            )

        self.assertEqual([parsed.path for parsed in parsed_files], ["first.ts", "second.ts"])
        self.assertEqual(parsed_files[0].functions[0].name, "first")
        self.assertEqual(parsed_files[1].classes[0].name, "Second")

    def test_parse_many_resolves_tsconfig_path_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            source_path = os.path.join(repo_path, "src")
            os.makedirs(source_path)
            with open(os.path.join(repo_path, "tsconfig.json"), "w", encoding="utf-8") as config_file:
                json.dump(
                    {"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}},
                    config_file,
                )
            main_path = os.path.join(source_path, "main.ts")
            helper_path = os.path.join(source_path, "helper.ts")
            with open(main_path, "w", encoding="utf-8") as source_file:
                source_file.write("import { helper } from '@app/helper'; helper();")
            with open(helper_path, "w", encoding="utf-8") as source_file:
                source_file.write("export function helper() { return true; }")

            parsed_files = ParserService().parse_many(
                [(main_path, "src/main.ts"), (helper_path, "src/helper.ts")]
            )

        self.assertEqual(parsed_files[0].imports[0].kind, "local")
        self.assertEqual(parsed_files[0].imports[0].resolved, "src/helper.ts")

    def test_parse_many_resolves_workspace_package_imports(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            app_path = os.path.join(repo_path, "apps", "web")
            library_path = os.path.join(repo_path, "packages", "shared", "src")
            os.makedirs(app_path)
            os.makedirs(library_path)
            with open(os.path.join(repo_path, "package.json"), "w", encoding="utf-8") as package_file:
                json.dump({"private": True, "workspaces": ["apps/*", "packages/*"]}, package_file)
            with open(
                os.path.join(repo_path, "packages", "shared", "package.json"),
                "w",
                encoding="utf-8",
            ) as package_file:
                json.dump({"name": "@example/shared", "source": "src/index.ts"}, package_file)
            main_path = os.path.join(app_path, "main.ts")
            shared_path = os.path.join(library_path, "index.ts")
            with open(main_path, "w", encoding="utf-8") as source_file:
                source_file.write("import { shared } from '@example/shared'; shared();")
            with open(shared_path, "w", encoding="utf-8") as source_file:
                source_file.write("export function shared() { return true; }")

            parsed_files = ParserService().parse_many(
                [
                    (main_path, "apps/web/main.ts"),
                    (shared_path, "packages/shared/src/index.ts"),
                ]
            )

        self.assertEqual(parsed_files[0].imports[0].kind, "local")
        self.assertEqual(parsed_files[0].imports[0].resolved, "packages/shared/src/index.ts")

    def test_parse_many_calculates_aggregate_mccabe_complexity(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            source_path = os.path.join(repo_path, "complex.ts")
            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write(
                    """
                    export function evaluate(value: number) {
                      if (value > 0 && value < 10) {
                        for (let index = 0; index < value; index += 1) value += index;
                      }
                      return value ? value : 0;
                    }
                    """
                )

            parsed_file = ParserService().parse_many([(source_path, "complex.ts")])[0]

        # Module base + function base + if + logical AND + for + ternary.
        self.assertEqual(parsed_file.complexity, 6)


class RepositoryIndexerServiceTests(unittest.TestCase):
    def test_index_repository_uses_batch_parser(self) -> None:
        repository_service = Mock(spec=RepositoryService)
        repository_service.scan_repository.return_value = {
            "files": [
                {
                    "absolute_path": os.path.abspath("first.ts"),
                    "path": "first.ts",
                }
            ],
            "stats": {"files": 1, "typescript": 1, "javascript": 0},
        }
        parser_service = Mock(spec=ParserService)
        parser_service.parse_many.return_value = []
        indexer = RepositoryIndexerService(repository_service, parser_service, GraphService())

        with tempfile.TemporaryDirectory() as repo_path:
            metadata = indexer.index_repository("example", repo_path)

        parser_service.parse_many.assert_called_once()
        parser_service.parse.assert_not_called()
        self.assertEqual(metadata.repository, "example")

    def test_documentation_scan_ignores_generated_trees_and_binary_assets(self) -> None:
        repository_service = RepositoryService()
        indexer = RepositoryIndexerService(repository_service, ParserService(), GraphService())

        with tempfile.TemporaryDirectory() as repo_path:
            docs_path = os.path.join(repo_path, "docs")
            ignored_path = os.path.join(docs_path, "node_modules", "dependency")
            os.makedirs(ignored_path)
            with open(os.path.join(docs_path, "guide.md"), "w", encoding="utf-8") as docs_file:
                docs_file.write("Guide")
            with open(os.path.join(docs_path, "logo.png"), "wb") as image_file:
                image_file.write(b"not documentation")
            with open(os.path.join(ignored_path, "readme.md"), "w", encoding="utf-8") as ignored_file:
                ignored_file.write("Ignored")

            assets = indexer._load_documentation(repo_path)

        self.assertEqual([(asset.path, asset.source) for asset in assets], [("docs/guide.md", "Guide")])

    def test_parallel_indexing_fans_parsing_out_across_workers(self) -> None:
        repository_service = Mock(spec=RepositoryService)
        repository_service.scan_repository.return_value = {
            "files": [
                {
                    "absolute_path": os.path.abspath(f"file-{index}.ts"),
                    "path": f"file-{index}.ts",
                }
                for index in range(6)
            ],
            "stats": {"files": 6, "typescript": 6, "javascript": 0},
        }
        parser_service = Mock(spec=ParserService)
        parser_barrier = Barrier(3)

        def parse_batch(files):
            batch = list(files)
            parser_barrier.wait(timeout=3)
            return [
                ParsedFile(path=relative_path, file=os.path.basename(relative_path), source_code="")
                for _, relative_path in batch
            ]

        parser_service.parse_many.side_effect = parse_batch
        indexer = RepositoryIndexerService(repository_service, parser_service, GraphService())
        indexer._load_documentation = Mock(return_value=[])
        indexer._load_package_intelligence = Mock(return_value=None)
        progress_events: list[tuple[str, str]] = []

        metadata = indexer.index_repository_parallel(
            "example",
            os.getcwd(),
            progress=lambda stage, status, _detail=None: progress_events.append((stage, status)),
            parse_workers=3,
        )

        self.assertEqual(parser_service.parse_many.call_count, 3)
        self.assertEqual(len(metadata.parsedFiles), 6)
        for worker_index in range(1, 4):
            self.assertIn((f"parse_{worker_index}", "running"), progress_events)
            self.assertIn((f"parse_{worker_index}", "completed"), progress_events)

    def test_parallel_stage_exposes_parser_failure_detail(self) -> None:
        repository_service = Mock(spec=RepositoryService)
        repository_service.scan_repository.return_value = {
            "files": [{"absolute_path": os.path.abspath("broken.ts"), "path": "broken.ts"}],
            "stats": {"files": 1, "typescript": 1, "javascript": 0},
        }
        parser_service = Mock(spec=ParserService)
        parser_service.parse_many.side_effect = RuntimeError("Node parser runtime is missing")
        indexer = RepositoryIndexerService(repository_service, parser_service, GraphService())
        indexer._load_documentation = Mock(return_value=[])
        indexer._load_package_intelligence = Mock(return_value=None)
        progress_events: list[tuple[str, str, str | None]] = []

        with self.assertRaisesRegex(RuntimeError, "Node parser runtime is missing"):
            indexer.index_repository_parallel(
                "example",
                os.getcwd(),
                progress=lambda stage, status, detail=None: progress_events.append(
                    (stage, status, detail)
                ),
                parse_workers=1,
            )

        self.assertIn(
            ("parse_1", "failed", "Node parser runtime is missing"),
            progress_events,
        )


if __name__ == "__main__":
    unittest.main()
