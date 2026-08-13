import unittest

from career_taxonomy import match_role_track, role_interview_focus, translate_job_query


class CareerTaxonomyTests(unittest.TestCase):
    def test_legacy_role_aliases_expand_search_without_claiming_current_jobs(self):
        self.assertEqual(match_role_track("上海大模型产品经理"), "ai_product_manager")
        self.assertEqual(translate_job_query("AI 产品运营"), "AI product operations")
        self.assertEqual(translate_job_query("Rust 后端"), "Rust 后端")

    def test_interview_focus_is_role_specific_but_contains_no_fixed_questions(self):
        pm_focus = role_interview_focus("AI 产品经理")
        engineer_focus = role_interview_focus("大模型应用工程师")
        self.assertIn("模型能力边界与方案取舍", pm_focus)
        self.assertIn("RAG 与知识检索", engineer_focus)
        self.assertNotEqual(pm_focus, engineer_focus)


if __name__ == "__main__":
    unittest.main()
