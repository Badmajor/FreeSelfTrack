"""Real ClamAV with bundled official signatures, isolated from the shared stack."""

import io
import json
import os
import secrets
import subprocess
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from test_chat import post, setup_chat

from app.core.malware_scanner import MalwareScanner
from app.services.attachment_scanning import AttachmentScanning

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ATTACHMENT_SCAN_INTEGRATION") != "1", reason="Opt-in real ClamAV"
)
# Standard harmless antivirus test string, not executable malware.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@pytest.fixture(scope="module")
def real_scanner(tmp_path_factory):
    directory = tmp_path_factory.mktemp("clamav")
    env = {
        **os.environ,
        "POSTGRES_PASSWORD": secrets.token_hex(20),
        "AUTH_SECRET_KEY": secrets.token_hex(32),
        "MINIO_ROOT_PASSWORD": secrets.token_hex(20),
    }
    config = json.loads(
        subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                str(ROOT / "docker-compose.yml"),
                "config",
                "--format",
                "json",
            ],
            env=env,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    )
    service = config["services"]["clamav"]
    service["ports"] = ["127.0.0.1::3310"]
    service["networks"] = ["default"]
    service["volumes"] = ["signatures:/var/lib/clamav"]
    config_file = directory / "compose.json"
    config_file.write_text(
        json.dumps({"services": {"clamav": service}, "volumes": {"signatures": {}}})
    )
    command = ["docker", "compose", "-p", "fstscan" + uuid4().hex[:8], "-f", str(config_file)]

    def compose(*args):
        result = subprocess.run([*command, *args], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return result.stdout

    try:
        compose("up", "-d", "--wait", "--wait-timeout", "240")
        endpoint = compose("port", "clamav", "3310").strip()
        host, port = endpoint.rsplit(":", 1)
        yield MalwareScanner(host, int(port), 60)
    finally:
        compose("down", "-v")


def test_real_clean_eicar_and_archive(real_scanner):
    assert real_scanner.scan(io.BytesIO(b"An ordinary document")) == "ready"
    assert real_scanner.scan(io.BytesIO(EICAR)) == "infected"
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("test.txt", EICAR)
    assert real_scanner.scan(archive) == "infected"


async def test_real_scanner_controls_api_access(
    real_scanner, client, db_session, attachment_storage
):
    owner, member, _, task, _ = await setup_chat(client)
    response = await post(
        client,
        task,
        owner,
        files=[("files", ("clean.txt", b"safe text")), ("files", ("test.txt", EICAR))],
    )
    assert response.status_code == 201
    service = AttachmentScanning(db_session, attachment_storage, real_scanner)
    while await service.scan_next() is not None:
        pass
    for item in response.json()["attachments"]:
        downloaded = await client.get(f"/api/attachments/{item['id']}/content", headers=member)
        assert downloaded.status_code == (200 if item["filename"] == "clean.txt" else 404)
