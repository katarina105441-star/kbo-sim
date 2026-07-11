import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import Field, { HOME, BASES } from './Field.jsx'

function buildSteps(events) {
  const steps = []
  ;(events || []).forEach((ev, ei) => {
    if (!ev || !ev.t) return
    if (ev.t === 'pa') {
      const seq = Array.isArray(ev.count_seq) ? ev.count_seq : []
      for (let i = 0; i < Math.max(0, seq.length - 1); i++) {
        steps.push({ kind: 'pitch', ev, ei, pitch: i })
      }
      steps.push({ kind: 'outcome', ev, ei })
    } else if (ev.t === 'steal') steps.push({ kind: 'steal', ev, ei })
    else if (ev.t === 'pitch_change') steps.push({ kind: 'change', ev, ei })
    else if (ev.t === 'half_end') steps.push({ kind: 'half', ev, ei })
    else if (ev.t === 'game_end') steps.push({ kind: 'end', ev, ei })
  })
  return steps
}

const DUR = { pitch: 650, outcome: 1900, steal: 900, change: 1100, half: 900, end: 0 }
const basePos = b => (b === 4 ? HOME : BASES[b])

function runnerTokens(ev, phase, animate, meTid, halfIsTop, awayTid) {
  if (!ev) return []
  const battingMe = halfIsTop ? awayTid === meTid : awayTid !== meTid
  const toks = []
  const before = Array.isArray(ev.bases_before) ? ev.bases_before : [null, null, null]
  const after = Array.isArray(ev.bases_after) ? ev.bases_after : [null, null, null]
  if (phase === 'pitch') {
    for (let i = 0; i < 3; i++) {
      if (before[i]) toks.push({
        key: `${ev.seed}-p${i}`, pid: before[i], me: battingMe, path: [basePos(i + 1)],
      })
    }
    return toks
  }
  const scoredRows = Array.isArray(ev.scored) ? ev.scored : []
  const scored = new Set(scoredRows.map(s => s.pid))
  for (let i = 0; i < 3; i++) {
    const pid = before[i]
    if (!pid) continue
    const from = i + 1
    let to = null
    if (scored.has(pid)) to = 4
    else {
      const j = after.indexOf(pid)
      to = j >= 0 ? j + 1 : null
    }
    if (to === null) continue
    const path = []
    for (let b = from; b <= to; b++) path.push(basePos(b))
    toks.push({
      key: `${ev.seed}-${pid}`,
      pid,
      me: battingMe,
      path: animate && to !== from ? path : [basePos(to === 4 ? from : to)],
    })
    if (to === 4 && !animate) toks.pop()
  }
  const batter = ev.batter || {}
  const bpid = batter.pid
  if (!bpid) return toks
  let bto = null
  if (scored.has(bpid)) bto = 4
  else {
    const j = after.indexOf(bpid)
    bto = j >= 0 ? j + 1 : null
  }
  if (bto !== null && !(bto === 4 && !animate)) {
    const path = [{ x: HOME.x, y: HOME.y }]
    for (let b = 1; b <= bto; b++) path.push(basePos(b))
    toks.push({
      key: `${ev.seed}-${bpid}`,
      pid: bpid,
      me: battingMe,
      path: animate ? path : [basePos(Math.min(bto, 3))],
    })
  }
  return toks
}

function ScoreBug({ meta, ev, count, outs, score, after }) {
  const dot = (on, cls) => <span className={`dot ${cls}${on ? ' on' : ''}`} />
  const bases = ev?.t === 'pa'
    ? (after ? ev.bases_after : ev.bases_before) || [null, null, null]
    : [null, null, null]
  return (
    <div className="scorebug">
      <span className="sb-team">{meta.away.tid} <b>{score[0]}</b></span>
      <span className="sb-team">{meta.home.tid} <b>{score[1]}</b></span>
      <span className="sb-inn">{ev?.inning ? `${ev.inning}회${ev.half}` : '경기 준비'}</span>
      <svg viewBox="0 0 40 40" className="sb-diamond">
        {[[20, 6, bases[1]], [32, 18, bases[0]], [8, 18, bases[2]]].map(([x, y, occ], i) => (
          <rect key={i} x={x - 6} y={y - 6} width="12" height="12"
                transform={`rotate(45 ${x} ${y})`}
                fill={occ ? '#ffb02e' : '#dde3ec'} />
        ))}
      </svg>
      <span className="sb-count">
        B {dot(count.b > 0, 'b')}{dot(count.b > 1, 'b')}{dot(count.b > 2, 'b')}<br />
        S {dot(count.s > 0, 's')}{dot(count.s > 1, 's')}<br />
        O {dot(outs > 0, 'o')}{dot(outs > 1, 'o')}
      </span>
    </div>
  )
}

