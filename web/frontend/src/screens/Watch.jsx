import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import Field, { HOME, BASES } from './Field.jsx'

// 이벤트 → 재생 스텝 (투구 하나하나 → 결과 연출)
function buildSteps(events) {
  const steps = []
  events.forEach((ev, ei) => {
    if (ev.t === 'pa') {
      const n = ev.count_seq.length
      for (let i = 0; i < n - 1; i++) steps.push({ kind: 'pitch', ev, ei, pitch: i })
      steps.push({ kind: 'outcome', ev, ei })
    } else if (ev.t === 'steal') steps.push({ kind: 'steal', ev, ei })
    else if (ev.t === 'pitch_change') steps.push({ kind: 'change', ev, ei })
    else if (ev.t === 'half_end') steps.push({ kind: 'half', ev, ei })
    else if (ev.t === 'game_end') steps.push({ kind: 'end', ev, ei })
  })
  return steps
}

const DUR = { pitch: 650, outcome: 1900, steal: 900, change: 1100, half: 900, end: 0 }
const basePos = (b) => (b === 4 ? HOME : BASES[b])

// 주자 토큰 (사실 diff → 연출 경로: 베이스를 순서대로 경유)
// phase 'pitch' = 타석 진행 중: bases_before 주자만 제자리 표시
// phase 'outcome' = 결과: before→after/득점 경로로 이동 애니 (jumped면 즉시 배치)
function runnerTokens(ev, phase, animate, meTid, halfIsTop, awayTid) {
  const battingMe = (halfIsTop ? awayTid === meTid : awayTid !== meTid)
  const toks = []
  const before = ev.bases_before, after = ev.bases_after
  if (phase === 'pitch') {
    for (let i = 0; i < 3; i++)
      if (before[i]) toks.push({ key: `${ev.seed}-p${i}`, pid: before[i],
                                 me: battingMe, path: [basePos(i + 1)] })
    return toks
  }
  const scored = new Set(ev.scored.map(s => s.pid))
  for (let i = 0; i < 3; i++) {
    const pid = before[i]
    if (!pid) continue
    const from = i + 1
    let to = null
    if (scored.has(pid)) to = 4
    else { const j = after.indexOf(pid); to = j >= 0 ? j + 1 : null }
    if (to === null) continue                       // 아웃: 토큰 제거
    const path = []
    for (let b = from; b <= to; b++) path.push(basePos(b))
    toks.push({ key: `${ev.seed}-${pid}`, pid, me: battingMe,
                path: (animate && to !== from) ? path
                      : [basePos(to === 4 ? from : to)] })
    if (to === 4 && !animate) toks.pop()            // 점프 시 득점자는 표시 안 함
  }
  const bpid = ev.batter.pid
  let bto = null
  if (scored.has(bpid)) bto = 4
  else { const j = after.indexOf(bpid); bto = j >= 0 ? j + 1 : null }
  if (bto !== null && !(bto === 4 && !animate)) {
    const path = [{ x: HOME.x, y: HOME.y }]
    for (let b = 1; b <= bto; b++) path.push(basePos(b))
    toks.push({ key: `${ev.seed}-${bpid}`, pid: bpid, me: battingMe,
                path: animate ? path : [basePos(Math.min(bto, 3))] })
  }
  return toks
}

function ScoreBug({ meta, ev, count, outs, score, after }) {
  const dot = (on, cls) => <span className={'dot ' + cls + (on ? ' on' : '')} />
  const bases = ev?.t === 'pa' ? (after ? ev.bases_after : ev.bases_before)
                               : [null, null, null]
  return (
    <div className="scorebug">
      <span className="sb-team">{meta.away.tid} <b>{score[0]}</b></span>
      <span className="sb-team">{meta.home.tid} <b>{score[1]}</b></span>
      <span className="sb-inn">{ev?.inning ? `${ev.inning}회${ev.half}` : '경기 종료'}</span>
      <svg viewBox="0 0 40 40" className="sb-diamond">
        {[[20, 6, bases[1]], [32, 18, bases[0]], [8, 18, bases[2]]].map(([x, y, occ], i) => (
          <rect key={i} x={x - 6} y={y - 6} width="12" height="12"
                transform={`rotate(45 ${x} ${y})`}
                fill={occ ? '#ffb02e' : '#dde3ec'} />))}
      </svg>
      <span className="sb-count">
        B {dot(count.b > 0, 'b')}{dot(count.b > 1, 'b')}{dot(count.b > 2, 'b')}<br />
        S {dot(count.s > 0, 's')}{dot(count.s > 1, 's')}<br />
        O {dot(outs > 0, 'o')}{dot(outs > 1, 'o')}
      </span>
    </div>
  )
}

