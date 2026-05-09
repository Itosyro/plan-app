"""Smoke tests for the Mini-App static mount.

If ``webapp/dist`` exists at app boot, ``GET /app/`` should return the
SPA's ``index.html``. We don't require the bundle to be present in CI
(pure-Python test suite), so the test skips when missing instead of
failing — the Dockerfile builds the bundle into the image.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WEBAPP_DIST = Path(__file__).resolve().parent.parent / "webapp" / "dist"


@pytest.mark.skipif(
    not (WEBAPP_DIST / "index.html").exists(),
    reason="webapp/dist not built (run `cd webapp && npm run build`)",
)
def test_app_root_serves_index_html(client: TestClient) -> None:
    """``GET /app/`` returns the Mini-App's index.html with #root marker."""
    resp = client.get("/app/")
    assert resp.status_code == 200
    body = resp.text
    assert '<div id="root">' in body
    # The Telegram WebApp script tag must be present so initData works.
    assert "telegram-web-app.js" in body


@pytest.mark.skipif(
    not (WEBAPP_DIST / "index.html").exists(),
    reason="webapp/dist not built",
)
def test_app_unknown_path_falls_back_to_index(client: TestClient) -> None:
    """SPA fallback — ``/app/whatever`` resolves to index.html."""
    resp = client.get("/app/")
    assert resp.status_code == 200
