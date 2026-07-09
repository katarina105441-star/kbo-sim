import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import TeamSelect from './screens/TeamSelect.jsx'
import Dashboard from './screens/Dashboard.jsx'
import Standings from './screens/Standings.jsx'
import Results from './screens/Results.jsx'
import Roster from './screens/Roster.jsx'
import Offseason from './screens/Offseason.jsx'
import PlayerModal from './screens/PlayerModal.jsx'
import Watch from './screens/Watch.jsx'

const TABS = [
  ['dashboard', '대시보드'], ['standings', '순위표'], ['results', '일정·결과'],
  ['roster', '로스터'], ['offseason', '오프시즌'],
]

export default function App() {
  const [state, setState] = useState(null)      // 게임 상태 (null = 미시작)
  const [tab, setTab] = useState('dashboard')
  const [playerPid, setPlayerPid] = useState(null)
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState('')
  const [watch, setWatch] = useState(null)      // {day, idx} = 관전 중

  useEffect(() => { api.state().then(setState).catch(() => {}) }, [])

  const refresh = () => api.state().then(setState)
  const advance = async (unit) => {
    setBusy(true)
    try {
      const r = await api.advance(unit)
      setState(r.state)
      setFlash(`${r.played_days}일 진행`)
      setTimeout(() => setFlash(''), 2500)
    } finally { setBusy(false) }
  }
  const save = async () => { await api.save(); setFlash('저장 완료'); setTimeout(() => setFlash(''), 2000) }
  const load = async () => { setState(await api.load()); setFlash('불러오기 완료'); setTimeout(() => setFlash(''), 2000) }

  if (!state) return <TeamSelect onStart={async (tid, seed) => setState(await api.newGame(tid, seed))} onLoad={load} />

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">⚾ KBO 매니저</span>
        <span className="season-pos">{state.year}년차 · {state.day}/{state.days_total}일</span>
        <nav>
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? 'tab on' : 'tab'}
                    onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
        <span className="spacer" />
        {flash && <span className="flash">{flash}</span>}
        <button className="ghost" onClick={save}>저장</button>
        <button className="ghost" onClick={load}>불러오기</button>
      </header>
      <main>
        {tab === 'dashboard' && <Dashboard state={state} busy={busy} onAdvance={advance} />}
        {tab === 'standings' && <Standings userTid={state.user_tid} onTeam={() => setTab('roster')} />}
        {tab === 'results' && <Results userTid={state.user_tid}
                                       onWatch={(day, idx) => setWatch({ day, idx })} />}
        {tab === 'roster' && <Roster userTid={state.user_tid} onPlayer={setPlayerPid} />}
        {tab === 'offseason' && <Offseason state={state} />}
      </main>
      {playerPid && <PlayerModal pid={playerPid} onClose={() => setPlayerPid(null)} />}
      {watch && <Watch day={watch.day} gameIdx={watch.idx} userTid={state.user_tid}
                       onClose={() => setWatch(null)} />}
    </div>
  )
}
