"""Quote search across transcript segments.

The query is a spoken phrase, optionally restricted to one speaker.
Segments are stitched into *chains* only when they are time-adjacent
(``prev.end == next.start``) **and** share the same speaker, so a phrase
spread across a speaker change can never be reported as one quote.

Searching ignores all whitespace (both in the transcript and in the
query), but every character of the stitched text keeps a mapping back to
its original segment and character offset.  Each hit therefore reports
the covered segments, the overall time interval and the exact character
ranges to highlight in every segment's original text.
"""
from __future__ import annotations

import re

_EPS = 1e-6
_WS_RE = re.compile(r"\s")


def _round_key(value: float) -> float:
    return round(float(value), 6)


def _valid_segments(segments: list[dict]) -> list[dict]:
    """Segments sorted by (start, id); entries without usable times are skipped."""
    valid = []
    for seg in segments:
        try:
            start = float(seg.get("start"))
            end = float(seg.get("end"))
        except (TypeError, ValueError):
            continue
        if end < start - _EPS:
            continue
        valid.append(seg)
    return sorted(valid, key=lambda s: (_round_key(s.get("start", 0.0)),
                                        str(s.get("id", ""))))


def _can_join(prev: dict, nxt: dict) -> bool:
    """Adjacent in time (end touches start) and spoken by the same person."""
    if (prev.get("speaker") or "") != (nxt.get("speaker") or ""):
        return False
    return abs(float(prev.get("end")) - float(nxt.get("start"))) <= _EPS


def build_chains(segments: list[dict]) -> list[list[dict]]:
    """Group segments into maximal same-speaker, time-adjacent chains."""
    chains: list[list[dict]] = []
    group: list[dict] = []
    for seg in _valid_segments(segments):
        if group and _can_join(group[-1], seg):
            group.append(seg)
        else:
            if group:
                chains.append(group)
            group = [seg]
    if group:
        chains.append(group)
    return chains


def _normalize(text: str, case_sensitive: bool) -> tuple[str, list[int]]:
    """Drop whitespace (optionally fold case), keeping original offsets.

    Returns the compressed string and ``mapping[i]`` = index of that
    character in the original text.
    """
    chars: list[str] = []
    mapping: list[int] = []
    for i, ch in enumerate(text):
        if _WS_RE.match(ch):
            continue
        chars.append(ch if case_sensitive else ch.lower())
        mapping.append(i)
    return "".join(chars), mapping


def _merge_ranges(mapping: list[int], lo: int, hi: int) -> list[list[int]]:
    """Map a half-open span of compressed indices to original [start, end) ranges.

    Consecutive compressed characters whose original offsets are adjacent
    collapse into one range; skipped whitespace splits ranges apart.
    """
    ranges: list[list[int]] = []
    start = prev = mapping[lo]
    for j in range(lo + 1, hi):
        orig = mapping[j]
        if orig == prev + 1:
            prev = orig
            continue
        ranges.append([start, prev + 1])
        start = prev = orig
    ranges.append([start, prev + 1])
    return ranges


def search(document: dict, query: str, speaker: str = "",
           case_sensitive: bool = False) -> dict:
    """Find every occurrence of ``query`` in the document's speech chains.

    Raises ValueError for an empty / whitespace-only query.
    """
    raw_query = query or ""
    needle, _ = _normalize(raw_query, case_sensitive)
    if not needle:
        raise ValueError("请输入要检索的引语内容")

    wanted_speaker = (speaker or "").strip()
    matches: list[dict] = []
    for chain in build_chains(document.get("segments") or []):
        chain_speaker = chain[0].get("speaker") or ""
        if wanted_speaker and chain_speaker != wanted_speaker:
            continue

        pieces = []
        offset = 0
        parts: list[str] = []
        for seg in chain:
            norm, mapping = _normalize(
                seg.get("text") if isinstance(seg.get("text"), str) else "",
                case_sensitive)
            pieces.append({
                "seg": seg,
                "offset": offset,
                "norm": norm,
                "mapping": mapping,
            })
            parts.append(norm)
            offset += len(norm)
        chain_text = "".join(parts)

        pos = 0
        while True:
            found = chain_text.find(needle, pos)
            if found < 0:
                break
            mlo, mhi = found, found + len(needle)
            # pieces actually contributing matched characters
            hit_idx = [
                i for i, p in enumerate(pieces)
                if p["offset"] < mhi
                and p["offset"] + len(p["norm"]) > mlo
            ]
            first_i, last_i = hit_idx[0], hit_idx[-1]
            seg_results = []
            for i in range(first_i, last_i + 1):
                p = pieces[i]
                seg = p["seg"]
                lo = max(mlo - p["offset"], 0)
                hi = min(mhi - p["offset"], len(p["norm"]))
                seg_results.append({
                    "id": seg.get("id"),
                    "start": float(seg.get("start")),
                    "end": float(seg.get("end")),
                    "speaker": seg.get("speaker", ""),
                    "text": seg.get("text", "")
                    if isinstance(seg.get("text"), str) else "",
                    "ranges": (_merge_ranges(p["mapping"], lo, hi)
                               if hi > lo else []),
                })
            matches.append({
                "start": float(chain[first_i].get("start")),
                "end": float(chain[last_i].get("end")),
                "speaker": chain_speaker,
                "crossSegment": last_i > first_i,
                "segmentIds": [s.get("id") for s in chain[first_i:last_i + 1]],
                "text": chain_text[mlo:mhi],
                "segments": seg_results,
            })
            pos = found + 1  # allow overlapping occurrences

    matches.sort(key=lambda m: (_round_key(m["start"]),
                                _round_key(m["end"])))
    for i, match in enumerate(matches):
        match["index"] = i
    return {
        "query": raw_query,
        "speaker": wanted_speaker,
        "caseSensitive": bool(case_sensitive),
        "total": len(matches),
        "matches": matches,
    }
