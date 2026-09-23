import { useState } from 'react'
import { api } from '../api.js'
import { fmtTime } from '../utils.js'

/**
 * Render text with the engine's [start, end) character ranges highlighted.
 */
function MarkedText({ text, ranges }) {
  if (!ranges || ranges.length === 0) return <>{text}</>
  const parts = []
  let cursor = 0
  ranges.forEach(([lo, hi], i) => {
    if (lo > cursor) parts.push(<span key={`t${i}`}>{text.slice(cursor, lo)}</span>)
    parts.push(<mark key={`m${i}`}>{text.slice(lo, hi)}</mark>)
    cursor = hi
  })
  if (cursor < text.length) parts.push(<span key="rest">{text.slice(cursor)}</span>)
  return <>{parts}</>
}

/**
 * Quote (spoken phrase) search panel.
 * Props:
 *   projectId
 *   document      current editor document (unsaved edits are searchable)
 *   speakers      known speaker names for the optional datalist
 *   activeMatch   match currently located on the timeline
 *   onLocate(match, query)
 */
export default function QuoteSearch({
  projectId, document, speakers = [], activeMatch, onLocate,
}) {
  const [query, setQuery] = useState('')
  const [speaker, setSpeaker] = useState('')
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // whitespace-only phrase never triggers a search
  const canSearch = query.trim().length > 0

  const runSearch = async () => {
    if (!canSearch) return
    setLoading(true)
    setError('')
    try {
      const r = await api.quoteSearch(projectId, {
        query, speaker, caseSensitive, document,
      })
      setResult(r)
    } catch (e) {
      setResult(null)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      runSearch()
    }
  }

  return (
    <div className="panel quote-search">
      <details open>
        <summary>
          <strong>🔎 引语检索</strong>
          <span className="muted small qs-summary-hint">
            跨时间相接、同一说话人的片段查找引语（忽略空白）
          </span>
        </summary>
        <div className="qs-controls">
          <input
            className="qs-query"
            value={query}
            placeholder="输入引语短语，如：后来2003年改制"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <input
            className="qs-speaker"
            list="qs-speaker-list"
            value={speaker}
            placeholder="说话人（可选，精确匹配）"
            onChange={(e) => setSpeaker(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <datalist id="qs-speaker-list">
            {[...new Set(speakers)].map((s) => <option key={s} value={s} />)}
          </datalist>
          <label className="qs-case">
            <input
              type="checkbox"
              checked={caseSensitive}
              onChange={(e) => setCaseSensitive(e.target.checked)}
            />
            区分大小写
          </label>
          <button
            className="btn primary"
            disabled={!canSearch || loading}
            onClick={runSearch}
          >
            {loading ? '检索中…' : '检索'}
          </button>
        </div>
        {!canSearch && (
          <div className="muted small qs-hint">输入引语内容后才能检索（空白查询不执行）。</div>
        )}
        {error && <div className="error">{error}</div>}

        {result && !error && (
          <div className="qs-results">
            <div className="qs-count">
              命中 <strong>{result.total}</strong> 处
              {result.speaker ? ` · 说话人：${result.speaker}` : ''}
            </div>
            {result.total === 0 && (
              <div className="empty-hint">
                未找到该引语。注意：引语不能跨越说话人切换或时间空隙。
              </div>
            )}
            {result.matches.map((m) => (
              <div
                key={`${m.start}-${m.end}-${m.segmentIds.join('|')}`}
                className={`qs-hit ${
                  activeMatch && activeMatch.start === m.start
                  && activeMatch.end === m.end ? 'active' : ''
                }`}
                onClick={() => onLocate(m, query)}
                title="点击在时间轴上定位"
              >
                <div className="qs-hit-head">
                  <span className="qs-hit-range">
                    {fmtTime(m.start)} – {fmtTime(m.end)}
                  </span>
                  <span className="tag">{m.speaker || '（无说话人）'}</span>
                  {m.crossSegment && (
                    <span className="tag">跨 {m.segmentIds.length} 个片段</span>
                  )}
                  <span className="qs-hit-ids muted small">
                    {m.segmentIds.join('、')}
                  </span>
                </div>
                <div className="qs-hit-segments">
                  {m.segments.map((s) => (
                    <div className="qs-hit-seg" key={s.id}>
                      <span className="muted small qs-hit-seg-time">
                        [{fmtTime(s.start)}–{fmtTime(s.end)}]
                      </span>{' '}
                      <MarkedText text={s.text} ranges={s.ranges} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </details>
    </div>
  )
}
