from app.models.code_models import GenerationContext


class PromptBuilderService:
    def build_prompt(self, context: GenerationContext) -> str:
        class_names = ", ".join(code_class.name for code_class in context.classes) or "None"
        method_names = ", ".join(method.name for method in context.methods) or "None"
        framework_name = context.test_framework or "the project's existing test framework"
        dependency_lines = [
            f"- {import_reference.module} -> {import_reference.resolved or 'unresolved'} ({import_reference.kind})"
            for import_reference in context.imports
        ] or ["- None"]
        existing_test_lines = [f"- {test_path}" for test_path in context.existing_tests] or ["- None"]
        dependency_sections = [
            "\n".join(
                [
                    f"Dependency: {dependency.name}",
                    f"Reason: {dependency.reason}",
                    f"Path: {dependency.path or 'unknown'}",
                    "Source:",
                    dependency.source,
                ]
            )
            for dependency in context.dependencies
        ]
        dependencies_context = "\n\n".join(dependency_sections) if dependency_sections else "No dependencies available."
        package_summary = self._build_package_summary(context)
        documentation_summary = self._build_documentation_summary(context)

        return "\n".join(
            [
                "You are a senior QA engineer.",
                "Generate a Markdown response only.",
                "Do not return JSON.",
                "",
                "Repository Context",
                "",
                f"Target: {context.target}",
                f"Test Type: {context.test_type}",
                f"Test Framework: {framework_name}",
                "",
                f"Classes: {class_names}",
                f"Methods: {method_names}",
                "",
                "Existing Tests:",
                *existing_test_lines,
                "",
                "Dependencies:",
                *dependency_lines,
                "",
                "Package Intelligence:",
                package_summary,
                "",
                "Documentation:",
                documentation_summary,
                "",
                "Target Source:",
                context.target_source,
                "",
                "Dependency Summaries:",
                dependencies_context,
                "",
                f"Generate {framework_name} {context.test_type} tests for {context.target}.",
                "Follow the existing testing style when existing tests are available.",
                "",
                "Use exactly this Markdown structure:",
                "# Test Plan",
                "## Happy Path",
                "## Edge Cases",
                "## Failure Scenarios",
                "## Example Test Code",
            ]
        )

    def _build_package_summary(self, context: GenerationContext) -> str:
        if context.package_info is None:
            return "No package.json intelligence available."

        parts = [
            f"TypeScript: {context.package_info.typescriptVersion or 'not detected'}",
            f"React: {context.package_info.reactVersion or 'not detected'}",
            f"Vue: {context.package_info.vueVersion or 'not detected'}",
        ]
        if context.package_info.dependencies:
            dependency_names = ", ".join(sorted(context.package_info.dependencies.keys()))
            parts.append(f"Dependencies: {dependency_names}")
        if context.package_info.devDependencies:
            dev_dependency_names = ", ".join(sorted(context.package_info.devDependencies.keys()))
            parts.append(f"Dev Dependencies: {dev_dependency_names}")
        if context.package_info.scripts:
            script_names = ", ".join(sorted(context.package_info.scripts.keys()))
            parts.append(f"Scripts: {script_names}")

        return "\n".join(parts)

    def _build_documentation_summary(self, context: GenerationContext) -> str:
        if not context.documentation:
            return "No repository documentation indexed."

        lines = []
        for document in context.documentation:
            preview = document.source.strip().replace("\r", "").split("\n")
            excerpt = " ".join(preview[:3])[:300]
            lines.append(f"- {document.path}: {excerpt}")

        return "\n".join(lines)
