"""ClamAV adapter tests against a local stub that speaks clamd's INSTREAM protocol.

These prove the adapter's wire format and its fail-closed reply handling. They do not
prove malware detection, which depends on a real clamd and signature database.
"""

from __future__ import annotations

import hashlib
import socket
import struct
import threading
from collections.abc import Iterator

import pytest

from app.services import document_scanner
from app.services.document_scanner import ClamAVScanner, ScanOutcome
from app.services.object_storage import StoredObject, attachment_disposition

BODY = b"%PDF-1.7\nsynthetic evidence" * 5000
CHECKSUM = hashlib.sha256(BODY).hexdigest()


class ClamdStub:
    def __init__(self, reply: bytes) -> None:
        self.reply = reply
        self.received = b""
        self.command = b""
        self._server = socket.create_server(("127.0.0.1", 0))
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _read_exact(self, conn: socket.socket, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = conn.recv(size - len(data))
            if not chunk:
                break
            data += chunk
        return data

    def _serve(self) -> None:
        conn, _ = self._server.accept()
        with conn:
            while not self.command.endswith(b"\0"):
                self.command += conn.recv(1)
            if self.command == b"zINSTREAM\0":
                while True:
                    size = struct.unpack("!I", self._read_exact(conn, 4))[0]
                    if size == 0:
                        break
                    self.received += self._read_exact(conn, size)
            conn.sendall(self.reply + b"\0")

    def close(self) -> None:
        self._server.close()


class OneObjectStorage:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, *, key: str, version_id: str | None = None) -> bytes:
        assert key == "quarantine/doc.pdf" and version_id == "v1"
        return self.body

    def inspect(self, *, key: str, version_id: str | None = None) -> StoredObject | None:
        return StoredObject(version_id, CHECKSUM)


@pytest.fixture
def stub(request: pytest.FixtureRequest) -> Iterator[ClamdStub]:
    server = ClamdStub(request.param)
    yield server
    server.close()


def _scan(monkeypatch: pytest.MonkeyPatch, port: int, body: bytes = BODY) -> ScanOutcome:
    monkeypatch.setattr(document_scanner, "get_object_storage", lambda: OneObjectStorage(body))
    result = ClamAVScanner("127.0.0.1", port, 5).scan(
        object_key="quarantine/doc.pdf", object_version_id="v1", checksum=CHECKSUM, scan_token="t"
    )
    assert result.provider == "clamav"
    return result.outcome


@pytest.mark.parametrize("stub", [b"stream: OK"], indirect=True)
def test_only_an_exact_ok_is_clean_and_the_whole_object_is_streamed(
    stub: ClamdStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _scan(monkeypatch, stub.port) == ScanOutcome.CLEAN
    assert stub.received == BODY


@pytest.mark.parametrize("stub", [b"stream: Win.Test.EICAR_HDB-1 FOUND"], indirect=True)
def test_found_is_infected(stub: ClamdStub, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _scan(monkeypatch, stub.port) == ScanOutcome.INFECTED


@pytest.mark.parametrize("stub", [b"INSTREAM size limit exceeded. ERROR", b"", b"OK"], indirect=True)
def test_any_other_reply_is_an_error_never_clean(stub: ClamdStub, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _scan(monkeypatch, stub.port) == ScanOutcome.ERROR


@pytest.mark.parametrize("stub", [b"stream: OK"], indirect=True)
def test_tampered_object_is_not_sent_for_a_clean_result(stub: ClamdStub, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _scan(monkeypatch, stub.port, b"different bytes") == ScanOutcome.ERROR
    assert stub.received == b""


def test_scanner_is_unavailable_until_configured() -> None:
    result = document_scanner.get_document_scanner().scan(
        object_key="k", object_version_id=None, checksum="c", scan_token="t"
    )
    assert result.outcome == ScanOutcome.UNAVAILABLE


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("enrollment letter.pdf", 'attachment; filename="enrollment letter.pdf"'),
        ('evil".pdf', 'attachment; filename="evil_.pdf"'),
        ("résumé\r\nX-Injected: 1.pdf", 'attachment; filename="r_sum___X-Injected_ 1.pdf"'),
    ],
)
def test_download_disposition_cannot_be_broken_by_a_file_name(filename: str, expected: str) -> None:
    assert attachment_disposition(filename) == expected


class SilentClamd:
    """Accepts a connection and then never answers."""

    def __init__(self) -> None:
        self._server = socket.create_server(("127.0.0.1", 0))
        self.port = self._server.getsockname()[1]
        self._conns: list[socket.socket] = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                self._conns.append(self._server.accept()[0])
            except OSError:
                return

    def close(self) -> None:
        self._server.close()


def test_a_hung_scanner_times_out_instead_of_reporting_a_result(monkeypatch: pytest.MonkeyPatch) -> None:
    silent = SilentClamd()
    monkeypatch.setattr(document_scanner, "get_object_storage", lambda: OneObjectStorage(BODY[:100]))
    checksum = hashlib.sha256(BODY[:100]).hexdigest()
    with pytest.raises(TimeoutError):
        ClamAVScanner("127.0.0.1", silent.port, 1).scan(
            object_key="quarantine/doc.pdf", object_version_id="v1", checksum=checksum, scan_token="t"
        )
    silent.close()


def test_unreachable_scanner_raises_rather_than_reporting_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_scanner, "get_object_storage", lambda: OneObjectStorage(BODY))
    with socket.create_server(("127.0.0.1", 0)) as probe:
        closed_port = probe.getsockname()[1]
    with pytest.raises(OSError):
        ClamAVScanner("127.0.0.1", closed_port, 1).scan(
            object_key="quarantine/doc.pdf", object_version_id="v1", checksum=CHECKSUM, scan_token="t"
        )
    assert ClamAVScanner("127.0.0.1", closed_port, 1).ping() is False


@pytest.mark.parametrize(
    ("stub", "expected"),
    [(b"ClamAV 1.5.4/27812/Sun Nov  8 08:23:14 2026", True), (b"ClamAV 1.5.4", False)],
    indirect=["stub"],
)
def test_signature_date_is_read_from_clamd(stub: ClamdStub, expected: bool) -> None:
    published = ClamAVScanner("127.0.0.1", stub.port, 2).signatures_published_at()
    assert (published is not None) is expected
