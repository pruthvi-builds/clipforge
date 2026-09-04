import importlib

import pytest

from clipforge import config as config_mod


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLIPFORGE_DB_PATH", str(tmp_path / "data" / "t.db"))
    config_mod.get_settings(reload=True)
    import clipforge.db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    return dbmod


def test_project_crud(db):
    db.create_project("abc123", "My Podcast", "podcast")
    p = db.get_project("abc123")
    assert p["name"] == "My Podcast" and p["style"] == "podcast"
    db.set_project_status("abc123", "completed")
    assert db.get_project("abc123")["status"] == "completed"
    assert any(r["id"] == "abc123" for r in db.list_projects())
    db.delete_project("abc123")
    assert db.get_project("abc123") is None


def test_clip_replace_and_render_update(db):
    db.create_project("p1", "v", "general")
    clips = [{
        "index": 1, "start": 10.0, "end": 42.0, "duration": 32.0, "category": "story",
        "hook": "The mistake", "alt_hook": "", "opening_text": "", "reason": "r",
        "self_contained": True, "score": {"overall": 88}, "text": "words",
        "emphasis_words": ["mistake"], "llm_used": True,
    }]
    db.replace_clips("p1", clips)
    got = db.get_project("p1")["clips"]
    assert len(got) == 1 and got[0]["score"]["overall"] == 88
    assert got[0]["emphasis_words"] == ["mistake"]
    db.update_clip_render("p1-01", status="completed", render_path="/x/01.mp4")
    assert db.get_clip("p1-01")["render_status"] == "completed"


def test_job_lifecycle(db):
    db.create_project("p2", "v", "general")
    db.enqueue_job("job1", "analyze", "p2", {"n_clips": 3}, priority=5)
    claimed = db.claim_next_job()
    assert claimed["id"] == "job1" and claimed["params"]["n_clips"] == 3
    assert db.claim_next_job() is None  # only one, now processing
    db.update_job("job1", stage="transcription", progress=0.5, message="halfway")
    assert db.get_job("job1")["progress"] == 0.5
    db.finish_job("job1", "completed")
    assert db.get_job("job1")["state"] == "completed"


def test_settings_kv(db):
    db.set_setting("whisper_model", "medium")
    assert db.get_setting("whisper_model") == "medium"
    assert db.all_settings()["whisper_model"] == "medium"
