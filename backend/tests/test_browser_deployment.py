"""Opt-in real nginx/Chrome checks; see docs/development/testing.md."""

import json
import os
import shutil
import ssl
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

import pytest
from websockets.sync.client import connect

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_SECURITY") != "1", reason="requires Docker, Chrome and built SPA"
)
ROOT = Path(__file__).resolve().parents[2]


def command(*args):
    return subprocess.check_output(args, text=True).strip()


@pytest.fixture(scope="module")
def deployment(tmp_path_factory):
    directory = tmp_path_factory.mktemp("browser-security")
    shutil.copytree(os.environ["BROWSER_SECURITY_DIST"], directory / "html")
    # A fixture upstream isolates nginx behavior from shared database/services.
    (directory / "upstream.py").write_text("""
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.send_header("Content-Disposition", "attachment; filename=test.txt")
        self.send_header("Cache-Control", "private, no-store")
        self.end_headers()
        self.wfile.write(b"attachment")
    def do_POST(self):
        self.send_response(401)
        self.end_headers()
    def log_message(self, *args):
        pass
HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
""")
    name = "fst023-" + uuid4().hex[:10]
    command("docker", "network", "create", name)
    try:
        command(
            "docker",
            "run",
            "-d",
            "--name",
            name + "-api",
            "--network",
            name,
            "--network-alias",
            "backend",
            "-v",
            f"{directory}:/fixtures:ro",
            "python:3.13-slim",
            "python",
            "/fixtures/upstream.py",
        )
        command(
            "docker",
            "run",
            "-d",
            "--name",
            name + "-web",
            "--network",
            name,
            "-e",
            "PUBLIC_HOST=localhost",
            "-p",
            "127.0.0.1::80",
            "-v",
            f"{ROOT / 'frontend/nginx.conf'}:/etc/nginx/templates/default.conf.template:ro",
            "-v",
            f"{directory / 'html'}:/usr/share/nginx/html:ro",
            "nginx:1.27-alpine",
        )
        port = command("docker", "port", name + "-web", "80/tcp").rsplit(":", 1)[1]
        origin = "http://localhost:" + port
        for _ in range(100):
            try:
                with urlopen(origin + "/health", timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail(command("docker", "logs", name + "-web"))
        command("docker", "exec", name + "-web", "nginx", "-t")
        yield origin, directory, name
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name + "-web", name + "-api"], check=False, capture_output=True
        )
        command("docker", "network", "rm", name)


def test_nginx_headers_routes_and_attachment(deployment):
    origin, _, _ = deployment
    for path in ("/", "/projects/example/board", "/health", "/api/attachments/example/content"):
        with urlopen(origin + path) as response:
            assert response.status == 200
            for name in (
                "Content-Security-Policy",
                "X-Content-Type-Options",
                "Referrer-Policy",
                "Permissions-Policy",
                "X-Frame-Options",
            ):
                assert response.headers[name]
            assert response.headers["Strict-Transport-Security"] is None
            if path.startswith("/api/"):
                assert response.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
                assert response.headers["Content-Disposition"] == "attachment; filename=test.txt"
                assert response.headers["Cache-Control"] == "private, no-store"
            elif path != "/health":
                assert b'<div id="root">' in response.read()
    with pytest.raises(HTTPError) as failure:
        urlopen(origin + "/assets/not-found.js")
    assert failure.value.code == 404
    assert failure.value.headers["X-Frame-Options"] == "DENY"


