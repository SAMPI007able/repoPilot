from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class WorkspaceRow(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repo_url: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    default_branch: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stats: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    package_info: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    graph_preview: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    docs_summary: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    active_artifact_id: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    builds: Mapped[list["WorkspaceBuildRow"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["ArtifactRow"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    runtime_manifest: Mapped["RuntimeManifestRow | None"] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        uselist=False,
    )


class WorkspaceBuildRow(Base):
    __tablename__ = "workspace_builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stages: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    workspace: Mapped[WorkspaceRow] = relationship(back_populates="builds")


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(nullable=False, default=1)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    compressed_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    workspace: Mapped[WorkspaceRow] = relationship(back_populates="artifacts")


class RuntimeManifestRow(Base):
    __tablename__ = "runtime_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    manifest_version: Mapped[str] = mapped_column(String(16), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    analysis_summary: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    unsupported_reasons: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    supported: Mapped[bool] = mapped_column(nullable=False, default=True)
    approved: Mapped[bool] = mapped_column(nullable=False, default=False)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    workspace: Mapped[WorkspaceRow] = relationship(back_populates="runtime_manifest")
