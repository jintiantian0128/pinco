import base64
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main


class TencentAsrTests(unittest.TestCase):
    def test_monthly_reservation_fails_closed_without_durable_store(self):
        store = SimpleNamespace(durable=False)
        with patch.object(main, "get_state_store", return_value=store):
            with self.assertRaises(main.HTTPException) as raised:
                main.reserve_tencent_asr_request()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["code"], "TENCENT_ASR_DURABLE_LIMIT_REQUIRED")

    def test_monthly_limit_is_checked_before_calling_tencent(self):
        store = SimpleNamespace(
            durable=True,
            reserve_monthly_usage=lambda key, limit: {"reserved": False, "used": limit, "limit": limit},
        )
        with patch.object(main, "get_state_store", return_value=store), patch.object(
            main, "TENCENT_ASR_MONTHLY_LIMIT", 4
        ):
            with self.assertRaises(main.HTTPException) as raised:
                main.reserve_tencent_asr_request()
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.detail["code"], "TENCENT_ASR_MONTHLY_LIMIT_REACHED")
        self.assertEqual(raised.exception.detail["message"], "当月语音输入额度已用完，请使用文本输入")

    def test_tencent_provider_quota_codes_are_classified_without_exposing_payloads(self):
        self.assertEqual(
            main.tencent_asr_quota_error_code(RuntimeError("FailedOperation.UserHasNoFreeAmount: exhausted")),
            "FailedOperation.UserHasNoFreeAmount",
        )
        self.assertEqual(
            main.tencent_asr_quota_error_code(RuntimeError("FailedOperation.UserHasNoAmount")),
            "FailedOperation.UserHasNoAmount",
        )
        self.assertIsNone(main.tencent_asr_quota_error_code(RuntimeError("AuthFailure.InvalidSecretId")))

    def test_transcription_uses_signed_sdk_and_expected_short_audio_contract(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio:
            audio.write(b"small synthetic mp3 bytes")
            audio_path = audio.name
        captured = {}

        class FakeRequest:
            def from_json_string(self, payload):
                captured["payload"] = json.loads(payload)

        class FakeClient:
            def __init__(self, credential, region, profile):
                captured["region"] = region
                captured["endpoint"] = profile.httpProfile.endpoint
                captured["timeout"] = profile.httpProfile.reqTimeout

            def SentenceRecognition(self, request):
                return SimpleNamespace(Result="你好 Pinco")

        try:
            with patch.object(main, "TENCENTCLOUD_SECRET_ID", "test-secret-id"), \
                 patch.object(main, "TENCENTCLOUD_SECRET_KEY", "test-secret-key"), \
                 patch.object(main, "prepare_aliyun_audio", return_value=(audio_path, "mp3", False)), \
                 patch.object(main, "reserve_tencent_asr_request") as reserve, \
                 patch("main.shutil.which", return_value="/usr/bin/ffprobe"), \
                 patch("main.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="2.0")), \
                 patch("tencentcloud.asr.v20190614.asr_client.AsrClient", FakeClient), \
                 patch("tencentcloud.asr.v20190614.models.SentenceRecognitionRequest", FakeRequest):
                result = main.transcribe_with_tencent_asr(audio_path)
            self.assertEqual(result, "你好 Pinco")
            reserve.assert_called_once()
            self.assertEqual(captured["region"], main.TENCENTCLOUD_REGION)
            self.assertEqual(captured["endpoint"], "asr.tencentcloudapi.com")
            self.assertEqual(captured["timeout"], 60)
            request = captured["payload"]
            self.assertEqual(request["EngSerViceType"], "16k_zh")
            self.assertEqual(request["SourceType"], 1)
            self.assertEqual(request["VoiceFormat"], "mp3")
            self.assertEqual(request["Data"], base64.b64encode(b"small synthetic mp3 bytes").decode("ascii"))
            self.assertEqual(request["DataLen"], len(b"small synthetic mp3 bytes"))
        finally:
            os.unlink(audio_path)

    def test_tencent_limit_error_is_not_misreported_as_provider_failure(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio:
            audio.write(b"synthetic audio")
            audio_path = audio.name
        try:
            with patch.object(main, "TENCENTCLOUD_SECRET_ID", "test-secret-id"), \
                 patch.object(main, "TENCENTCLOUD_SECRET_KEY", "test-secret-key"), \
                 patch.object(main, "prepare_aliyun_audio", return_value=(audio_path, "mp3", False)), \
                 patch.object(main, "reserve_tencent_asr_request", side_effect=main.HTTPException(status_code=429, detail={"code": "TENCENT_ASR_MONTHLY_LIMIT_REACHED"})), \
                 patch("main.shutil.which", return_value="/usr/bin/ffprobe"), \
                 patch("main.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="1.0")):
                with self.assertRaises(main.HTTPException) as raised:
                    main.transcribe_with_tencent_asr(audio_path)
            self.assertEqual(raised.exception.status_code, 429)
            self.assertEqual(raised.exception.detail["code"], "TENCENT_ASR_MONTHLY_LIMIT_REACHED")
        finally:
            os.unlink(audio_path)


if __name__ == "__main__":
    unittest.main()
