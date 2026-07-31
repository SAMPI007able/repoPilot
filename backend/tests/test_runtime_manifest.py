import json
import os
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.models.code_models import (
    DocumentationAsset,
    PackageIntelligence,
    ParsedFile,
    RepositoryMetadata,
    RepositoryStatistics,
)
from app.models.runtime_manifest_models import (
    CommandConfiguration,
    EnvironmentConfiguration,
    LifecycleConfiguration,
    RepositoryConfiguration,
    ResourceConfiguration,
    RuntimeConfiguration,
    RuntimeManifest,
    RuntimeServiceConfiguration,
)
from app.persistence.database import Database
from app.persistence.models import WorkspaceRow
from app.persistence.runtime_manifest_persistence_service import (
    RuntimeManifestPersistenceService,
    RuntimeManifestRevisionConflictError,
)
from app.services.ai.provider import AIProvider
from app.services.repository_services import RepositoryService
from app.services.runtime_manifest_analyzer import (
    DeterministicRuntimeManifestAnalyzer,
    StructuredAIRuntimeManifestFallback,
)
from app.services.runtime_manifest_policy import RuntimeManifestPolicy
from app.services.secret_redactor import SecretRedactor


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "vite-basic"


def fixture_metadata() -> RepositoryMetadata:
    package_json = json.loads((FIXTURE_ROOT / "package.json").read_text(encoding="utf-8"))
    repository_files = sorted(
        path.relative_to(FIXTURE_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file()
    )
    return RepositoryMetadata(
        repository="testforge-preview-fixture",
        statistics=RepositoryStatistics(files=1, typescript=1, javascript=0),
        packageInfo=PackageIntelligence(
            dependencies=package_json["dependencies"],
            devDependencies=package_json["devDependencies"],
            scripts=package_json["scripts"],
            engines=package_json["engines"],
            vueVersion=package_json["dependencies"]["vue"],
        ),
        parsed_file_details=[
            ParsedFile(
                path="src/main.ts",
                file="main.ts",
                source_code=(FIXTURE_ROOT / "src" / "main.ts").read_text(encoding="utf-8"),
            )
        ],
        documentation=[
            DocumentationAsset(
                path="README.md",
                source=(FIXTURE_ROOT / "README.md").read_text(encoding="utf-8"),
            )
        ],
        repositoryFiles=repository_files,
    )


def valid_manifest() -> RuntimeManifest:
    return RuntimeManifest(
        runtime=RuntimeConfiguration(version="22"),
        repository=RepositoryConfiguration(branch="main"),
        install=CommandConfiguration(command="npm ci"),
        build=CommandConfiguration(command="npm run build"),
        services=[
            RuntimeServiceConfiguration(
                name="web",
                command="npm run dev -- --host 0.0.0.0",
                port=5173,
            )
        ],
        environment=EnvironmentConfiguration(required=["VITE_API_URL"]),
        resources=ResourceConfiguration(),
        lifecycle=LifecycleConfiguration(),
    )


class FakeProvider(AIProvider):
    def generate(self, prompt: str) -> str:
        del prompt
        return json.dumps(
            {
                "runtime_version": "22",
                "build_script": "build",
                "start_script": "dev",
                "port": 5173,
                "health_path": "/",
            }
        )


class RuntimeManifestValidationTests(unittest.TestCase):
    def test_environment_names_and_lifecycle_are_strict(self) -> None:
        with self.assertRaises(ValidationError):
            EnvironmentConfiguration(required=["api-key"])
        with self.assertRaisesRegex(ValidationError, "both required and optional"):
            EnvironmentConfiguration(required=["VITE_API_URL"], optional=["VITE_API_URL"])
        with self.assertRaisesRegex(ValidationError, "cannot exceed"):
            LifecycleConfiguration(idleTimeoutMinutes=30, maximumLifetimeMinutes=20)

    def test_manifest_rejects_unknown_infrastructure_fields(self) -> None:
        payload = valid_manifest().model_dump(mode="json", by_alias=True)
        payload["privileged"] = True
        with self.assertRaises(ValidationError):
            RuntimeManifest.model_validate(payload)

    def test_repository_branch_rejects_option_and_ref_injection(self) -> None:
        for branch in ("--upload-pack=evil", "feature/../main", "main@{upstream}"):
            with self.subTest(branch=branch), self.assertRaises(ValidationError):
                RepositoryConfiguration(branch=branch)


class RuntimeManifestAnalyzerTests(unittest.TestCase):
    def test_vite_fixture_produces_valid_deterministic_manifest(self) -> None:
        analysis = DeterministicRuntimeManifestAnalyzer().analyze(fixture_metadata())

        self.assertTrue(analysis.supported)
        self.assertEqual(analysis.summary.framework, "Vite + Vue")
        self.assertEqual(analysis.summary.package_manager, "npm")
        self.assertEqual(analysis.manifest.install.command, "npm ci")
        self.assertEqual(analysis.manifest.build.command, "npm run build")
        self.assertEqual(
            analysis.manifest.services[0].command,
            "npm run dev -- --host 0.0.0.0",
        )
        self.assertEqual(analysis.manifest.services[0].port, 5173)
        self.assertIn("VITE_API_URL", analysis.manifest.environment.required)
        self.assertEqual(RuntimeManifestPolicy().validate(analysis.manifest), [])

    def test_ai_fallback_is_schema_bounded_and_policy_checked(self) -> None:
        metadata = fixture_metadata()
        metadata.packageInfo.scripts = {}
        analyzer = DeterministicRuntimeManifestAnalyzer(
            StructuredAIRuntimeManifestFallback(FakeProvider())
        )

        analysis = analyzer.analyze(metadata, instructions="Use the normal Vite scripts")

        self.assertTrue(analysis.supported)
        self.assertEqual(analysis.manifest.build.command, "npm run build")
        self.assertEqual(RuntimeManifestPolicy().validate(analysis.manifest), [])

    def test_missing_package_intelligence_is_actionable_and_unsupported(self) -> None:
        metadata = RepositoryMetadata(
            repository="unsupported",
            statistics=RepositoryStatistics(files=0, typescript=0, javascript=0),
        )

        analysis = DeterministicRuntimeManifestAnalyzer().analyze(metadata)

        self.assertFalse(analysis.supported)
        self.assertTrue(
            any("package.json" in reason for reason in analysis.unsupported_reasons)
        )


class RuntimeManifestPolicyTests(unittest.TestCase):
    def test_secret_redaction_removes_common_credentials(self) -> None:
        redacted = SecretRedactor().redact(
            "API_KEY=abc123 password:supersecret Authorization Bearer token.value "
            "https://user:pass@example.com"
        )
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("supersecret", redacted)
        self.assertNotIn("token.value", redacted)
        self.assertNotIn("user:pass", redacted)

    def test_shell_injection_and_excess_resources_are_rejected(self) -> None:
        manifest = valid_manifest()
        manifest.services[0].command = "npm run dev; curl https://example.invalid"
        manifest.resources.memory_limit = "8Gi"

        violations = RuntimeManifestPolicy().validate(manifest)

        self.assertTrue(any("forbidden shell operator" in item for item in violations))
        self.assertTrue(any("memory_limit" in item for item in violations))

    def test_repository_url_rejects_ssrf_and_credentials(self) -> None:
        repository_service = RepositoryService()
        self.assertEqual(
            repository_service.validate_public_repository_url(
                "https://github.com/openai/example"
            ),
            "https://github.com/openai/example",
        )
        for invalid_url in (
            "http://github.com/openai/example",
            "https://token@github.com/openai/example",
            "https://127.0.0.1/openai/example",
            "https://github.com/openai/example?ref=main",
        ):
            with self.subTest(invalid_url=invalid_url), self.assertRaises(ValueError):
                repository_service.validate_public_repository_url(invalid_url)


class RuntimeManifestPersistenceTests(unittest.TestCase):
    def test_analysis_update_approval_and_revision_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database = Database(f"sqlite:///{os.path.join(data_dir, 'preview.db')}")
            database.create_schema()
            with database.session() as session:
                session.add(
                    WorkspaceRow(
                        id="workspace-id",
                        repo_url="https://github.com/openai/example",
                        repo_name="example",
                        status="ready",
                    )
                )
            persistence = RuntimeManifestPersistenceService(database)
            analysis = DeterministicRuntimeManifestAnalyzer().analyze(fixture_metadata())

            created = persistence.save_analysis("workspace-id", analysis)
            updated_manifest = created.manifest.model_copy(deep=True)
            updated_manifest.services[0].port = 4173
            updated = persistence.update_manifest(
                "workspace-id",
                updated_manifest,
                created.revision,
                supported=True,
                unsupported_reasons=[],
            )
            with self.assertRaises(RuntimeManifestRevisionConflictError):
                persistence.approve("workspace-id", created.revision)
            approved = persistence.approve("workspace-id", updated.revision)

            self.assertEqual(approved.manifest.services[0].port, 4173)
            self.assertTrue(approved.approved)
            self.assertIsNotNone(approved.approved_at)
            database.close()


if __name__ == "__main__":
    unittest.main()
