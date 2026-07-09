import React, { useEffect, useState } from 'react'

// ---- 좌표계 (viewBox 0 0 440 420, 홈플레이트 기준) ----
export const HOME = { x: 220, y: 372 }
export const BASES = { 1: { x: 296, y: 296 }, 2: { x: 220, y: 220 }, 3: { x: 144, y: 296 } }
const MOUND = { x: 220, y: 310 }
const FIELDERS = [
  ['P', 220, 305], ['C', 220, 392], ['1B', 302, 270], ['2B', 262, 226],
  ['SS', 178, 226], ['3B', 138, 270], ['LF', 100, 130], ['CF', 220, 84], ['RF', 340, 130],
]

// 연출용 결정론 난수 (이벤트 seed → 모든 클라이언트 동일 연출)
const srand = (seed) => { let s = seed >>> 0; return () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff) }

// 타구 목적지 (사실이 아닌 연출 — outcome/ball_type + seed로 도출)
export function ballTarget(outcome, ballType, seed) {
  const r = srand(seed)
  const ang = (r() * 70 - 35) * Math.PI / 180        // 중앙 기준 ±35도
  const dist = { '1B': 150, '2B': 215, '3B': 235, HR: 300, E: 120,
                 GO: 95, DP: 90, FO: 195, SF: 210, LO: 130 }[outcome] ?? 120
  const d = dist * (0.9 + r() * 0.2)
  return { x: HOME.x + Math.sin(ang) * d, y: HOME.y - 30 - Math.cos(ang) * d }
}

function Ball({ anim }) {
  if (!anim) return null
  const { outcome, ballType } = anim
  const to = ballTarget(outcome, ballType, anim.seed)
  const dur = ballType === 'GB' ? '0.55s' : ballType === 'LD' ? '0.5s' : '1.1s'
  // 궤적: 땅볼=직선, 라이너=빠른 직선, 뜬공/홈런=포물선(베지어 제어점 위로)
  const mid = ballType === 'FB' || outcome === 'HR'
    ? `Q ${(HOME.x + to.x) / 2} ${Math.min(HOME.y, to.y) - 130} `
    : `L `
  const path = `M ${HOME.x} ${HOME.y - 24} ${mid}${to.x} ${to.y}`
  return (
    <circle r="4.5" fill="#fff" stroke="#c33" strokeWidth="1.2" key={anim.key}>
      <animateMotion dur={dur} fill="freeze" path={path} />
      {outcome === 'HR' && <animate attributeName="opacity" from="1" to="0"
                                    begin="0.9s" dur="0.3s" fill="freeze" />}
    </circle>
  )
}

function Runner({ token }) {
  // token: {pid, path: [{x,y}...], me}  경유지(베이스)를 순서대로 달린다
  const [pos, setPos] = useState(token.path[0])
  const [leg, setLeg] = useState(0)
  useEffect(() => {
    if (leg >= token.path.length - 1) return
    const t = setTimeout(() => { setPos(token.path[leg + 1]); setLeg(leg + 1) }, 60 + leg * 340)
    return () => clearTimeout(t)
  }, [leg, token])
  return (
    <g style={{ transform: `translate(${pos.x}px, ${pos.y}px)`,
                transition: 'transform 0.32s linear' }}>
      <circle r="7" fill={token.me ? '#e8542f' : '#1a67c9'} stroke="#fff" strokeWidth="2" />
    </g>
  )
}

export default function Field({ runners, anim }) {
  return (
    <svg viewBox="0 0 440 420" className="field">
      {/* 외야 잔디 + 담장 호 */}
      <path d="M 220 385 L 28 193 A 262 262 0 0 1 412 193 Z" fill="#3d8b4f" />
      <path d="M 28 193 A 262 262 0 0 1 412 193" fill="none" stroke="#245c31" strokeWidth="7" />
      {/* 내야 부채꼴 (흙) */}
      <path d="M 220 385 L 100 265 A 168 168 0 0 1 340 265 Z" fill="#c8965a" />
      {/* 내야 잔디 다이아몬드 */}
      <path d={`M ${HOME.x} ${HOME.y - 14} L ${BASES[1].x - 8} ${BASES[1].y + 8}
                L ${BASES[2].x} ${BASES[2].y + 16} L ${BASES[3].x + 8} ${BASES[3].y + 8} Z`}
            fill="#4a9c5c" />
      {/* 파울라인 */}
      <line x1={HOME.x} y1={HOME.y} x2="24" y2="176" stroke="#fff" strokeWidth="2.5" />
      <line x1={HOME.x} y1={HOME.y} x2="416" y2="176" stroke="#fff" strokeWidth="2.5" />
      {/* 마운드 + 베이스 */}
      <circle cx={MOUND.x} cy={MOUND.y} r="11" fill="#b8854e" />
      <rect x={MOUND.x - 4} y={MOUND.y - 1.5} width="8" height="3" fill="#fff" />
      {Object.values(BASES).map((b, i) => (
        <rect key={i} x={b.x - 6} y={b.y - 6} width="12" height="12" fill="#fff"
              stroke="#999" transform={`rotate(45 ${b.x} ${b.y})`} />))}
      <path d={`M ${HOME.x - 7} ${HOME.y - 6} h 14 v 6 l -7 6 l -7 -6 Z`} fill="#fff" stroke="#999" />
      {/* 수비 9명 */}
      {FIELDERS.map(([pos, x, y]) => (
        <g key={pos}>
          <circle cx={x} cy={y} r="6.5" fill="#f5f7fb" stroke="#33415e" strokeWidth="1.5" />
          <text x={x} y={y - 10} textAnchor="middle" fontSize="9" fill="#1b2430"
                fontWeight="700">{pos}</text>
        </g>))}
      {/* 주자 + 타구 */}
      {runners.map(t => <Runner key={t.key} token={t} />)}
      <Ball anim={anim} />
    </svg>
  )
}