def test_chrome_csp_and_spa(deployment):
    origin, directory, _ = deployment
    chrome = os.environ.get("BROWSER_SECURITY_CHROME", "/opt/google/chrome/chrome")
    profile = directory / "chrome"
    with (directory / "chrome.log").open("w") as log:
        process = subprocess.Popen(
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                "about:blank",
            ],
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                portfile = profile / "DevToolsActivePort"
                if portfile.exists():
                    break
                time.sleep(0.1)
            port = portfile.read_text().splitlines()[0]
            with urlopen(f"http://localhost:{port}/json") as response:
                target = next(
                    item
                    for item in json.load(response)
                    if item["type"] == "page" and item["url"] == "about:blank"
                )
            with connect(target["webSocketDebuggerUrl"]) as socket:
                sequence = 0

                def cdp(method, params=None):
                    nonlocal sequence
                    sequence += 1
                    socket.send(
                        json.dumps({"id": sequence, "method": method, "params": params or {}})
                    )
                    while True:
                        reply = json.loads(socket.recv(timeout=15))
                        if reply.get("id") == sequence:
                            assert "error" not in reply, reply
                            return reply.get("result", {})

                def evaluate(expression):
                    result = cdp(
                        "Runtime.evaluate",
                        {"expression": expression, "awaitPromise": True, "returnByValue": True},
                    )
                    assert "exceptionDetails" not in result, result
                    return result["result"].get("value")

                cdp("Page.enable")
                cdp("Page.navigate", {"url": origin + "/projects/example/board"})
                for _ in range(100):
                    if evaluate("!!document.querySelector('input[type=password]')"):
                        break
                    time.sleep(0.1)
                else:
                    pytest.fail(
                        "SPA did not render: " + str(evaluate("document.documentElement.outerHTML"))
                    )
                # CDP only inserts a script element: the browser must enforce CSP on it.
                assert (
                    evaluate("""new Promise(resolve => {
                    const script = document.createElement('script');
                    script.textContent = 'window.inlineInjectionExecuted = true';
                    document.body.append(script);
                    setTimeout(() => resolve(window.inlineInjectionExecuted !== true), 100);
                })""")
                    is True
                )
                assert (
                    evaluate("""new Promise(resolve => {
                    const frame = document.createElement('iframe');
                    frame.src = '/';
                    frame.onload = () => resolve(frame.contentDocument === null);
                    document.body.append(frame);
                })""")
                    is True
                )
        finally:
            process.terminate()
            process.wait(timeout=15)


def test_tls_termination_and_http_redirect(deployment):
    _, directory, network = deployment
    command(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=localhost",
        "-addext",
        "subjectAltName=DNS:localhost",
        "-keyout",
        str(directory / "key.pem"),
        "-out",
        str(directory / "cert.pem"),
    )
    config = (ROOT / "deploy/nginx-tls.conf.example").read_text()
    config = config.replace("tracker.example.com", "localhost")
    config = config.replace("/etc/nginx/certs/fullchain.pem", "/fixtures/cert.pem")
    config = config.replace("/etc/nginx/certs/privkey.pem", "/fixtures/key.pem")
    config = config.replace("http://127.0.0.1:5173", f"http://{network}-web:80")
    (directory / "tls.conf").write_text(config)
    name = network + "-tls"
    try:
        command(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "-p",
            "127.0.0.1::443",
            "-p",
            "127.0.0.1::80",
            "-v",
            f"{directory}:/fixtures:ro",
            "-v",
            f"{directory / 'tls.conf'}:/etc/nginx/conf.d/default.conf:ro",
            "nginx:1.27-alpine",
        )
        command("docker", "exec", name, "nginx", "-t")
        port = command("docker", "port", name, "443/tcp").rsplit(":", 1)[1]
        context = ssl.create_default_context(cafile=str(directory / "cert.pem"))
        for _ in range(100):
            try:
                with urlopen(
                    f"https://localhost:{port}/health", context=context, timeout=1
                ) as response:
                    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("TLS frontend did not become healthy")
        with urlopen(
            f"https://localhost:{port}/api/attachments/test/content", context=context
        ) as response:
            assert "default-src 'none'; sandbox" in response.headers.get_all(
                "Content-Security-Policy"
            )
            assert response.headers["Content-Disposition"] == "attachment; filename=test.txt"
        # http.client intentionally does not follow redirects to the real port 443.
        from http.client import HTTPConnection

        http_port = command("docker", "port", name, "80/tcp").rsplit(":", 1)[1]
        connection = HTTPConnection("localhost", int(http_port), timeout=5)
        try:
            connection.request("GET", "/projects/example?view=board")
            response = connection.getresponse()
            assert response.status == 308
            assert response.getheader("Location") == "https://localhost/projects/example?view=board"
            assert response.getheader("Strict-Transport-Security") is None
        finally:
            connection.close()
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)


def test_compose_configuration():
    environment = os.environ | {
        "POSTGRES_PASSWORD": "isolated-test-db",
        "MINIO_ROOT_PASSWORD": "isolated-test-storage",
        "AUTH_SECRET_KEY": "isolated-compose-configuration-test-only",
        "PUBLIC_APP_URL": "https://tracker.example.com",
        "PUBLIC_HOST": "tracker.example.com",
        "FRONTEND_BIND_ADDRESS": "127.0.0.1",
    }
    result = subprocess.check_output(
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
        env=environment,
        text=True,
    )
    services = json.loads(result)["services"]
    assert not services["backend"].get("ports")
    assert services["frontend"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert services["frontend"]["environment"]["PUBLIC_HOST"] == "tracker.example.com"
    assert json.loads(services["backend"]["environment"]["TRACKER_CORS_ORIGINS"]) == [
        "https://tracker.example.com"
    ]
