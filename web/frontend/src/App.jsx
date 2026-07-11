import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import './live.css'
import './draft.css'
import './fa.css'
import './fa-compensation.css'
import './trade.css'
import './development.css'
import './team-identity.css'
import './front-office.css'
import './engagement.css'
import './manager-career.css'
import './onboarding.css'
import TeamSelect from './screens/TeamSelect.jsx'
import Dashboard from './screens/Dashboard.jsx'
import Standings from './screens/Standings.jsx'
import Results from './screens/Results.jsx'
import Roster from './screens/Roster.jsx'
import Lineup from './screens/Lineup.jsx'
import Development from './screens/Development.jsx'
import Offseason from './screens/Offseason.jsx'
import PlayerModal from './screens/PlayerModal.jsx'
import Watch from './screens/Watch.jsx'
import LiveGame from './screens/LiveGame.jsx'
import HelpModal from './components/HelpModal.jsx'

const TABS = [
  ['dashboard', '대시보드'], ['standings', '순위표'], ['results', '일정·결과'],
  ['roster', '로스터'], ['lineup', '라인업 관리'], ['development', '2군·육성'],
  ['offseason', '오프시즌'],
]
const GUIDE_KEY = 'kbo-manager-guide-v1'

export default function App() {
  const [state, setState] = useState(null)
  const [tab, setTab] = useState('dashboard')
  const [playerPid, setPlayerPid] = useState(null)
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState('')
  const [watch, setWatch] = useState(null)
  const [live, setLive] = useState(null)
  const [rev, setRev] = useState(0)
  const [help, setHelp] = useState(false)
  const [welcomeHelp, setWelcomeHelp] = useState(false)
  const [meta, setMeta] = useState(null)

  const notify = (message, duration = 2600) => {
    setFlash(message)
    window.setTimeout(() => setFlash(''), duration)
  }

  const openOffseasonIfActive = async () => {
    const active = await Promise.all([
      api.tradeState().then(() => true).catch(() => false),
      api.faState().then(() => true).catch(() => false),
      api.compensationState().then(() => true).catch(() => false),
      api.draftState().then(() => true).catch(() => false),
    ])
    if (active.some(Boolean)) setTab('offseason')
  }

  useEffect(() => {
    api.meta().then(setMeta).catch(() => {})
    api.state().then(async next => {
      setState(next)
      await openOffseasonIfActive()
    }).catch(() => {})
  }, [])

  const closeHelp = () => {
    setHelp(false)
    setWelcomeHelp(false)
    try { window.localStorage.setItem(GUIDE_KEY, 'seen') } catch (_) {}
  }

  const refresh = () => api.state().then(setState)
  const advance = async unit => {
    setBusy(true)
    try {
      const response = await api.advance(unit)
      setState(response.state)
      if (unit === 'season_end') await openOffseasonIfActive()
      notify(`${response.played_days}일 진행`)
    } catch (e) {
      notify(e.message, 3400)
      if (e.message.includes('트레이드') || e.message.includes('FA') ||
          e.message.includes('보상선수') || e.message.includes('드래프트')) setTab('offseason')
    } finally { setBusy(false) }
  }

  const startLive = async () => {
    setBusy(true)
    try {
      const data = state.live_active ? await api.liveState() : await api.liveStart()
      setLive(data)
      await refresh()
    } catch (e) {
      notify(e.message, 3400)
    } finally { setBusy(false) }
  }

  const acceptCareerOffer = async nextState => {
    setLive(null)
    setState(nextState)
    notify(`새 구단 ${nextState.my_team.name} 부임`, 3200)
    await openOffseasonIfActive()
  }

  const save = async () => {
    try {
      await api.save()
      notify('저장 완료')
    } catch (e) {
      notify(`저장 실패: ${e.message}`, 3600)
    }
  }

  const load = async () => {
    setLive(null)
    const next = await api.load()
    setState(next)
    await openOffseasonIfActive()
    notify('불러오기 완료')
  }

  const startCareer = async (tid, seed) => {
    setLive(null)
    const next = await api.newGame(tid, seed)
    setState(next)
    setTab('dashboard')
    let seen = false
    try { seen = window.localStorage.getItem(GUIDE_KEY) === 'seen' } catch (_) {}
    if (!seen) {
      setWelcomeHelp(true)
      setHelp(true)
    }
  }

  if (!state) return <TeamSelect onStart={startCareer} onLoad={load} />

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
        {flash && <span className="flash" role="status">{flash}</span>}
        <button className="ghost help-trigger" onClick={() => { setWelcomeHelp(false); setHelp(true) }}>도움말</button>
        <button className="ghost" onClick={save}>저장</button>
        <button className="ghost" onClick={() => load().catch(e => notify(`불러오기 실패: ${e.message}`, 3600))}>불러오기</button>
      </header>
      <main>
        {tab === 'dashboard' && <Dashboard state={state} busy={busy}
                                             onAdvance={advance} onLive={startLive}
                                             onRefresh={refresh}
                                             onCareerAccepted={acceptCareerOffer} />}
        {tab === 'standings' && <Standings userTid={state.user_tid} onTeam={() => setTab('roster')} />}
        {tab === 'results' && <Results key={rev} userTid={state.user_tid}
                                       onWatch={(day, idx) => setWatch({ day, idx })} />}
        {tab === 'roster' && <Roster userTid={state.user_tid} onPlayer={setPlayerPid} />}
        {tab === 'lineup' && <Lineup />}
        {tab === 'development' && <Development onPlayer={setPlayerPid} />}
        {tab === 'offseason' && <Offseason state={state} onState={setState} />}
      </main>
      {playerPid && <PlayerModal pid={playerPid} onClose={() => setPlayerPid(null)} />}
      {watch && <Watch day={watch.day} gameIdx={watch.idx} userTid={state.user_tid}
                       onClose={() => { setWatch(null); setRev(r => r + 1); refresh() }} />}
      {live && <LiveGame initial={live}
                         onFinished={() => { setRev(r => r + 1); refresh() }}
                         onClose={() => { setLive(null); setRev(r => r + 1); refresh() }} />}
      {help && <HelpModal welcome={welcomeHelp} version={meta?.version || ''} onClose={closeHelp} />}
      <div className="version-stamp">v{meta?.version || '—'}</div>
    </div>
  )
}
