import pytest

from clipforge.captions.ass import CAPTION_STYLES, CaptionOptions, build_ass, _hex_to_ass
from clipforge.captions.srt import build_srt
from clipforge.models import Segment, Word


def _seg(start, end, text, wps=3.0):
    toks = text.split()
    step = (end - start) / max(1, len(toks))
    words = [
        Word(start=round(start + i * step, 3), end=round(start + (i + 1) * step, 3), text=t)
        for i, t in enumerate(toks)
    ]
    return Segment(start=start, end=end, text=text, words=words)


def test_hex_to_ass_bgr_order():
    # pure red -> &H000000FF
    assert _hex_to_ass("#FF0000") == "&H000000FF"
    assert _hex_to_ass("#00FF00") == "&H0000FF00"


@pytest.mark.parametrize("style", CAPTION_STYLES)
def test_every_style_produces_valid_ass_header(style):
    segs = [_seg(0.0, 3.0, "the biggest mistake was hiring too fast"),
            _seg(3.0, 6.0, "we spent three years on the wrong thing")]
    opt = CaptionOptions(style=style, play_w=1080, play_h=1920,
                         highlight_words=["mistake", "three years"])
    ass = build_ass(segs, opt, clip_start=0.0, has_word_timestamps=True,
                    opening_text="Nobody tells you this")
    assert "[Script Info]" in ass
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "[V4+ Styles]" in ass and "Style: CF," in ass
    assert ass.count("Dialogue:") >= 2
    # opening text line present
    assert "Nobody tells you this" in ass


def test_ass_word_timestamps_off_uses_segment_chunks():
    segs = [Segment(start=0.0, end=4.0, text="one two three four five six seven eight", words=[])]
    opt = CaptionOptions(style="clean", max_words=3)
    ass = build_ass(segs, opt, has_word_timestamps=False)
    assert ass.count("Dialogue:") >= 3   # 8 words / 3 per line


def test_ass_escapes_braces():
    segs = [_seg(0.0, 2.0, "this {has} braces")]
    ass = build_ass(segs, CaptionOptions(style="bold"))
    assert "{has}" not in ass  # curly replaced so libass override parsing is safe


def test_srt_format():
    segs = [_seg(10.0, 12.5, "hello world"), _seg(12.5, 15.0, "second line")]
    srt = build_srt(segs, clip_start=10.0)
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert srt.strip().startswith("1")
