import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import main
from state_store import JsonFileStateStore


class TrustFoundationTests(unittest.TestCase):
    def test_json_state_store_round_trip_and_atomic_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = JsonFileStateStore(path, lambda: {"users": {}})
            self.assertEqual(store.load(), {"users": {}})
            store.save({"users": {"u1": {"messages": []}}})
            self.assertEqual(store.load()["users"]["u1"]["messages"], [])
            self.assertFalse(store.health()["durable"])

    def test_llm_retry_never_returns_canned_answer(self):
        with patch.object(main, "llm_chat", side_effect=RuntimeError("429 quota")) as mocked:
            with self.assertRaises(RuntimeError):
                main.llm_chat_with_fallback([{"role": "user", "content": "我面试挂了"}])
            self.assertEqual(mocked.call_count, 2)

    def test_jd_failure_is_explicit(self):
        request = main.JDAnalyzeRequest(jd_text="AI 产品经理，要求三年经验和数据分析能力")
        with patch.object(main, "llm_chat_with_fallback", side_effect=RuntimeError("upstream unavailable")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.analyze_jd(request))
        self.assertEqual(raised.exception.status_code, 502)

    def test_resume_failure_never_returns_a_fixed_score(self):
        request = object()
        with patch.object(main, "get_uploaded_file", new=AsyncMock(return_value=("resume.pdf", b"pdf", {}))), patch.object(
            main, "extract_text_from_resume", return_value="真实简历文本" * 20
        ), patch.object(main, "llm_chat_with_fallback", side_effect=RuntimeError("upstream unavailable")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.upload_resume(request))
        self.assertEqual(raised.exception.status_code, 502)

    def test_image_validation_receipt_has_no_fake_remote_url(self):
        request = object()
        valid_png = b"\x89PNG\r\n\x1a\n" + b"payload"
        with patch.object(main, "get_uploaded_file", new=AsyncMock(return_value=("screenshot.png", valid_png, {}))):
            result = asyncio.run(main.upload_image(request))
        self.assertFalse(result["stored"])
        self.assertFalse(result["analysis_available"])
        self.assertNotIn("url", result)

    def test_membership_is_not_activated_without_payment(self):
        with self.assertRaises(HTTPException) as raised:
            main.subscribe_membership(
                main.MembershipSubscribeRequest(user_id="user-test", plan_id="pro", payment_method="wechat")
            )
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["code"], "PAYMENT_NOT_AVAILABLE")

    def test_payment_order_creation_is_idempotent_and_does_not_activate_membership(self):
        class FakePayClient:
            def __init__(self):
                self.pay_calls = 0

            def pay(self, **kwargs):
                self.pay_calls += 1
                self.last_pay = kwargs
                return 200, json.dumps({"prepay_id": "wx-prepay-real"})

            def sign(self, values):
                self.last_sign = values
                return "server-signature"

        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            fake = FakePayClient()
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None), patch.object(
                main, "can_user_initiate_payment", return_value=True
            ), patch.object(main, "get_wechat_pay_client", return_value=fake), patch.object(main, "WECHAT_APP_ID", "wx-test-app"):
                state = main.default_beta_state()
                user = main.ensure_user(state, "payment-device", "支付测试", "weapp")
                user["profile"]["wechat_openid"] = "openid-payment-test"
                store.save(state)
                request = main.MembershipSubscribeRequest(
                    user_id=user["profile"]["user_id"],
                    plan_id="pro",
                    billing_cycle="monthly",
                    request_id="membership-request-001",
                )
                first = main.subscribe_membership(request)
                second = main.subscribe_membership(request)
            self.assertEqual(first["order_id"], second["order_id"])
            self.assertEqual(fake.pay_calls, 1)
            self.assertEqual(first["payment_params"]["paySign"], "server-signature")
            persisted = store.load()
            self.assertEqual(persisted["orders"][0]["status"], "unpaid")
            self.assertEqual(persisted["users"][user["profile"]["user_id"]].get("membership", {}).get("plan_id", "free"), "free")

    def test_verified_payment_amount_is_required_and_fulfillment_is_idempotent(self):
        state = main.default_beta_state()
        with patch.object(main, "exchange_wechat_code", return_value=None), patch.object(main, "WECHAT_APP_ID", "wx-app"), patch.object(main, "WECHAT_PAY_MCH_ID", "mch-1"):
            user = main.ensure_user(state, "callback-device", "回调测试", "weapp")
            user_id = user["profile"]["user_id"]
            state["orders"].append({
                "id": "order-callback-1",
                "user_id": user_id,
                "product_type": "membership",
                "amount_total": 2990,
                "currency": "CNY",
                "status": "unpaid",
                "fulfilled": False,
                "metadata": {"plan_id": "pro", "billing_cycle": "monthly"},
            })
            transaction = {
                "out_trade_no": "order-callback-1",
                "trade_state": "SUCCESS",
                "appid": "wx-app",
                "mchid": "mch-1",
                "transaction_id": "wx-transaction-1",
                "success_time": "2026-08-05T10:00:00+08:00",
                "amount": {"total": 1, "currency": "CNY"},
            }
            with self.assertRaises(ValueError):
                main._apply_successful_payment(state, transaction)
            self.assertEqual(user.get("membership", {}).get("plan_id", "free"), "free")
            transaction["amount"]["total"] = 2990
            first = main._apply_successful_payment(state, transaction)
            expire_at = user["membership"]["expire_at"]
            second = main._apply_successful_payment(state, transaction)
            self.assertEqual(first["status"], "paid")
            self.assertTrue(second["fulfilled"])
            self.assertEqual(user["membership"]["plan_id"], "pro")
            self.assertEqual(user["membership"]["expire_at"], expire_at)
            self.assertEqual([item["name"] for item in state["events"]].count("payment.fulfilled"), 1)

    def test_membership_quota_is_server_enforced_and_renewal_cannot_reset_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "quota-user", "额度用户", "weapp")
                user_id = user["profile"]["user_id"]
                future_reset = "2099-01-01T00:00:00Z"
                user["membership"] = {
                    "plan_id": "pro",
                    "plan_name": "Pro版",
                    "expire_at": "2099-12-31T00:00:00Z",
                    "ai_chat_used": 0,
                    "resume_used": 0,
                    "interview_used": 5,
                    "usage_reset_at": future_reset,
                }
                store.save(state)
                with patch.object(main, "llm_chat_with_fallback") as llm:
                    with self.assertRaises(HTTPException) as raised:
                        asyncio.run(main.start_interview_practice(main.InterviewPracticeStartRequest(
                            user_id=user_id, position="AI 产品经理", duration_minutes=5
                        )))
                self.assertEqual(raised.exception.status_code, 402)
                self.assertEqual(raised.exception.detail["code"], "MEMBERSHIP_LIMIT_REACHED")
                llm.assert_not_called()

                state = store.load()
                state["users"][user_id]["membership"]["usage_reset_at"] = "2020-01-01T00:00:00Z"
                store.save(state)
                plan_json = '{"plan_summary":"练清岗位匹配","questions":["问题1","问题2","问题3"],"focus":["结构","证据"]}'
                with patch.object(main, "llm_chat_with_fallback", return_value=plan_json):
                    asyncio.run(main.start_interview_practice(main.InterviewPracticeStartRequest(
                        user_id=user_id, position="AI 产品经理", duration_minutes=5
                    )))
                rolled = store.load()["users"][user_id]["membership"]
                self.assertEqual(rolled["interview_used"], 1)
                self.assertGreater(rolled["usage_reset_at"], "2026")

                rolled["interview_used"] = 4
                rolled["usage_reset_at"] = future_reset
                state = store.load()
                state["users"][user_id]["membership"] = rolled
                main._activate_membership_from_order(state, {
                    "id": "renewal-order",
                    "user_id": user_id,
                    "metadata": {"plan_id": "pro", "billing_cycle": "monthly"},
                })
                renewed = state["users"][user_id]["membership"]
                self.assertEqual(renewed["interview_used"], 4)
                self.assertEqual(renewed["usage_reset_at"], future_reset)

    def test_expert_refund_only_releases_slot_after_verified_refund(self):
        state = main.default_beta_state()
        with patch.object(main, "exchange_wechat_code", return_value=None), patch.object(main, "WECHAT_APP_ID", "wx-app"), patch.object(main, "WECHAT_PAY_MCH_ID", "mch-1"):
            user = main.ensure_user(state, "refund-user", "退款用户", "weapp")
            user_id = user["profile"]["user_id"]
            state["experts"] = [{"id": "expert-1", "slots": [], "status": "approved"}]
            booking = {
                "id": "booking-paid-1",
                "user_id": user_id,
                "expertId": "expert-1",
                "slot": "2026-08-10 20:00",
                "status_code": "confirmed",
                "status": "待服务",
                "payment_status": "paid",
            }
            state["expert_bookings"] = [booking]
            user["bookings"] = [dict(booking)]
            order = {
                "id": "order-expert-1",
                "user_id": user_id,
                "product_type": "expert",
                "amount_total": 9900,
                "currency": "CNY",
                "status": "refund_processing",
                "fulfilled": True,
                "refund_idempotency_no": "refund-1",
                "metadata": {"booking_id": booking["id"], "expert_id": "expert-1"},
            }
            state["orders"] = [order]
            refund = {
                "out_trade_no": order["id"],
                "out_refund_no": "refund-1",
                "refund_id": "wx-refund-1",
                "refund_status": "SUCCESS",
                "success_time": "2026-08-05T11:00:00+08:00",
                "amount": {"refund": 9900, "total": 9900, "currency": "CNY"},
            }
            main._apply_successful_refund(state, refund)
            main._apply_successful_refund(state, refund)
            self.assertEqual(order["status"], "refunded")
            self.assertEqual(booking["payment_status"], "refunded")
            self.assertEqual(state["experts"][0]["slots"], ["2026-08-10 20:00"])
            self.assertEqual([item["name"] for item in state["events"]].count("payment.refunded"), 1)

    def test_expert_owner_cannot_delete_account_until_paid_service_is_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                owner = main.ensure_user(state, "expert-owner-delete", "专家", "weapp")
                buyer = main.ensure_user(state, "expert-buyer-delete", "买方", "weapp")
                owner_id = owner["profile"]["user_id"]
                buyer_id = buyer["profile"]["user_id"]
                expert_id = "expert-delete-lifecycle"
                booking = {
                    "id": "booking-delete-lifecycle",
                    "user_id": buyer_id,
                    "expert_owner_user_id": owner_id,
                    "expertId": expert_id,
                    "expertName": "专家",
                    "status_code": "confirmed",
                    "status": "待服务",
                    "payment_status": "paid",
                }
                state["experts"] = [{"id": expert_id, "owner_user_id": owner_id, "status": "approved"}]
                state["expert_bookings"] = [booking]
                buyer["bookings"] = [dict(booking)]
                state["orders"] = [{
                    "id": "order-delete-lifecycle",
                    "user_id": buyer_id,
                    "product_type": "expert",
                    "status": "paid",
                    "fulfilled": True,
                    "metadata": {"booking_id": booking["id"], "expert_id": expert_id},
                }]
                store.save(state)

                with self.assertRaises(HTTPException) as raised:
                    main.delete_account(main.AccountDeleteRequest(user_id=owner_id, confirmation="DELETE"))
                self.assertEqual(raised.exception.status_code, 409)
                self.assertIn(owner_id, store.load()["users"])

                state = store.load()
                state["expert_bookings"][0]["status_code"] = "completed"
                state["expert_bookings"][0]["status"] = "已完成"
                state["users"][buyer_id]["bookings"][0]["status_code"] = "completed"
                state["users"][buyer_id]["bookings"][0]["status"] = "已完成"
                store.save(state)
                main.delete_account(main.AccountDeleteRequest(user_id=owner_id, confirmation="DELETE"))

            persisted = store.load()
            self.assertNotIn(owner_id, persisted["users"])
            retained = persisted["expert_bookings"][0]
            self.assertEqual(retained["expertName"], "已注销专家")
            self.assertNotIn("expert_owner_user_id", retained)
            self.assertTrue(retained["expertId"].startswith("deleted-expert-"))
            self.assertEqual(persisted["users"][buyer_id]["bookings"][0]["expertName"], "已注销专家")
            self.assertTrue(persisted["orders"][0]["metadata"]["expert_id"].startswith("deleted-expert-"))

    def test_membership_interest_is_persisted_without_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "membership-device", "意向用户", "weapp")
                store.save(state)
                user_id = user["profile"]["user_id"]
                response = main.capture_membership_interest(main.MembershipInterestRequest(
                    user_id=user_id, plan_id="pro", billing_cycle="monthly"
                ))
                status = main.get_membership_status(user_id)
            self.assertIn("不会扣款", response["message"])
            self.assertEqual(status["plan_id"], "free")
            persisted = store.load()
            self.assertEqual(persisted["membership_interests"][0]["plan_id"], "pro")

    def test_bootstrap_exposes_session_token_but_not_its_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None), patch.object(
                main, "build_miniapp_readiness", return_value={}
            ), patch.object(main, "build_service_health_summary", return_value={}):
                response = main.miniapp_bootstrap(main.MiniappBootstrapRequest(
                    device_id="session-device", nickname="会话用户", platform="weapp"
                ))
                second = main.miniapp_bootstrap(main.MiniappBootstrapRequest(
                    device_id="session-device", nickname="会话用户", platform="weapp"
                ))
                self.assertTrue(main.user_session_is_valid(response["user"]["user_id"], response["session_token"]))
                self.assertTrue(main.user_session_is_valid(second["user"]["user_id"], second["session_token"]))
            self.assertGreaterEqual(len(response["session_token"]), 40)
            self.assertNotIn("session_token_hash", response["user"])
            self.assertNotIn("session_token_hashes", response["user"])
            persisted_profile = next(iter(store.load()["users"].values()))["profile"]
            self.assertNotEqual(persisted_profile["session_token_hashes"][0]["hash"], response["session_token"])

    def test_wechat_openid_becomes_stable_identity(self):
        state = main.default_beta_state()
        with patch.object(main, "exchange_wechat_code", return_value={"openid": "openid-123"}):
            user = main.ensure_user(state, "device-a", "小明", "weapp", "real-code")
        self.assertTrue(user["profile"]["wechat_bound"])
        self.assertEqual(user["profile"]["auth_level"], "wechat")
        self.assertEqual(user["profile"]["user_id"], main.stable_user_id("wechat:openid-123"))
        self.assertEqual(user["profile"]["wechat_openid"], "openid-123")

    def test_wechat_openid_never_leaves_bootstrap_or_account_export(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(
                main, "exchange_wechat_code", return_value={"openid": "private-openid-456"}
            ), patch.object(main, "build_miniapp_readiness", return_value={}), patch.object(
                main, "build_service_health_summary", return_value={}
            ):
                bootstrap = main.miniapp_bootstrap(main.MiniappBootstrapRequest(
                    device_id="openid-private-device", platform="weapp", code="real-code"
                ))
                exported = main.export_account(bootstrap["user"]["user_id"])
            self.assertNotIn("wechat_openid", bootstrap["user"])
            self.assertNotIn("wechat_openid", exported["profile"])
            persisted = next(iter(store.load()["users"].values()))["profile"]
            self.assertEqual(persisted["wechat_openid"], "private-openid-456")

    def test_unverified_payment_notification_is_rejected_without_state_change(self):
        class FakeRequest:
            headers = {"wechatpay-signature": "invalid"}

            async def body(self):
                return b'{"event_type":"TRANSACTION.SUCCESS"}'

        class RejectingClient:
            def callback(self, headers, body):
                return None

        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "get_wechat_pay_client", return_value=RejectingClient()):
                response = asyncio.run(main.handle_wechat_payment_notification(FakeRequest()))
            self.assertEqual(response.status_code, 400)
            self.assertEqual(store.load()["orders"], [])

    def test_analytics_drops_sensitive_text(self):
        sanitized = main.sanitize_event_properties({
            "content": "private chat",
            "jd_text": "private jd",
            "scenario": "interview",
            "duration": 30,
        })
        self.assertNotIn("content", sanitized)
        self.assertNotIn("jd_text", sanitized)
        self.assertEqual(sanitized["scenario"], "interview")
        self.assertEqual(sanitized["duration"], 30)

    def test_job_search_only_returns_source_linked_results(self):
        raw = [
            {"title": "AI产品经理 - 示例科技", "url": "https://www.liepin.com/job/123", "snippet": "负责 AI 产品规划"},
            {"title": "AI产品经理 - 无链接公司", "url": "", "snippet": "不应返回"},
        ]
        with patch.object(main, "_baidu_search_jobs", return_value=raw), patch.object(main, "JSEARCH_API_KEY", None):
            response = asyncio.run(main.search_jobs(main.JobSearchRequest(
                query="AI产品经理", platforms="liepin", limit=10
            )))
        self.assertEqual(response.total, 1)
        self.assertTrue(response.jobs[0].verified_source)
        self.assertEqual(response.jobs[0].url, "https://www.liepin.com/job/123")

    def test_five_minute_practice_persists_real_report(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "practice-device", "练习用户", "weapp")
                store.save(state)
                user_id = user["profile"]["user_id"]
                plan_json = '{"plan_summary":"练清岗位匹配","questions":["请用60秒自我介绍","为什么选择这个岗位","请概述最匹配的项目"],"focus":["结构","证据"]}'
                rescue_json = '{"framework":"先说结论，再讲真实行动，最后说明结果边界","first_prompt":"你最近一次真正负责的动作是什么？"}'
                mid_json = '{"feedback":"结构清楚，还缺结果数据","scores":{"content":80,"structure":85,"evidence":60,"role_fit":78,"clarity":82,"adaptability":75},"better_answer":"补充可验证结果","follow_up":"请继续用真实项目说明"}'
                report_json = '{"feedback":"结构清楚，还缺结果数据","scores":{"content":80,"structure":85,"evidence":60,"role_fit":78,"clarity":82,"adaptability":75},"better_answer":"补充可验证结果","follow_up":"","report":{"overall_score":76,"dimension_scores":{"content":80,"structure":85,"evidence":60,"role_fit":78,"clarity":82,"adaptability":75},"strengths":["结构清楚"],"improvements":["补结果数据"],"next_drill":"再练一次项目结果"}}'
                with patch.object(main, "llm_chat_with_fallback", side_effect=[plan_json, rescue_json, mid_json, mid_json, report_json]):
                    started = asyncio.run(main.start_interview_practice(main.InterviewPracticeStartRequest(
                        user_id=user_id, position="AI 产品经理", duration_minutes=5, practice_style="warmup"
                    )))
                    rescue = main.rescue_interview_practice(
                        started["session_id"], main.InterviewPracticeRescueRequest(user_id=user_id)
                    )
                    for _ in range(3):
                        answered = asyncio.run(main.answer_interview_practice(
                            started["session_id"],
                            main.InterviewPracticeAnswerRequest(user_id=user_id, answer="我负责了需求分析并推动产品上线，用户使用率提升了百分之二十")
                        ))
                self.assertTrue(answered["completed"])
                self.assertEqual(started["practice_style"], "warmup")
                self.assertFalse(rescue["question_advanced"])
                self.assertEqual(rescue["question_index"], 1)
                self.assertEqual(answered["report"]["overall_score"], 76)
                persisted = store.load()["users"][user_id]["interview_sessions"][0]
                self.assertEqual(persisted["status"], "completed")
                self.assertEqual(persisted["practice_style"], "warmup")
                self.assertEqual(len(persisted["rescue_uses"]), 1)
                published = main.publish_interview_practice_report(
                    started["session_id"], main.InterviewReportPublishRequest(user_id=user_id)
                )
                repeated = main.publish_interview_practice_report(
                    started["session_id"], main.InterviewReportPublishRequest(user_id=user_id)
                )
                self.assertTrue(published["created"])
                self.assertFalse(repeated["created"])
                self.assertEqual(published["post"]["author"], "匿名求职者")
                self.assertIn("原始回答未公开", published["post"]["content"])
                self.assertNotIn("用户使用率提升了百分之二十", published["post"]["content"])

    def test_crisis_checkin_uses_safety_protocol_without_storing_note(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "support-device", "支持用户", "weapp")
                store.save(state)
                result = main.create_emotional_check_in(main.EmotionalCheckInRequest(
                    user_id=user["profile"]["user_id"],
                    intensity=1,
                    event_type="rejection",
                    note="我不想活了",
                ))
            self.assertTrue(result["check_in"]["crisis"])
            self.assertIsNone(result["check_in"]["note"])
            self.assertIn("12356", result["response"])
            self.assertIn("120/110", result["response"])

    def test_low_mood_follow_up_and_helpfulness_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "followup-device", "回访用户", "weapp")
                store.save(state)
                user_id = user["profile"]["user_id"]
                with patch.object(main, "llm_chat_with_fallback", return_value="我听见你今天很累。我们先只做一件小事，好吗？"):
                    result = main.create_emotional_check_in(main.EmotionalCheckInRequest(
                        user_id=user_id, intensity=2, event_type="rejection"
                    ))
                check_in_id = result["check_in"]["id"]
                state = store.load()
                state["users"][user_id]["emotional_check_ins"][0]["follow_up_due_at"] = "2020-01-01T00:00:00"
                store.save(state)
                due = main.get_due_support_follow_ups(user_id)["follow_ups"]
                self.assertEqual(due[0]["check_in_id"], check_in_id)
                main.submit_support_feedback(
                    check_in_id, main.SupportFeedbackRequest(
                        user_id=user_id, helpful=False, understood_score=1
                    )
                )
                main.respond_to_support_follow_up(
                    check_in_id, main.SupportFollowUpResponseRequest(
                        user_id=user_id, current_intensity=4, micro_action_completed=True
                    )
                )
                self.assertEqual(main.get_due_support_follow_ups(user_id)["follow_ups"], [])
                persisted = store.load()["users"][user_id]["emotional_check_ins"][0]
                self.assertFalse(persisted["helpful"])
                self.assertEqual(persisted["understood_score"], 1)
                self.assertEqual(persisted["follow_up_intensity"], 4)
                self.assertTrue(persisted["micro_action_completed"])
                with patch.object(main, "PINCO_ADMIN_TOKEN", "metrics-secret"):
                    metrics = main.get_pmf_metrics("metrics-secret")["decision_metrics"]["emotional_support_helpful"]
                self.assertEqual(metrics["understood_score_sample"], 1)
                self.assertEqual(metrics["understood_score_average"], 1)
                self.assertEqual(metrics["understood_score_at_least_4_rate"], 0)
                self.assertEqual(metrics["micro_action_sample"], 1)
                self.assertEqual(metrics["micro_action_completed_rate"], 1)

    def test_job_materials_require_real_evidence_and_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "career-device", "求职用户", "weapp")
                store.save(state)
                user_id = user["profile"]["user_id"]
                evidence = main.create_evidence(main.EvidenceCreateRequest(
                    user_id=user_id,
                    title="推荐页改版",
                    situation="新用户留存低",
                    action="访谈用户并推动推荐策略和页面改版",
                    result="次日留存提升",
                    metrics="A/B 实验提升 12%",
                    skills=["用户研究", "实验设计"],
                ))["evidence"]
                job = main.create_workspace_job(main.WorkspaceJobCreateRequest(
                    user_id=user_id,
                    title="AI 产品经理",
                    company="示例科技",
                    jd_text="负责 AI 产品规划、用户研究和数据实验",
                ))["job"]
                material_json = '{"fit_decision":"MAYBE","fit_reasons":["用户研究证据匹配，但缺 AI 项目证据"],"match_summary":"用户研究匹配，AI经验是缺口","resume_bullets":["通过访谈和A/B实验推动推荐页改版，次日留存提升12%"],"outreach_message":"希望应聘该岗位","interview_stories":[{"question":"如何做实验","evidence_id":"' + evidence["id"] + '","answer_outline":"按真实实验说明"}],"gaps":["AI项目证据"]}'
                with patch.object(main, "llm_chat_with_fallback", return_value=material_json):
                    response = main.generate_job_materials(job["id"], main.JobMaterialGenerateRequest(
                        user_id=user_id, evidence_ids=[evidence["id"]]
                    ))
                edited = main.update_job_materials(job["id"], main.JobMaterialsUpdateRequest(
                    user_id=user_id,
                    resume_bullets=["推动推荐页改版，A/B 实验次日留存提升 12%"],
                    outreach_message="希望用真实实验经验参与该岗位。",
                ))
                feedback = main.submit_job_material_feedback(job["id"], main.JobMaterialFeedbackRequest(
                    user_id=user_id, rating="minor_edit"
                ))
                workspace = main.get_workspace(user_id)
                radar = workspace["capability_radar"]
                learning_plan = workspace["learning_plan"]
                updated_plan = main.update_learning_plan_progress(main.LearningPlanProgressRequest(
                    user_id=user_id, plan_id=learning_plan["id"], day=1, completed=True
                ))["learning_plan"]
                with patch.object(main, "PINCO_ADMIN_TOKEN", "m" * 32):
                    metrics = main.get_pmf_metrics("m" * 32)
            self.assertIn("AI经验是缺口", response["materials"]["match_summary"])
            self.assertEqual(response["materials"]["fit_decision"], "MAYBE")
            self.assertTrue(edited["materials"]["user_edited"])
            self.assertEqual(feedback["feedback"]["rating"], "minor_edit")
            persisted = store.load()["users"][user_id]["jobs"][0]["materials"]
            self.assertEqual(persisted["evidence_ids"], [evidence["id"]])
            self.assertEqual(persisted["user_feedback"]["rating"], "minor_edit")
            self.assertGreater(radar["dimensions"][0]["score"], 0)
            self.assertEqual(len(learning_plan["days"]), 7)
            self.assertEqual(updated_plan["completed_count"], 1)
            self.assertTrue(updated_plan["days"][0]["completed"])
            self.assertIn("MAYBE", updated_plan["next_batch_strategy"])
            self.assertEqual(metrics["decision_metrics"]["material_directly_usable"]["feedback_count"], 1)
            self.assertEqual(metrics["decision_metrics"]["material_directly_usable"]["fabrication_reports"], 0)

    def test_public_job_without_url_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            main.create_workspace_job(main.WorkspaceJobCreateRequest(
                user_id="missing", title="AI 产品", company="公司", source="猎聘"
            ))
        self.assertEqual(raised.exception.status_code, 400)

    def test_job_status_returns_opt_in_emotional_support_for_key_moments(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "status-support-user", "求职者", "weapp")
                store.save(state)
                user_id = user["profile"]["user_id"]
                job = main.create_workspace_job(main.WorkspaceJobCreateRequest(
                    user_id=user_id,
                    title="AI 应用工程师",
                    company="目标公司",
                    jd_text="负责 RAG 应用评测和产品化",
                ))["job"]

                rejected = main.update_workspace_job_status(
                    job["id"], main.WorkspaceJobStatusRequest(user_id=user_id, status="rejected")
                )
                offered = main.update_workspace_job_status(
                    job["id"], main.WorkspaceJobStatusRequest(user_id=user_id, status="offer")
                )
                saved = main.update_workspace_job_status(
                    job["id"], main.WorkspaceJobStatusRequest(user_id=user_id, status="saved")
                )

            self.assertEqual(rejected["support_action"]["scenario"], "emotion")
            self.assertIn("结果不等于你的价值", rejected["support_action"]["title"])
            self.assertIn("事实条件", offered["support_action"]["prompt"])
            self.assertIsNone(saved["support_action"])

    def test_community_actions_persist_only_after_real_user_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "community-device", "小林", "weapp")
                store.save(state)
                user_id = user["profile"]["user_id"]
                created = main.create_community_post(main.CommunityPostCreateRequest(
                    user_id=user_id,
                    title="我的面试复盘方法",
                    content="每次只复盘一个被追问的问题，并补充可验证的结果。",
                    post_type="share",
                ))["post"]
                commented = main.create_community_comment(
                    created["id"],
                    main.CommunityCommentCreateRequest(user_id=user_id, text="补充：最好当天完成。"),
                )["post"]
                hugged = main.toggle_community_hug(
                    created["id"], main.CommunityActionRequest(user_id=user_id)
                )["post"]
            self.assertEqual(commented["comments"][0]["author"], "小林")
            self.assertTrue(hugged["isHugged"])
            persisted = store.load()["community_posts"]
            self.assertTrue(any(post["id"] == created["id"] for post in persisted))
            self.assertFalse(any(post["id"] in {"post-1", "post-2", "post-3"} for post in persisted))

    def test_expert_market_requires_review_then_supports_delivery_and_real_review(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None), patch.object(main, "PINCO_ADMIN_TOKEN", "admin-secret"):
                state = main.default_beta_state()
                expert_user = main.ensure_user(state, "expert-device", "周老师", "weapp")
                candidate = main.ensure_user(state, "candidate-device", "小陈", "weapp")
                store.save(state)
                expert_user_id = expert_user["profile"]["user_id"]
                candidate_user_id = candidate["profile"]["user_id"]
                applied = main.apply_as_expert(main.ExpertApplicationRequest(
                    user_id=expert_user_id,
                    real_name="周老师",
                    title="AI 产品面试教练",
                    intro="专注帮助零到五年经验的求职者梳理真实项目证据和面试表达。",
                    tags=["AI产品", "项目深挖"],
                    experience_summary="有五年 AI 产品工作经验，参与过三款线上产品，并持续辅导校招和社招面试。",
                    proof_urls=["https://example.com/portfolio"],
                    reference_price=99,
                    slots=["2026-08-08 20:00"],
                ))["application"]
                seeded = main.list_experts()["experts"]
                self.assertEqual(len(seeded), 3)
                self.assertTrue(all(item["isDemo"] for item in seeded))
                self.assertTrue(all("尚未指定真人" in item["verificationStatus"] for item in seeded))
                main.review_expert_application(
                    applied["id"],
                    main.ExpertApplicationReviewRequest(decision="approved", review_note="资料已人工核验"),
                    x_pinco_admin_token="admin-secret",
                )
                public_expert = next(
                    item for item in main.list_experts()["experts"]
                    if item["name"] == "周老师"
                )
                saved_job = main.create_workspace_job(main.WorkspaceJobCreateRequest(
                    user_id=candidate_user_id,
                    title="AI 产品经理",
                    company="目标公司",
                    jd_text="负责大模型应用评测、商业化和跨团队落地",
                ))["job"]
                main.create_evidence(main.EvidenceCreateRequest(
                    user_id=candidate_user_id,
                    title="评测体系落地",
                    action="设计离线评测集并推动研发接入发布流程",
                    result="核心场景回归时间缩短",
                    metrics="回归时间缩短30%",
                ))
                booking = main.create_booking(main.BookingCreateRequest(
                    user_id=candidate_user_id,
                    expert_id=public_expert["id"],
                    expert_name="不信任客户端名字",
                    topic="项目深挖",
                    slot="2026-08-08 20:00",
                    desc="希望把一个真实项目讲清楚",
                    job_id=saved_job["id"],
                    share_context_with_expert=True,
                ))["booking"]
                self.assertEqual(booking["expert_briefing"]["job"]["label"], "目标公司 · AI 产品经理")
                self.assertEqual(booking["expert_briefing"]["evidence"][0]["title"], "评测体系落地")
                self.assertIn("希望把一个真实项目讲清楚", booking["expert_briefing"]["key_questions"])
                confirmed = main.decide_expert_booking(
                    booking["id"],
                    main.ExpertBookingDecisionRequest(expert_user_id=expert_user_id, decision="confirmed"),
                )["booking"]
                self.assertEqual(confirmed["payment_status"], "not_charged_beta")
                main.complete_expert_booking(
                    booking["id"],
                    main.ExpertBookingCompleteRequest(
                        expert_user_id=expert_user_id,
                        delivery_summary="完成项目故事拆解，并留下下一次练习的三条行动。",
                        next_actions=["补齐评测集规模和上线前后对比", "完成一次10分钟项目深挖复练"],
                    ),
                )
                main.review_expert_booking(
                    booking["id"],
                    main.ExpertBookingReviewRequest(user_id=candidate_user_id, score=5, comment="追问很具体，建议可以执行。"),
                )
                listed = next(
                    item for item in main.list_experts()["experts"]
                    if item["id"] == public_expert["id"]
                )
                self.assertEqual(listed["rating"], 5)
                self.assertEqual(listed["servedCount"], 1)
                self.assertEqual(listed["slots"], [])
                main.update_expert_availability(
                    public_expert["id"],
                    main.ExpertAvailabilityRequest(user_id=expert_user_id, slots=["2026-08-09 20:00"]),
                )
                second = main.create_booking(main.BookingCreateRequest(
                    user_id=candidate_user_id,
                    expert_id=public_expert["id"],
                    expert_name="客户端伪造名字",
                    topic="客户端任意主题",
                    slot="2026-08-09 20:00",
                    desc="希望确认固定交付",
                ))["booking"]
                cancelled = main.cancel_expert_booking(
                    second["id"], main.BookingCancelRequest(user_id=candidate_user_id, reason="时间冲突")
                )["booking"]
                self.assertEqual(cancelled["status_code"], "cancelled")
                self.assertEqual(cancelled["refund_status"], "not_applicable_not_charged")
                self.assertEqual(second["topic"], listed["serviceName"])
                main.delete_account(main.AccountDeleteRequest(user_id=expert_user_id, confirmation="DELETE"))
                after_delete = store.load()
                self.assertNotIn(expert_user_id, after_delete["users"])
                self.assertTrue(all(item["isDemo"] for item in main.list_experts()["experts"]))
                buyer_bookings = after_delete["users"][candidate_user_id]["bookings"]
                self.assertTrue(all(item.get("expertName") == "已注销专家" for item in buyer_bookings))
                self.assertTrue(all(item.get("expert_owner_user_id") is None for item in after_delete["expert_bookings"]))

    def test_community_three_unique_reports_hold_content_for_review(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                author = main.ensure_user(state, "report-author", "作者", "weapp")
                reporters = [main.ensure_user(state, f"reporter-{index}", f"用户{index}", "weapp") for index in range(3)]
                store.save(state)
                post = main.create_community_post(main.CommunityPostCreateRequest(
                    user_id=author["profile"]["user_id"], title="待核验经验", content="这是用户发布的内容", post_type="share"
                ))["post"]
                for reporter in reporters:
                    result = main.report_community_post(
                        post["id"],
                        main.CommunityReportRequest(user_id=reporter["profile"]["user_id"], reason="疑似虚假求职信息"),
                    )
                self.assertTrue(result["pending_review"])
                public_ids = {item["id"] for item in main.get_community_posts(reporters[0]["profile"]["user_id"])["posts"]}
                author_ids = {item["id"] for item in main.get_community_posts(author["profile"]["user_id"])["posts"]}
                self.assertNotIn(post["id"], public_ids)
                self.assertIn(post["id"], author_ids)

    def test_account_export_omits_auth_secret_then_delete_removes_user(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "delete-device", "待删除用户", "weapp")
                main.issue_user_session(user)
                store.save(state)
                user_id = user["profile"]["user_id"]
                exported = main.export_account(user_id)
                self.assertNotIn("session_token_hash", exported["profile"])
                self.assertNotIn("session_token_hashes", exported["profile"])
                main.delete_account(main.AccountDeleteRequest(user_id=user_id, confirmation="DELETE"))
                self.assertNotIn(user_id, store.load()["users"])

    def test_community_job_binding_and_contribution_are_auditable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None), patch.object(
                main, "PINCO_ADMIN_TOKEN", "a" * 32
            ):
                state = main.default_beta_state()
                author = main.ensure_user(state, "points-author", "作者", "weapp")
                actor = main.ensure_user(state, "points-actor", "行动者", "weapp")
                store.save(state)
                author_id = author["profile"]["user_id"]
                actor_id = actor["profile"]["user_id"]
                job = main.create_workspace_job(main.WorkspaceJobCreateRequest(
                    user_id=author_id, title="AI 产品经理", company="真实公司", jd_text="负责 AI 产品评测"
                ))["job"]
                post = main.create_community_post(main.CommunityPostCreateRequest(
                    user_id=author_id,
                    title="一次真实复盘",
                    content="我如何从一次面试失败中复盘证据。",
                    post_type="share",
                    job_id=job["id"],
                    interview_round="业务一面",
                    experience_date="2026年8月",
                ))["post"]
                self.assertEqual(post["boundJobId"], job["id"])
                self.assertEqual(post["experienceRound"], "业务一面")
                self.assertEqual(post["experienceDate"], "2026年8月")
                public_post = next(item for item in main.get_community_posts(actor_id)["posts"] if item["id"] == post["id"])
                self.assertIsNone(public_post["boundJobId"])
                with self.assertRaises(HTTPException) as raised:
                    main.create_community_post(main.CommunityPostCreateRequest(
                        user_id=actor_id, title="不能绑定", content="不能绑定别人的岗位", post_type="share", job_id=job["id"]
                    ))
                self.assertEqual(raised.exception.status_code, 404)

                first = main.record_community_action(post["id"], main.CommunityActionAttributionRequest(
                    user_id=actor_id, action="practice"
                ))
                second = main.record_community_action(post["id"], main.CommunityActionAttributionRequest(
                    user_id=actor_id, action="practice"
                ))
                self.assertEqual(first["author_points_awarded"], 3)
                self.assertFalse(second["first_action"])
                self.assertEqual(main.get_contribution_status(author_id)["balance"], 3)

                main.moderate_community_post(
                    post["id"], main.CommunityModerationRequest(decision="featured", note="人工核验通过"), "a" * 32
                )
                main.moderate_community_post(
                    post["id"], main.CommunityModerationRequest(decision="featured", note="重复提交"), "a" * 32
                )
                status = main.get_contribution_status(author_id)
                self.assertEqual(status["balance"], 23)
                self.assertEqual(len(status["ledger"]), 2)
                main.delete_account(main.AccountDeleteRequest(user_id=actor_id, confirmation="DELETE"))
                after_delete = main.get_contribution_status(author_id)
                self.assertEqual(after_delete["balance"], 20)
                refreshed = next(item for item in main.get_community_posts(author_id)["posts"] if item["id"] == post["id"])
                self.assertEqual(refreshed["actionStarts"], 0)
                self.assertFalse(any(item.get("source_user_id") == actor_id for item in store.load()["point_ledger"]))

    def test_weak_retry_binds_job_and_post_and_returns_before_after_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            with patch.object(main, "_state_store", store), patch.object(main, "exchange_wechat_code", return_value=None):
                state = main.default_beta_state()
                user = main.ensure_user(state, "retry-device", "复练用户", "weapp")
                store.save(state)
                user_id = user["profile"]["user_id"]
                job = main.create_workspace_job(main.WorkspaceJobCreateRequest(
                    user_id=user_id, title="AI 产品经理", company="目标公司", jd_text="要求数据评测与商业化经验"
                ))["job"]
                post = main.create_community_post(main.CommunityPostCreateRequest(
                    user_id=user_id, title="面试复练方法", content="同一个问题改完再答，比较证据和结构。", post_type="share", job_id=job["id"]
                ))["post"]
                plan_json = '{"plan_summary":"同题复练","questions":["讲一个项目","再次讲项目","最后再答一次"],"focus":["结构","证据"]}'
                first_json = '{"feedback":"事实清楚，缺结果","scores":{"content":60,"structure":55,"evidence":40,"role_fit":60,"clarity":60,"adaptability":55},"better_answer":"补充结果","follow_up":"请围绕同一项目重答，只补充可验证结果"}'
                second_json = '{"feedback":"结果更清楚","scores":{"content":70,"structure":65,"evidence":60,"role_fit":68,"clarity":70,"adaptability":65},"better_answer":"说明指标口径","follow_up":"请仍围绕同一项目重答，补充指标口径"}'
                final_json = '{"feedback":"证据完整度提升","scores":{"content":78,"structure":75,"evidence":72,"role_fit":76,"clarity":76,"adaptability":72},"better_answer":"保留真实边界","follow_up":"","report":{"overall_score":75,"dimension_scores":{"content":78,"structure":75,"evidence":72,"role_fit":76,"clarity":76,"adaptability":72},"strengths":["持续补证据"],"improvements":["压缩背景"],"next_drill":"换一个项目复练"}}'
                with patch.object(main, "llm_chat_with_fallback", side_effect=[plan_json, first_json, second_json, final_json]):
                    started = asyncio.run(main.start_interview_practice(main.InterviewPracticeStartRequest(
                        user_id=user_id, position="AI 产品经理", duration_minutes=10, job_id=job["id"], source_post_id=post["id"]
                    )))
                    answers = []
                    for text in ["我负责需求并上线", "我负责需求并上线，转化提升百分之十", "我负责需求并上线，实验口径下转化提升百分之十"]:
                        answers.append(asyncio.run(main.answer_interview_practice(
                            started["session_id"], main.InterviewPracticeAnswerRequest(user_id=user_id, answer=text)
                        )))
                self.assertEqual(started["job_id"], job["id"])
                self.assertEqual(started["source_post_id"], post["id"])
                self.assertGreater(answers[1]["comparison"]["average_delta"], 0)
                self.assertTrue(answers[-1]["completed"])
                self.assertGreater(answers[-1]["report"]["retry_comparison"]["average_delta"], 0)
                persisted = store.load()["users"][user_id]["interview_sessions"][0]
                self.assertEqual(persisted["job_id"], job["id"])
                self.assertEqual(persisted["source_post_id"], post["id"])


if __name__ == "__main__":
    unittest.main()
