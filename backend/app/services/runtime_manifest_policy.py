import shlex

from app.models.runtime_manifest_models import RuntimeManifest


class RuntimeManifestPolicy:
    ALLOWED_RESOURCES = {
        "cpu_request": {"100m", "250m", "500m"},
        "cpu_limit": {"500m", "1", "2"},
        "memory_request": {"128Mi", "256Mi", "512Mi"},
        "memory_limit": {"512Mi", "1Gi", "2Gi"},
    }
    FORBIDDEN_COMMAND_TOKENS = (";", "&&", "||", "|", "`", "$(`", ">", "<", "\n", "\r")

    def validate(self, manifest: RuntimeManifest) -> list[str]:
        violations: list[str] = []
        violations.extend(self._validate_command("install.command", manifest.install.command, "install"))
        violations.extend(self._validate_command("build.command", manifest.build.command, "build"))
        for service in manifest.services:
            violations.extend(
                self._validate_command(
                    f"services.{service.name}.command",
                    service.command,
                    "start",
                )
            )

        public_services = [service for service in manifest.services if service.public]
        if len(public_services) != 1:
            violations.append("Exactly one public web service is required in this release.")

        resources = manifest.resources
        for field_name, allowed_values in self.ALLOWED_RESOURCES.items():
            value = getattr(resources, field_name)
            if value not in allowed_values:
                violations.append(
                    f"resources.{field_name} must be one of: {', '.join(sorted(allowed_values))}."
                )

        if manifest.runtime.family != "node":
            violations.append("Only Node.js web applications are supported in this release.")
        return violations

    def _validate_command(self, field: str, command: str, command_kind: str) -> list[str]:
        if any(token in command for token in self.FORBIDDEN_COMMAND_TOKENS):
            return [f"{field} contains a forbidden shell operator."]

        try:
            arguments = shlex.split(command, posix=True)
        except ValueError:
            return [f"{field} is not a valid command."]
        if not arguments:
            return [f"{field} cannot be empty."]

        package_manager = arguments[0]
        if package_manager not in {"npm", "pnpm", "yarn"}:
            return [f"{field} must use npm, pnpm, or yarn."]

        if command_kind == "install" and not self._is_allowed_install(arguments):
            return [f"{field} is outside the allowed package-install command set."]
        if command_kind in {"build", "start"} and not self._is_allowed_script(arguments):
            return [f"{field} must invoke a package.json script."]
        return []

    def _is_allowed_install(self, arguments: list[str]) -> bool:
        if arguments[:2] in (["npm", "ci"], ["npm", "install"]):
            return len(arguments) == 2
        if arguments[:2] == ["pnpm", "install"]:
            return set(arguments[2:]).issubset({"--frozen-lockfile"})
        if arguments[:2] == ["yarn", "install"]:
            return set(arguments[2:]).issubset({"--frozen-lockfile", "--immutable"})
        return False

    def _is_allowed_script(self, arguments: list[str]) -> bool:
        if arguments[0] in {"npm", "pnpm"}:
            return len(arguments) >= 3 and arguments[1] == "run" and not arguments[2].startswith("-")
        if arguments[0] == "yarn":
            if len(arguments) >= 3 and arguments[1] == "run":
                return not arguments[2].startswith("-")
            return len(arguments) >= 2 and arguments[1] not in {"install", "add", "remove"} and not arguments[1].startswith("-")
        return False
