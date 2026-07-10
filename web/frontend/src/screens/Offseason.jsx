import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import TradeBoard from './TradeBoard.jsx'
import FABoard from './FABoard.jsx'
import DraftBoard from './DraftBoard.jsx'

export default function Offseason({ state, onState }) {
  const [report, setReport] = useState([])
  const [trade, setTrade] = useState(null)
  const [fa, setFa] = useState(null)
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    const [reports, tradeState, faState, draftState] = await Promise.all([
      api.offseason().catch(() => []),
      api.tradeState().catch(() => null),
      api.faState().catch(() => null),
      api.draftState().catch(() => null),
    ])
    setReport(reports)
    setTrade(tradeState?.active ? tradeState : null)
    setFa(faState?.active ? faState : null)
    setDraft(draftState?.active ? draftState : null)
    setLoading(false)
  }

  useEffect(() => { load() }, [state.year, state.day])

  const completeTrade = async (result) => {
    setTrade(null)
    setReport(await api.offseason().catch(() => []))
    if (result.fa_active) {
      const faState = await api.faState().catch(() => null)
      setFa(faState?.active ? faState : null)
    } else {
      onState(result.game_state || await api.state())
    }
  }

  const completeFA = async (result) => {
    setFa(null)
    setReport(await api.offseason().catch(() => []))
    if (result.draft_active) {
      const draftState = await api.draftState().catch(() => null)
      setDraft(draftState?.active ? draftState : null)
    } else {
      onState(result.game_state || await api.state())
    }
  }

  const completeDraft = async (gameState) => {
    setDraft(null)
    if (gameState) onState(gameState)
    else onState(await api.state())
    setReport(await api.offseason().catch(() => []))
  }

  if (loading) return <section className="card">오프시즌 상태 확인 중…</section>

  return <div className="offseason-page">
    {trade && <TradeBoard market={trade} onMarketChange={setTrade} onComplete={completeTrade} />}
    {!trade && fa && <FABoard market={fa} onMarketChange={setFa} onComplete={completeFA} />}
    {!trade && !fa && draft && <DraftBoard draft={draft} onDraftChange={setDraft} onComplete={completeDraft} />}

    <section className="card">
      <h2>오프시즌 리포트 {state.year > 1 && <span className="muted">({state.year - 1}년차 종료 후)</span>}</h2>
      {state.postseason.length > 0 && <>
        <h3>포스트시즌</h3>
        <ul className="news">{state.postseason.map((line, i) => <li key={i}>{line}</li>)}</ul>
      </>}
      {report.length === 0
        ? <p className="muted">첫 시즌이 끝나면 에이징 → 트레이드 → FA → 드래프트 → 재정 순서로 진행됩니다.</p>
        : report.map(stage => <div key={stage.stage}>
            <h3>{stage.stage}
              {stage.stage === '트레이드' && trade && <span className="muted"> · 진행 중</span>}
              {stage.stage === 'FA' && fa && <span className="muted"> · 진행 중</span>}
              {stage.stage === '드래프트' && draft && <span className="muted"> · 진행 중</span>}
            </h3>
            <ul className="news">
              {stage.items.slice(0, 12).map((item, i) => <li key={i}>{item}</li>)}
              {stage.items.length > 12 && <li className="muted">외 {stage.items.length - 12}건</li>}
            </ul>
          </div>)}
    </section>
  </div>
}
