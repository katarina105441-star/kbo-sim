import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import DraftBoard from './DraftBoard.jsx'

export default function Offseason({ state, onState }) {
  const [report, setReport] = useState([])
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    const [reports, draftState] = await Promise.all([
      api.offseason().catch(() => []),
      api.draftState().catch(() => null),
    ])
    setReport(reports)
    setDraft(draftState?.active ? draftState : null)
    setLoading(false)
  }

  useEffect(() => { load() }, [state.year, state.day])

  const completeDraft = async (gameState) => {
    setDraft(null)
    if (gameState) onState(gameState)
    else onState(await api.state())
    setReport(await api.offseason().catch(() => []))
  }

  if (loading) return <section className="card">오프시즌 상태 확인 중…</section>

  return <div className="offseason-page">
    {draft && <DraftBoard draft={draft} onDraftChange={setDraft} onComplete={completeDraft} />}

    <section className="card">
      <h2>오프시즌 리포트 {state.year > 1 && <span className="muted">({state.year - 1}년차 종료 후)</span>}</h2>
      {state.postseason.length > 0 && <>
        <h3>포스트시즌</h3>
        <ul className="news">{state.postseason.map((line, i) => <li key={i}>{line}</li>)}</ul>
      </>}
      {report.length === 0
        ? <p className="muted">첫 시즌이 끝나면 에이징 → 트레이드 → FA → 드래프트 → 재정 순서로 진행됩니다.</p>
        : report.map(stage => <div key={stage.stage}>
            <h3>{stage.stage}{stage.stage === '드래프트' && draft && <span className="muted"> · 진행 중</span>}</h3>
            <ul className="news">
              {stage.items.slice(0, 12).map((item, i) => <li key={i}>{item}</li>)}
              {stage.items.length > 12 && <li className="muted">외 {stage.items.length - 12}건</li>}
            </ul>
          </div>)}
    </section>
  </div>
}
