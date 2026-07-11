import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('KBO Manager UI error', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="fatal-screen">
        <div className="fatal-card">
          <span className="fatal-code">화면 복구 안내</span>
          <h1>게임 화면을 불러오지 못했습니다.</h1>
          <p>저장 데이터는 자동으로 삭제되지 않았습니다. 먼저 새로고침하고, 반복되면 실행 창을 종료한 뒤 다시 시작하세요.</p>
          <pre>{String(this.state.error.message || this.state.error)}</pre>
          <div className="btn-row">
            <button className="primary" onClick={() => window.location.reload()}>새로고침</button>
            <button onClick={() => this.setState({ error: null })}>화면 다시 시도</button>
          </div>
        </div>
      </main>
    )
  }
}
