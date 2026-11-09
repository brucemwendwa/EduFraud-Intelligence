"""Private S3-compatible storage boundary for uploaded evidence."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.errors import ValidationFailedError


class ObjectStorage(Protocol):
    def put(self, *, key: str, body: bytes, content_type: str, checksum: str) -> StoredObject: ...
    def delete(self, *, key: str, version_id: str | None = None) -> None: ...
    def inspect(self, *, key: str, version_id: str | None = None) -> StoredObject | None: ...
    def get(self, *, key: str, version_id: str | None = None) -> bytes: ...
    def download_url(self, *, key: str, filename: str, content_type: str, version_id: str | None = None) -> str: ...


@dataclass(frozen=True)
class StoredObject:
    """Provider identity. ETag is deliberately not used as an integrity checksum."""

    version_id: str | None
    checksum: str | None


def attachment_disposition(filename: str) -> str:
    """Build a Content-Disposition value that a user-supplied file name cannot break out of."""
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", filename).strip() or "document"
    return f'attachment; filename="{safe}"'


def _hex_to_base64(checksum: str) -> str:
    return base64.b64encode(bytes.fromhex(checksum)).decode()


def _base64_to_hex(checksum: str) -> str | None:
    try:
        return base64.b64decode(checksum, validate=True).hex()
    except (binascii.Error, ValueError):
        return None


@dataclass(frozen=True)
class StorageHealth:
    reachable: bool
    versioning: str | None = None
    public_access_blocked: bool | None = None
    default_encryption: bool | None = None


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
            config=Config(
                s3={"addressing_style": self.settings.s3_addressing_style},
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 2},
            ),
        )

    def put(self, *, key: str, body: bytes, content_type: str, checksum: str) -> StoredObject:
        response = self._client().put_object(
            Bucket=self.settings.s3_bucket_name,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata={"sha256": checksum},
            # S3 recomputes this on receipt and refuses the object if it differs.
            ChecksumSHA256=_hex_to_base64(checksum),
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
            response = self._client().head_object(ChecksumMode="ENABLED", **params)
        except Exception:  # provider details must not leak through the API
            return None
        # Prefer the checksum the storage service computed; user metadata is only what was declared at upload.
        computed = response.get("ChecksumSHA256")
        checksum = _base64_to_hex(computed) if computed else response.get("Metadata", {}).get("sha256")
        return StoredObject(response.get("VersionId"), checksum)

    def get(self, *, key: str, version_id: str | None = None) -> bytes:
        params = {"Bucket": self.settings.s3_bucket_name, "Key": key}
        if version_id:
            params["VersionId"] = version_id
        return self._client().get_object(**params)["Body"].read()

    def health(self) -> StorageHealth:
        """Probe the configured bucket. Provider errors are reduced to a reachable/unreachable answer."""
        client = self._client()
        try:
            client.head_bucket(Bucket=self.settings.s3_bucket_name)
        except Exception:  # noqa: BLE001 - provider details must not leak through the API
            return StorageHealth(reachable=False)
        bucket = self.settings.s3_bucket_name
        return StorageHealth(
            reachable=True,
            versioning=_optional(lambda: client.get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")),
            public_access_blocked=_optional(
                lambda: all(client.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"].values())
            ),
            default_encryption=_optional(lambda: bool(client.get_bucket_encryption(Bucket=bucket))),
        )

    def download_url(self, *, key: str, filename: str, content_type: str, version_id: str | None = None) -> str:
        params = {
            "Bucket": self.settings.s3_bucket_name,
            "Key": key,
            "ResponseContentType": content_type,
            "ResponseContentDisposition": attachment_disposition(filename),
        }
        if version_id:
            params["VersionId"] = version_id  # the link serves only the exact object that was scanned
        return self._client().generate_presigned_url(
            "get_object", Params=params, ExpiresIn=self.settings.s3_presigned_url_ttl_seconds
        )


def _optional[T](read: Callable[[], T]) -> T | None:
    """A bucket setting that some providers or restricted keys cannot report."""
    try:
        return read()
    except Exception:  # noqa: BLE001 - absence of a report is not an outage
        return None


def get_object_storage(settings: Settings | None = None) -> ObjectStorage:
    settings = settings or get_settings()
    if not settings.s3_bucket_name or not settings.s3_access_key_id or not settings.s3_secret_access_key:
        raise ValidationFailedError("Document storage is not configured.")
    return S3ObjectStorage(settings)
