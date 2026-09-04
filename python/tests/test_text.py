from clipforge.util.text import (
    feature_flags, filler_ratio, keywords, looks_incomplete, split_sentences,
    starts_awkwardly, strip_leading_filler, word_count,
)


def test_split_sentences_basic():
    s = split_sentences("Hello there. How are you? I am fine!")
    assert [x.text for x in s] == ["Hello there.", "How are you?", "I am fine!"]


def test_split_sentences_handles_abbreviations():
    s = split_sentences("I met Dr. Smith on Tuesday. It went well.")
    assert len(s) == 2
    assert s[0].text.startswith("I met Dr. Smith")


def test_split_sentences_offsets_roundtrip():
    text = "One two three. Four five six."
    for sent in split_sentences(text):
        assert text[sent.start_char:sent.end_char].strip() == sent.text


def test_starts_awkwardly():
    assert starts_awkwardly("So we decided to move on.")
    assert starts_awkwardly("And then it broke.")
    assert not starts_awkwardly("The biggest mistake was hiring fast.")


def test_strip_leading_filler():
    assert strip_leading_filler("So, the point is simple.") == "the point is simple."
    # never returns empty
    assert strip_leading_filler("So") == "So"


def test_looks_incomplete():
    assert looks_incomplete("we raised ten million dollars and")
    assert not looks_incomplete("We raised ten million dollars.")


def test_filler_ratio():
    assert filler_ratio("um uh like you know basically") > 0.4
    assert filler_ratio("A clean declarative sentence about product retention.") < 0.2


def test_feature_flags():
    f = feature_flags("The biggest mistake I made was hiring 10 people too fast.")
    assert f["strong_claim"] and f["number"] and f["story"]
    q = feature_flags("Why did the company fail so quickly?")
    assert q["question"]


def test_word_count_and_keywords():
    assert word_count("one two three") == 3
    kw = keywords("retention retention product product product ads")
    assert kw[0] == "product"
