from app.models.runtime_manifest_models import (
    RuntimeManifest,
    RuntimeManifestRecord,
)
from app.persistence.runtime_manifest_persistence_service import (
    RuntimeManifestPersistenceService,
)
from app.persistence.workspace_persistence_service import WorkspacePersistenceService
from app.services.runtime_manifest_analyzer import RuntimeManifestAnalyzer
from app.services.runtime_manifest_policy import RuntimeManifestPolicy


class RuntimeManifestWorkspaceNotReadyError(LookupError):
    pass


class RuntimeManifestPolicyError(ValueError):
    def __init__(self, violations: list[str]) -> None:
        super().__init__("Runtime manifest violates preview policy.")
        self.violations = violations


class RuntimeManifestService:
    def __init__(
        self,
        workspace_persistence: WorkspacePersistenceService,
        manifest_persistence: RuntimeManifestPersistenceService,
        analyzer: RuntimeManifestAnalyzer,
        policy: RuntimeManifestPolicy,
    ) -> None:
        self.workspace_persistence = workspace_persistence
        self.manifest_persistence = manifest_persistence
        self.analyzer = analyzer
        self.policy = policy

    def analyze(
        self,
        workspace_id: str,
        instructions: str | None = None,
    ) -> RuntimeManifestRecord:
        metadata = self.workspace_persistence.load_metadata(workspace_id)
        if metadata is None:
            raise RuntimeManifestWorkspaceNotReadyError(workspace_id)
        analysis = self.analyzer.analyze(metadata, instructions=instructions)
        violations = self.policy.validate(analysis.manifest)
        if violations:
            analysis.supported = False
            analysis.unsupported_reasons = list(
                dict.fromkeys([*analysis.unsupported_reasons, *violations])
            )
        return self.manifest_persistence.save_analysis(workspace_id, analysis)

    def get(self, workspace_id: str) -> RuntimeManifestRecord:
        return self.manifest_persistence.get(workspace_id)

    def update(
        self,
        workspace_id: str,
        manifest: RuntimeManifest,
        expected_revision: int,
    ) -> RuntimeManifestRecord:
        violations = self.policy.validate(manifest)
        if violations:
            raise RuntimeManifestPolicyError(violations)
        existing = self.manifest_persistence.get(workspace_id)
        persistent_blockers = [
            reason
            for reason in existing.unsupported_reasons
            if reason.startswith(
                (
                    "No root package.json",
                    "Bun repositories",
                    "Multiple package-manager lockfiles",
                )
            )
        ]
        return self.manifest_persistence.update_manifest(
            workspace_id,
            manifest,
            expected_revision,
            supported=not persistent_blockers,
            unsupported_reasons=persistent_blockers,
        )

    def approve(
        self,
        workspace_id: str,
        expected_revision: int,
    ) -> RuntimeManifestRecord:
        record = self.manifest_persistence.get(workspace_id)
        if not record.supported:
            raise RuntimeManifestPolicyError(record.unsupported_reasons)
        violations = self.policy.validate(record.manifest)
        if violations:
            raise RuntimeManifestPolicyError(violations)
        return self.manifest_persistence.approve(workspace_id, expected_revision)
