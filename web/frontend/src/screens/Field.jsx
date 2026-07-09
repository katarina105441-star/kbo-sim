import React, { useEffect, useRef, useState } from 'react'

// ---- 좌표계: 내야가 주인공 (viewBox 0 0 440 400) ----
export const HOME = { x: 220, y: 330 }
export const BASES = { 1: { x: 325, y: 225 }, 2: { x: 220, y: 120 }, 3: { x: 115, y: 225 } }
const MOUND = { x: 220, y: 235 }
const FIELDERS = [                       // 투수·포수는 별도 강조 렌더
  ['1B', 312, 200], ['2B', 268, 148], ['SS', 172, 148], ['3B', 128, 200],
  ['LF', 92, 88], ['CF', 220, 48], ['RF', 348, 88],
]

const srand = (seed) => { let s = seed >>> 0; return () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff) }

// 타구 목적지 (연출 — outcome/ball_type + seed로 결정론 도출)
function ballTarget(outcome, ballType, seed) {
  const r = srand(seed)
  const ang = (r() * 70 - 35) * Math.PI / 180
  const dist = { '1B': 160, '2B': 235, '3B': 255, HR: 330, E: 130,
                 GO: 105, DP: 100, FO: 215, SF: 230, LO: 145 }[outcome] ?? 130
  const d = dist * (0.9 + r() * 0.2)
  return { x: HOME.x + Math.sin(ang) * d, y: HOME.y - 24 - Math.cos(ang) * d }
}

function ballPath(outcome, ballType, seed) {
  const to = ballTarget(outcome, ballType, seed)
  const arc = ballType === 'FB' || outcome === 'HR'
    ? `Q ${(HOME.x + to.x) / 2} ${Math.min(HOME.y, to.y) - 140} ` : 'L '
  return `M ${HOME.x} ${HOME.y - 20} ${arc}${to.x} ${to.y}`
}

// rAF 기반 비행 훅 — SMIL은 React 마운트 시점에 타임라인이 이미 지나가
// 애니메이션이 안 보이는 문제가 있어 JS로 직접 구동한다.
function useFlight(d, durMs, key) {
  const pathRef = useRef(null)
  const [st, setSt] = useState({ pt: null, p: 0, done: false })
  useEffect(() => {
    const el = pathRef.current
    if (!el) return
    const len = el.getTotalLength()
    const t0 = performance.now()
    let raf
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / durMs)
      const pos = el.getPointAtLength(len * p)
      setSt({ pt: { x: pos.x, y: pos.y }, p, done: p >= 1 })
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [key])
  return { pathRef, ...st }
}

const OUT_TYPES = ['GO', 'FO', 'LO', 'DP', 'SF']

function BattedBall({ anim }) {
  const d = ballPath(anim.outcome, anim.ballType, anim.seed)
  const dur = anim.ballType === 'GB' ? 550 : anim.ballType === 'LD' ? 500 : 1050
  const { pathRef, pt, p, done } = useFlight(d, dur, anim.key)
  const isOut = OUT_TYPES.includes(anim.outcome)
  const fade = anim.outcome === 'HR' && p > 0.88
  return (
    <g>
      <path ref={pathRef} d={d} fill="none" stroke="none" />
      {/* 궤적 잔상: 진행만큼 그려지고, 도착 후 서서히 사라짐 */}
      <path d={d} fill="none" stroke="#ffe9a8" strokeWidth="2"
            strokeDasharray="4 5" className={done ? 'trail-fade' : ''}
            style={{ opacity: done ? undefined : 0.35 + p * 0.4 }} />
      {pt && !fade && (
        <circle cx={pt.x} cy={pt.y} r="4.5" fill="#fff" stroke="#c33"
                strokeWidth="1.2" />)}
      {/* 포구/낙구 표시 */}
      {done && pt && anim.outcome !== 'HR' && (
        <circle cx={pt.x} cy={pt.y} r="8" className="catch-ring"
                fill="none" stroke={isOut ? '#ffd21e' : '#fff'} strokeWidth="2.5" />)}
      {done && anim.outcome === 'HR' && (
        <text x={pt?.x ?? 220} y={pt?.y ?? 60} textAnchor="middle" fontSize="16"
              className="trail-fade">💥</text>)}
    </g>
  )
}

