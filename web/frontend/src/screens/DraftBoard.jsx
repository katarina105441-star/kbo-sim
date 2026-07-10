import React, { useMemo, useState } from 'react'
import { api } from '../api.js'

const POSITIONS = ['전체', '투수', '야수', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'SP', 'RP', 'CL']

export default function DraftBoard({ draft, onDraftChange, onComplete }) {
  const [position, setPosition] = useState('전체')
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const candidates = useMemo(() => {
    const rows = draft.candidates || []
    if (position === '전체') return rows
    if (position === '투수' || position === '야수') return rows.filter(p => p.type === position)
    return rows.filter(p => p.pos === position)
  }, [draft, position])

  const execute = async (fn) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await fn()
      setMessage(`${result.selected.round}라운드 ${result.selected.name} (${result.selected.pos}) 지명`)
      setSelected('')
      if (result.season_started) onComplete(result.game_state)
      else onDraftChange(result.draft)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const pick = () => {
    const player = draft.candidates.find(p => p.pid === selected)
    if (!player) return
    if (!window.confirm(`${player.name} (${player.age}세 ${player.pos})을 지명할까요?`)) return
    execute(() => api.draftPick(player.pid))
  }

  const autoPick = () => {
    const player = draft.candidates.find(p => p.recommended)
    const label = player ? `${player.name} (${player.pos})` : 'AI 추천 선수'
    if (!window.confirm(`${label}을 자동 지명할까요?`)) return
    execute(api.draftAutoPick)
  }

  return <section className="draft-board">
    <div className="draft-header">
      <div>
        <h2>{draft.year}년 신인 드래프트</h2>
        <p className="muted">{draft.round}라운드 · 전체 {draft.overall_pick}번째 지명 · 남은 유망주 {draft.remaining_pool}명</p>
      </div>
      <div className="draft-turn">
        <span>{draft.team.name}</span>
        <b>{draft.user_turn ? '우리 팀 지명 차례' : 'AI 진행 중'}</b>
      </div>
    </div>

    <div className="draft-needs">
      <b>포지션 수요</b>
      {draft.needs.length === 0
        ? <span className="muted">뚜렷한 약점 없음</span>
        : draft.needs.map(n => <span key={n.pos}>{n.pos} {n.score.toFixed(2)}</span>)}
      <span className="muted">현재 로스터 {draft.roster_count}/25</span>
    </div>

    {message && <div className="notice ok">{message}</div>}
    {error && <div className="notice bad">{error}</div>}

    <div className="draft-toolbar">
      <select value={position} onChange={e => setPosition(e.target.value)}>
        {POSITIONS.map(pos => <option key={pos}>{pos}</option>)}
      </select>
      <span className="muted">실제 능력치는 숨겨져 있으며 스카우팅 평가에는 오차가 있습니다.</span>
      <button disabled={busy} onClick={autoPick}>AI 추천 지명</button>
      <button className="primary" disabled={busy || !selected} onClick={pick}>선택 선수 지명</button>
    </div>

    <div className="draft-table-wrap">
      <table className="dense draft-table">
        <thead><tr>
          <th>선택</th><th>보드</th><th className="tl">이름</th><th>나이</th><th>포지션</th>
          <th>투/타</th><th>등급</th><th>평가값</th><th>팀 수요</th><th>종합 적합</th><th>비고</th>
        </tr></thead>
        <tbody>
          {candidates.map(player => <tr key={player.pid}
              className={`${selected === player.pid ? 'draft-selected' : ''} ${player.recommended ? 'draft-recommended' : ''}`}
              onClick={() => setSelected(player.pid)}>
            <td><input type="radio" name="draft-player" checked={selected === player.pid}
                       onChange={() => setSelected(player.pid)} /></td>
            <td>{player.scout_rank}</td>
            <td className="tl"><b>{player.name}</b></td>
            <td>{player.age}</td><td>{player.pos}</td>
            <td>{player.throws}/{player.bats}</td>
            <td><span className={`scout-grade grade-${player.scout_grade}`}>{player.scout_grade}</span></td>
            <td>{player.scout_score.toFixed(2)}</td>
            <td>{player.need_bonus.toFixed(2)}</td>
            <td><b>{player.fit_score.toFixed(2)}</b></td>
            <td>{player.recommended ? <span className="recommend-tag">AI 추천</span> : ''}</td>
          </tr>)}
        </tbody>
      </table>
    </div>

    <div className="draft-results">
      <h3>지명 현황</h3>
      {draft.results.length === 0
        ? <p className="muted">아직 지명 결과가 없습니다.</p>
        : <div className="pick-log">{draft.results.slice(-20).reverse().map((pick, i) =>
            <div key={`${pick.round}-${pick.tid}-${pick.pid}-${i}`}>
              <span>{pick.round}R</span><b>{pick.tid}</b><span>{pick.name}</span><span>{pick.age}세 {pick.pos}</span>
            </div>)}</div>}
    </div>
  </section>
}
