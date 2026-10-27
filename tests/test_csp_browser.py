"""Opt-in browser CSP smoke test using installed Chrome (no extra dependencies).

PowerShell: $env:RUN_CSP_BROWSER='1'; poetry run pytest tests/test_csp_browser.py -q
The loopback bridge serves only a temporary SQLite-backed TestClient app.
"""

import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
from threading import Thread

from fastapi.testclient import TestClient
import pytest

from tests.admin_helpers import admin_login
from tests.test_admin import create_admin
from tests.test_team_registrations import create_team_competition


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_CSP_BROWSER") != "1", reason="Opt-in installed Chrome test"
)

PROBE = r"""
window.__violations = [];
document.addEventListener('securitypolicyviolation', event => {
  window.__violations.push({directive: event.effectiveDirective, blocked: event.blockedURI});
});
document.addEventListener('DOMContentLoaded', () => {
  const result = {inlineBlocked: !window.__cspCanary};
  const mockWidget = document.querySelector('[data-captcha-layout-probe] .smart-captcha');
  if (mockWidget) {
    // Reproduce an asynchronously inserted, fixed-width provider iframe.
    const frame = document.createElement('iframe');
    frame.width = '300'; frame.height = '100'; frame.style.border = '0';
    mockWidget.append(frame);
  }
  if (location.pathname.startsWith('/admin/')) {
    result.jquery = !!window.jQuery;
    result.tabler = !!window.tabler;
    result.select2 = !!window.jQuery?.fn.select2;
    result.flatpickr = !!window.flatpickr;
    const select = document.querySelector('[name="registration_type"]');
    if (select) {
      select.value = 'team'; select.dispatchEvent(new Event('change'));
      result.teamFields = document.querySelector('[name="min_team_size"]').required;
    }
  } else if (location.pathname === '/docs') {
    result.swagger = !!document.querySelector('.swagger-ui');
  } else if (location.pathname === '/redoc') {
    result.redoc = (document.querySelector('redoc')?.textContent || '').includes('Спортивный клуб');
  } else {
    result.bootstrap = !!window.bootstrap;
    const button = document.querySelector('#add-team-member');
    if (button) {
      const before = document.querySelectorAll('.team-member-card').length;
      button.click();
      result.addMember = document.querySelectorAll('.team-member-card').length === before + 1;
    }
  }
  setTimeout(() => {
    if (mockWidget) {
      const outer = mockWidget.parentElement.getBoundingClientRect();
      const frame = mockWidget.querySelector('iframe').getBoundingClientRect();
      result.captchaFits = frame.left >= outer.left - 1 && frame.right <= outer.right + 1;
      result.captchaVisible = frame.width > 200 && frame.height > 50;
    }
    if (location.pathname === '/redoc') {
      const text = document.querySelector('redoc')?.textContent || '';
      result.redoc = text.includes('Спортивный клуб');
      if (!result.redoc) result.redocDiagnostic = text.slice(0, 500);
    }
    result.violations = window.__violations;
    const output = document.createElement('pre');
    output.id = 'csp-browser-result'; output.textContent = JSON.stringify(result);
    document.body.append(output);
  }, 1800);
});
"""


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/competitions/team-cup/register",
        "/admin/login",
        "/admin/competition/create",
        "/docs",
        "/redoc",
    ],
)
def test_csp_in_installed_chrome(
    path, test_app, db_session, tmp_path, captcha_width=None
):
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not chrome.exists():
        pytest.skip("Installed Chrome not found")
    create_admin(db_session)
    create_team_competition(db_session)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/__csp_probe.js":
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.end_headers()
                self.wfile.write(PROBE.encode())
                return
            response = self.server.client.get(self.path, follow_redirects=False)
            body = response.content
            if "text/html" in response.headers.get("content-type", ""):
                if captcha_width:
                    mock = (
                        f'<div class="registration-captcha" data-captcha-layout-probe style="width:{captcha_width}px">'
                        '<div class="smart-captcha"></div></div>'
                        '<script src="/static/js/captcha-fit.js" defer></script>'
                    ).encode()
                    body = body.replace(
                        b'<div class="form-submit-row">',
                        mock + b'<div class="form-submit-row">',
                    )
                body = body.replace(
                    b"<head>", b'<head><script src="/__csp_probe.js"></script>'
                )
                body = body.replace(
                    b"</body>", b"<script>window.__cspCanary=true;</script></body>"
                )
            self.send_response(response.status_code)
            for name, value in response.headers.items():
                if name.lower() not in {
                    "content-length",
                    "content-encoding",
                    "transfer-encoding",
                }:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    with TestClient(test_app, base_url=url) as client:
        if path.startswith("/admin/") and path != "/admin/login":
            admin_login(
                client, data={"username": "admin", "password": "strong-admin-password"}
            )
        server.client = client
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            process = subprocess.run(
                [
                    str(chrome),
                    "--headless",
                    "--disable-gpu",
                    "--no-first-run",
                    f"--user-data-dir={tmp_path / 'chrome'}",
                    "--dump-dom",
                    "--virtual-time-budget=7000",
                    f"{url}{path}",
                ],
                capture_output=True,
                timeout=55,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    dom = process.stdout.decode("utf-8", errors="replace")
    match = re.search(r'<pre id="csp-browser-result">(.*?)</pre>', dom, re.S)
    assert match, process.stderr.decode("utf-8", errors="replace")[-3000:]
    result = json.loads(html.unescape(match[1]))
    print(path, json.dumps(result))
    assert result.pop("inlineBlocked") is True
    violations = result.pop("violations")
    assert any(
        v["blocked"] == "inline" and v["directive"] == "script-src-elem"
        for v in violations
    )
    unexpected = [v for v in violations if v["blocked"] != "inline"]
    assert not unexpected, unexpected
    assert result and all(result.values()), result


@pytest.mark.parametrize("captcha_width", [250, 290])
def test_captcha_fits_narrow_container(test_app, db_session, tmp_path, captcha_width):
    test_csp_in_installed_chrome(
        "/competitions/team-cup/register",
        test_app,
        db_session,
        tmp_path,
        captcha_width=captcha_width,
    )
