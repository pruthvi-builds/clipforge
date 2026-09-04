from clipforge.export.naming import clip_filename, clip_slug
from clipforge.util.fsutil import sanitize_filename


def test_clip_slug():
    assert clip_slug("The Mistake That Cost Me 3 Years!") == "the-mistake-that-cost-me-3-years"
    assert clip_slug("") == "clip"


def test_clip_filename_top():
    assert clip_filename(1, "story", "whatever", top=True) == "01_highest-potential.mp4"


def test_clip_filename_category_and_hook():
    fn = clip_filename(2, "story", "How I lost two years")
    assert fn.startswith("02_story_")
    assert fn.endswith(".mp4")


def test_clip_filename_no_random_uuid():
    fn = clip_filename(3, "surprising insight", "Nobody tells you this")
    assert fn == "03_insight_nobody-tells-you-this.mp4"


def test_sanitize_filename_blocks_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/tmp/evil;rm -rf.mp4").endswith(".mp4")
    assert not sanitize_filename("...hidden").startswith(".")
    assert sanitize_filename("") == "video"