function WatchGate({ state, error, onRetry, onClose }) {
  return (
    <div className="watch watch-gate">
      <header className="watch-top">
        <b>경기 관전</b>
        <span className="spacer" />
        <button className="ghost dark" onClick={onClose}>✕ 닫기</button>
      </header>
      <div className="watch-gate-card" role="status">
        {state === 'loading' ? <>
          <div className="watch-spinner" />
          <h2>중계 데이터를 불러오는 중입니다.</h2>
          <p>잠시 후에도 진행되지 않으면 재시도하거나 관전 화면을 닫으세요.</p>
        </> : <>
          <span className="watch-error-code">관전 데이터 오류</span>
          <h2>중계 화면을 열지 못했습니다.</h2>
          <p>{error || '경기 데이터 응답이 올바르지 않습니다.'}</p>
          <div className="btn-row">
            <button className="primary" onClick={onRetry}>다시 불러오기</button>
            <button onClick={onClose}>일정·결과로 돌아가기</button>
          </div>
        </>}
      </div>
    </div>
  )
}

export default function Watch({ day, gameIdx, userTid, onClose }) {
  const [meta, setMeta] = useState(null)
  const [events, setEvents] = useState([])
  const [nextFrom, setNextFrom] = useState(0)
  const [done, setDone] = useState(false)
  const [loadState, setLoadState] = useState('loading')
  const [loadError, setLoadError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const fetching = useRef(false)
  const mounted = useRef(true)
  const [si, setSi] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(1)
  const [jumped, setJumped] = useState(false)
  const [cards, setCards] = useState({})
  const logRef = useRef(null)

  useEffect(() => () => { mounted.current = false }, [])

  const fetchChunk = async frm => {
    if (fetching.current) return
    fetching.current = true
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 12000)
    try {
      const response = await fetch(`/api/watch/${day}/${gameIdx}?frm=${frm}`, {
        signal: controller.signal,
        cache: 'no-store',
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.detail || `중계 서버 오류 (HTTP ${response.status})`)
      if (!body || !body.meta || !Array.isArray(body.events)
          || !Number.isInteger(body.next) || typeof body.done !== 'boolean') {
        throw new Error('중계 서버가 불완전한 데이터를 반환했습니다.')
      }
      if (!mounted.current) return
      setMeta(current => current?.final ? current : body.meta)
      setEvents(current => frm === 0 ? body.events : [...current, ...body.events])
      setNextFrom(body.next)
      setDone(body.done)
      setLoadState('ready')
      setLoadError('')
    } catch (error) {
      if (!mounted.current) return
      const message = error?.name === 'AbortError'
        ? '중계 서버 응답이 12초 안에 도착하지 않았습니다.'
        : String(error?.message || error)
      setLoadError(message)
      setLoadState('error')
      setPlaying(false)
    } finally {
      window.clearTimeout(timeout)
      fetching.current = false
    }
  }

  const retry = () => {
    setMeta(null)
    setEvents([])
    setNextFrom(0)
    setDone(false)
    setSi(0)
    setPlaying(true)
    setLoadError('')
    setLoadState('loading')
    setRetryKey(value => value + 1)
  }

  useEffect(() => { fetchChunk(0) }, [day, gameIdx, retryKey])

  const steps = useMemo(() => buildSteps(events), [events])

  useEffect(() => {
    if (loadState === 'ready' && !done && steps.length - si < 60) fetchChunk(nextFrom)
  }, [si, steps.length, done, nextFrom, loadState])

  const step = steps[si]

  useEffect(() => {
    if (!playing || !step || step.kind === 'end') return
    const delay = (DUR[step.kind] || 900) / speed
    const timer = setTimeout(() => {
      setJumped(false)
      setSi(current => Math.min(current + 1, Math.max(0, steps.length - 1)))
    }, delay)
    return () => clearTimeout(timer)
  }, [playing, si, speed, step, steps.length])

  useEffect(() => {
    if (!step || step.ev.t !== 'pa') return
    for (const pid of [step.ev.batter?.pid, step.ev.pitcher?.pid].filter(Boolean)) {
      if (!cards[pid]) {
        api.player(pid)
          .then(data => mounted.current && setCards(current => ({ ...current, [pid]: data })))
          .catch(() => {})
      }
    }
  }, [si, step])

  useEffect(() => { logRef.current?.scrollTo(0, 1e9) }, [si])

  if (loadState !== 'ready' || !meta) {
    return <WatchGate state={loadState} error={loadError} onRetry={retry} onClose={onClose} />
  }

  const ev = step?.ev
  const isPa = ev?.t === 'pa'
  const outcomeShown = step?.kind === 'outcome'
  let count = { b: 0, s: 0 }
  if (isPa && step.kind === 'pitch') {
    for (let i = 0; i <= step.pitch; i++) {
      const pitchResult = ev.count_seq?.[i]
      if (pitchResult === 'B') count.b++
      else if (pitchResult === 'S' || (pitchResult === 'F' && count.s < 2)) count.s++
    }
  }
  const scored = Array.isArray(ev?.scored) ? ev.scored : []
  const rawScore = Array.isArray(ev?.score) ? ev.score : [0, 0]
  const score = isPa && outcomeShown
    ? [rawScore[0] + (ev.half === '초' ? scored.length : 0),
       rawScore[1] + (ev.half === '말' ? scored.length : 0)]
    : rawScore
  const outs = isPa ? Math.min(3, (ev.outs || 0) + (outcomeShown ? (ev.outs_added || 0) : 0)) : 0
  const log = []
  for (let i = 0; i < si; i++) {
    const row = steps[i]
    if (['outcome', 'steal', 'change'].includes(row.kind) && row.ev.text) log.push(row.ev.text)
  }
  if (outcomeShown && ev?.text) log.push(ev.text)

  const todayLine = pid => {
    let ab = 0
    let hits = 0
    for (let i = 0; i < si; i++) {
      const row = steps[i]
      if (row.kind !== 'outcome' || row.ev.batter?.pid !== pid) continue
      const outcome = row.ev.outcome
      if (!['BB', 'HBP', 'SF'].includes(outcome)) ab++
      if (['1B', '2B', '3B', 'HR'].includes(outcome)) hits++
    }
    return `${ab}타수 ${hits}안타`
  }

  const runners = isPa
    ? runnerTokens(ev, outcomeShown ? 'outcome' : 'pitch', !jumped,
      userTid, ev.half === '초', meta.away.tid)
    : []
  const anim = outcomeShown && !jumped && ev?.ball_type
    ? { key: ev.seed, outcome: ev.outcome, ballType: ev.ball_type, seed: ev.seed }
    : null
  const popLabels = {
    K: '삼진!', HR: '홈런!!', DP: '병살타!', '3B': '3루타!', '2B': '2루타!',
    '1B': '안타!', E: '실책!', SF: '희생플라이', BB: '볼넷', HBP: '사구',
    GO: '아웃', FO: '아웃', LO: '아웃',
  }
  const pop = outcomeShown && !jumped && ev
    ? { key: ev.seed, text: popLabels[ev.outcome] || ev.outcome }
    : null
  const fieldBatter = isPa && !outcomeShown
    ? { name: ev.batter?.name || '-', bats: ev.batter?.bats, throws: ev.pitcher?.throws }
    : null
  const pitchAnim = isPa && step.kind === 'pitch' && !jumped
    ? {
        key: `${ev.seed}-${step.pitch}`,
        result: ev.count_seq?.[step.pitch] || 'S',
        seed: ((ev.seed || 0) + step.pitch * 7919) & 0x7fffffff,
      }
    : null

  const jumpTo = predicate => {
    if (!steps.length) return
    setJumped(true)
    for (let i = si + 1; i < steps.length; i++) {
      if (predicate(steps[i])) {
        setSi(i)
        return
      }
    }
    setSi(steps.length - 1)
  }

  const skipToEnd = async () => {
    if (!window.confirm('정말 결과를 볼까요? 남은 경기가 모두 공개됩니다.')) return
    setJumped(true)
    setPlaying(false)
    try {
      const response = await fetch(`/api/watch/${day}/${gameIdx}/skip?frm=${nextFrom}`, {
        method: 'POST', cache: 'no-store',
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.detail || `중계 서버 오류 (HTTP ${response.status})`)
      if (!body || !body.meta || !Array.isArray(body.events)) {
        throw new Error('결과 데이터가 올바르지 않습니다.')
      }
      setMeta(body.meta)
      setEvents(current => {
        const all = [...current, ...body.events]
        setTimeout(() => setSi(Math.max(0, buildSteps(all).length - 1)), 0)
        return all
      })
      setDone(true)
    } catch (error) {
      setLoadError(String(error?.message || error))
      setLoadState('error')
    }
  }

  const ratingsLine = pid => cards[pid]
    ? Object.entries(cards[pid].ratings || {}).slice(0, 3)
      .map(([key, value]) => `${key}${value}`).join(' · ')
    : ''

  return (
    <div className="watch">
      <header className="watch-top">
        <b>{meta.away.name} @ {meta.home.name}</b>
        <span className="muted">{day}일차</span>
        <span className="spacer" />
        <button className="ghost dark" onClick={onClose}>✕ 닫기</button>
      </header>
      <ScoreBug meta={meta} ev={ev} count={count} outs={outs} score={score}
                after={outcomeShown} />
      <div className="watch-body">
        <div className="watch-left">
          <Field runners={runners} anim={anim} pitch={pitchAnim} batter={fieldBatter}
                 pitcherName={isPa ? ev.pitcher?.name : null} pop={pop} />
          {isPa && <div className="matchup">
            <div className="pcard">
              <div className="plabel">타자 {ev.batter?.order || '-'}번</div>
              <b>{ev.batter?.name || '-'}</b>
              <div className="muted">{ratingsLine(ev.batter?.pid)}</div>
              <div>{todayLine(ev.batter?.pid)}</div>
            </div>
            <div className="pcard">
              <div className="plabel">투수</div>
              <b>{ev.pitcher?.name || '-'}</b>
              <div className="muted">{ratingsLine(ev.pitcher?.pid)}</div>
              <div>{ev.pitcher?.pitches || 0}구{ev.pitcher?.fatigued ? ' · 피로 ▼' : ''}</div>
            </div>
          </div>}
          {!step && done && <div className="game-over">관전할 플레이 데이터가 없습니다.</div>}
          {step?.kind === 'end' && <div className="game-over">
            경기 종료 — {meta.away.tid} {ev.score?.[0] ?? 0} : {ev.score?.[1] ?? 0} {meta.home.tid}
            {ev.tie ? ` (${ev.innings}회 무승부)` : ''}
          </div>}
        </div>
        <div className="watch-log" ref={logRef}>
          {log.length ? log.map((line, index) => <div key={index} className="log-line">{line}</div>)
            : <div className="watch-log-empty">중계가 시작되면 플레이 기록이 표시됩니다.</div>}
        </div>
      </div>
      <footer className="watch-controls">
        <button onClick={() => setPlaying(!playing)}>{playing ? '⏸ 일시정지' : '▶ 재생'}</button>
        {[1, 2, 4].map(value => <button key={value} className={speed === value ? 'on' : ''}
          onClick={() => setSpeed(value)}>{value}x</button>)}
        <button disabled={!steps.length} onClick={() => jumpTo(row => row.kind === 'outcome')}>다음 타석 ⏭</button>
        <button disabled={!steps.length} onClick={() => jumpTo(row => row.kind === 'half')}>다음 이닝 ⏭⏭</button>
        <button onClick={skipToEnd}>결과로 ⏭⏭⏭</button>
      </footer>
    </div>
  )
}
