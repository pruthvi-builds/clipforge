from clipforge.clipdetect.overlap import deduplicate
from clipforge.models import Candidate, ClipScore


def _c(start, end, overall, text="unique words here " * 3):
    c = Candidate(start=start, end=end, text=text)
    c.score = ClipScore(overall=overall)
    return c


def test_keeps_higher_scoring_of_overlapping_pair():
    a = _c(0, 30, 90, "the mistake that cost me three years of my life")
    b = _c(5, 33, 70, "the mistake that cost me three years of my life story")
    out = deduplicate([a, b], max_overlap=0.4)
    assert len(out) == 1
    assert out[0].score.overall == 90


def test_keeps_non_overlapping():
    a = _c(0, 25, 80, "alpha beta gamma delta epsilon zeta")
    b = _c(40, 70, 60, "one two three four five six seven eight")
    out = deduplicate([a, b])
    assert len(out) == 2


def test_text_near_duplicate_removed_even_if_time_disjoint():
    txt = "nobody tells you that revenue hides a hundred problems in a startup"
    a = _c(0, 30, 88, txt)
    b = _c(120, 150, 50, txt + " really")
    out = deduplicate([a, b], max_overlap=0.9, max_text_sim=0.5)
    assert len(out) == 1
    assert out[0].score.overall == 88


def test_output_sorted_by_start():
    cs = [_c(60, 90, 70, "x y z a b c"), _c(0, 30, 65, "d e f g h i"),
          _c(31, 55, 60, "j k l m n o")]
    out = deduplicate(cs)
    assert [c.start for c in out] == sorted(c.start for c in out)
