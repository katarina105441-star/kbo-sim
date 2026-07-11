"""런처 상태 및 릴리스 메타데이터 API 검증."""
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.version import RELEASE_NAME, __version__


class TestMetaApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_health_is_available_without_game_session(self):
        main.SESSION = None
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "version": __version__})

    def test_metadata_is_available_without_game_session(self):
        main.SESSION = None
        response = self.client.get("/api/meta")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["name"], "KBO 매니저")
        self.assertEqual(body["version"], __version__)
        self.assertEqual(body["release_name"], RELEASE_NAME)
        self.assertRegex(body["python"], r"^\d+\.\d+\.\d+")
        self.assertIsInstance(body["save_exists"], bool)
        self.assertIn("platform", body)
        self.assertIn("frozen", body)


if __name__ == "__main__":
    unittest.main()
