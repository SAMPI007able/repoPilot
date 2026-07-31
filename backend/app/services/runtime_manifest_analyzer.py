import json
import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.models.code_models import RepositoryMetadata
from app.models.runtime_manifest_models import (
    AnalysisEvidence,
    CommandConfiguration,
    EnvironmentConfiguration,
    HealthcheckConfiguration,
    LifecycleConfiguration,
    RepositoryConfiguration,
    ResourceConfiguration,
    RuntimeAnalysisSummary,
    RuntimeConfiguration,
    RuntimeManifest,
    RuntimeManifestAnalysis,
    RuntimeServiceConfiguration,
)
from app.services.ai.provider import AIProvider
from app.services.secret_redactor import SecretRedactor


class RuntimeManifestAnalyzer(Protocol):
    def analyze(
        self,
        repository_metadata: RepositoryMetadata,
        instructions: str | None = None,
        branch: str = "main",
    ) -> RuntimeManifestAnalysis: ...


class AIManifestHints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_version: str | None = Field(default=None, pattern=r"^(20|22)$")
    build_script: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:_-]+$")
    start_script: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:_-]+$")
    port: int | None = Field(default=None, ge=1024, le=65535)
    health_path: str | None = Field(default=None, pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/\-]*$")


class RuntimeManifestFallback(Protocol):
    def propose(
        self,
        repository_metadata: RepositoryMetadata,
        instructions: str | None,
        unresolved_fields: list[str],
    ) -> AIManifestHints | None: ...


class StructuredAIRuntimeManifestFallback:
    def __init__(
        self,
        provider: AIProvider,
        redactor: SecretRedactor | None = None,
    ) -> None:
        self.provider = provider
        self.redactor = redactor or SecretRedactor()

    def propose(
        self,
        repository_metadata: RepositoryMetadata,
        instructions: str | None,
        unresolved_fields: list[str],
    ) -> AIManifestHints | None:
        package_info = repository_metadata.packageInfo
        evidence = {
            "repository": repository_metadata.repository,
            "repositoryFiles": repository_metadata.repositoryFiles,
            "scripts": package_info.scripts if package_info else {},
            "dependencyNames": sorted(
                set((package_info.dependencies if package_info else {}))
                | set((package_info.devDependencies if package_info else {}))
            ),
            "engines": package_info.engines if package_info else {},
            "documentationFiles": [
                document.path for document in repository_metadata.documentation[:20]
            ],
            "userInstructions": self.redactor.redact((instructions or "")[:2000]),
            "unresolvedFields": unresolved_fields,
        }
        prompt = "\n".join(
            [
                "You propose missing fields for a strictly validated Node web runtime manifest.",
                "Return one JSON object only; no Markdown and no commands other than package.json script names.",
                "Allowed keys: runtime_version, build_script, start_script, port, health_path.",
                "Use null when repository evidence is insufficient.",
                "Evidence:",
                json.dumps(evidence, ensure_ascii=False),
            ]
        )
        response = self.provider.generate(prompt).strip()
        if response.startswith("```"):
            response = re.sub(r"^```(?:json)?\s*|\s*```$", "", response, flags=re.IGNORECASE)
        return AIManifestHints.model_validate_json(response)


