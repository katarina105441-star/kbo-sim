import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Offseason({ state }) {
  const [report, setReport] = useState([])
  useEffect(() => { api.offseason().then(setReport) }, [state.year])

  return (
    <section className="card">
      <h2>오프시즌 리포트 {state.year > 1 && <span className="muted">({state.year - 1}년차 종료 후)</span>}</h2>
      {state.postseason.length > 0 && <>
        <h3>포스트시즌</h3>
        <ul className="news">{state.postseason.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </>}
      {report.length === 0
        ? <p className="muted">첫 시즌이 끝나면 에이징 → 트레이드 → FA → 드래프트 → 재정
            순서의 오프시즌 요약이 여기 표시됩니다. (MVP-1은 전자동, 개입은 MVP-2)</p>
        : report.map(r => (
          <div key={r.stage}>
            <h3>{r.stage}</h3>
            <ul className="news">
              {r.items.slice(0, 12).map((it, i) => <li key={i}>{it}</li>)}
              {r.items.length > 12 && <li className="muted">외 {r.items.length - 12}건</li>}
            </ul>
          </div>))}
    </section>
  )
}