// 투구: 마운드 → 홈플레이트. 볼은 코스가 빠지고 스트라이크는 존 가운데.
function PitchBall({ pitch }) {
  const r = srand(pitch.seed)
  const off = pitch.result === 'B' ? (r() > 0.5 ? 1 : -1) * (9 + r() * 6)
            : pitch.result === 'S' ? (r() - 0.5) * 6 : (r() - 0.5) * 12
  const d = `M ${MOUND.x} ${MOUND.y - 8} L ${HOME.x + off} ${HOME.y + 2}`
  const { pathRef, pt, done } = useFlight(d, 240, pitch.key)
  return (
    <g>
      <path ref={pathRef} d={d} fill="none" stroke="none" />
      {pt && !done && <circle cx={pt.x} cy={pt.y} r="3.5" fill="#fff" />}
      {done && pt && <circle cx={pt.x} cy={pt.y} r="6" className="catch-ring"
                             fill="none"
                             stroke={pitch.result === 'B' ? '#4caf50' : '#ffb02e'}
                             strokeWidth="2" />}
    </g>
  )
}

function Runner({ token }) {
  const [pos, setPos] = useState(token.path[0])
  const [leg, setLeg] = useState(0)
  const last = token.path[token.path.length - 1]
  const scoring = token.path.length > 1 && last.x === HOME.x && last.y === HOME.y
  const arrived = leg >= token.path.length - 1
  useEffect(() => {
    if (arrived) return
    const t = setTimeout(() => { setPos(token.path[leg + 1]); setLeg(leg + 1) }, 60 + leg * 340)
    return () => clearTimeout(t)
  }, [leg, token])
  return (
    <g style={{ transform: `translate(${pos.x}px, ${pos.y}px)`,
                transition: 'transform 0.32s linear' }}
       className={scoring && arrived ? 'runner-score' : ''}>
      <circle r="7.5" fill={scoring && arrived ? '#ffd21e' : '#1a67c9'}
              stroke="#fff" strokeWidth="2" />
    </g>
  )
}

function PopText({ pop }) {
  if (!pop) return null
  const big = ['삼진!', '홈런!!', '병살타!', '3루타!'].includes(pop.text)
  return (
    <text key={pop.key} x="220" y="188" textAnchor="middle"
          className={big ? 'pop big' : 'pop'}
          fontSize={big ? 34 : 22} fontWeight="900"
          fill={pop.text === '홈런!!' ? '#ffd21e' : '#fff'}
          stroke="#10213f" strokeWidth="1">{pop.text}</text>
  )
}

