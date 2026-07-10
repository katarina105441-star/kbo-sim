import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const baseLabel = (bases) => ['1루', '2루', '3루'].filter((_, i) => bases[i]).join(' · ') || '주자 없음'

export default function LiveGame({ initial, onClose, onFinished }) {
  const [data, setData] = useState(initial)
  const [logs, setLogs] = useState(initial.events || [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pitcher, setPitcher] = useState('')

  useEffect(() => {
    const relievers = data.state?.available_relievers || []
    if (!relievers.some(p => p.pid === pitcher)) setPitcher(relievers[0]?.pid || '')
  }, [data.state])

  const apply = async (fn) => {
    setBusy(true); setError('')
    try {
      const next = await fn()
      setData(next)
      if (next.events?.length) setLogs(old => [...old, ...next.events])
      if (next.done) onFinished?.(next)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const s = data.state
  const meta = data.meta
  const userFielding = s.fielding_side === meta.user_side
  const canPitch = !data.done && userFielding && s.can_change_pitcher

  return <div className="live-game">
    <header className="live-top">
      <div>
        <b>실시간 운영 · {meta.away.name} @ {meta.home.name}</b>
        <span className="muted"> {meta.day}일차</span>
      </div>
      <button className="ghost dark" onClick={onClose}>✕ 닫기</button>
    </header>

    <div className="live-score">
      <span>{meta.away.tid} <b>{s.score[0]}</b></span>
      <span>{s.done ? '경기 종료' : `${s.inning}회${s.half}`}</span>
      <span>{meta.home.tid} <b>{s.score[1]}</b></span>
    </div>

    <main className="live-layout">
      <section className="card live-status">
        <h2>현재 상황</h2>
        {!s.done && <>
          <div className="live-situation">
            <div><b>{s.outs}사</b><span>{baseLabel(s.bases)}</span></div>
            <div><small>타자</small><b>{s.next_batter?.name}</b>
              <span>{s.next_batter?.order}번 · {s.next_batter?.bats}타</span></div>
            <div><small>투수</small><b>{s.pitcher?.name}</b>
              <span>{s.pitcher?.pitches}구{s.pitcher?.fatigued ? ' · 피로 ▼' : ''}</span></div>
          </div>

          <div className="live-actions">
            <button className="primary" disabled={busy} onClick={() => apply(api.liveStep)}>다음 타석 ▶</button>
            <button disabled={busy} onClick={() => {
              if (window.confirm('남은 경기를 자동으로 진행할까요?')) apply(api.liveAuto)
            }}>자동 완료 ⏭</button>
          </div>

          <div className="pitcher-change">
            <h3>투수 교체</h3>
            {canPitch ? <div className="pitcher-row">
              <select value={pitcher} onChange={e => setPitcher(e.target.value)}>
                {s.available_relievers.map(p => <option key={p.pid} value={p.pid}>
                  {p.name} ({p.pos}) · OVR {Math.round(p.ovr)} · STA {p.stamina}
                </option>)}
              </select>
              <button disabled={busy || !pitcher} onClick={() => apply(() => api.livePitcher(pitcher))}>교체</button>
            </div> : <p className="muted">
              {!userFielding ? '우리 팀 공격 중에는 투수를 교체할 수 없습니다.'
                : '현재 교체 가능한 투수가 없습니다.'}
            </p>}
          </div>
        </>}

        {s.done && data.result && <div className="live-final">
          <h2>경기 종료</h2>
          <p>{meta.away.tid} {data.result.away.runs} : {data.result.home.runs} {meta.home.tid}</p>
          <button className="primary" onClick={onClose}>결과 확인</button>
        </div>}
        {error && <div className="notice bad">{error}</div>}
      </section>

      <section className="card live-log">
        <h2>경기 로그</h2>
        {logs.length === 0 ? <p className="muted">다음 타석을 진행하세요.</p> :
          logs.filter(e => e.text).slice(-30).map((e, i) =>
            <div className="log-line" key={`${e.seed || i}-${i}`}>{e.text}</div>)}
      </section>
    </main>
  </div>
}
