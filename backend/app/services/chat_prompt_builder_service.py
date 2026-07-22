from app.models.code_models import RepositoryMetadata


class ChatPromptBuilderService:
    """
    Builds a free-form codebase chat prompt.
    The retrieval layer (graph + context) is unchanged — only the prompt
    template differs from test generation.
    """

    def build_prompt(self, query: str, repository_metadata: RepositoryMetadata) -> str:
        files_summary = self._build_files_summary(repository_metadata)
        relationships_summary = self._build_relationships_summary(repository_metadata)
        documentation_summary = self._build_documentation_summary(repository_metadata)
        package_summary = self._build_package_summary(repository_metadata)

        return "\n".join(
            [
                "You are an expert software architect with deep knowledge of this codebase.",
                "Answer the developer's question clearly and concisely using only the context provided.",
                "Format your response in Markdown.",
                "If you reference a file or class, use its exact name.",
                "Do not invent information that is not present in the context.",
                "",
                "=== REPOSITORY CONTEXT ===",
                "",
                f"Repository: {repository_metadata.repository}",
                f"Total indexed files: {repository_metadata.statistics.files}",
                f"TypeScript files: {repository_metadata.statistics.typescript}",
                f"JavaScript files: {repository_metadata.statistics.javascript}",
                f"Test framework: {repository_metadata.testFramework or 'unknown'}",
                "",
                "--- Package Intelligence ---",
                package_summary,
                "",
                "--- Documentation ---",
                documentation_summary,
                "",
                "--- File Inventory (file: classes | functions | imports) ---",
                files_summary,
                "",
                "--- Dependency Graph (source → target via module) ---",
                relationships_summary,
                "",
                "=== DEVELOPER QUESTION ===",
                "",
                query,
                "",
                "Answer:",
            ]
        )

    def _build_files_summary(self, repository_metadata: RepositoryMetadata) -> str:
        if not repository_metadata.parsedFiles:
            return "No parsed file data available."

        lines = []
        for pf in repository_metadata.parsedFiles:
            lines.append(
                f"{pf.path}: {pf.classes} class(es) | {pf.functions} function(s) | {pf.imports} import(s)"
            )
        return "\n".join(lines)

    def _build_relationships_summary(self, repository_metadata: RepositoryMetadata) -> str:
        if not repository_metadata.relationships:
            return "No dependency relationships available."

        lines = []
        for rel in repository_metadata.relationships:
            lines.append(f"{rel.source} → {rel.target}  [{rel.module}]")
        return "\n".join(lines)

    def _build_documentation_summary(self, repository_metadata: RepositoryMetadata) -> str:
        if not repository_metadata.documentation:
            return "No documentation indexed."

        lines = []
        for doc in repository_metadata.documentation:
            preview = doc.source.strip().replace("\r", "").split("\n")
            excerpt = " ".join(preview[:3])[:400]
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
