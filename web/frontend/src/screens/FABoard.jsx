import React, { useMemo, useState } from 'react'
import { api } from '../api.js'

export default function FABoard({ market, onMarketChange, onComplete }) {
  const p = market.player
  const m = market.market
  const suggested = Math.min(m.max_offer, Math.max(m.fair_aav, p.salary))
  const [aav, setAav] = useState(suggested.toFixed(2))
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const cost = useMemo(() => {
    const offer = Number(aav || 0)
    const comp = m.user_is_home ? 0 : m.compensation
    return offer + comp
  }, [aav, m])

  const apply = async (fn) => {
    setBusy(true); setMessage(''); setError('')
    try {
      const result = await fn()
      const r = result.result
      const outcome = r.accepted_user_offer
        ? `${r.name} 영입 성공: ${r.years}년·AAV ${r.aav.toFixed(2)}억`
        : r.user_offered
          ? `${r.name}이(가) ${r.to_tid}을 선택했습니다.`
          : `${r.name}: ${r.from_tid} → ${r.to_tid}, AAV ${r.aav.toFixed(2)}억`
      setMessage(outcome)
      if (result.fa_complete) onComplete(result)
      else {
        onMarketChange(result.fa)
        const next = result.fa
        const nextSuggested = Math.min(next.market.max_offer,
          Math.max(next.market.fair_aav, next.player.salary))
        setAav(nextSuggested.toFixed(2))
      }
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const offer = () => {
    const value = Number(aav)
    if (!Number.isFinite(value) || value <= 0) return
    if (!window.confirm(`${p.name}에게 ${m.years}년·AAV ${value.toFixed(2)}억을 제안할까요?`)) return
    apply(() => api.faOffer(value))
  }

  const statLine = p.is_pitcher
    ? `${p.pit_line.w}승 ${p.pit_line.l}패 ${p.pit_line.sv}세 · ${p.pit_line.ip.toFixed(1)}이닝 · ERA ${p.pit_line.era.toFixed(2)}`
    : `타율 ${p.bat_line.avg.toFixed(3)} · ${p.bat_line.hr}홈런 · ${p.bat_line.rbi}타점 · OPS ${p.bat_line.ops.toFixed(3)}`

  return <section className="fa-board">
    <div className="fa-header">
      <div>
        <h2>{market.year}년 FA 시장</h2>
        <p className="muted">{market.index}/{market.declared}번째 선수 · 봉인식 단발 입찰</p>
      </div>
      <button disabled={busy} onClick={() => {
        if (window.confirm('남은 FA 시장을 기존 AI 방식으로 모두 처리할까요?')) apply(api.faAutoFinish)
      }}>남은 시장 자동 처리</button>
    </div>

    {message && <div className="notice ok">{message}</div>}
    {error && <div className="notice bad">{error}</div>}

    <div className="fa-player-grid">
      <div className="fa-player-card">
        <div className="fa-grade">{p.grade}</div>
        <div>
          <h3>{p.name} <span>{p.age}세 · {p.pos}</span></h3>
          <p>{p.team_id} · OVR {Math.round(p.ovr)} · 기존 연봉 {p.salary.toFixed(2)}억</p>
          <p className="muted">{statLine}</p>
        </div>
      </div>
      <div className="fa-market-card">
        <div><span>시장 적정 AAV</span><b>{m.fair_aav.toFixed(2)}억</b></div>
        <div><span>계약 기간</span><b>{m.years}년</b></div>
        <div><span>보상금</span><b>{m.user_is_home ? '없음' : `${m.compensation.toFixed(2)}억`}</b></div>
        <div><span>경쟁 구단</span><b>{m.competitors}팀</b></div>
        <div><span>우리 팀 포지션 수요</span><b>{(m.user_need * 100).toFixed(0)}%</b></div>
      </div>
    </div>

    <div className="fa-offer-box">
      <div className="fa-budget-line">
        <span>구단 예산 <b>{m.user_budget.toFixed(2)}억</b></span>
        <span>이번 시장 누적 비용 <b>{m.user_spent.toFixed(2)}억</b></span>
        <span>외부 영입 {m.user_signings}/{m.signing_limit}</span>
      </div>
      <label>
        제안 AAV
        <input type="number" min="0" step="0.1" value={aav}
               onChange={e => setAav(e.target.value)} disabled={!m.can_offer || busy} />
        <span>억 × {m.years}년</span>
      </label>
      <p className="muted">최대 제안 가능 {m.max_offer.toFixed(2)}억 · 이번 계약의 첫해 시장비용 약 {cost.toFixed(2)}억</p>
      <div className="fa-actions">
        <button className="primary" disabled={busy || !m.can_offer || Number(aav) <= 0} onClick={offer}>직접 제안</button>
        <button disabled={busy} onClick={() => apply(api.faPass)}>패스</button>
        <button disabled={busy} onClick={() => apply(api.faAuto)}>기존 AI 판단</button>
      </div>
    </div>

    <div className="fa-results">
      <h3>시장 계약 현황</h3>
      {market.results.length === 0 ? <p className="muted">아직 완료된 계약이 없습니다.</p> :
        <table className="dense"><thead><tr><th>등급</th><th className="tl">선수</th><th>포지션</th><th>이동</th><th>계약</th><th>보상금</th></tr></thead>
          <tbody>{market.results.slice(-15).reverse().map(r => <tr key={r.pid}>
            <td>{r.grade}</td><td className="tl">{r.name}</td><td>{r.pos}</td>
            <td>{r.from_tid} → {r.to_tid}</td><td>{r.years}년·{r.aav.toFixed(2)}억</td><td>{r.comp.toFixed(2)}억</td>
          </tr>)}</tbody></table>}
    </div>
  </section>
}
