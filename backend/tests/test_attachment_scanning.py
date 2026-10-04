import io
import socketserver
import struct
import threading
from contextlib import contextmanager
from uuid import UUID

import pytest
from test_chat import post, setup_chat

from app.core.malware_scanner import MalwareScanner, ScanUnavailable
from app.models import Attachment
from app.services.attachment_scanning import AttachmentScanning


@contextmanager
def scanner_server(reply):
    bodies = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            def read(size):
                data = bytearray()
                while len(data) < size:
                    chunk = self.request.recv(size - len(data))
                    if not chunk:
                        return bytes(data)
                    data.extend(chunk)
                return bytes(data)

            assert read(10) == b"zINSTREAM\0"
            body = bytearray()
            while size := struct.unpack("!I", read(4))[0]:
                assert size <= 1024 * 1024
                body.extend(read(size))
            bodies.append(bytes(body))
            for byte in reply:
                self.request.sendall(bytes([byte]))

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield MalwareScanner("127.0.0.1", server.server_address[1], 2), bodies
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.parametrize(
    "reply,expected", [(b"stream: OK\0", "ready"), (b"stream: Eicar-Test FOUND\0", "infected")]
)
def test_protocol_streaming_and_fragmented_verdict(reply, expected):
    payload = b"safe bytes" * 150000
    with scanner_server(reply) as (scanner, bodies):
        assert scanner.scan(io.BytesIO(payload)) == expected
    assert bodies == [payload]


@pytest.mark.parametrize(
    "reply", [b"", b"stream: OK", b"stream: size limit ERROR\0", b"UNKNOWN COMMAND\0", b"OK\0"]
)
def test_only_explicit_complete_clean_verdict_is_accepted(reply):
    with scanner_server(reply) as (scanner, _):
        with pytest.raises(ScanUnavailable):
            scanner.scan(io.BytesIO(b"file"))


class VerdictScanner:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def scan(self, stream):
        self.calls += 1
        if self.verdict == "error":
            raise ScanUnavailable()
        return self.verdict


@pytest.mark.parametrize("verdict", ["ready", "infected", "error"])
async def test_scan_state_and_download_access(client, db_session, attachment_storage, verdict):
    owner, member, _, task, _ = await setup_chat(client)
    response = await post(client, task, owner, files=[("files", ("a.txt", b"hello"))])
    attachment_id = UUID(response.json()["attachments"][0]["id"])
    url = f"/api/attachments/{attachment_id}/content"
    assert (await client.get(url, headers=member)).status_code == 404
    scanner = VerdictScanner(verdict)
    service = AttachmentScanning(db_session, attachment_storage, scanner)
    assert await service.scan_next() == attachment_id
    row = await db_session.get(Attachment, attachment_id)
    assert row.state == ("pending" if verdict == "error" else verdict)
    assert (await client.get(url, headers=member)).status_code == (
        200 if verdict == "ready" else 404
    )
    if verdict == "error":
        scanner.verdict = "ready"
        assert await service.scan_next() == attachment_id
        assert (await client.get(url, headers=member)).status_code == 200
    else:
        assert await service.scan_next() is None
        assert scanner.calls == 1


async def test_corruption_fails_closed_without_scanning(client, db_session, attachment_storage):
    owner, _, _, task, _ = await setup_chat(client)
    response = await post(client, task, owner, files=[("files", ("a", b"original"))])
    attachment_id = UUID(response.json()["attachments"][0]["id"])
    row = await db_session.get(Attachment, attachment_id)
    attachment_storage.objects[row.object_key] = b"modified"
    scanner = VerdictScanner("ready")
    await AttachmentScanning(db_session, attachment_storage, scanner).scan_next()
    assert row.state == "failed"
    assert scanner.calls == 0


async def test_missing_object_does_not_starve_later_uploads(client, db_session, attachment_storage):
    owner, _, _, task, _ = await setup_chat(client)
    response = await post(
        client, task, owner, files=[("files", ("a", b"a")), ("files", ("b", b"b"))]
    )
    ids = sorted(UUID(item["id"]) for item in response.json()["attachments"])
    first = await db_session.get(Attachment, ids[0])
    attachment_storage.objects.pop(first.object_key)
    service = AttachmentScanning(db_session, attachment_storage, VerdictScanner("ready"))
    assert await service.scan_next() == ids[0]
    assert await service.scan_next(ids[0]) == ids[1]
    assert (await db_session.get(Attachment, ids[1])).state == "ready"
    assert (await db_session.get(Attachment, ids[0])).state == "pending"
