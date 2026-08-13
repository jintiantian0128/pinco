import os
import tempfile
import unittest
from unittest.mock import patch

import main
from state_store import JsonFileStateStore


class PilotFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = JsonFileStateStore(
            os.path.join(self.directory.name, "state.json"),
            main.default_beta_state,
        )
        state = main.default_beta_state()
        self.user = main.ensure_user(state, "pilot-feedback-device", "首批用户", "test")
        self.user_id = self.user["profile"]["user_id"]
        self.store.save(state)
        self.store_patch = patch.object(main, "_state_store", self.store)
        self.token_patch = patch.object(main, "PINCO_ADMIN_TOKEN", "a" * 32)
        self.store_patch.start()
        self.token_patch.start()

    def tearDown(self):
        self.token_patch.stop()
        self.store_patch.stop()
        self.directory.cleanup()

    def submit(self, professional=4, emotional=5, intent="yes", helpful="证据库", blocker="岗位筛选"):
        return main.submit_pilot_feedback(main.PilotFeedbackRequest(
            user_id=self.user_id,
            professional_value_score=professional,
            emotional_value_score=emotional,
            return_intent=intent,
            most_helpful=helpful,
            biggest_blocker=blocker,
        ))

    def test_feedback_is_upserted_and_metrics_use_latest_user_answer(self):
        first = self.submit()
        second = self.submit(professional=3, emotional=4, intent="unsure", helpful="面试练习")

        self.assertEqual(first["feedback"]["id"], second["feedback"]["id"])
        saved = main.get_pilot_feedback(self.user_id)["feedback"]
        self.assertEqual(saved["most_helpful"], "面试练习")
        self.assertEqual(saved["return_intent"], "unsure")

        state = self.store.load()
        self.assertEqual(len(state["pilot_feedback"]), 1)
        self.assertEqual(
            sum(1 for item in state["events"] if item.get("name") == "pilot.feedback.submitted"),
            2,
        )
        metrics = main.get_pmf_metrics("a" * 32)["decision_metrics"]["pilot_feedback"]
        self.assertEqual(metrics["responses"], 1)
        self.assertEqual(metrics["professional_value_average"], 3)
        self.assertEqual(metrics["emotional_value_average"], 4)
        self.assertEqual(metrics["return_yes_rate"], 0)

    def test_account_deletion_removes_feedback_and_event(self):
        self.submit()
        main.delete_account(main.AccountDeleteRequest(
            user_id=self.user_id,
            confirmation="DELETE",
        ))
        state = self.store.load()
        self.assertEqual(state["pilot_feedback"], [])
        self.assertFalse(any(
            item.get("user_id") == self.user_id for item in state["events"]
        ))

    def test_invalid_return_intent_is_rejected(self):
        with self.assertRaises(main.HTTPException) as raised:
            self.submit(intent="maybe")
        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
