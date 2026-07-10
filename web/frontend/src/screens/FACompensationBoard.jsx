import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

function PlayerTable({ players, mode, selected, onToggle, busy, onChoose }) {
  if (!players.length) return <p className="muted">선택 가능한 선수가 없습니다.</p>
  return <div className="comp-table-wrap"><table className="dense comp-table">
    <thead><tr>
      {mode === 'protect' && <th>보호</th>}
      <th className="tl">선수</th><th>구분</th><th>나이</th><th>포지션</th>
      <th>OVR</th><th>POT</th><th>연봉</th><th>가치</th>
      {mode === 'select' && <th>선택</th>}
    </tr></thead>
    <tbody>{players.map(player => <tr key={player.pid}>
      {mode === 'protect' && <td><input type="checkbox" checked={selected.has(player.pid)}
        disabled={busy} onChange={() => onToggle(player.pid)} /></td>}
      <td className="tl"><b>{player.name}</b></td>
      <td>{player.level === 'active' ? '1군' : '2군'}</td>
      <td>{player.age}</td><td>{player.pos}</td><td><b>{Math.round(player.ovr)}</b></td>
      <td>{Math.round(player.pot)}</td><td>{player.salary.toFixed(2)}억</td><td>{player.value.toFixed(2)}억</td>
      {mode === 'select' && <td><button disabled={busy} onClick={() => onChoose(player)}>
        보상선수 지명</button></td>}
    </tr>)}</tbody>
  </table></div>
}

export default function FACompensationBoard({ market, onMarketChange, onComplete }) {
  const s = market.signing
  const [selected, setSelected] = useState(new Set(market.recommended_protected || []))
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    setSelected(new Set(market.recommended_protected || []))
  }, [market.index, market.mode])

  const chosen = useMemo(() => selected.size, [selected])
  const toggle = (pid) => setSelected(current => {
    const next = new Set(current)
    if (next.has(pid)) next.delete(pid)
    else if (next.size < s.protection_count) next.add(pid)
    return next
  })

  const apply = async (fn) => {
    setBusy(true); setMessage(''); setError('')
    try {
      const response = await fn()
      const result = response.result
      if (result?.kind === 'player') {
        setMessage(`${result.fa_name} 보상으로 ${result.player.name} + ${result.cash.toFixed(2)}억을 확정했습니다.`)
      } else if (result) {
        setMessage(`${result.fa_name} 보상으로 현금 ${result.cash.toFixed(2)}억을 확정했습니다.`)
      }
      if (response.compensation_complete) onComplete(response)
      else onMarketChange(response.compensation)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const submitProtection = () => {
    if (chosen !== s.protection_count) return
    if (!window.confirm(`${s.protection_count}명을 보호선수로 제출할까요? 제출 후 상대 구단이 보상 방식을 결정합니다.`)) return
    apply(() => api.compensationProtect([...selected]))
  }

  const choosePlayer = (player) => {
    if (!window.confirm(`${player.name}을(를) 보상선수로 지명하고 현금 ${s.player_cash.toFixed(2)}억을 받을까요?`)) return
    apply(() => api.compensationPlayer(player.pid))
  }

  return <section className="comp-board">
    <div className="comp-header">
      <div>
        <h2>FA 보상선수</h2>
        <p className="muted">{market.index}/{market.total}번째 보상 건</p>
      </div>
      <button disabled={busy} onClick={() => {
        if (window.confirm('남은 FA 보상 절차를 AI에게 맡길까요?')) apply(api.compensationAutoFinish)
      }}>남은 보상 자동 처리</button>
    </div>

    {message && <div className="notice ok">{message}</div>}
    {error && <div className="notice bad">{error}</div>}

    <div className="comp-summary">
      <div className={`fa-grade grade-${s.grade.toLowerCase()}`}>{s.grade}</div>
      <div><h3>{s.name}</h3><p>{s.from_tid} → {s.to_tid} · AAV {s.aav.toFixed(2)}억</p></div>
      <div className="comp-options">
        <span>현금만 <b>{s.full_cash.toFixed(2)}억</b></span>
        <span>선수 포함 <b>선수 1명 + {s.player_cash.toFixed(2)}억</b></span>
      </div>
    </div>

    {market.mode === 'protect' ? <>
      <div className="comp-instruction">
        <h3>우리 팀 보호선수 명단 제출</h3>
        <p>영입한 FA를 제외한 보유 선수 중 <b>{s.protection_count}명</b>을 보호해야 합니다.
          원소속팀 AI는 비보호선수와 현금 보상을 비교해 결정합니다.</p>
        <div className="comp-count">선택 {chosen}/{s.protection_count}</div>
      </div>
      <PlayerTable players={market.protectable} mode="protect" selected={selected}
        onToggle={toggle} busy={busy} />
      <div className="comp-actions">
        <button className="primary" disabled={busy || chosen !== s.protection_count}
          onClick={submitProtection}>보호명단 제출</button>
        <button disabled={busy} onClick={() => apply(api.compensationAutoProtect)}>AI 추천 명단 즉시 제출</button>
      </div>
    </> : <>
      <div className="comp-instruction">
        <h3>상대 구단 비보호선수 선택</h3>
        <p>보상선수를 지명하면 현금은 {s.player_cash.toFixed(2)}억, 선수를 포기하면 현금 {s.full_cash.toFixed(2)}억을 받습니다.</p>
      </div>
      <PlayerTable players={market.candidates} mode="select" selected={new Set()}
        busy={busy} onChoose={choosePlayer} />
      <div className="comp-actions">
        <button className="primary" disabled={busy} onClick={() => {
          if (window.confirm(`보상선수 없이 현금 ${s.full_cash.toFixed(2)}억만 받을까요?`)) apply(api.compensationCash)
        }}>현금 보상 선택</button>
        <button disabled={busy} onClick={() => apply(api.compensationAuto)}>AI 추천 결정</button>
      </div>
    </>}

    {market.results.length > 0 && <div className="comp-results">
      <h3>보상 처리 현황</h3>
      <ul className="news">{market.results.slice(-10).reverse().map((r, i) => <li key={`${r.pid}-${i}`}>
        {r.fa_name}: {r.kind === 'player' ? `${r.player.name} + ${r.cash.toFixed(2)}억` : `현금 ${r.cash.toFixed(2)}억`}
      </li>)}</ul>
    </div>}
  </section>
}
