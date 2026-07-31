import os
from pathlib import Path
from typing import Protocol


class ArtifactStore(Protocol):
    def put(self, key: str, contents: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalArtifactStore:
    def __init__(self, root_path: str) -> None:
        self.root_path = Path(root_path).resolve()
        self.root_path.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, contents: bytes, content_type: str) -> None:
        del content_type
        artifact_path = self._resolve_key(key)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = artifact_path.with_suffix(f"{artifact_path.suffix}.tmp")
        temporary_path.write_bytes(contents)
        temporary_path.replace(artifact_path)

    def get(self, key: str) -> bytes:
        return self._resolve_key(key).read_bytes()

    def delete(self, key: str) -> None:
        artifact_path = self._resolve_key(key)
        if artifact_path.exists():
            artifact_path.unlink()

    def _resolve_key(self, key: str) -> Path:
        artifact_path = (self.root_path / key).resolve()
        if self.root_path not in artifact_path.parents:
            raise ValueError(f"Unsafe artifact key: {key}")
        return artifact_path


class S3ArtifactStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 artifact storage.") from exc

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def put(self, key: str, contents: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=contents,
            ContentType=content_type,
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def create_artifact_store(default_local_root: str) -> ArtifactStore:
    store_type = os.getenv("ARTIFACT_STORE", "local").lower()
    if store_type == "local":
        return LocalArtifactStore(os.getenv("ARTIFACT_LOCAL_ROOT", default_local_root))
    if store_type == "s3":
        bucket = os.getenv("ARTIFACT_S3_BUCKET")
        if not bucket:
            raise ValueError("ARTIFACT_S3_BUCKET is required when ARTIFACT_STORE=s3.")
        return S3ArtifactStore(
            bucket=bucket,
            endpoint_url=os.getenv("ARTIFACT_S3_ENDPOINT_URL"),
            region=os.getenv("ARTIFACT_S3_REGION"),
            access_key_id=os.getenv("ARTIFACT_S3_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("ARTIFACT_S3_SECRET_ACCESS_KEY"),
        )
    raise ValueError(f"Unsupported ARTIFACT_STORE: {store_type}")
