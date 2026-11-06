"""Private S3-compatible storage boundary for uploaded evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.errors import ValidationFailedError


class ObjectStorage(Protocol):
    def put(self, *, key: str, body: bytes, content_type: str, checksum: str) -> StoredObject: ...
    def delete(self, *, key: str, version_id: str | None = None) -> None: ...
    def inspect(self, *, key: str, version_id: str | None = None) -> StoredObject | None: ...
    def download_url(self, *, key: str, filename: str, content_type: str) -> str: ...


@dataclass(frozen=True)
class StoredObject:
    """Provider identity. ETag is deliberately not used as an integrity checksum."""

    version_id: str | None
    checksum: str | None


@dataclass(frozen=True)
class S3ObjectStorage:
    settings: Settings

    def _client(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # deployment failure must not silently use local disk
            raise ValidationFailedError("Document storage is unavailable.") from exc
        return boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            region_name=self.settings.s3_region,
            aws_access_key_id=self.settings.s3_access_key_id.get_secret_value(),
            aws_secret_access_key=self.settings.s3_secret_access_key.get_secret_value(),
            use_ssl=self.settings.s3_use_tls,
            config=Config(s3={"addressing_style": self.settings.s3_addressing_style}),
        )

    def put(self, *, key: str, body: bytes, content_type: str, checksum: str) -> StoredObject:
        response = self._client().put_object(
            Bucket=self.settings.s3_bucket_name,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata={"sha256": checksum},
            ServerSideEncryption="AES256",
        )
        return StoredObject(response.get("VersionId"), checksum)

    def delete(self, *, key: str, version_id: str | None = None) -> None:
        params = {"Bucket": self.settings.s3_bucket_name, "Key": key}
        if version_id:
            params["VersionId"] = version_id
        self._client().delete_object(**params)

    def inspect(self, *, key: str, version_id: str | None = None) -> StoredObject | None:
        params = {"Bucket": self.settings.s3_bucket_name, "Key": key}
        if version_id:
            params["VersionId"] = version_id
        try:
            response = self._client().head_object(**params)
        except Exception:  # provider details must not leak through the API
            return None
        return StoredObject(response.get("VersionId"), response.get("Metadata", {}).get("sha256"))

    def download_url(self, *, key: str, filename: str, content_type: str) -> str:
        return self._client().generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.s3_bucket_name,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=self.settings.s3_presigned_url_ttl_seconds,
        )


def get_object_storage(settings: Settings | None = None) -> ObjectStorage:
    settings = settings or get_settings()
    if not settings.s3_bucket_name or not settings.s3_access_key_id or not settings.s3_secret_access_key:
        raise ValidationFailedError("Document storage is not configured.")
    return S3ObjectStorage(settings)
