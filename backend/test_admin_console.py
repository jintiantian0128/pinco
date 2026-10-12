import os
import tempfile
import unittest
from unittest.mock import patch

import main
from state_store import JsonFileStateStore


class AdminConsoleTests(unittest.TestCase):
    def test_console_is_no_store_and_never_embeds_admin_token(self):
        response = main.admin_console()
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        with open(response.path, "r", encoding="utf-8") as file:
            html = file.read()
        self.assertIn("Pinco 运营工作台", html)
        self.assertIn("首批用户愿意继续用", html)
        self.assertIn("pilot_feedback", html)
        self.assertIn("实名（仅审核可见）", html)
        self.assertIn("对外展示名", html)
        self.assertIn("expert-demo-ai-pm", html)
        self.assertIn("bind_expert_id", html)
        self.assertIn("data-tab=\"events\"", html)
        self.assertIn("/api/v1/admin/events", html)
        self.assertIn("用户行为", html)
        self.assertIn("data-tab=\"system\"", html)
        self.assertIn("/api/v1/admin/config", html)
        self.assertIn("保存并应用", html)
        self.assertIn("/api/v1/admin/login", html)
        self.assertIn('id="username"', html)
        self.assertIn('id="password"', html)
        self.assertNotIn('id="token"', html)
        self.assertNotIn("localStorage", html)
        self.assertNotIn("sessionStorage", html)
        self.assertNotIn("?token=", html)

    def test_admin_password_login_returns_short_lived_signed_session(self):
        main._admin_login_failures.clear()
        request = main.Request({"type": "http", "client": ("192.0.2.10", 12345), "headers": []})
        with patch.object(main, "PINCO_ADMIN_TOKEN", "c" * 40), patch.object(main, "PINCO_ADMIN_USERNAME", "pinco-owner"), patch.object(main, "PINCO_ADMIN_PASSWORD", "a-unique-password-123"):
            result = main.admin_login(main.AdminLoginRequest(username="pinco-owner", password="a-unique-password-123"), request)
            main.require_admin_token(result["access_token"])
            self.assertEqual(result["expires_in"], 8 * 60 * 60)
            with self.assertRaises(main.HTTPException) as denied:
                main.admin_login(main.AdminLoginRequest(username="pinco-owner", password="wrong-password"), request)
            self.assertEqual(denied.exception.status_code, 401)
            with self.assertRaises(main.HTTPException) as invalidated_after_password_change:
                with patch.object(main, "PINCO_ADMIN_PASSWORD", "new-password-rotated"):
                    main.require_admin_token(result["access_token"])
            self.assertEqual(invalidated_after_password_change.exception.status_code, 403)

    def test_report_queue_contains_bounded_post_context(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            state["community_posts"].append({
                "id": "post-review",
                "title": "待核验内容",
                "content": "运营需要看到这段正文才能做判断。",
                "post_type": "share",
                "author_name": "测试用户",
                "moderation_status": "pending_review",
                "is_featured": False,
                "created_at": "2026-08-13T00:00:00+08:00",
            })
            state["community_reports"].append({
                "id": "report-review",
                "post_id": "post-review",
                "user_id": "reporter",
                "reason": "疑似夸大经历",
                "status": "pending",
                "created_at": "2026-08-13T00:01:00+08:00",
            })
            store.save(state)
            with patch.object(main, "_state_store", store), patch.object(main, "PINCO_ADMIN_TOKEN", "a" * 32):
                result = main.list_community_reports("a" * 32)
        self.assertEqual(result["reports"][0]["post"]["title"], "待核验内容")
        self.assertEqual(result["reports"][0]["post"]["moderation_status"], "pending_review")
        self.assertNotIn("created_by", result["reports"][0]["post"])

    def test_admin_events_are_authenticated_bounded_and_do_not_expose_properties(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            state["events"] = [{
                "id": "event-1",
                "name": "screen.viewed",
                "user_id": "private-user-id",
                "session_id": "private-session-id",
                "created_at": "2026-10-12T10:00:00+08:00",
                "properties": {"message": "private chat body", "page": "conversation"},
            }]
            store.save(state)
            with patch.object(main, "_state_store", store), patch.object(main, "PINCO_ADMIN_TOKEN", "a" * 32):
                with self.assertRaises(main.HTTPException) as denied:
                    main.list_admin_events(x_pinco_admin_token=None)
                self.assertEqual(denied.exception.status_code, 403)
                result = main.list_admin_events(x_pinco_admin_token="a" * 32)
        self.assertEqual(result["total_events"], 1)
        self.assertEqual(result["events"][0]["name"], "screen.viewed")
        self.assertNotIn("private-user-id", str(result))
        self.assertNotIn("private-session-id", str(result))
        self.assertNotIn("private chat body", str(result))
        self.assertNotIn("properties", result["events"][0])

    def test_admin_model_config_is_protected_and_never_returns_api_key(self):
        with patch.object(main, "PINCO_ADMIN_TOKEN", "b" * 32), patch.object(main, "LLM_PROVIDER", "openai"), patch.object(main, "OPENAI_API_KEY", "top-secret-key"):
            with self.assertRaises(main.HTTPException) as denied:
                main.get_admin_config(x_pinco_admin_token=None)
            self.assertEqual(denied.exception.status_code, 403)
            result = main.get_admin_config(x_pinco_admin_token="b" * 32)
        self.assertTrue(result["api_key_configured"])
        self.assertNotIn("top-secret-key", str(result))


if __name__ == "__main__":
    unittest.main()
