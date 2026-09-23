"""Unit tests for the quote-search engine (app.quotes).

Run with: python3 test_quotes.py  (or via pytest).
"""
from __future__ import annotations

import os

os.environ.setdefault("STATIC_DIR", "/nonexistent")

import pytest  # noqa: E402

from app.quotes import build_chains, search  # noqa: E402


def doc(segments, annotations=None):
    return {"segments": segments, "annotations": annotations or []}


def seg(sid, start, end, speaker, text):
    return {"id": sid, "start": start, "end": end,
            "speaker": speaker, "text": text}


# ---------- chain construction ----------

def test_chains_only_join_time_adjacent_same_speaker():
    s = [
        seg("a", 0, 1, "甲", "一"),
        seg("b", 1, 2, "甲", "二"),     # adjacent, same speaker
        seg("c", 2, 3, "乙", "三"),     # speaker change -> break
        seg("d", 4, 5, "乙", "四"),     # time gap (3->4) -> break
        seg("e", 5, 6, "乙", "五"),     # adjacent again
    ]
    assert [[x["id"] for x in g] for g in build_chains(s)] == \
        [["a", "b"], ["c"], ["d", "e"]]


def test_chains_sorted_by_start_even_when_input_is_not():
    s = [seg("b", 1, 2, "甲", "x"), seg("a", 0, 1, "甲", "y")]
    assert [[x["id"] for x in g] for g in build_chains(s)] == [["a", "b"]]


def test_invalid_segments_are_skipped():
    s = [
        seg("ok1", 0, 1, "甲", "x"),
        {"id": "bad", "start": 2, "end": 1, "speaker": "甲", "text": "y"},
        seg("ok2", 2, 3, "甲", "z"),
    ]
    assert [[x["id"] for x in g] for g in build_chains(s)] == \
        [["ok1"], ["ok2"]]


def test_empty_speakers_only_chain_with_empty_speakers():
    s = [
        {"id": "a", "start": 0, "end": 1, "speaker": "", "text": "无"},
        {"id": "b", "start": 1, "end": 2, "speaker": None, "text": "名"},
    ]
    # "" and None normalize to the same speaker
    assert [[x["id"] for x in g] for g in build_chains(s)] == [["a", "b"]]


# ---------- basic matching ----------

def test_single_segment_match_and_ranges():
    d = doc([seg("a", 0, 2, "甲", "你好世界")])
    r = search(d, "好世")
    assert r["total"] == 1
    m = r["matches"][0]
    assert m["start"] == 0 and m["end"] == 2
    assert m["speaker"] == "甲"
    assert m["crossSegment"] is False
    assert m["segmentIds"] == ["a"]
    assert m["segments"][0]["ranges"] == [[1, 3]]


def test_whitespace_in_query_and_transcript_is_ignored():
    d = doc([seg("a", 0, 2, "甲", "今天  天气\t真好")])
    r = search(d, " 今天天 气真好 ")
    assert r["total"] == 1
    # the matched text is the whitespace-stripped chain text
    assert r["matches"][0]["text"] == "今天天气真好"


def test_ranges_split_around_internal_whitespace():
    d = doc([seg("a", 0, 2, "甲", "a b")])  # offsets: a=0, space=1, b=2
    m = search(d, "ab")["matches"][0]
    assert m["segments"][0]["ranges"] == [[0, 1], [2, 3]]


def test_case_insensitive_by_default():
    d = doc([seg("a", 0, 1, "甲", "Hello World")])
    assert search(d, "hello")["total"] == 1
    assert search(d, "hello", case_sensitive=True)["total"] == 0
    assert search(d, "HELLO WORLD")["total"] == 1


def test_overlapping_occurrences_are_all_reported():
    d = doc([seg("a", 0, 1, "甲", "aaa")])
    assert [m["text"] for m in search(d, "aa")["matches"]] == ["aa", "aa"]


# ---------- cross-segment behaviour ----------

def test_cross_segment_match_over_adjacent_same_speaker():
    d = doc([
        seg("a", 0, 1, "甲", "我们明天"),
        seg("b", 1, 2, "甲", "一起去工厂"),
    ])
    r = search(d, "明天一起")
    assert r["total"] == 1
    m = r["matches"][0]
    assert m["crossSegment"] is True
    assert m["start"] == 0 and m["end"] == 2
    assert m["segmentIds"] == ["a", "b"]
    segs = {s["id"]: s for s in m["segments"]}
    assert segs["a"]["ranges"] == [[2, 4]]   # 明天
    assert segs["b"]["ranges"] == [[0, 2]]   # 一起


def test_match_cannot_cross_speaker_boundary():
    # 甲 says 明天, immediately followed by 乙 saying 一起 — joining them
    # into one quote would be wrong.
    d = doc([
        seg("a", 0, 1, "甲", "明天"),
        seg("b", 1, 2, "乙", "一起"),
    ])
    assert search(d, "明天一起")["total"] == 0
    assert search(d, "明天")["matches"][0]["speaker"] == "甲"
    assert search(d, "一起")["matches"][0]["speaker"] == "乙"


def test_match_cannot_cross_time_gap():
    d = doc([
        seg("a", 0, 1, "甲", "明天"),
        seg("b", 3, 4, "甲", "一起"),
    ])
    assert search(d, "明天一起")["total"] == 0


def test_speaker_filter_restricts_chains():
    d = doc([
        seg("a", 0, 1, "甲", "你好"),
        seg("b", 1, 2, "乙", "你好"),
    ])
    assert search(d, "你好", speaker="甲")["total"] == 1
    assert search(d, "你好", speaker="乙")["matches"][0]["start"] == 1
    assert search(d, "你好", speaker="丙")["total"] == 0


def test_segment_with_only_whitespace_does_not_break_mapping():
    # segment b contributes no searchable characters but is still adjacent
    d = doc([
        seg("a", 0, 1, "甲", "开始"),
        seg("b", 1, 1.5, "甲", "   "),
        seg("c", 1.5, 2, "甲", "结束"),
    ])
    m = search(d, "开始结束")["matches"][0]
    assert m["segmentIds"] == ["a", "b", "c"]
    segs = {s["id"]: s for s in m["segments"]}
    assert segs["a"]["ranges"] == [[0, 2]]
    assert segs["b"]["ranges"] == []
    assert segs["c"]["ranges"] == [[0, 2]]
    assert m["start"] == 0 and m["end"] == 2


def test_matches_are_sorted_by_time():
    d = doc([
        seg("late", 5, 6, "甲", "重复"),
        seg("early", 0, 1, "甲", "重复"),
    ])
    r = search(d, "重复")
    assert [m["start"] for m in r["matches"]] == [0, 5]
    assert [m["index"] for m in r["matches"]] == [0, 1]


def test_empty_query_raises():
    with pytest.raises(ValueError):
        search(doc([seg("a", 0, 1, "甲", "x")]), "   ")


def test_empty_document():
    r = search(doc([]), "随便")
    assert r["total"] == 0 and r["matches"] == []


def test_whitespace_inside_query_with_speaker_change_not_false_positive():
    d = doc([
        seg("a", 0, 1, "甲", "后来"),
        seg("b", 1, 2, "乙", "改制"),
    ])
    # the space is ignored while searching, but the speaker boundary is not
    assert search(d, "后 来改 制")["total"] == 0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
