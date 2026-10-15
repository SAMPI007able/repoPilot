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

    def test_parse_many_indexes_python_and_java_without_typescript_compiler(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            package_root = os.path.join(repo_path, "app")
            java_root = os.path.join(repo_path, "src", "main", "java", "com", "example")
            os.makedirs(package_root)
            os.makedirs(java_root)
            with open(os.path.join(package_root, "__init__.py"), "w", encoding="utf-8") as source_file:
                source_file.write("")
            helper_path = os.path.join(package_root, "helper.py")
            main_path = os.path.join(package_root, "main.py")
            service_path = os.path.join(java_root, "Service.java")
            client_path = os.path.join(java_root, "Client.java")
            with open(helper_path, "w", encoding="utf-8") as source_file:
                source_file.write("def helper():\n    return True\n")
            with open(main_path, "w", encoding="utf-8") as source_file:
                source_file.write(
                    "from app.helper import helper\n\n"
                    "class Greeter:\n"
                    "    def greet(self, value):\n"
                    "        if value and helper():\n"
                    "            return value\n"
                    "        return None\n"
                )
            with open(service_path, "w", encoding="utf-8") as source_file:
                source_file.write("package com.example;\npublic class Service { public int id() { return 1; } }\n")
            with open(client_path, "w", encoding="utf-8") as source_file:
                source_file.write(
                    "package com.example;\n"
                    "import com.example.Service;\n"
                    "public class Client { public int run(Service service) { if (service != null) { return service.id(); } return 0; } }\n"
                )
            ts_path = os.path.join(repo_path, "index.ts")
            with open(ts_path, "w", encoding="utf-8") as source_file:
                source_file.write("export const ready = true;\n")

            parsed_files = ParserService().parse_many(
                [
                    (main_path, "app/main.py"),
                    (helper_path, "app/helper.py"),
                    (client_path, "src/main/java/com/example/Client.java"),
                    (service_path, "src/main/java/com/example/Service.java"),
                    (ts_path, "index.ts"),
                ]
            )

        python_main, python_helper, java_client, java_service, typescript = parsed_files
        self.assertEqual(python_main.classes[0].name, "Greeter")
        self.assertEqual([function.name for function in python_main.functions], ["greet"])
        self.assertEqual(python_main.imports[0].kind, "local")
        self.assertEqual(python_main.imports[0].resolved, "app/helper.py")
        self.assertGreaterEqual(python_main.complexity, 4)
        self.assertEqual(python_helper.functions[0].name, "helper")
        self.assertEqual(java_client.classes[0].name, "Client")
        self.assertEqual(java_client.imports[0].kind, "local")
        self.assertEqual(java_client.imports[0].resolved, "src/main/java/com/example/Service.java")
        self.assertEqual(java_service.classes[0].name, "Service")
        self.assertEqual(typescript.functions, [])
        self.assertEqual(typescript.source_code.strip(), "export const ready = true;")

    def test_python_syntax_from_other_versions_does_not_fail_the_batch(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            legacy_path = os.path.join(repo_path, "legacy.py")
            modern_path = os.path.join(repo_path, "service.py")
            with open(legacy_path, "w", encoding="utf-8") as source_file:
                source_file.write("print 'legacy'\nclass Legacy:\n    def run(self):\n        return 1\n")
            with open(modern_path, "w", encoding="utf-8") as source_file:
                source_file.write(
                    "class Service:\n"
                    "    def run(self, value):\n"
                    "        match value:\n"
                    "            case 1:\n"
                    "                return value\n"
                    "            case _:\n"
                    "                return 0\n"
                )

            parsed_files = ParserService().parse_many(
                [(legacy_path, "legacy.py"), (modern_path, "service.py")]
            )

        self.assertEqual(parsed_files[0].classes[0].name, "Legacy")
        self.assertEqual(parsed_files[0].functions[0].name, "run")
        self.assertGreaterEqual(parsed_files[0].complexity, 2)
        self.assertEqual(parsed_files[1].classes[0].name, "Service")

    def test_java_records_and_text_blocks_are_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            source_path = os.path.join(repo_path, "Person.java")
            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write(
                    "public record Person(String name) {\n"
                    "  public String label() {\n"
                    '    return """\n'
                    "      if (ignored) {\n"
                    '      """;\n'
                    "  }\n"
                    "}\n"
                )

            parsed_file = ParserService().parse_many([(source_path, "Person.java")])[0]

        self.assertEqual(parsed_file.classes[0].name, "Person")
        self.assertIn("label", [function.name for function in parsed_file.functions])
        self.assertNotIn("if", [function.name for function in parsed_file.functions])

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


class RepositoryScanTests(unittest.TestCase):
    def test_scan_skips_python_virtualenv_and_counts_languages(self) -> None:
        with tempfile.TemporaryDirectory() as repo_path:
            os.makedirs(os.path.join(repo_path, ".venv", "lib"))
            os.makedirs(os.path.join(repo_path, "src", "main", "java", "com", "example"))
            with open(os.path.join(repo_path, ".venv", "lib", "site.py"), "w", encoding="utf-8") as source_file:
                source_file.write("ignored = True\n")
            with open(os.path.join(repo_path, "src", "app.py"), "w", encoding="utf-8") as source_file:
                source_file.write("value = 1\n")
            with open(
                os.path.join(repo_path, "src", "main", "java", "com", "example", "App.java"),
                "w",
                encoding="utf-8",
            ) as source_file:
                source_file.write("class App {}")
            with open(os.path.join(repo_path, "src", "index.ts"), "w", encoding="utf-8") as source_file:
                source_file.write("export {}\n")

            result = RepositoryService().scan_repository(repo_path)

        self.assertEqual(result["stats"], {"files": 3, "typescript": 1, "javascript": 0, "python": 1, "java": 1})
        self.assertEqual(
            sorted(file_info["path"] for file_info in result["files"]),
            ["src/app.py", "src/index.ts", "src/main/java/com/example/App.java"],
        )


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
