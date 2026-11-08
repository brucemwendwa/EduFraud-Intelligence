#!/usr/bin/env python3
"""Exercise the application's storage adapter against a real, dedicated test bucket.

Uses only synthetic bytes under a unique verification/ prefix and removes every version it creates.
Reads the same S3_* variables as the application. Run from backend/:

    S3_BUCKET_NAME=... S3_REGION=... S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... \\
    .venv/bin/python ../scripts/verify_s3.py

--emulator skips controls an S3 emulator cannot enforce. A run with it is NOT AWS verification.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402
from app.services.object_storage import S3ObjectStorage, _hex_to_base64  # noqa: E402

BODY = b"%PDF-1.7\nsynthetic EduShield storage verification\n%%EOF\n"
CHECKSUM = hashlib.sha256(BODY).hexdigest()
results: list[tuple[str, str, str]] = []


def record(name: str, passed: bool, detail: str = "") -> bool:
    results.append(("PASS" if passed else "FAIL", name, detail))
    return passed


def skip(name: str, detail: str) -> None:
    results.append(("SKIP", name, detail))


def object_url(settings: Settings, key: str) -> str:
    if settings.s3_endpoint_url:
        return f"{settings.s3_endpoint_url.rstrip('/')}/{settings.s3_bucket_name}/{key}"
    return f"https://{settings.s3_bucket_name}.s3.{settings.s3_region}.amazonaws.com/{key}"


def verify(settings: Settings, emulator: bool) -> None:
    storage = S3ObjectStorage(settings)
    client = storage._client()  # noqa: SLF001 - this tool inspects the bucket the adapter writes to
    bucket = settings.s3_bucket_name
    key = f"verification/{uuid.uuid4().hex}/evidence.pdf"
    replacement_key = f"{key}.replacement"
    created: list[tuple[str, str | None]] = []
    try:
        stored = storage.put(key=key, body=BODY, content_type="application/pdf", checksum=CHECKSUM)
        created.append((key, stored.version_id))
        record("upload returns a version id", bool(stored.version_id))

        inspected = storage.inspect(key=key, version_id=stored.version_id)
        record("object persists with its checksum", inspected is not None and inspected.checksum == CHECKSUM)
        record("stored bytes are identical", storage.get(key=key, version_id=stored.version_id) == BODY)
        head = client.head_object(Bucket=bucket, Key=key)
        record("object encrypted at rest", head.get("ServerSideEncryption") in ("AES256", "aws:kms"))

        health = storage.health()
        record("bucket versioning enabled", health.versioning == "Enabled", str(health.versioning))
        if emulator:
            skip("public access blocked", "emulator does not enforce this")
            skip("anonymous read refused", "emulator does not enforce this")
            skip("presigned link expires", "emulator does not enforce this")
            skip("plain HTTP refused", "emulator does not enforce this")
        else:
            record("public access blocked", health.public_access_blocked is True, str(health.public_access_blocked))
            record("default encryption configured", health.default_encryption is True)
            record("anonymous read refused", httpx.get(object_url(settings, key), timeout=20).status_code in (401, 403))
            short = S3ObjectStorage(replace_ttl(settings, 1))
            expiring = short.download_url(
                key=key, filename="evidence.pdf", content_type="application/pdf", version_id=stored.version_id
            )
            time.sleep(4)
            record("presigned link expires", httpx.get(expiring, timeout=20).status_code == 403)
            plain = object_url(settings, key).replace("https://", "http://", 1)
            refused = httpx.get(plain, timeout=20, follow_redirects=False).status_code
            record("plain HTTP refused", refused in (301, 403), f"HTTP {refused}")

        link = storage.download_url(
            key=key, filename="evidence.pdf", content_type="application/pdf", version_id=stored.version_id
        )
        download = httpx.get(link, timeout=20)
        record("presigned download serves the object", download.status_code == 200 and download.content == BODY)
        record("download is an attachment", "attachment" in download.headers.get("content-disposition", ""))

        second = client.put_object(Bucket=bucket, Key=key, Body=b"later overwrite", ServerSideEncryption="AES256")
        created.append((key, second.get("VersionId")))
        record(
            "earlier version survives an overwrite",
            second.get("VersionId") != stored.version_id and storage.get(key=key, version_id=stored.version_id) == BODY,
        )

        new = storage.put(key=replacement_key, body=BODY, content_type="application/pdf", checksum=CHECKSUM)
        created.append((replacement_key, new.version_id))
        record(
            "replacement leaves the original in place",
            storage.inspect(key=key, version_id=stored.version_id) is not None
            and storage.inspect(key=replacement_key, version_id=new.version_id) is not None,
        )

        if emulator:
            skip("wrong checksum refused by storage", "emulator does not enforce this")
        else:
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=f"{key}.corrupt",
                    Body=b"tampered in transit",
                    ChecksumSHA256=_hex_to_base64(CHECKSUM),
                    ServerSideEncryption="AES256",
                )
            except client.exceptions.ClientError:
                record("wrong checksum refused by storage", True)
            else:
                record("wrong checksum refused by storage", False, "object was accepted")

        storage.delete(key=replacement_key, version_id=new.version_id)
        gone = storage.inspect(key=replacement_key, version_id=new.version_id) is None
        record("cleanup removes the exact version", gone)
    finally:
        prefix = key.rsplit("/", 1)[0] + "/"
        listing = client.list_object_versions(Bucket=bucket, Prefix=prefix)
        for item in listing.get("Versions", []) + listing.get("DeleteMarkers", []):
            client.delete_object(Bucket=bucket, Key=item["Key"], VersionId=item["VersionId"])
        remaining = client.list_object_versions(Bucket=bucket, Prefix=prefix)
        record("verification objects removed", not remaining.get("Versions") and not remaining.get("DeleteMarkers"))


def replace_ttl(settings: Settings, seconds: int) -> Settings:
    return settings.model_copy(update={"s3_presigned_url_ttl_seconds": seconds})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--emulator", action="store_true", help="skip controls an emulator cannot enforce")
    args = parser.parse_args()
    settings = Settings()
    if not settings.s3_bucket_name or not settings.s3_access_key_id or not settings.s3_secret_access_key:
        print("Set S3_BUCKET_NAME, S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY.", file=sys.stderr)
        return 2
    verify(settings, args.emulator)
    for status, name, detail in results:
        print(f"{status:5} {name}{f' ({detail})' if detail else ''}")
    failed = sum(status == "FAIL" for status, _, _ in results)
    print(f"\n{len(results) - failed} checked or skipped, {failed} failed")
    if args.emulator:
        print("Emulator run: this is not AWS verification.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
