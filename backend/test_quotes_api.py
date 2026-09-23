"""End-to-end API tests for quote search.

Run with: python3 test_quotes_api.py  (or via pytest).
"""
import os
import shutil
import tempfile

os.environ.setdefault("STATIC_DIR", "/nonexistent")
_TMP = tempfile.mkdtemp(prefix="quotes-api-")
os.environ["DATA_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DOC = {
    "segments": [
        {"id": "s1", "start": 0.0, "end": 5.0,
         "speaker": "访谈者", "text": "感谢您今天接受访谈"},
        {"id": "s2", "start": 5.0, "end": 10.0,
         "speaker": "访谈者", "text": "我们 聊聊改制"},
        {"id": "s3", "start": 10.0, "end": 15.0,
         "speaker": "受访者", "text": "我叫李明"},
        {"id": "s4", "start": 15.0, "end": 20.0,
         "speaker": "受访者", "text": "后来2003年改制"},
        # 5s gap, same speaker -> not chainable with s4
        {"id": "s5", "start": 25.0, "end": 30.0,
         "speaker": "受访者", "text": "最早全靠手摇"},
    ],
    "annotations": [],
}


def run():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        p = c.post("/api/projects", json={"name": "引语检索测试"}).json()
        pid = p["id"]
        c.put(f"/api/projects/{pid}",
              json={"name": "引语检索测试", "document": DOC})

        # empty / whitespace-only query is rejected; nothing is searched
        assert c.post(f"/api/projects/{pid}/quote-search",
                      json={"query": ""}).status_code == 400
        assert c.post(f"/api/projects/{pid}/quote-search",
                      json={"query": "   \t"}).status_code == 400
        missing = c.post("/api/projects/nope/quote-search",
                         json={"query": "改制"})
        assert missing.status_code == 404

        # single-segment hit with exact original-text ranges
        r = c.post(f"/api/projects/{pid}/quote-search",
                   json={"query": "李明"}).json()
        assert r["total"] == 1
        m = r["matches"][0]
        assert m["segmentIds"] == ["s3"]
        assert (m["start"], m["end"]) == (10.0, 15.0)
        assert m["segments"][0]["ranges"] == [[2, 4]]

        # whitespace in query/transcript is ignored; ranges stay mapped
        r = c.post(f"/api/projects/{pid}/quote-search",
                   json={"query": "我们 聊 聊"}).json()
        assert r["total"] == 1
        m = r["matches"][0]
        # "我们 聊聊" -> stripped offsets 2,3,4,5 in s2
        assert m["segments"][0]["ranges"] == [[0, 2], [3, 5]]

        # phrase continuing across two adjacent same-speaker segments
        r = c.post(f"/api/projects/{pid}/quote-search",
                   json={"query": "接受访谈我们聊聊"}).json()
        assert r["total"] == 1
        m = r["matches"][0]
        assert m["crossSegment"] is True
        assert m["segmentIds"] == ["s1", "s2"]
        assert (m["start"], m["end"]) == (0.0, 10.0)
        assert m["speaker"] == "访谈者"
        by_id = {s["id"]: s for s in m["segments"]}
        assert by_id["s1"]["ranges"] == [[5, 9]]  # 接受访谈
        assert by_id["s2"]["ranges"] == [[0, 2], [3, 5]]  # 我们聊聊

        # speaker boundary must never be bridged
        r = c.post(f"/api/projects/{pid}/quote-search",
                   json={"query": "我叫李明后来"}).json()
        assert r["total"] == 0
        # time gap must never be bridged
        assert c.post(f"/api/projects/{pid}/quote-search",
                      json={"query": "改制最早全靠手摇"}).json()["total"] == 0

        # optional speaker filter
        r = c.post(f"/api/projects/{pid}/quote-search",
                   json={"query": "改制", "speaker": "受访者"}).json()
        assert r["total"] == 1
        assert r["matches"][0]["segmentIds"] == ["s4"]
        assert c.post(f"/api/projects/{pid}/quote-search",
                      json={"query": "改制", "speaker": "路人"}).json()["total"] == 0

        # case-sensitive flag
        doc_en = {
            "segments": [{"id": "e1", "start": 0, "end": 1,
                          "speaker": "A", "text": "Hello there"}],
            "annotations": [],
        }
        assert c.post(f"/api/projects/{pid}/quote-search",
                      json={"query": "hello", "document": doc_en}
                      ).json()["total"] == 1
        assert c.post(f"/api/projects/{pid}/quote-search",
                      json={"query": "hello", "caseSensitive": True,
                            "document": doc_en}
                      ).json()["total"] == 0

        # editor's unsaved document is searchable and not persisted
        unsaved = {
            "segments": [
                {"id": "u1", "start": 0, "end": 2,
                 "speaker": "甲", "text": "尚未保存的内容"},
            ],
            "annotations": [],
        }
        r = c.post(f"/api/projects/{pid}/quote-search",
                   json={"query": "尚未保存", "document": unsaved}).json()
        assert r["total"] == 1
        again = c.get(f"/api/projects/{pid}").json()
        assert [s["id"] for s in again["document"]["segments"]][0] == "s1"

        print("ALL QUOTE SEARCH API TESTS PASSED")


if __name__ == "__main__":
    run()
    shutil.rmtree(_TMP, ignore_errors=True)
