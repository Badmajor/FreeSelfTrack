"""Real Chrome UI acceptance against the disposable TASK-038 stack."""

import base64
import json
import os
import subprocess
import time
from urllib.request import urlopen

from websockets.sync.client import connect


def check_release_ui(origin, directory, temporary, permanent, organization_id):
    profile = directory / "chrome"
    with (directory / "chrome.log").open("w") as log:
        process = subprocess.Popen(
            [
                os.getenv("BROWSER_SECURITY_CHROME", "/opt/google/chrome/chrome"),
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
            portfile = profile / "DevToolsActivePort"
            for _ in range(100):
                if portfile.exists():
                    break
                time.sleep(0.1)
            port = portfile.read_text().splitlines()[0]
            with urlopen(f"http://localhost:{port}/json", timeout=10) as response:
                target = next(item for item in json.load(response) if item["type"] == "page")
            with connect(target["webSocketDebuggerUrl"]) as websocket:
                sequence = 0

                def cdp(method, params=None):
                    nonlocal sequence
                    sequence += 1
                    websocket.send(
                        json.dumps({"id": sequence, "method": method, "params": params or {}})
                    )
                    while True:
                        reply = json.loads(websocket.recv(timeout=15))
                        if reply.get("id") == sequence:
                            assert "error" not in reply, method
                            return reply.get("result", {})

                def evaluate(expression):
                    result = cdp(
                        "Runtime.evaluate",
                        {"expression": expression, "awaitPromise": True, "returnByValue": True},
                    )
                    assert "exceptionDetails" not in result, "Browser evaluation failed"
                    return result["result"].get("value")

                def wait(expression):
                    for _ in range(150):
                        if evaluate(expression):
                            return
                        time.sleep(0.1)
                    raise AssertionError("UI condition timed out: " + expression)

                def fill(selector, value):
                    evaluate(
                        "(() => { const input = document.querySelector("
                        + json.dumps(selector)
                        + "); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')"
                        + ".set.call(input, "
                        + json.dumps(value)
                        + ");"
                        + "input.dispatchEvent(new Event('input', {bubbles:true})); })()"
                    )

                def login(email, password):
                    wait("!!document.querySelector('#email')")
                    fill("#email", email)
                    fill("#password", password)
                    evaluate("document.querySelector('#password').form.requestSubmit()")

                def click(label):
                    evaluate(
                        "[...document.querySelectorAll('button')]"
                        ".find(b => b.textContent.trim() === " + json.dumps(label) + ").click()"
                    )

                cdp("Page.enable")
                cdp("Page.navigate", {"url": origin})
                login("browser-user@example.com", temporary)
                wait("document.body.innerText.includes('Set a permanent password')")
                assert not evaluate("!!document.querySelector('aside')")
                fill("#current-password", temporary)
                fill("#new-password", permanent)
                evaluate("document.querySelector('#new-password').form.requestSubmit()")
                login("browser-user@example.com", permanent)
                wait(
                    "!document.querySelector('#email') && "
                    "document.body.innerText.includes('Sign out')"
                )
                assert not evaluate("document.body.innerText.includes('Set a permanent password')")
                assert evaluate("localStorage.getItem('freeselftrack.access_token')") is None
                click("Sign out")
                login("release-admin", "x")
                wait(
                    "!document.querySelector('#email') && "
                    "document.body.innerText.includes('Sign out')"
                )
                cdp(
                    "Page.navigate",
                    {"url": origin + "/management/organizations/" + organization_id},
                )
                wait("document.querySelectorAll('.entity-audit ol > li').length === 20")
                click("Next audit page")
                wait(
                    "document.querySelector('.entity-audit nav').innerText.includes('Page 2') && "
                    "document.querySelectorAll('.entity-audit ol > li').length > 0"
                )
                click("Previous audit page")
                wait(
                    "document.querySelector('.entity-audit nav').innerText.includes('Page 1') && "
                    "document.querySelectorAll('.entity-audit ol > li').length === 20"
                )
                screenshot = cdp("Page.captureScreenshot", {"format": "png"})["data"]
                (directory / "release-audit.png").write_bytes(base64.b64decode(screenshot))
        finally:
            process.terminate()
            process.wait(timeout=15)