class DeterministicRuntimeManifestAnalyzer:
    ENVIRONMENT_PATTERNS = (
        re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)"),
        re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]*)"),
        re.compile(r"process\.env\[['\"]([A-Z][A-Z0-9_]*)['\"]\]"),
    )

    def __init__(self, fallback: RuntimeManifestFallback | None = None) -> None:
        self.fallback = fallback

    def analyze(
        self,
        repository_metadata: RepositoryMetadata,
        instructions: str | None = None,
        branch: str = "main",
    ) -> RuntimeManifestAnalysis:
        package_info = repository_metadata.packageInfo
        files = {path.lower() for path in repository_metadata.repositoryFiles}
        warnings: list[str] = []
        unsupported_reasons: list[str] = []
        evidence: list[AnalysisEvidence] = []

        package_manager = self._detect_package_manager(files, evidence, unsupported_reasons)
        framework = self._detect_framework(package_info, files, evidence)
        scripts = package_info.scripts if package_info else {}
        runtime_version = self._detect_runtime_version(package_info, evidence, warnings)
        build_script = "build" if "build" in scripts else None
        start_script = self._detect_start_script(scripts, framework)
        unresolved_fields = [
            name
            for name, value in (("build_script", build_script), ("start_script", start_script))
            if value is None
        ]
        ai_hints = None
        if unresolved_fields and self.fallback and package_info is not None:
            try:
                ai_hints = self.fallback.propose(
                    repository_metadata,
                    instructions,
                    unresolved_fields,
                )
                if ai_hints:
                    evidence.append(
                        AnalysisEvidence(
                            field="unresolvedFields",
                            source="bounded AI fallback",
                            detail="AI hints were schema-validated and will still pass manifest policy validation.",
                            confidence=0.45,
                        )
                    )
            except Exception:
                warnings.append("AI fallback was unavailable; deterministic analysis results were retained.")

        runtime_version = (ai_hints.runtime_version if ai_hints and ai_hints.runtime_version else runtime_version)
        build_script = build_script or (ai_hints.build_script if ai_hints else None)
        start_script = start_script or (ai_hints.start_script if ai_hints else None)
        if package_info is None:
            unsupported_reasons.append(
                "No root package.json intelligence is available. Re-index a Node.js web repository."
            )
        if build_script is None:
            unsupported_reasons.append("No package.json build script could be determined.")
        if start_script is None:
            unsupported_reasons.append("No package.json dev, preview, or start script could be determined.")
        if "bun.lock" in files or "bun.lockb" in files:
            unsupported_reasons.append("Bun repositories are not supported in this release.")

        port = (ai_hints.port if ai_hints and ai_hints.port else self._detect_port(scripts, framework))
        health_path = ai_hints.health_path if ai_hints and ai_hints.health_path else "/"
        install_command = self._install_command(package_manager, files)
        build_command = self._script_command(package_manager, build_script or "build")
        start_command = self._start_command(
            package_manager,
            start_script or "start",
            framework,
        )
        environment_names = self._detect_environment_names(repository_metadata)
        if environment_names:
            warnings.append(
                "Environment-variable references are marked required for review; submit values through the future secret form."
            )
        if instructions:
            warnings.append(
                "User instructions informed bounded fallback only; no instruction or proposed command was executed."
            )

        evidence.extend(
            [
                AnalysisEvidence(
                    field="repository.branch",
                    source="workspace default",
                    detail=branch or "main",
                    confidence=0.6,
                ),
                AnalysisEvidence(
                    field="install.command",
                    source="lockfile/package-manager inference",
                    detail=install_command,
                    confidence=0.95 if files else 0.7,
                ),
                AnalysisEvidence(
                    field="build.command",
                    source="package.json scripts",
                    detail=build_command,
                    confidence=0.95 if build_script in scripts else 0.45,
                ),
                AnalysisEvidence(
                    field="services.web.command",
                    source="package.json scripts and framework defaults",
                    detail=start_command,
                    confidence=0.9 if start_script in scripts else 0.45,
                ),
                AnalysisEvidence(
                    field="services.web.port",
                    source="script/config/framework default",
                    detail=str(port),
                    confidence=0.75,
                ),
                AnalysisEvidence(
                    field="services.web.healthcheck.path",
                    source="framework health default or bounded fallback",
                    detail=health_path,
                    confidence=0.65,
                ),
                AnalysisEvidence(
                    field="environment.required",
                    source="parsed process.env and import.meta.env references",
                    detail=", ".join(environment_names) if environment_names else "None detected",
                    confidence=0.7 if environment_names else 0.5,
                ),
                AnalysisEvidence(
                    field="resources",
                    source="platform safe defaults",
                    detail="250m request / 1 CPU limit / 256Mi request / 1Gi limit",
                    confidence=1.0,
                ),
                AnalysisEvidence(
                    field="lifecycle",
                    source="platform safe defaults",
                    detail="20 minute idle timeout / 60 minute maximum lifetime",
                    confidence=1.0,
                ),
            ]
        )

        manifest = RuntimeManifest(
            runtime=RuntimeConfiguration(version=runtime_version),
            repository=RepositoryConfiguration(branch=branch or "main"),
            install=CommandConfiguration(command=install_command),
            build=CommandConfiguration(command=build_command),
            services=[
                RuntimeServiceConfiguration(
                    name="web",
                    command=start_command,
                    port=port,
                    public=True,
                    healthcheck=HealthcheckConfiguration(path=health_path),
                )
            ],
            environment=EnvironmentConfiguration(required=environment_names),
            resources=ResourceConfiguration(),
            lifecycle=LifecycleConfiguration(),
        )
        confidence = min((item.confidence for item in evidence), default=0.0)
        return RuntimeManifestAnalysis(
            manifest=manifest,
            summary=RuntimeAnalysisSummary(
                framework=framework,
                package_manager=package_manager,
                confidence=confidence,
            ),
            evidence=evidence,
            warnings=warnings,
            supported=not unsupported_reasons,
            unsupported_reasons=list(dict.fromkeys(unsupported_reasons)),
        )

    def _detect_package_manager(
        self,
        files: set[str],
        evidence: list[AnalysisEvidence],
        unsupported_reasons: list[str],
    ) -> str:
        if "pnpm-lock.yaml" in files:
            manager = "pnpm"
            source = "pnpm-lock.yaml"
        elif "yarn.lock" in files:
            manager = "yarn"
            source = "yarn.lock"
        else:
            manager = "npm"
            source = "package-lock.json" if "package-lock.json" in files else "default Node package manager"
        evidence.append(
            AnalysisEvidence(
                field="packageManager",
                source=source,
                detail=manager,
                confidence=0.98 if "lock" in source else 0.65,
            )
        )
        if sum(name in files for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")) > 1:
            unsupported_reasons.append("Multiple package-manager lockfiles were detected; keep exactly one.")
        return manager

    def _detect_framework(self, package_info, files: set[str], evidence: list[AnalysisEvidence]) -> str:
        dependencies = {}
        if package_info:
            dependencies = {**package_info.dependencies, **package_info.devDependencies}
        if "vite" in dependencies or any(path.startswith("vite.config.") for path in files):
            framework = "Vite + Vue" if "vue" in dependencies else "Vite + React" if "react" in dependencies else "Vite"
        elif "next" in dependencies:
            framework = "Next.js"
        elif "nuxt" in dependencies:
            framework = "Nuxt"
        else:
            framework = "Node.js web application"
        evidence.append(
            AnalysisEvidence(
                field="framework",
                source="dependencies and configuration filenames",
                detail=framework,
                confidence=0.9 if framework != "Node.js web application" else 0.55,
            )
        )
        return framework

    def _detect_runtime_version(self, package_info, evidence, warnings) -> str:
        configured = package_info.engines.get("node", "") if package_info else ""
        match = re.search(r"(?:20|22)", configured)
        version = match.group(0) if match else "22"
        evidence.append(
            AnalysisEvidence(
                field="runtime.version",
                source="package.json engines.node" if match else "platform default",
                detail=version,
                confidence=0.95 if match else 0.6,
            )
        )
        if configured and not match:
            warnings.append(f"Node engine '{configured}' is outside the supported Node 20/22 matrix; defaulted to 22 for review.")
        return version

    def _detect_start_script(self, scripts: dict[str, str], framework: str) -> str | None:
        for candidate in (("dev", "preview", "start") if framework.startswith("Vite") else ("start", "dev", "preview")):
            if candidate in scripts:
                return candidate
        return None

    def _detect_port(self, scripts: dict[str, str], framework: str) -> int:
        for command in scripts.values():
            match = re.search(r"(?:--port(?:=|\s+)|-p\s+)(\d{4,5})", command)
            if match and 1024 <= int(match.group(1)) <= 65535:
                return int(match.group(1))
        if framework.startswith("Vite"):
            return 5173
        if framework in {"Next.js", "Nuxt"}:
            return 3000
        return 3000

    def _install_command(self, manager: str, files: set[str]) -> str:
        if manager == "pnpm":
            return "pnpm install --frozen-lockfile"
        if manager == "yarn":
            return "yarn install --immutable" if ".yarnrc.yml" in files else "yarn install --frozen-lockfile"
        return "npm ci" if "package-lock.json" in files else "npm install"

    def _script_command(self, manager: str, script: str) -> str:
        return f"{manager} {script}" if manager == "yarn" else f"{manager} run {script}"

    def _start_command(self, manager: str, script: str, framework: str) -> str:
        command = self._script_command(manager, script)
        if framework.startswith("Vite"):
            return f"{command} --host 0.0.0.0" if manager == "yarn" else f"{command} -- --host 0.0.0.0"
        return command

    def _detect_environment_names(self, repository_metadata: RepositoryMetadata) -> list[str]:
        names: set[str] = set()
        for parsed_file in repository_metadata.parsed_file_details:
            for pattern in self.ENVIRONMENT_PATTERNS:
                names.update(pattern.findall(parsed_file.source_code))
        return sorted(name for name in names if name not in {"NODE_ENV"})
