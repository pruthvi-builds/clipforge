"""Chunked upload endpoints (start / chunk / finish + resume)."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

ffmpeg = pytest.importorskip("shutil")
if not __import__("shutil").which("ffmpeg"):
    pytest.skip("ffmpeg not available", allow_module_level=True)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLIPFORGE_DB_PATH", str(tmp_path / "data" / "cf.db"))
    from clipforge import config as cfg
    cfg.get_settings.cache_clear() if hasattr(cfg.get_settings, "cache_clear") else None
    from clipforge.server import app as appmod
    importlib.reload(appmod)
    from starlette.testclient import TestClient
    appmod.db.init_db()
    return TestClient(appmod.app)


def _synth(path: Path) -> bytes:
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=3",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True,
    )
    return path.read_bytes()


def test_chunked_upload_roundtrip(client, tmp_path):
    data = _synth(tmp_path / "in.mp4")
    pid = client.post("/api/projects", json={"name": "c", "style": "general"}).json()["id"]

    r = client.post(f"/api/projects/{pid}/upload/chunked/start",
                    json={"filename": "in.mp4", "size": len(data)})
    assert r.status_code == 200 and r.json()["received"] == 0

    step = 64 * 1024
    for off in range(0, len(data), step):
        chunk = data[off:off + step]
        r = client.patch(f"/api/projects/{pid}/upload/chunked",
                         content=chunk, headers={"X-Offset": str(off)})
        assert r.status_code == 200, r.text
        assert r.json()["received"] == min(off + step, len(data))

    r = client.post(f"/api/projects/{pid}/upload/chunked/finish")
    assert r.status_code == 200, r.text
    meta = r.json()["meta"]
    assert meta["width"] == 320 and meta["has_audio"] is True


def test_chunk_offset_mismatch_reports_resume_point(client, tmp_path):
    data = _synth(tmp_path / "in.mp4")
    pid = client.post("/api/projects", json={"name": "c", "style": "general"}).json()["id"]
    client.post(f"/api/projects/{pid}/upload/chunked/start",
                json={"filename": "in.mp4", "size": len(data)})

    client.patch(f"/api/projects/{pid}/upload/chunked",
                 content=data[:1000], headers={"X-Offset": "0"})
    # wrong offset -> 409 with the true resume point
    r = client.patch(f"/api/projects/{pid}/upload/chunked",
                     content=data[5000:6000], headers={"X-Offset": "5000"})
    assert r.status_code == 409
    assert r.json()["error"]["received"] == 1000
