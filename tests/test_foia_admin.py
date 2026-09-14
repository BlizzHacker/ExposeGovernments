import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


class FoiaAdminTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.data_dir = Path(cls.temporary.name)
        cls.token_path = cls.data_dir / "admin-token"
        cls.token_path.write_text("test-secret", encoding="utf-8")
        os.environ["EXPOSE_DATA_DIR"] = str(cls.data_dir)
        os.environ["EXPOSE_ADMIN_TOKEN_PATH"] = str(cls.token_path)
        os.environ["EXPOSE_INVESTIGATION_DIR"] = str(cls.data_dir / "investigations")

        generator = types.ModuleType("orr-pdf-generator")

        def generate(record):
            path = cls.data_dir / (record["id"] + ".pdf")
            path.write_bytes(b"%PDF-1.4\n")
            return path

        generator.generate_orr_pdf = generate
        sys.modules["orr-pdf-generator"] = generator
        source = Path(__file__).parents[1] / "ops" / "live" / "foia-api.py"
        spec = importlib.util.spec_from_file_location("foia_api_under_test", source)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.client = cls.module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        os.environ.pop("EXPOSE_DATA_DIR", None)
        os.environ.pop("EXPOSE_ADMIN_TOKEN_PATH", None)
        os.environ.pop("EXPOSE_INVESTIGATION_DIR", None)

    def setUp(self):
        for path in self.data_dir.glob("*"):
            if path != self.token_path and path.is_file():
                path.unlink()
        self.module.save_db(
            {
                "last_id": 1,
                "requests": [
                    {
                        "id": "abc123",
                        "type": "standard",
                        "description": "All agreements concerning the named program.",
                        "agency": "city_clerk",
                        "recipient_name": "City Clerk",
                        "status": "pending_review",
                        "created_at": "2026-09-01T12:00:00+00:00",
                        "updates": [],
                    }
                ],
            }
        )

    @property
    def auth(self):
        return {"Authorization": "Bearer test-secret"}

    def test_unsigned_jwt_is_rejected(self):
        unsigned_token = ".".join(
            ["eyJhbGciOiJub25lIn0", "eyJpc3MiOiJhdXRoZW50aWsifQ", ""]
        )
        response = self.client.get(
            "/api/foia/admin/pending",
            headers={"Authorization": "Bearer " + unsigned_token},
        )
        self.assertEqual(response.status_code, 401)

    def test_preparation_and_delivery_are_separate_states(self):
        prepared = self.client.post("/api/foia/admin/approve/abc123", headers=self.auth)
        self.assertEqual(prepared.status_code, 200)
        self.assertEqual(prepared.get_json()["status"], "prepared_for_delivery")

        record = self.module.load_db()["requests"][0]
        self.assertEqual(record["status"], "prepared_for_delivery")
        self.assertTrue(record["pdf_url"].endswith("abc123.pdf"))

        delivered = self.client.post(
            "/api/foia/admin/mark-delivered/abc123",
            headers=self.auth,
            json={"delivery_note": "Hand delivered to the clerk on September 13, 2026."},
        )
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(self.module.load_db()["requests"][0]["status"], "sent")

    def test_review_updates_use_optimistic_concurrency(self):
        first = self.client.post(
            "/api/foia/admin/review/foia:miamiok:abc123",
            headers=self.auth,
            json={"status": "needs_records", "notes": "Obtain the underlying contract.", "expected_version": 0},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["review"]["version"], 1)

        stale = self.client.post(
            "/api/foia/admin/review/foia:miamiok:abc123",
            headers=self.auth,
            json={"status": "closed", "notes": "Stale edit", "expected_version": 0},
        )
        self.assertEqual(stale.status_code, 409)

    def test_network_response_contains_fixed_chapter_inventory(self):
        self.module.NETWORK_SNAPSHOT_PATH.write_text(
            json.dumps(
                {
                    "generated_at": "2026-09-13T12:00:00+00:00",
                    "chapters": [
                        {
                            "key": "miamiok",
                            "health": {"status": "ok", "detail": "HTTPS 200"},
                            "automation": {"status": "ok", "detail": "Current"},
                            "requests": {"connected": True, "total": 1, "pending": 1},
                        }
                    ],
                    "errors": [],
                }
            ),
            encoding="utf-8",
        )
        response = self.client.get("/api/foia/admin/network", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["chapters"]), 14)
        self.assertEqual(payload["chapters"][0]["health"]["status"], "ok")
        self.assertEqual(payload["items"][0]["review"]["version"], 0)


if __name__ == "__main__":
    unittest.main()
