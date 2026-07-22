from app.models.code_models import RepositoryMetadata


class DocumentationPromptBuilderService:
    def build_prompt(self, repository_metadata: RepositoryMetadata, query: str) -> str:
        documentation_summary = self._build_documentation_summary(repository_metadata)
        package_summary = self._build_package_summary(repository_metadata)

        return "\n".join(
            [
                "You are an expert software architect and product specialist.",
                "Answer the user query using only the repository and uploaded documentation context.",
                "Format your response in Markdown and keep it concise.",
                "Do not invent details that are not present in the provided documentation.",
                "",
                "=== REPOSITORY CONTEXT ===",
                f"Repository: {repository_metadata.repository}",
                f"Total indexed files: {repository_metadata.statistics.files}",
                f"TypeScript files: {repository_metadata.statistics.typescript}",
                f"JavaScript files: {repository_metadata.statistics.javascript}",
                f"Test framework: {repository_metadata.testFramework or 'unknown'}",
                "",
                "--- Package Intelligence ---",
                package_summary,
                "",
                "--- Indexed Documentation ---",
                documentation_summary,
                "",
                "=== USER QUERY ===",
                query,
                "",
                "Answer:",
            ]
        )

    def _build_documentation_summary(self, repository_metadata: RepositoryMetadata) -> str:
        if not repository_metadata.documentation:
            return "No project documentation indexed."

        lines = []
        for doc in repository_metadata.documentation:
            preview = doc.source.strip().replace("\r", "").split("\n")
            excerpt = " ".join(preview[:4])[:400]
            lines.append(f"- {doc.path}: {excerpt}")

        return "\n".join(lines)

    def _build_package_summary(self, repository_metadata: RepositoryMetadata) -> str:
        info = repository_metadata.packageInfo
        if info is None:
            return "No package.json intelligence available."

        parts = [
            f"TypeScript: {info.typescriptVersion or 'not detected'}",
            f"React: {info.reactVersion or 'not detected'}",
            f"Vue: {info.vueVersion or 'not detected'}",
        ]
        if info.dependencies:
            parts.append(f"Dependencies: {', '.join(sorted(info.dependencies.keys()))}")
        if info.devDependencies:
            parts.append(f"Dev Dependencies: {', '.join(sorted(info.devDependencies.keys()))}")
        return "\n".join(parts)
