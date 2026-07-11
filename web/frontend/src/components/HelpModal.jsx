import React, { useState } from 'react'

const STEPS = [
  {
    title: '1. 대시보드에서 목표 확인',
    body: '현재 순위, 구단주 목표, 신뢰도와 해임 위험을 먼저 확인합니다. 시즌 중 긴급 안건이 나타나면 응답해야 다음 날짜로 진행할 수 있습니다.',
  },
  {
    title: '2. 원하는 속도로 시즌 진행',
    body: '하루·시리즈·한 달·시즌 끝까지 중 하나를 선택합니다. 내 팀 경기는 직접 운영할 수 있고, 일정·결과 화면에서는 중계형 관전도 가능합니다.',
  },
  {
    title: '3. 선수단과 2군 관리',
    body: '로스터에서 선수 능력과 기록을 확인하고, 라인업 관리에서 타순·수비·선발 로테이션을 조정합니다. 2군·육성에서는 승격, 강등, 성장 집중 분야를 지정합니다.',
  },
  {
    title: '4. 오프시즌과 감독 커리어',
    body: '트레이드, FA, 보상선수, 드래프트를 직접 진행합니다. 성적에 따라 평가·해임·재취업·구단 이동이 발생하며 10시즌 이후 은퇴와 최종 결산이 가능합니다.',
  },
  {
    title: '5. 저장하고 안전하게 종료',
    body: '상단 저장 버튼을 누른 뒤 실행 창에서 Ctrl+C로 종료합니다. 저장 파일은 게임 폴더의 saves/save.pkl에 있습니다.',
  },
]

export default function HelpModal({ onClose, welcome = false, version = '' }) {
  const [step, setStep] = useState(0)
  const current = STEPS[step]

  return (
    <div className="help-backdrop" role="dialog" aria-modal="true" aria-label="게임 도움말">
      <div className="help-modal">
        <button className="help-close" onClick={onClose} aria-label="도움말 닫기">×</button>
        <div className="help-heading">
          <span>{welcome ? '첫 커리어 안내' : '게임 도움말'}</span>
          <h2>{current.title}</h2>
          {version && <small>버전 {version}</small>}
        </div>
        <p>{current.body}</p>
        <div className="help-map">
          <div><b>대시보드</b><span>목표·진행·이벤트·커리어</span></div>
          <div><b>일정·결과</b><span>관전·박스스코어</span></div>
          <div><b>로스터·라인업</b><span>선수단 운영</span></div>
          <div><b>오프시즌</b><span>트레이드·FA·드래프트</span></div>
        </div>
        <div className="help-progress">
          {STEPS.map((_, index) => (
            <button key={index} className={index === step ? 'on' : ''}
              onClick={() => setStep(index)} aria-label={`${index + 1}단계`} />
          ))}
        </div>
        <div className="help-actions">
          <button disabled={step === 0} onClick={() => setStep(step - 1)}>이전</button>
          {step < STEPS.length - 1
            ? <button className="primary" onClick={() => setStep(step + 1)}>다음</button>
            : <button className="primary" onClick={onClose}>게임 시작</button>}
        </div>
      </div>
    </div>
  )
}
