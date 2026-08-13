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
        self.assertNotIn("localStorage", html)
        self.assertNotIn("sessionStorage", html)
        self.assertNotIn("?token=", html)

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


if __name__ == "__main__":
    unittest.main()
