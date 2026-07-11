"""관전 화면이 네트워크 오류에서 영구 정지하지 않는지 정적 회귀 검증."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "web" / "frontend" / "src" / "screens" / "Watch.jsx"
STYLES = ROOT / "web" / "frontend" / "src" / "styles.css"


class TestWatchRecoveryUi(unittest.TestCase):
    def test_watch_request_has_timeout_status_check_and_finally_reset(self):
        source = WATCH.read_text(encoding="utf-8")
        self.assertIn("AbortController", source)
        self.assertIn("response.ok", source)
        self.assertIn("finally", source)
        self.assertIn("fetching.current = false", source)

    def test_watch_failure_exposes_retry_and_close_actions(self):
        source = WATCH.read_text(encoding="utf-8")
        self.assertIn("중계 화면을 열지 못했습니다", source)
        self.assertIn("다시 불러오기", source)
        self.assertIn("일정·결과로 돌아가기", source)
        self.assertIn("onRetry", source)
        self.assertIn("onClose", source)

    def test_watch_payload_is_validated_before_render(self):
        source = WATCH.read_text(encoding="utf-8")
        self.assertIn("Array.isArray(body.events)", source)
        self.assertIn("Number.isInteger(body.next)", source)
        self.assertIn("typeof body.done !== 'boolean'", source)

    def test_loading_and_error_states_are_full_screen_visible(self):
        css = STYLES.read_text(encoding="utf-8")
        self.assertIn(".watch-gate-card", css)
        self.assertIn(".watch-spinner", css)
        self.assertIn(".watch-error-code", css)


if __name__ == "__main__":
    unittest.main()
