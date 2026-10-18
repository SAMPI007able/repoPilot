import os
import re

from app.models.code_models import RepositoryMetadata


class ChatPromptBuilderService:
    """Build a bounded, query-aware repository prompt for codebase chat."""

    def __init__(self) -> None:
        # Conservative for mixed prose, paths, and identifiers. The provider
        # performs an exact Gemini token count before sending the request.
        token_budget = self._positive_env(
            "AI_CHAT_MAX_INPUT_TOKENS", 30_000, "GEMINI_CHAT_MAX_INPUT_TOKENS"
        )
        self.max_prompt_characters = token_budget * 3
        self.max_files = self._positive_env(
            "AI_CHAT_MAX_FILES", 300, "GEMINI_CHAT_MAX_FILES"
        )
        self.max_relationships = self._positive_env(
            "AI_CHAT_MAX_RELATIONSHIPS", 500, "GEMINI_CHAT_MAX_RELATIONSHIPS"
        )
        self.max_query_characters = self._positive_env(
            "AI_CHAT_MAX_QUERY_CHARACTERS", 4_000, "GEMINI_CHAT_MAX_QUERY_CHARACTERS"
        )
        self.max_documentation_characters = self._positive_env(
            "AI_CHAT_MAX_DOCUMENTATION_CHARACTERS",
            6_000,
            "GEMINI_CHAT_MAX_DOCUMENTATION_CHARACTERS",
        )
        self.max_package_characters = self._positive_env(
            "AI_CHAT_MAX_PACKAGE_CHARACTERS",
            4_000,
            "GEMINI_CHAT_MAX_PACKAGE_CHARACTERS",
        )

    def build_prompt(
        self,
        query: str,
        repository_metadata: RepositoryMetadata,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        query = query[: self.max_query_characters]
        terms = self._query_terms(query)
        files, selected_paths = self._ranked_files(repository_metadata, terms)
        relationships = self._ranked_relationships(repository_metadata, terms, selected_paths)
        package_summary = self._build_package_summary(repository_metadata)
        documentation_summary = self._build_documentation_summary(repository_metadata)
        conversation = self._build_conversation(history or [])

        fixed = self._render_prompt(
            repository_metadata, package_summary, documentation_summary,
            "", "", conversation, query,
        )
        available = max(0, self.max_prompt_characters - len(fixed) - 256)
        files_summary = self._fit_lines(files, int(available * 0.45), "files")
        relationships_summary = self._fit_lines(
            relationships, max(0, available - len(files_summary)), "relationships"
        )
        prompt = self._render_prompt(
            repository_metadata, package_summary, documentation_summary,
            files_summary, relationships_summary, conversation, query,
        )
        return prompt[: self.max_prompt_characters]

    @staticmethod
    def _render_prompt(
        metadata: RepositoryMetadata,
        package_summary: str,
        documentation_summary: str,
        files_summary: str,
        relationships_summary: str,
        conversation: str,
        query: str,
    ) -> str:
        return "\n".join([
            "You are an expert software architect with deep knowledge of this codebase.",
            "Answer the developer's question clearly and concisely using only the context provided.",
            "Use conversation history for follow-up references, never as repository evidence.",
            "The inventory and graph may be relevance-ranked and truncated to fit the documented token budget.",
            "Format the response in Markdown and use exact names when referencing files or classes.",
            "Do not invent information that is absent from the context.",
            "", "=== REPOSITORY CONTEXT ===",
            f"Repository: {metadata.repository}",
            f"Total indexed files: {metadata.statistics.files}",
            f"TypeScript files: {metadata.statistics.typescript}",
            f"JavaScript files: {metadata.statistics.javascript}",
            f"Python files: {metadata.statistics.python}",
            f"Java files: {metadata.statistics.java}",
            f"Test framework: {metadata.testFramework or 'unknown'}",
            "", "--- Package Intelligence ---", package_summary,
            "", "--- Documentation ---", documentation_summary,
            "", "--- Relevant File Inventory (file: classes | functions | imports | complexity) ---",
            files_summary or "No parsed file data available.",
            "", "--- Relevant Dependency Graph (source → target via module) ---",
            relationships_summary or "No dependency relationships available.",
            "", "=== CONVERSATION HISTORY ===", conversation,
            "", "=== DEVELOPER QUESTION ===", query, "", "Answer:",
        ])

    @staticmethod
    def _query_terms(query: str) -> set[str]:
        return {
            term.lower()
            for term in re.findall(r"[A-Za-z0-9_./$@-]+", query)
            if len(term) >= 3
        }

    def _ranked_files(
        self, metadata: RepositoryMetadata, terms: set[str]
    ) -> tuple[list[str], set[str]]:
        ranked = sorted(
            metadata.parsedFiles,
            key=lambda item: (
                -self._relevance(item.path, terms), -item.complexity, item.path.lower()
            ),
        )[: self.max_files]
        paths = {item.path for item in ranked}
        lines = [
            f"{item.path}: {item.classes} class(es) | {item.functions} function(s) | "
            f"{item.imports} import(s) | complexity {item.complexity}"
            for item in ranked
        ]
        omitted = len(metadata.parsedFiles) - len(ranked)
        if omitted > 0:
            lines.append(f"... {omitted} additional files omitted by relevance limit.")
        return lines, paths

    def _ranked_relationships(
        self, metadata: RepositoryMetadata, terms: set[str], selected_paths: set[str]
    ) -> list[str]:
        ranked = sorted(
            metadata.relationships,
            key=lambda rel: (
                -(self._relevance(f"{rel.source} {rel.target} {rel.module}", terms)
                  + int(rel.source in selected_paths) + int(rel.target in selected_paths)),
                rel.source.lower(), rel.target.lower(),
            ),
        )[: self.max_relationships]
        lines = [f"{rel.source} → {rel.target}  [{rel.module}]" for rel in ranked]
        omitted = len(metadata.relationships) - len(ranked)
        if omitted > 0:
            lines.append(f"... {omitted} additional relationships omitted by relevance limit.")
        return lines

    @staticmethod
    def _relevance(value: str, terms: set[str]) -> int:
        lower = value.lower()
        return sum(1 for term in terms if term in lower)

    @staticmethod
    def _build_conversation(history: list[tuple[str, str]]) -> str:
        if not history:
            return "No earlier messages in this chat session."
        labels = {"user": "Developer", "assistant": "Assistant"}
        return "\n\n".join(
            f"{labels.get(role, role.title())}:\n{content}" for role, content in history
        )

    def _build_documentation_summary(self, metadata: RepositoryMetadata) -> str:
        if not metadata.documentation:
            return "No documentation indexed."
        lines: list[str] = []
        used = 0
        for doc in metadata.documentation:
            excerpt = " ".join(doc.source.strip().replace("\r", "").split("\n")[:3])[:400]
            line = f"- {doc.path}: {excerpt}"
            if used + len(line) + 1 > self.max_documentation_characters:
                lines.append("... additional documentation omitted to stay within prompt budget.")
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines)

    def _build_package_summary(self, metadata: RepositoryMetadata) -> str:
        info = metadata.packageInfo
        if info is None:
            return "No package.json intelligence available."
        parts = [
            f"TypeScript: {info.typescriptVersion or 'not detected'}",
            f"React: {info.reactVersion or 'not detected'}",
            f"Vue: {info.vueVersion or 'not detected'}",
        ]
        if info.dependencies:
            parts.append(f"Dependencies: {', '.join(sorted(info.dependencies))}")
        if info.devDependencies:
            parts.append(f"Dev Dependencies: {', '.join(sorted(info.devDependencies))}")
        return "\n".join(parts)[: self.max_package_characters]

    @staticmethod
    def _fit_lines(lines: list[str], character_budget: int, label: str) -> str:
        selected: list[str] = []
        used = 0
        for index, line in enumerate(lines):
            if used + len(line) + 1 > character_budget:
                omitted = len(lines) - index
                marker = f"... {omitted} additional {label} omitted to stay within prompt budget."
                if used + len(marker) + 1 <= character_budget:
                    selected.append(marker)
                break
            selected.append(line)
            used += len(line) + 1
        return "\n".join(selected)

    @staticmethod
    def _positive_env(name: str, default: int, legacy_name: str | None = None) -> int:
        configured = os.getenv(name)
        if configured is None and legacy_name:
            configured = os.getenv(legacy_name)
        value = int(configured or str(default))
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero.")
        return value
