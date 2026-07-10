import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const playerLabel = (p) => `${p.name} (${p.pos}) · OVR ${Math.round(p.ovr)}`

export default function SubstitutionControls({ state, userSide, busy, apply }) {
  const batting = state.batting_side === userSide
  const fielding = state.fielding_side === userSide
  const bat = state.batting_substitutions
  const fld = state.fielding_substitutions
  const [ph, setPh] = useState('')
  const [pr, setPr] = useState('')
  const [base, setBase] = useState('')
  const [outPid, setOutPid] = useState('')
  const [defPid, setDefPid] = useState('')

  const battingBench = batting ? (bat?.bench || []) : []
  const runners = batting ? (bat?.runners || []) : []
  const fielders = fielding ? (fld?.lineup || []).filter(p => p.slot !== 'DH') : []
  const selectedFielder = fielders.find(p => p.pid === outPid)
  const defenseBench = useMemo(() => {
    if (!fielding || !selectedFielder) return []
    return (fld?.bench || []).filter(p => p.pos === selectedFielder.slot)
  }, [fielding, selectedFielder, fld])

  useEffect(() => {
    if (!battingBench.some(p => p.pid === ph)) setPh(battingBench[0]?.pid || '')
    if (!battingBench.some(p => p.pid === pr)) setPr(battingBench[0]?.pid || '')
    if (!runners.some(r => String(r.base) === String(base))) setBase(runners[0]?.base ? String(runners[0].base) : '')
  }, [state])

  useEffect(() => {
    if (!fielders.some(p => p.pid === outPid)) setOutPid(fielders[0]?.pid || '')
  }, [state, fielding])

  useEffect(() => {
    if (!defenseBench.some(p => p.pid === defPid)) setDefPid(defenseBench[0]?.pid || '')
  }, [outPid, state])

  if (!batting && !fielding) return null

  return <div className="substitution-panel">
    <h3>야수 교체</h3>
    {batting && <>
      <div className="sub-row">
        <span className="sub-label">대타</span>
        <span className="sub-target">{state.next_batter?.order}번 {state.next_batter?.name} 대신</span>
        <select value={ph} onChange={e => setPh(e.target.value)}>
          {battingBench.map(p => <option key={p.pid} value={p.pid}>{playerLabel(p)}</option>)}
        </select>
        <button disabled={busy || !ph} onClick={() => apply(() => api.livePinchHitter(ph))}>투입</button>
      </div>

      <div className="sub-row">
        <span className="sub-label">대주자</span>
        <select className="base-select" value={base} onChange={e => setBase(e.target.value)}>
          {runners.map(r => <option key={r.base} value={r.base}>{r.base}루 · {r.name}</option>)}
        </select>
        <select value={pr} onChange={e => setPr(e.target.value)}>
          {battingBench.map(p => <option key={p.pid} value={p.pid}>{playerLabel(p)} · 주루 {p.speed}</option>)}
        </select>
        <button disabled={busy || !base || !pr}
                onClick={() => apply(() => api.livePinchRunner(Number(base), pr))}>투입</button>
      </div>
      {battingBench.length === 0 && <p className="muted">사용 가능한 야수 벤치가 없습니다.</p>}
      {runners.length === 0 && <p className="muted">현재 대주자로 바꿀 주자가 없습니다.</p>}
    </>}

    {fielding && <div className="sub-row">
      <span className="sub-label">대수비</span>
      <select value={outPid} onChange={e => setOutPid(e.target.value)}>
        {fielders.map(p => <option key={p.pid} value={p.pid}>{p.slot} · {p.name}</option>)}
      </select>
      <select value={defPid} onChange={e => setDefPid(e.target.value)}>
        {defenseBench.map(p => <option key={p.pid} value={p.pid}>
          {p.name} · 수비 {p.fielding} · OVR {Math.round(p.ovr)}
        </option>)}
      </select>
      <button disabled={busy || !outPid || !defPid}
              onClick={() => apply(() => api.liveDefense(outPid, defPid))}>투입</button>
      {selectedFielder && defenseBench.length === 0 &&
        <span className="muted sub-note">{selectedFielder.slot} 주 포지션 벤치 없음</span>}
    </div>}
  </div>
}
