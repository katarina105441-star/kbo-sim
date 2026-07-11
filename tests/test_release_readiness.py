"""첫 실행 안내·릴리스 패키징 문서와 점검 스크립트 검증."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestReleaseReadiness(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_first_run_doc_contains_non_developer_path(self):
        text = self.read("docs/FIRST_RUN.md")
        self.assertIn("코딩을 몰라도", text)
        self.assertIn("python -m uvicorn web.backend.main:app --port 8000", text)
        self.assertIn("저장된 게임 불러오기", text)
        self.assertIn("구단주 이벤트", text)

    def test_release_checklist_contains_required_commands(self):
        text = self.read("docs/RELEASE_CHECKLIST.md")
        self.assertIn("python -m unittest discover -s tests", text)
        self.assertIn("npm run build", text)
        self.assertIn("scripts/career_balance_check.py --seeds 4 --seasons 30 --strict", text)
        self.assertIn("scripts/release_check.py", text)

    def test_release_notes_cover_major_mvp3_systems(self):
        text = self.read("docs/RELEASE_NOTES_MVP3.md")
        for phrase in ("직접 운영", "트레이드", "FA", "드래프트",
                       "실제 해임", "재취업", "명예의 전당"):
            self.assertIn(phrase, text)

    def test_onboarding_constants_are_visible_to_frontend(self):
        text = self.read("web/frontend/src/onboarding.js")
        self.assertIn("QUICK_START_STEPS", text)
        self.assertIn("FEATURE_GUIDE", text)
        self.assertIn("RELEASE_CHECKS", text)
        self.assertIn("저장", text)

    def test_readme_points_to_new_docs_and_current_scope(self):
        text = self.read("README.md")
        self.assertIn("docs/FIRST_RUN.md", text)
        self.assertIn("docs/RELEASE_CHECKLIST.md", text)
        self.assertIn("docs/RELEASE_NOTES_MVP3.md", text)
        self.assertIn("MVP-3 완료 범위", text)
        self.assertIn("첫 실행 안내·릴리스 문서·자동 릴리스 점검", text)

    def test_release_check_script_has_fast_default(self):
        text = self.read("scripts/release_check.py")
        self.assertIn("check_files()", text)
        self.assertIn("check_python()", text)
        self.assertIn("--frontend", text)
        self.assertIn("--balance", text)
        self.assertIn("릴리스 점검 PASS", text)


if __name__ == "__main__":
    unittest.main()