export default function Watch({ day, gameIdx, userTid, onClose }) {
  // 스트림은 청크로 받는다 — 재생 시점 너머(남은 이닝·최종 결과)를 미리 모름
  const [meta, setMeta] = useState(null)
  const [events, setEvents] = useState([])
  const [nextFrom, setNextFrom] = useState(0)
  const [done, setDone] = useState(false)
  const fetching = useRef(false)
  const [si, setSi] = useState(0)          // 스텝 커서
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(1)
  const [jumped, setJumped] = useState(false)   // 점프 시 애니 생략
  const [cards, setCards] = useState({})
  const logRef = useRef(null)

  const fetchChunk = (frm) => {
    if (fetching.current) return
    fetching.current = true
    fetch(`/api/watch/${day}/${gameIdx}?frm=${frm}`).then(r => r.json()).then(d => {
      setMeta(m => m?.final ? m : d.meta)
      setEvents(e => [...e, ...d.events])
      setNextFrom(d.next)
      setDone(d.done)
      fetching.current = false
    })
  }
  useEffect(() => { fetchChunk(0) }, [day, gameIdx])

  const steps = useMemo(() => buildSteps(events), [events])

  // 버퍼가 얕아지면 다음 청크 선요청
  useEffect(() => {
    if (!done && steps.length - si < 60) fetchChunk(nextFrom)
  }, [si, steps.length, done])
  const step = steps[si]

  // 자동 재생 타이머
  useEffect(() => {
    if (!playing || !step || step.kind === 'end') return
    const t = setTimeout(() => { setJumped(false); setSi(si + 1) },
                         DUR[step.kind] / speed)
    return () => clearTimeout(t)
  }, [playing, si, speed, steps])

  // 선수 카드 로드 (타자/투수 변경 시)
  useEffect(() => {
    if (!step || step.ev.t !== 'pa') return
    for (const pid of [step.ev.batter.pid, step.ev.pitcher.pid]) {
      if (!cards[pid]) api.player(pid).then(d => setCards(c => ({ ...c, [pid]: d })))
    }
  }, [si, events])

  useEffect(() => { logRef.current?.scrollTo(0, 1e9) }, [si])

  if (!meta) return <div className="modal-bg"><div className="modal">로딩…</div></div>

  // ---- 현재 표시 상태 도출 (완료된 이벤트 폴드) ----
  const ev = step?.ev
  const isPa = ev?.t === 'pa'
  const outcomeShown = step?.kind === 'outcome'
  let count = { b: 0, s: 0 }
  if (isPa && step.kind === 'pitch') {
    for (let i = 0; i <= step.pitch; i++) {
      const c = ev.count_seq[i]
      if (c === 'B') count.b++
      else if (c === 'S' || (c === 'F' && count.s < 2)) count.s++
    }
  }
  const score = isPa
    ? (outcomeShown
       ? [ev.score[0] + (ev.half === '초' ? ev.scored.length : 0),
          ev.score[1] + (ev.half === '말' ? ev.scored.length : 0)]
       : ev.score)
    : (ev?.score || [0, 0])
  const outs = isPa ? Math.min(3, ev.outs + (outcomeShown ? ev.outs_added : 0)) : 0
  const log = []
  for (let i = 0; i < si; i++)
    if (['outcome', 'steal', 'change'].includes(steps[i].kind) && steps[i].ev.text
        && steps[i].kind !== 'pitch') log.push(steps[i].ev.text)
  if (outcomeShown && ev.text) log.push(ev.text)

  // 오늘 성적 폴드 (현재 타자)
  const todayLine = (pid) => {
    let ab = 0, h = 0
    for (let i = 0; i < si; i++) {
      const s2 = steps[i]
      if (s2.kind !== 'outcome' || s2.ev.batter.pid !== pid) continue
      const o = s2.ev.outcome
      if (!['BB', 'HBP', 'SF'].includes(o)) ab++
      if (['1B', '2B', '3B', 'HR'].includes(o)) h++
    }
    return `${ab}타수 ${h}안타`
  }

  const runners = isPa
    ? runnerTokens(ev, outcomeShown ? 'outcome' : 'pitch', !jumped,
                   userTid, ev.half === '초', meta.away.tid)
    : []
  const anim = (outcomeShown && !jumped && ev.ball_type)
    ? { key: ev.seed, outcome: ev.outcome, ballType: ev.ball_type, seed: ev.seed }
    : null
  const POP = { K: '삼진!', HR: '홈런!!', DP: '병살타!', '3B': '3루타!',
                '2B': '2루타!', '1B': '안타!', E: '실책!', SF: '희생플라이',
                BB: '볼넷', HBP: '사구', GO: '아웃', FO: '아웃', LO: '아웃' }
  const pop = (outcomeShown && !jumped)
    ? { key: ev.seed, text: POP[ev.outcome] || ev.outcome } : null
  const fieldBatter = isPa && !outcomeShown
    ? { name: ev.batter.name, bats: ev.batter.bats, throws: ev.pitcher.throws }
    : null
  const pitchAnim = (isPa && step.kind === 'pitch' && !jumped)
    ? { key: `${ev.seed}-${step.pitch}`, result: ev.count_seq[step.pitch],
        seed: (ev.seed + step.pitch * 7919) & 0x7fffffff }
    : null

  const jumpTo = (pred) => {
    setJumped(true)
    for (let i = si + 1; i < steps.length; i++)
      if (pred(steps[i])) { setSi(i); return }
    setSi(steps.length - 1)
  }
  const skipToEnd = () => {
    if (!window.confirm('정말 결과를 볼까요? 남은 경기가 모두 공개됩니다.')) return
    setJumped(true)
    setPlaying(false)
    fetch(`/api/watch/${day}/${gameIdx}/skip?frm=${nextFrom}`, { method: 'POST' })
      .then(r => r.json()).then(d => {
        setMeta(d.meta)
        setEvents(e => {
          const all = [...e, ...d.events]
          setTimeout(() => setSi(buildSteps(all).length - 1), 0)
          return all
        })
        setDone(true)
      })
  }
  const card = (pid) => cards[pid]
  const ratingsLine = (pid) => card(pid)
    ? Object.entries(card(pid).ratings).slice(0, 3)
        .map(([k, v]) => `${k}${v}`).join(' · ') : ''

  return (
    <div className="watch">
      <header className="watch-top">
        <b>{meta.away.name} @ {meta.home.name}</b>
        <span className="muted"> {day}일차</span>
        <span className="spacer" />
        <button className="ghost dark" onClick={onClose}>✕ 닫기</button>
      </header>
      <ScoreBug meta={meta} ev={ev} count={count} outs={outs} score={score}
                after={outcomeShown} />
      <div className="watch-body">
        <div className="watch-left">
          <Field runners={runners} anim={anim} pitch={pitchAnim} batter={fieldBatter}
                 pitcherName={isPa ? ev.pitcher.name : null} pop={pop} />
          {isPa && (
            <div className="matchup">
              <div className="pcard">
                <div className="plabel">타자 {ev.batter.order}번</div>
                <b>{ev.batter.name}</b>
                <div className="muted">{ratingsLine(ev.batter.pid)}</div>
                <div>{todayLine(ev.batter.pid)}</div>
              </div>
              <div className="pcard">
                <div className="plabel">투수</div>
                <b>{ev.pitcher.name}</b>
                <div className="muted">{ratingsLine(ev.pitcher.pid)}</div>
                <div>{ev.pitcher.pitches}구{ev.pitcher.fatigued ? ' · 피로 ▼' : ''}</div>
              </div>
            </div>)}
          {step?.kind === 'end' && (
            <div className="game-over">
              경기 종료 — {meta.away.tid} {ev.score[0]} : {ev.score[1]} {meta.home.tid}
              {ev.tie ? ` (${ev.innings}회 무승부)` : ''}
            </div>)}
        </div>
        <div className="watch-log" ref={logRef}>
          {log.map((l, i) => <div key={i} className="log-line">{l}</div>)}
        </div>
      </div>
      <footer className="watch-controls">
        <button onClick={() => setPlaying(!playing)}>{playing ? '⏸ 일시정지' : '▶ 재생'}</button>
        {[1, 2, 4].map(x => (
          <button key={x} className={speed === x ? 'on' : ''}
                  onClick={() => setSpeed(x)}>{x}x</button>))}
        <button onClick={() => jumpTo(s => s.kind === 'outcome')}>다음 타석 ⏭</button>
        <button onClick={() => jumpTo(s => s.kind === 'half')}>다음 이닝 ⏭⏭</button>
        <button onClick={skipToEnd}>결과로 ⏭⏭⏭</button>
      </footer>
    </div>
  )
}
