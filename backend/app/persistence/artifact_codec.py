import gzip
import hashlib
import json
from dataclasses import dataclass

from app.models.code_models import RepositoryMetadata


ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EncodedArtifact:
    contents: bytes
    checksum_sha256: str
    compressed_size: int


class RepositoryArtifactCodec:
    def encode(self, workspace_id: str, commit_sha: str | None, metadata: RepositoryMetadata) -> EncodedArtifact:
        metadata_payload = metadata.model_dump(mode="json")
        metadata_payload["parsed_file_details"] = [
            parsed_file.model_dump(mode="json")
            for parsed_file in metadata.parsed_file_details
        ]
        payload = {
            "schemaVersion": ARTIFACT_SCHEMA_VERSION,
            "workspaceId": workspace_id,
            "commitSha": commit_sha,
            "metadata": metadata_payload,
        }
        raw_contents = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        compressed_contents = gzip.compress(raw_contents, compresslevel=6)
        return EncodedArtifact(
            contents=compressed_contents,
            checksum_sha256=hashlib.sha256(compressed_contents).hexdigest(),
            compressed_size=len(compressed_contents),
        )

    def decode(self, contents: bytes, expected_checksum: str | None = None) -> RepositoryMetadata:
        if expected_checksum:
            actual_checksum = hashlib.sha256(contents).hexdigest()
            if actual_checksum != expected_checksum:
                raise RuntimeError("Repository artifact checksum verification failed.")

        payload = json.loads(gzip.decompress(contents).decode("utf-8"))
        if payload.get("schemaVersion") != ARTIFACT_SCHEMA_VERSION:
            raise RuntimeError(
                f"Unsupported repository artifact schema: {payload.get('schemaVersion')}"
            )
        return RepositoryMetadata.model_validate(payload["metadata"])