export default function Field({ runners, anim, pitch, batter, pitcherName, pop }) {
  // 타석: 우타=3루쪽 박스, 좌타=1루쪽. 스위치는 투수 반대손
  let batSide = null
  if (batter) {
    const b = batter.bats === 'S'
      ? (batter.throws === 'L' ? 'R' : 'L') : batter.bats
    batSide = b === 'R' ? -17 : 17
  }
  return (
    <svg viewBox="0 0 440 400" className="field">
      {/* 외야: 담장 호만 살짝 (내야가 주인공) */}
      <path d="M 220 345 L 30 155 A 269 269 0 0 1 410 155 Z" fill="#3d8b4f" />
      <path d="M 30 155 A 269 269 0 0 1 410 155" fill="none" stroke="#245c31" strokeWidth="8" />
      <path d="M 30 155 A 269 269 0 0 1 410 155" fill="none" stroke="#e9c46a" strokeWidth="2" />
      {/* 내야 흙 부채꼴 (확대) */}
      <path d={`M ${HOME.x} ${HOME.y + 12} L 78 188 A 200 200 0 0 1 362 188 Z`} fill="#c8965a" />
      {/* 내야 잔디 */}
      <path d={`M ${HOME.x} ${HOME.y - 22} L ${BASES[1].x - 14} ${BASES[1].y + 14}
                L ${BASES[2].x} ${BASES[2].y + 26} L ${BASES[3].x + 14} ${BASES[3].y + 14} Z`}
            fill="#4a9c5c" />
      {/* 주루 라인 */}
      {[[HOME, BASES[1]], [BASES[1], BASES[2]], [BASES[2], BASES[3]], [BASES[3], HOME]]
        .map(([a, b], i) => (
          <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke="#e7d3b0" strokeWidth="2.5" opacity="0.8" />))}
      {/* 파울라인 */}
      <line x1={HOME.x} y1={HOME.y} x2="26" y2="136" stroke="#fff" strokeWidth="2.5" />
      <line x1={HOME.x} y1={HOME.y} x2="414" y2="136" stroke="#fff" strokeWidth="2.5" />
      {/* 마운드 */}
      <circle cx={MOUND.x} cy={MOUND.y} r="16" fill="#b8854e" />
      <rect x={MOUND.x - 5} y={MOUND.y - 2} width="10" height="4" fill="#fff" />
      {/* 베이스 */}
      {Object.values(BASES).map((b, i) => (
        <rect key={i} x={b.x - 7} y={b.y - 7} width="14" height="14" fill="#fff"
              stroke="#999" transform={`rotate(45 ${b.x} ${b.y})`} />))}
      <path d={`M ${HOME.x - 8} ${HOME.y - 7} h 16 v 7 l -8 7 l -8 -7 Z`} fill="#fff" stroke="#999" />
      {/* 타석 박스 2개 */}
      {[-17, 17].map(dx => (
        <rect key={dx} x={HOME.x + dx - 7} y={HOME.y - 14} width="14" height="24"
              fill="none" stroke="#e7d3b0" strokeWidth="1.5" opacity="0.9" />))}

      {/* 수비 7명 (내야 4 + 외야 3) */}
      {FIELDERS.map(([pos, x, y]) => (
        <g key={pos}>
          <circle cx={x} cy={y} r="7" fill="#f5f7fb" stroke="#33415e" strokeWidth="1.5" />
          <text x={x} y={y - 11} textAnchor="middle" fontSize="9.5" fill="#eef"
                fontWeight="700">{pos}</text>
        </g>))}
      {/* 투수 (강조) */}
      <g>
        <circle cx={MOUND.x} cy={MOUND.y - 8} r="9" fill="#f5f7fb"
                stroke="#e8542f" strokeWidth="3" />
        <text x={MOUND.x} y={MOUND.y - 22} textAnchor="middle" fontSize="10.5"
              fill="#ffd977" fontWeight="800">{pitcherName || 'P'}</text>
      </g>
      {/* 포수 + 심판 */}
      <circle cx={HOME.x} cy={HOME.y + 18} r="7" fill="#f5f7fb" stroke="#33415e" strokeWidth="1.5" />
      <text x={HOME.x + 14} y={HOME.y + 22} fontSize="9" fill="#cdd">C</text>
      <circle cx={HOME.x} cy={HOME.y + 34} r="5.5" fill="#3b4252" stroke="#222" />
      {/* 타자 (강조 — 좌/우 타석) */}
      {batter && batSide !== null && (
        <g>
          <circle cx={HOME.x + batSide} cy={HOME.y - 2} r="9" fill="#e8542f"
                  stroke="#fff" strokeWidth="2.5" />
          <text x={HOME.x + batSide * 3.2} y={HOME.y + 4} textAnchor="middle"
                fontSize="10.5" fill="#ffd977" fontWeight="800">{batter.name}</text>
        </g>)}

      {/* 주자 + 투구/타구 + 결과 팝업 */}
      {runners.map(t => <Runner key={t.key} token={t} />)}
      {pitch && <PitchBall key={pitch.key} pitch={pitch} />}
      {anim && <BattedBall key={anim.key} anim={anim} />}
      <PopText pop={pop} />
    </svg>
  )
}
