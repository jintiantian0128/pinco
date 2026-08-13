from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from pypdf import PdfReader
from io import BytesIO
from threading import Lock
from datetime import datetime, timedelta
from dotenv import load_dotenv
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen
from state_store import StateStore, create_state_store
from career_taxonomy import role_interview_focus, translate_job_query
from decimal import Decimal, ROUND_HALF_UP
from copy import deepcopy
import hashlib
import uuid
import os
import json
import re
import asyncio
import time
import sys
import shutil
import subprocess
import secrets
import base64
import statistics

# --- Configuration ---
# Missing model credentials leave the service explicitly unavailable. The app
# never substitutes canned answers for a real model response.

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def read_release_sha(path: Optional[str] = None) -> Optional[str]:
    """Return the immutable CI release fingerprint, if this is a CI build."""
    candidate = os.environ.get("PINCO_RELEASE_SHA", "").strip()
    release_path = path or os.path.join(BACKEND_DIR, ".pinco-release-sha")
    if not candidate:
        try:
            with open(release_path, "r", encoding="utf-8") as release_file:
                candidate = release_file.read().strip()
        except FileNotFoundError:
            return None
    return candidate.lower() if re.fullmatch(r"[0-9a-fA-F]{7,64}", candidate) else None


PINCO_RELEASE_SHA = read_release_sha()

load_dotenv(os.path.join(BACKEND_DIR, ".env"), override=False)

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()  # mock | openai | anthropic
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-20250514")
ASR_PROVIDER = os.environ.get("ASR_PROVIDER", "disabled").strip().lower()
ASR_API_KEY = os.environ.get("ASR_API_KEY")
ASR_BASE_URL = os.environ.get("ASR_BASE_URL", "https://api.openai.com/v1").rstrip("/")
ASR_MODEL = os.environ.get("ASR_MODEL", "whisper-1")
ENABLE_LOCAL_WHISPER = os.environ.get("ENABLE_LOCAL_WHISPER", "false").strip().lower() in {"1", "true", "yes", "on"}
ASR_DEVICE_VERIFIED = os.environ.get("ASR_DEVICE_VERIFIED", "false").strip().lower() in {"1", "true", "yes", "on"}
ALIYUN_NLS_APP_KEY = os.environ.get("ALIYUN_NLS_APP_KEY")
ALIYUN_AK_ID = os.environ.get("ALIYUN_AK_ID")
ALIYUN_AK_SECRET = os.environ.get("ALIYUN_AK_SECRET")
ALIYUN_NLS_ENDPOINT = os.environ.get(
    "ALIYUN_NLS_ENDPOINT",
    "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr",
)
BING_SEARCH_KEY = os.environ.get("BING_SEARCH_KEY")
JSEARCH_API_KEY = os.environ.get("JSEARCH_API_KEY")
JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com"

# WeChat Pay is opt-in and fail-closed. Public sales require both the feature
# switch and a completed live pay + callback + refund verification. Before that,
# only explicitly allow-listed internal user ids can create real test orders.
WECHAT_PAY_ENABLED = os.environ.get("WECHAT_PAY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
WECHAT_PAY_LIVE_VERIFIED = os.environ.get("WECHAT_PAY_LIVE_VERIFIED", "false").strip().lower() in {"1", "true", "yes", "on"}
MEMBERSHIP_SALES_ENABLED = os.environ.get("MEMBERSHIP_SALES_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
EXPERT_PAYMENTS_ENABLED = os.environ.get("EXPERT_PAYMENTS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
WECHAT_PAY_MCH_ID = os.environ.get("WECHAT_PAY_MCH_ID", "").strip()
WECHAT_PAY_CERT_SERIAL_NO = os.environ.get("WECHAT_PAY_CERT_SERIAL_NO", "").strip()
WECHAT_PAY_PRIVATE_KEY_BASE64 = os.environ.get("WECHAT_PAY_PRIVATE_KEY_BASE64", "").strip()
WECHAT_PAY_API_V3_KEY = os.environ.get("WECHAT_PAY_API_V3_KEY", "").strip()
WECHAT_PAY_PUBLIC_KEY_ID = os.environ.get("WECHAT_PAY_PUBLIC_KEY_ID", "").strip()
WECHAT_PAY_PUBLIC_KEY_BASE64 = os.environ.get("WECHAT_PAY_PUBLIC_KEY_BASE64", "").strip()
WECHAT_PAY_NOTIFY_URL = os.environ.get("WECHAT_PAY_NOTIFY_URL", "").strip()
WECHAT_PAY_REFUND_NOTIFY_URL = os.environ.get("WECHAT_PAY_REFUND_NOTIFY_URL", "").strip()
WECHAT_PAY_TEST_USER_IDS = {
    value.strip() for value in os.environ.get("WECHAT_PAY_TEST_USER_IDS", "").split(",") if value.strip()
}

MOCK_MODE = LLM_PROVIDER == "mock" or (LLM_PROVIDER != "anthropic" and not OPENAI_API_KEY) or (LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY)

_openai_client = None
_anthropic_client = None
_llm_probe_cache = {"checked_at": 0, "status": None}
_aliyun_nls_token_cache = {"id": "", "expires_at": 0}
_aliyun_nls_token_lock = Lock()
_wechat_pay_client = None
_wechat_pay_client_lock = Lock()

def get_active_llm_base_url() -> Optional[str]:
    if LLM_PROVIDER == "anthropic":
        return ANTHROPIC_BASE_URL
    if LLM_PROVIDER == "openai":
        return OPENAI_BASE_URL
    return None

def get_llm_config_issue() -> Optional[str]:
    if LLM_PROVIDER == "mock":
        return "当前是 mock 模式，不会调用真实模型。"
    if LLM_PROVIDER not in {"openai", "anthropic"}:
        return f"不支持的 LLM_PROVIDER：{LLM_PROVIDER}。请使用 openai 或 anthropic。"
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            return "OPENAI_API_KEY 未配置。"
        if "api.kimi.com/coding" in OPENAI_BASE_URL:
            return "api.kimi.com/coding 是 Anthropic-compatible endpoint；请把 LLM_PROVIDER 改为 anthropic，或改用 OPENAI_BASE_URL=https://api.moonshot.cn/v1。"
    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            return "ANTHROPIC_API_KEY 未配置。"
        if "moonshot.cn" in ANTHROPIC_BASE_URL:
            return "api.moonshot.cn/v1 是 OpenAI-compatible endpoint；请把 LLM_PROVIDER 改为 openai，或改用 ANTHROPIC_BASE_URL=https://api.kimi.com/coding。"
    return None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        key = OPENAI_API_KEY
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        _openai_client = OpenAI(base_url=OPENAI_BASE_URL, api_key=key, timeout=45.0)
    return _openai_client

def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        key = ANTHROPIC_API_KEY
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        _anthropic_client = Anthropic(base_url=ANTHROPIC_BASE_URL, api_key=key, timeout=45.0)
    return _anthropic_client

def extract_anthropic_text(resp: Any) -> str:
    parts = []
    for block in getattr(resp, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()

def llm_chat(messages: list, temperature: float = 0.7, system_prompt: Optional[str] = None, max_tokens: int = 2048) -> str:
    if MOCK_MODE:
        raise RuntimeError("MOCK_MODE")
    config_issue = get_llm_config_issue()
    if config_issue:
        raise RuntimeError(config_issue)
    normalized_messages = []
    collected_system = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            if content:
                collected_system.append(content)
            continue
        normalized_messages.append(msg)
    effective_system = "\n\n".join(collected_system + ([system_prompt] if system_prompt else [])) or None
    if LLM_PROVIDER == "anthropic":
        client = get_anthropic_client()
        resp = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            system=effective_system,
            messages=normalized_messages,
        )
        text = extract_anthropic_text(resp)
        if not text:
            raise RuntimeError("EMPTY_LLM_RESPONSE")
        return text
    else:
        client = get_openai_client()
        full_messages = ([{"role": "system", "content": effective_system}] if effective_system else []) + normalized_messages
        resp = client.chat.completions.create(model=DEFAULT_MODEL, messages=full_messages, temperature=temperature, max_tokens=max_tokens)
        return resp.choices[0].message.content

def sanitize_prompt_text(text: Optional[str]) -> str:
    if not text:
        return ""
    sanitized = text
    replacements = {
        "毒舌": "直接",
        "骂醒": "点醒",
        "抑郁": "情绪很低落",
        "想死": "非常难受",
        "不想活": "撑不住了",
        "活不下去": "状态很差",
    }
    for old, new in replacements.items():
        sanitized = sanitized.replace(old, new)
    return sanitized

def _is_llm_recoverable(error_text: str) -> bool:
    recoverable = ["Request not allowed", "403", "402", "membership", "quota", "rate_limit", "429", "overloaded"]
    return any(kw in error_text for kw in recoverable)

def llm_chat_with_fallback(messages: list, temperature: float = 0.7, system_prompt: Optional[str] = None, max_tokens: int = 2048) -> str:
    """Retry once with a safer prompt, but never replace a failed model call with canned content."""
    try:
        return llm_chat(messages, temperature=temperature, system_prompt=system_prompt, max_tokens=max_tokens)
    except Exception as error:
        error_text = str(error)
        if not _is_llm_recoverable(error_text):
            raise
        print(f"LLM fallback retry triggered: {error_text}")
        safe_messages = []
        for msg in messages:
            safe_messages.append({
                "role": msg.get("role"),
                "content": sanitize_prompt_text(msg.get("content")),
            })
        safe_system = sanitize_prompt_text(system_prompt) or "你是 Pinco 学姐，擅长中文求职与职场建议。先接住情绪，再给温和、具体、可执行的建议。"
        try:
            return llm_chat(safe_messages, temperature=min(temperature, 0.6), system_prompt=safe_system, max_tokens=max_tokens)
        except Exception as retry_error:
            retry_text = str(retry_error)
            if not _is_llm_recoverable(retry_text):
                raise
            print(f"LLM provider blocked twice: {retry_text}")
            raise retry_error

def is_rate_limit_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return (
        "429" in error_text
        or "rate_limit" in error_text
        or "rate limit" in error_text
        or "usage limit" in error_text
        or "quota" in error_text
        or "too many requests" in error_text
    )

def is_auth_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return (
        "401" in error_text
        or "authentication_error" in error_text
        or "api key appears to be invalid" in error_text
        or "invalid api key" in error_text
        or "expired" in error_text
    )

def llm_http_exception(error: Exception) -> HTTPException:
    if get_llm_config_issue() and str(error) == get_llm_config_issue():
        return HTTPException(
            status_code=400,
            detail={
                "code": "LLM_CONFIG_ERROR",
                "message": str(error),
                "provider": LLM_PROVIDER,
                "model": DEFAULT_MODEL,
                "base_url": get_active_llm_base_url(),
            },
        )
    if is_rate_limit_error(error):
        return HTTPException(
            status_code=429,
            detail={
                "code": "LLM_RATE_LIMITED",
                "message": "模型服务额度已用完或被限流，请稍后重试或更换可用 API Key。",
                "provider": LLM_PROVIDER,
                "model": DEFAULT_MODEL,
            },
        )
    if is_auth_error(error):
        return HTTPException(
            status_code=401,
            detail={
                "code": "LLM_AUTH_FAILED",
                "message": "模型服务 API Key 无效或已过期，请更换可用 Key 后重试。",
                "provider": LLM_PROVIDER,
                "model": DEFAULT_MODEL,
            },
        )
    return HTTPException(
        status_code=502,
        detail={
            "code": "LLM_UPSTREAM_ERROR",
            "message": "模型上游服务暂时不可用，请检查模型服务配置。",
            "provider": LLM_PROVIDER,
            "model": DEFAULT_MODEL,
            "raw": str(error),
        },
    )

def classify_llm_error(error: Exception) -> Dict[str, Any]:
    text = str(error)
    if get_llm_config_issue() and text == get_llm_config_issue():
        return {"status": "config_error", "online": False, "code": "LLM_CONFIG_ERROR", "message": text}
    if is_rate_limit_error(error):
        return {"status": "rate_limited", "online": False, "code": "LLM_RATE_LIMITED", "message": "模型服务额度已用完或被限流。"}
    if is_auth_error(error):
        return {"status": "auth_failed", "online": False, "code": "LLM_AUTH_FAILED", "message": "模型服务 API Key 无效或已过期。"}
    return {"status": "upstream_error", "online": False, "code": "LLM_UPSTREAM_ERROR", "message": "模型上游服务暂时不可用。", "raw": text}

def probe_llm(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force and _llm_probe_cache["status"] and now - _llm_probe_cache["checked_at"] < 60:
        return _llm_probe_cache["status"]

    base = {
        "provider": LLM_PROVIDER,
        "model": DEFAULT_MODEL,
        "base_url": get_active_llm_base_url(),
        "mock_mode": MOCK_MODE,
        "checked_at": int(now),
    }
    if MOCK_MODE:
        status = {**base, "status": "mock", "online": False, "code": "LLM_MOCK_MODE", "message": "当前为 mock 模式。"}
    else:
        config_issue = get_llm_config_issue()
        if config_issue:
            status = {**base, "status": "config_error", "online": False, "code": "LLM_CONFIG_ERROR", "message": config_issue}
        else:
            try:
                text = llm_chat(
                    [{"role": "user", "content": "请只回复 OK"}],
                    temperature=0,
                    system_prompt="你是健康检查接口。只回复 OK。",
                    max_tokens=8,
                )
                status = {**base, "status": "connected", "online": True, "code": "LLM_CONNECTED", "message": "真实模型连通。", "sample": text[:20]}
            except Exception as error:
                status = {**base, **classify_llm_error(error)}
    _llm_probe_cache["checked_at"] = now
    _llm_probe_cache["status"] = status
    return status

async def llm_chat_stream(messages: list, temperature: float = 0.7, system_prompt: Optional[str] = None, max_tokens: int = 2048):
    """Stream LLM response as async generator. Yields text chunks."""
    if MOCK_MODE:
        raise RuntimeError("MOCK_MODE")

    config_issue = get_llm_config_issue()
    if config_issue:
        raise RuntimeError(config_issue)

    normalized_messages = []
    collected_system = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            if content:
                collected_system.append(content)
            continue
        normalized_messages.append(msg)
    effective_system = "\n\n".join(collected_system + ([system_prompt] if system_prompt else [])) or None

    if LLM_PROVIDER == "anthropic":
        client = get_anthropic_client()
        with client.messages.stream(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            system=effective_system,
            messages=normalized_messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
    else:
        client = get_openai_client()
        full_messages = ([{"role": "system", "content": effective_system}] if effective_system else []) + normalized_messages
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


async def llm_chat_stream_with_fallback(messages: list, temperature: float = 0.7, system_prompt: Optional[str] = None, max_tokens: int = 2048):
    """Stream LLM response with fallback on content policy blocks."""
    try:
        async for chunk in llm_chat_stream(messages, temperature=temperature, system_prompt=system_prompt, max_tokens=max_tokens):
            yield chunk
    except Exception as error:
        error_text = str(error)
        if not _is_llm_recoverable(error_text):
            raise
        print(f"LLM stream fallback retry triggered: {error_text}")
        safe_messages = []
        for msg in messages:
            safe_messages.append({
                "role": msg.get("role"),
                "content": sanitize_prompt_text(msg.get("content")),
            })
        safe_system = sanitize_prompt_text(system_prompt) or "你是 Pinco 学姐，擅长中文求职与职场建议。先接住情绪，再给温和、具体、可执行的建议。"
        try:
            async for chunk in llm_chat_stream(safe_messages, temperature=min(temperature, 0.6), system_prompt=safe_system, max_tokens=max_tokens):
                yield chunk
        except Exception as retry_error:
            retry_text = str(retry_error)
            if not _is_llm_recoverable(retry_text):
                raise
            print(f"LLM stream provider blocked twice: {retry_text}")
            raise retry_error


# --- Models ---

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    user_id: Optional[str] = None
    scenario: str = "general"
    interview_mode: bool = False
    interview_round: int = 0
    interview_position: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    role: str = "assistant"
    search_results: Optional[List[Dict[str, Any]]] = None
    query_analysis: Optional[Dict[str, Any]] = None
    agent: Optional[Dict[str, Any]] = None
    progress_suggestion: Optional[Dict[str, Any]] = None

class GenericLLMRequest(BaseModel):
    messages: List[Message]
    system: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048

class JDAnalyzeRequest(BaseModel):
    jd_text: str
    target_position: Optional[str] = None

class JDAnalyzeResponse(BaseModel):
    summary: str
    core_requirements: List[str]
    hidden_requirements: List[str]
    interview_focus: List[str]
    salary_negotiation_tips: List[str]

class InterviewStartRequest(BaseModel):
    position: str
    resume_summary: Optional[str] = None
    focus_areas: Optional[List[str]] = []

class InterviewStartResponse(BaseModel):
    first_question: str
    interview_context: str
    suggested_focus: List[str]

class InterviewPracticeStartRequest(BaseModel):
    user_id: str
    position: str
    job_id: Optional[str] = None
    source_post_id: Optional[str] = None
    duration_minutes: int = 10
    company: str = ""
    interview_round: str = ""
    interview_date: str = ""
    anxiety_focus: str = ""
    practice_style: str = "real"
    resume_summary: Optional[str] = None
    jd_text: Optional[str] = None
    focus_areas: List[str] = Field(default_factory=list)

class InterviewPracticeAnswerRequest(BaseModel):
    user_id: str
    answer: str

class InterviewPracticeRescueRequest(BaseModel):
    user_id: str

class InterviewReportPublishRequest(BaseModel):
    user_id: str

class ResumeMetrics(BaseModel):
    completeness: int
    matching: int
    quantification: int
    keyword: int

class ResumeAnalysisResponse(BaseModel):
    filename: str
    score: int
    summary: str
    metrics: ResumeMetrics
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]

class ConfigResponse(BaseModel):
    provider: str
    mock_mode: bool
    base_url: Optional[str] = None
    model: str

class ConfigUpdateRequest(BaseModel):
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None

class MiniappBootstrapRequest(BaseModel):
    device_id: str
    platform: str = "weapp"
    code: Optional[str] = None
    nickname: Optional[str] = None

class MiniappMessageRequest(BaseModel):
    user_id: str
    scenario: str = "general"
    content: str

class AccountDeleteRequest(BaseModel):
    user_id: str
    confirmation: str

class BookingCreateRequest(BaseModel):
    user_id: str
    expert_id: str
    expert_name: str
    topic: str
    slot: str
    desc: str
    job_id: Optional[str] = None
    share_context_with_expert: bool = False

class ExpertApplicationRequest(BaseModel):
    user_id: str
    real_name: str = Field(min_length=2, max_length=30)
    title: str = Field(min_length=2, max_length=80)
    intro: str = Field(min_length=20, max_length=600)
    tags: List[str] = Field(default_factory=list)
    experience_summary: str = Field(default="", max_length=1500)
    proof_urls: List[str] = Field(default_factory=list)
    reference_price: float = Field(default=0, ge=0, le=5000)
    slots: List[str] = Field(default_factory=list)
    service_name: str = Field(default="30分钟求职问题诊断", min_length=4, max_length=80)
    service_deliverables: List[str] = Field(default_factory=lambda: ["问题诊断", "下一步行动清单"])

class ExpertApplicationReviewRequest(BaseModel):
    decision: str
    review_note: str = Field(default="", max_length=500)

class ExpertAvailabilityRequest(BaseModel):
    user_id: str
    slots: List[str] = Field(default_factory=list)

class ExpertBookingDecisionRequest(BaseModel):
    expert_user_id: str
    decision: str
    note: str = Field(default="", max_length=500)

class ExpertBookingCompleteRequest(BaseModel):
    expert_user_id: str
    delivery_summary: str = Field(min_length=10, max_length=2000)
    next_actions: List[str] = Field(default_factory=list)

class ExpertBookingReviewRequest(BaseModel):
    user_id: str
    score: int = Field(ge=1, le=5)
    comment: str = Field(min_length=2, max_length=500)

class BookingCancelRequest(BaseModel):
    user_id: str
    reason: str = Field(default="", max_length=500)

class CommunityActionRequest(BaseModel):
    user_id: str

class CommunityActionAttributionRequest(BaseModel):
    user_id: str
    action: str = "practice"
    job_id: Optional[str] = None

class CommunityPostCreateRequest(BaseModel):
    user_id: str
    title: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=2, max_length=1000)
    post_type: str = "treehole"
    job_id: Optional[str] = None
    interview_round: str = Field(default="", max_length=40)
    experience_date: str = Field(default="", max_length=40)

class CommunityCommentCreateRequest(BaseModel):
    user_id: str
    text: str = Field(min_length=1, max_length=200)

class CommunityReportRequest(BaseModel):
    user_id: str
    reason: str = Field(min_length=2, max_length=200)

class CommunityModerationRequest(BaseModel):
    decision: str
    note: str = Field(default="", max_length=500)

class ProductEventRequest(BaseModel):
    name: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)

class PilotFeedbackRequest(BaseModel):
    user_id: str
    professional_value_score: int = Field(ge=1, le=5)
    emotional_value_score: int = Field(ge=1, le=5)
    return_intent: str
    most_helpful: str = Field(default="", max_length=500)
    biggest_blocker: str = Field(default="", max_length=500)

class SupportPreferenceRequest(BaseModel):
    user_id: str
    mode: str = "listen_then_action"
    follow_up_enabled: bool = True
    memory_consent: bool = False

class EmotionalCheckInRequest(BaseModel):
    user_id: str
    intensity: int
    event_type: str = "daily"
    note: Optional[str] = None

class SupportFeedbackRequest(BaseModel):
    user_id: str
    helpful: bool
    understood_score: Optional[int] = Field(default=None, ge=1, le=5)

class SupportFollowUpResponseRequest(BaseModel):
    user_id: str
    current_intensity: int = Field(ge=1, le=5)
    micro_action_completed: Optional[bool] = None

class CareerProfileRequest(BaseModel):
    user_id: str
    target_roles: List[str] = Field(default_factory=list)
    years_experience: float = 0
    cities: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    job_search_deadline: str = Field(default="", max_length=40)

class EvidenceCreateRequest(BaseModel):
    user_id: str
    title: str
    situation: str = ""
    action: str
    result: str
    metrics: str = ""
    skills: List[str] = Field(default_factory=list)

class WorkspaceJobCreateRequest(BaseModel):
    user_id: str
    title: str
    company: str
    location: str = ""
    source: str = "manual"
    source_url: Optional[str] = None
    jd_text: str = ""
    status: str = "saved"

class WorkspaceJobStatusRequest(BaseModel):
    user_id: str
    status: str

class JobMaterialGenerateRequest(BaseModel):
    user_id: str
    evidence_ids: List[str] = Field(default_factory=list)

class JobMaterialsUpdateRequest(BaseModel):
    user_id: str
    resume_bullets: List[str] = Field(default_factory=list)
    outreach_message: str = Field(default="", max_length=1000)

class JobMaterialFeedbackRequest(BaseModel):
    user_id: str
    rating: str
    note: str = Field(default="", max_length=500)

class LearningPlanProgressRequest(BaseModel):
    user_id: str
    plan_id: str
    day: int = Field(ge=1, le=7)
    completed: bool = True

class JobSearchRequest(BaseModel):
    query: str
    city: Optional[str] = None
    limit: int = 8
    platforms: Optional[str] = None
    resume_info: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None

class JobResult(BaseModel):
    title: str
    company: str
    location: str
    salary: Optional[str] = None
    summary: str
    url: Optional[str] = None
    source: str
    posted_at: Optional[str] = None
    platform: Optional[str] = None
    match_score: Optional[int] = None
    resume_match_score: Optional[int] = None
    predicted_salary: Optional[str] = None
    verified_source: bool = False
    retrieved_at: Optional[str] = None
    source_status: str = "source_link_only"
    verification_note: str = "仅确认来源链接存在，请打开原页面确认仍在招聘"


class JobSearchResponse(BaseModel):
    query: str
    total: int
    query_analysis: Optional[Dict[str, Any]] = None
    jobs: List[JobResult]

class ReadinessItem(BaseModel):
    key: str
    label: str
    ready: bool
    detail: str

class MembershipPlan(BaseModel):
    id: str
    name: str
    price: float
    price_yearly: Optional[float] = None
    features: List[str]
    ai_chat_limit: int
    resume_analysis_limit: int
    mock_interview_limit: int
    expert_discount: float
    job_search_platforms: List[str]
    purchasable: bool = False
    billing_note: str = "微信支付尚未开放"

class UserMembership(BaseModel):
    plan_id: str
    plan_name: str
    expire_at: Optional[str] = None
    ai_chat_used: int
    ai_chat_limit: int
    resume_used: int
    resume_limit: int
    interview_used: int
    interview_limit: int
    expert_discount: float
    usage_reset_at: Optional[str] = None

class MembershipSubscribeRequest(BaseModel):
    user_id: str
    plan_id: str
    billing_cycle: str = "monthly"
    payment_method: Optional[str] = "wechat"
    request_id: Optional[str] = Field(default=None, min_length=8, max_length=64)

class MembershipInterestRequest(BaseModel):
    user_id: str
    plan_id: str
    billing_cycle: str = "monthly"

class ExpertPayRequest(BaseModel):
    user_id: str
    booking_id: str
    expert_id: Optional[str] = None
    slot: Optional[str] = None
    topic: Optional[str] = None
    coupon_code: Optional[str] = None
    request_id: Optional[str] = Field(default=None, min_length=8, max_length=64)

class ExpertPayResponse(BaseModel):
    success: bool
    order_id: str
    expert_id: str
    expert_name: str
    topic: str
    slot: str
    original_price: float
    discount: float
    actual_price: float
    final_price: float
    payment_method: str
    booking_id: Optional[str] = None
    payment_params: Optional[Dict[str, str]] = None

class PaymentOrderStatus(BaseModel):
    order_id: str
    status: str
    product_type: str
    amount_total: int
    currency: str = "CNY"
    fulfilled: bool = False
    message: str

class PaymentRefundRequest(BaseModel):
    user_id: str
    reason: str = Field(default="用户取消未开始的专家预约", max_length=80)

# --- System Prompts ---

PINCO_PERSONA = """你是 Pinco（温柔学姐），一位专门帮助 0-5 年职场中国年轻人的 AI 职业导师。
人设特点：
- 温柔但专业，像一位靠谱的学姐
- 善于倾听，先接住情绪，再给 actionable 的建议
- 用中文回复，适度使用 emoji（✨ 📝 💪 🎯）让语气更温暖
- 回答要简洁、有结构，避免长篇大论
- 善用 STAR 法则、SWOT 分析等框架拆解问题
核心能力：
1. 简历诊断与优化
2. 模拟面试（行为面 + 专业面）
3. JD 解读与投递策略
4. 职场沟通与成长规划
5. 岗位搜索——检索结果只能称为“带来源链接的岗位候选”，不能保证仍在招聘；必须提醒用户打开原页面确认有效期。只有来源页明确包含单一职位、招聘主体和岗位描述时才可以展示，新闻、科普、榜单和搜索列表不能冒充岗位。
6. 图片边界——除非请求里实际包含了视觉模型可读取的图片内容，否则必须明确说自己看不到画面，绝不能猜测或描述图片。
如果用户上传了简历或贴出了 JD，主动给出针对性分析。
当岗位检索失败或没有可信来源时，要明确说明当前没有拿到可验证结果，并给出重试或补充筛选条件的下一步；禁止编造岗位。"""

INTERVIEWER_PERSONA = """你是一位经验丰富的大厂面试官，正在进行一场模拟面试。

【面试流程】
面试共 5 轮，每轮提出一个面试问题，并根据候选人的回答进行简要点评。
轮次设计：
- 第 1 轮：自我介绍（考察表达能力和岗位匹配度）
- 第 2 轮：项目深挖（考察项目深度和决策逻辑）
- 第 3 轮：情景/行为题（考察问题解决能力和思维方式）
- 第 4 轮：专业/业务理解（考察行业认知和技术/业务深度）
- 第 5 轮：反问环节 + 综合点评（候选人反问 + 面试官给出评分）

【当前规则】
1. 请先礼貌地打招呼，说明这是第几轮面试
2. 提出本轮的面试问题（自然、有针对性，不要生硬）
3. 如果这是第 2-5 轮，先简要点评候选人上一轮的回答（1-2 句话，先说优点再给建议）
4. 问题要围绕目标岗位展开，体现专业性
5. 第 5 轮结束时，给出综合评分（百分制）和详细反馈：
   - 内容质量（30%）：回答是否充实、有深度
   - 表达结构（30%）：逻辑是否清晰、条理是否分明
   - STAR 法则（20%）：是否善用情境-任务-行动-结果框架
   - 岗位匹配（20%）：回答是否体现对目标岗位的理解

【语气要求】
- 专业但有温度，像真实的面试官
- 点评要具体，不要泛泛而谈"不错""还行"
- 用中文回复，适度使用 emoji 让氛围更轻松"""

RESUME_ANALYSIS_PERSONA = """你是一位资深 HR 和简历优化专家。用户刚刚在对话中贴出了自己的简历内容，请针对性地给出专业分析。

分析维度：
1. 结构完整性：基本信息、教育背景、工作经历、项目经验是否齐全
2. 量化程度：是否有数据支撑（增长%、用户数、营收等）
3. 关键词匹配：是否包含目标岗位的高频关键词
4. STAR 法则：项目描述是否遵循情境-任务-行动-结果
5. 亮点提炼：最应该突出的 3 个优势是什么

输出要求：
- 先给总体评分（百分制）和一句话总结
- 分点列出 2-3 个最大问题
- 给出 3-5 条具体可执行的修改建议
- 如果某段经历写得不错，点名表扬
- 语气温和但有洞察力，像一位靠谱的职场导师"""

JD_ANALYSIS_PERSONA = """你是一位资深猎头 + 大厂 HR。用户刚刚贴出了一份职位描述（JD），请深度解读。

解读维度：
1. 岗位画像：这个岗位核心要解决什么问题
2. 硬性要求：学历、年限、技能等不可妥协的条件
3. 隐性门槛：字里行间透露的额外要求（如抗压能力、加班意愿）
4. 面试重点：根据 JD 推测面试官最可能问的方向
5. 匹配建议：假设用户是 0-5 年经验的求职者，给出投递和准备建议

输出要求：
- 用结构化方式呈现，带 emoji 分隔
- 给出至少 3 个面试准备方向
- 最后给出谈薪策略建议
- 语气专业但易懂，像一位 insider 在分享"""

def detect_content_type(messages: list) -> str:
    """Detect if the last user message contains resume or JD content."""
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    if "[RESUME_ANALYSIS]" in last_user_msg:
        return "resume"
    if "[JD_ANALYSIS]" in last_user_msg:
        return "jd"

    resume_keywords = ["简历", "工作经历", "项目经验", "教育背景", "自我评价", "技能", "负责", "主导", "参与"]
    jd_keywords = ["岗位职责", "任职要求", "岗位要求", "职位描述", "福利待遇", "工作地点", "投递", "简历投递"]

    if any(kw in last_user_msg for kw in resume_keywords) and len(last_user_msg) > 300:
        return "resume"
    if any(kw in last_user_msg for kw in jd_keywords) and len(last_user_msg) > 200:
        return "jd"

    return "general"


def detect_search_intent(messages: list) -> Optional[str]:
    """Return a query only when the user explicitly asks for live job search."""
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    normalized = re.sub(r"\s+", "", last_user_msg)
    if not normalized or any(phrase in normalized for phrase in ["不要搜索", "不用搜索", "别搜索"]):
        return None
    # Merely mentioning a target role, resume or job-search profile is not a
    # request to hit external providers. Search requires both an explicit
    # action/question and a job object.
    patterns = [
        r"(?:帮我|请|能否|能不能|可以)?(?:找|搜|搜索|查找|查查|推荐).{0,16}(?:岗位|职位|工作|机会|内推|实习)",
        r"(?:岗位|职位|工作|机会|内推|实习).{0,16}(?:有哪些|有没有|在招|招聘|推荐|帮我找|帮我搜)",
        r"(?:哪里|哪家|哪些公司).{0,16}(?:在招|招聘|有岗位|有职位|招人)",
    ]
    return last_user_msg if any(re.search(pattern, normalized) for pattern in patterns) else None

RESUME_ANALYSIS_PROMPT = """你是一位资深 HR 和简历优化专家。请分析以下简历文本。

【极其重要】你必须直接输出一个合法的 JSON 对象，不要包含 markdown 代码块标记（如 ```json），不要添加任何解释性文字。

JSON 结构要求：
{
  "score": 0-100 的整数,
  "summary": "候选人画像摘要（30字以内）",
  "metrics": {"completeness": 0-100, "matching": 0-100, "quantification": 0-100, "keyword": 0-100},
  "strengths": ["亮点1", "亮点2", "亮点3"],
  "weaknesses": ["硬伤1", "硬伤2"],
  "suggestions": ["具体建议1", "具体建议2", "具体建议3"]
}

评分标准：
- completeness：信息完整度（基本信息、教育、工作/项目经历）
- matching：与互联网/科技行业岗位通用要求的匹配度
- quantification：是否有数据化成果（增长%、用户数、营收等）
- keyword：是否包含行业关键词（产品、运营、数据分析、增长等）

简历文本：
"""

JD_ANALYSIS_PROMPT = """你是一位资深猎头 + 大厂 HR。请解读以下职位描述（JD）。

【极其重要】你必须直接输出一个合法的 JSON 对象，不要包含 markdown 代码块标记（如 ```json），不要添加任何解释性文字。

JSON 结构要求：
{
  "summary": "该岗位核心画像一句话总结",
  "core_requirements": ["硬性要求1", "硬性要求2", "硬性要求3"],
  "hidden_requirements": ["隐性要求1", "隐性要求2"],
  "interview_focus": ["面试重点1", "面试重点2", "面试重点3"],
  "salary_negotiation_tips": ["谈薪建议1", "谈薪建议2"]
}

JD 内容：
"""

INTERVIEW_START_PROMPT = """你是一位经验丰富的大厂面试官。现在要为候选人开启一场模拟面试。

【极其重要】你必须直接输出一个合法的 JSON 对象，不要包含 markdown 代码块标记（如 ```json），不要添加任何解释性文字。

候选人信息：
- 目标岗位：{position}
- 简历摘要：{resume_summary}
- 希望重点考察：{focus_areas}

JSON 结构要求：
{{
  "first_question": "开场第一个面试问题，自然、有针对性",
  "interview_context": "这场面试的考察重点和难度设定",
  "suggested_focus": ["建议追问方向1", "建议追问方向2"]
}}
"""

app = FastAPI(title="Pinco API", version="0.7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(PROJECT_ROOT, "_workspace", "demos")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend", "dist")
# 云托管容器文件系统是临时的，数据存 /app/data（Dockerfile WORKDIR 为 /app）
BETA_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BETA_STATE_FILE = os.environ.get(
    "PINCO_STATE_FILE",
    os.path.join(BETA_DATA_DIR, "internal_beta_state.json"),
)
PINCO_STATE_BACKEND = os.environ.get("PINCO_STATE_BACKEND", "file").strip().lower()
MONGODB_URI = os.environ.get("MONGODB_URI")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "pinco")
MONGODB_STATE_COLLECTION = os.environ.get("MONGODB_STATE_COLLECTION", "app_state")
MYSQL_ADDRESS = os.environ.get("MYSQL_ADDRESS")
MYSQL_USERNAME = os.environ.get("MYSQL_USERNAME")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "pinco")
MYSQL_STATE_TABLE = os.environ.get("MYSQL_STATE_TABLE", "pinco_state")
PINCO_ADMIN_TOKEN = os.environ.get("PINCO_ADMIN_TOKEN", "").strip()
WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET")
WECHAT_REQUEST_DOMAIN = os.environ.get("WECHAT_REQUEST_DOMAIN")
_state_lock = Lock()
_state_store: Optional[StateStore] = None

# --- Helpers ---

def _decode_base64_secret(value: str, label: str) -> str:
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8").strip()
    except Exception as error:
        raise RuntimeError(f"{label} 不是有效的 UTF-8 Base64 内容") from error
    if not decoded:
        raise RuntimeError(f"{label} 解码后为空")
    return decoded


def get_wechat_pay_config_issue() -> Optional[str]:
    required = {
        "WECHAT_APP_ID": WECHAT_APP_ID,
        "WECHAT_PAY_MCH_ID": WECHAT_PAY_MCH_ID,
        "WECHAT_PAY_CERT_SERIAL_NO": WECHAT_PAY_CERT_SERIAL_NO,
        "WECHAT_PAY_PRIVATE_KEY_BASE64": WECHAT_PAY_PRIVATE_KEY_BASE64,
        "WECHAT_PAY_API_V3_KEY": WECHAT_PAY_API_V3_KEY,
        "WECHAT_PAY_PUBLIC_KEY_ID": WECHAT_PAY_PUBLIC_KEY_ID,
        "WECHAT_PAY_PUBLIC_KEY_BASE64": WECHAT_PAY_PUBLIC_KEY_BASE64,
        "WECHAT_PAY_NOTIFY_URL": WECHAT_PAY_NOTIFY_URL,
        "WECHAT_PAY_REFUND_NOTIFY_URL": WECHAT_PAY_REFUND_NOTIFY_URL,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        return "缺少 " + "、".join(missing)
    if len(WECHAT_PAY_API_V3_KEY) != 32:
        return "WECHAT_PAY_API_V3_KEY 必须是 32 字节"
    if not WECHAT_PAY_NOTIFY_URL.startswith("https://") or not WECHAT_PAY_REFUND_NOTIFY_URL.startswith("https://"):
        return "支付和退款通知地址必须是公网 HTTPS 地址"
    try:
        private_key = _decode_base64_secret(WECHAT_PAY_PRIVATE_KEY_BASE64, "WECHAT_PAY_PRIVATE_KEY_BASE64")
        public_key = _decode_base64_secret(WECHAT_PAY_PUBLIC_KEY_BASE64, "WECHAT_PAY_PUBLIC_KEY_BASE64")
    except RuntimeError as error:
        return str(error)
    if "PRIVATE KEY" not in private_key:
        return "商户私钥内容格式不正确"
    if "PUBLIC KEY" not in public_key:
        return "微信支付平台公钥内容格式不正确"
    return None


def get_wechat_pay_client():
    issue = get_wechat_pay_config_issue()
    if issue:
        raise RuntimeError(issue)
    global _wechat_pay_client
    if _wechat_pay_client is None:
        with _wechat_pay_client_lock:
            if _wechat_pay_client is None:
                from wechatpayv3 import WeChatPay, WeChatPayType
                _wechat_pay_client = WeChatPay(
                    wechatpay_type=WeChatPayType.MINIPROG,
                    mchid=WECHAT_PAY_MCH_ID,
                    private_key=_decode_base64_secret(WECHAT_PAY_PRIVATE_KEY_BASE64, "WECHAT_PAY_PRIVATE_KEY_BASE64"),
                    cert_serial_no=WECHAT_PAY_CERT_SERIAL_NO,
                    appid=WECHAT_APP_ID,
                    apiv3_key=WECHAT_PAY_API_V3_KEY,
                    notify_url=WECHAT_PAY_NOTIFY_URL,
                    public_key=_decode_base64_secret(WECHAT_PAY_PUBLIC_KEY_BASE64, "WECHAT_PAY_PUBLIC_KEY_BASE64"),
                    public_key_id=WECHAT_PAY_PUBLIC_KEY_ID,
                    timeout=(10, 30),
                )
    return _wechat_pay_client


def wechat_pay_is_configured() -> bool:
    return get_wechat_pay_config_issue() is None


def can_user_initiate_payment(user_id: Optional[str], product_type: str) -> bool:
    if not WECHAT_PAY_ENABLED or not wechat_pay_is_configured():
        return False
    if user_id and user_id in WECHAT_PAY_TEST_USER_IDS:
        return True
    public_switch = MEMBERSHIP_SALES_ENABLED if product_type == "membership" else EXPERT_PAYMENTS_ENABLED
    return bool(public_switch and WECHAT_PAY_LIVE_VERIFIED)


def _money_to_fen(value: float) -> int:
    return int((Decimal(str(value)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_wechat_pay_response(result: Any, action: str, accepted: set[int]) -> Dict[str, Any]:
    try:
        status_code, raw = result
        payload = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) and raw else {}
    except Exception as error:
        raise RuntimeError(f"微信支付{action}响应格式异常") from error
    if int(status_code) not in accepted:
        safe_code = payload.get("code", "WECHAT_PAY_UPSTREAM_ERROR") if isinstance(payload, dict) else "WECHAT_PAY_UPSTREAM_ERROR"
        safe_message = payload.get("message", f"HTTP {status_code}") if isinstance(payload, dict) else f"HTTP {status_code}"
        raise RuntimeError(f"微信支付{action}失败：{safe_code} {safe_message}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"微信支付{action}响应不是 JSON 对象")
    return payload


def _build_miniprogram_payment_params(prepay_id: str) -> Dict[str, str]:
    if not prepay_id:
        raise RuntimeError("微信支付下单响应缺少 prepay_id")
    client = get_wechat_pay_client()
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    package = f"prepay_id={prepay_id}"
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": client.sign([WECHAT_APP_ID, timestamp, nonce, package]),
    }


def _payment_unavailable_detail(product_type: str, user_id: Optional[str] = None) -> Dict[str, str]:
    issue = get_wechat_pay_config_issue()
    if issue:
        message = f"微信支付尚未完成商户配置：{issue}。当前不会扣款。"
    elif not WECHAT_PAY_ENABLED:
        message = "微信支付总开关尚未开启，当前不会扣款。"
    elif not WECHAT_PAY_LIVE_VERIFIED and user_id not in WECHAT_PAY_TEST_USER_IDS:
        message = "微信支付仍在小额实付与退款验收，仅内部测试账号可用；当前不会扣款。"
    elif product_type == "membership" and not MEMBERSHIP_SALES_ENABLED:
        message = "会员价格与权益尚未确认公开售卖，当前不会扣款。"
    else:
        message = "专家服务支付尚未开放，当前不会扣款。"
    return {"code": "PAYMENT_NOT_AVAILABLE", "message": message}

def extract_text_from_pdf(file_content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(file_content))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return ""

def clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

def now_time_label() -> int:
    return int(datetime.now().timestamp() * 1000)

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def stable_user_id(device_id: str) -> str:
    digest = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:16]
    return f"user_{digest}"

def exchange_wechat_code(code: Optional[str]) -> Optional[Dict[str, Any]]:
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET or not code:
        return None
    if code.startswith("mock-"):
        return None
    query = urlencode({
        "appid": WECHAT_APP_ID,
        "secret": WECHAT_APP_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    })
    url = f"https://api.weixin.qq.com/sns/jscode2session?{query}"
    try:
        with urlopen(url, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("errcode"):
            print(f"WeChat code exchange failed: {data}")
            return None
        return data
    except Exception as error:
        print(f"WeChat code exchange error: {error}")
        return None

def default_timeline() -> List[Dict[str, Any]]:
    return [
        {"id": "timeline-1", "title": "先把问题说清", "desc": "进入会话，让学姐先帮你判断优先级", "status": "active"},
        {"id": "timeline-2", "title": "再做一次诊断", "desc": "从简历、面试或表达里抓一个最短板先突破", "status": "pending"},
        {"id": "timeline-3", "title": "必要时约专家", "desc": "复杂问题再用 1v1 连线加速", "status": "pending"},
    ]

def default_messages() -> List[Dict[str, Any]]:
    return [
        {
            "id": "welcome",
            "role": "assistant",
            "content": "你好呀，我是 Pinco。先把你现在最卡的一件事告诉我，我不拐弯，直接帮你判断下一步。",
            "createdAt": now_time_label(),
        }
    ]

def default_community_posts() -> List[Dict[str, Any]]:
    return [
        {
            "id": "editorial-practice-1",
            "author": "Pinco 编辑部",
            "roleTag": "官方干货",
            "created_at": "2026-08-04T00:00:00",
            "title": "把一条求职经验变成可练习的动作",
            "content": "收藏不是结束：先写出一个与你经历相关的例子，再限时 90 秒讲一遍，最后只改一个最卡的地方。你可以点下方“带我练”直接开始。",
            "liked_by": [],
            "hugged_by": [],
            "postType": "share",
            "comments": [],
            "is_example": True,
        },
        {
            "id": "editorial-support-1",
            "author": "Pinco 学姐",
            "roleTag": "官方说明",
            "created_at": "2026-08-04T00:00:00",
            "title": "树洞不是情绪打分比赛",
            "content": "你可以只说发生了什么，也可以说明此刻更需要被听见还是一起找办法。Pinco 默认不保存树洞正文，除非你明确开启情绪记忆。",
            "liked_by": [],
            "hugged_by": [],
            "postType": "treehole",
            "comments": [],
            "is_example": True,
        },
    ]

def default_expert_profiles() -> List[Dict[str, Any]]:
    """Seed honest demand-matching profiles without pretending that a fictional person was verified."""
    common = {
        "owner_user_id": None,
        "reference_price": 0,
        "slots": ["提交后 24 小时内由平台匹配"],
        "duration_minutes": 30,
        "status": "approved",
        "is_demo": True,
        "created_at": "2026-08-13T00:00:00",
        "updated_at": "2026-08-13T00:00:00",
    }
    return [
        {
            **common,
            "id": "expert-demo-ai-pm",
            "name": "AI 产品经理匹配专区",
            "title": "0-5 年 AI 产品求职·内测需求画像",
            "intro": "适合做 AI 产品经理岗位定位、项目经历深挖、产品案例面试和 Offer 判断。这是内测匹配入口，不是虚构真人专家。",
            "tags": ["AI产品", "项目深挖", "模拟面试", "Offer选择"],
            "service_name": "AI 产品求职问题匹配",
            "service_deliverables": ["平台确认问题类型", "匹配真人专家后再确认服务"],
        },
        {
            **common,
            "id": "expert-demo-ai-ops",
            "name": "AI 产品运营匹配专区",
            "title": "AI 增长 / 内容 / 用户运营·内测需求画像",
            "intro": "适合 AI 产品运营的方向选择、数据化简历、增长案例拆解与面试复盘。提交后由平台匹配真人，当前不代表已有指定专家接单。",
            "tags": ["AI运营", "增长", "内容策略", "数据复盘"],
            "service_name": "AI 产品运营问题匹配",
            "service_deliverables": ["平台确认问题类型", "匹配真人专家后再确认服务"],
        },
        {
            **common,
            "id": "expert-demo-agent-pm",
            "name": "AI Agent 产品匹配专区",
            "title": "Agent 产品设计 / 作品集·内测需求画像",
            "intro": "适合需要讲清 Agent 规划、记忆、工具调用和评测方案的候选人。这是真实专家入驻前的内测匹配入口。",
            "tags": ["AI Agent", "作品集", "方案设计", "技术理解"],
            "service_name": "AI Agent 产品求职问题匹配",
            "service_deliverables": ["平台确认问题类型", "匹配真人专家后再确认服务"],
        },
    ]


def default_beta_state() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "users": {},
        "community_posts": default_community_posts(),
        "events": [],
        "orders": [],
        "expert_applications": [],
        "experts": default_expert_profiles(),
        "expert_bookings": [],
        "expert_reviews": [],
        "membership_interests": [],
        "pilot_feedback": [],
        "community_reports": [],
        "point_ledger": [],
    }


def get_state_store() -> StateStore:
    global _state_store
    if _state_store is None:
        _state_store = create_state_store(
            backend=PINCO_STATE_BACKEND,
            file_path=BETA_STATE_FILE,
            default_factory=default_beta_state,
            mongo_uri=MONGODB_URI,
            mongo_database=MONGODB_DATABASE,
            mongo_collection=MONGODB_STATE_COLLECTION,
            mysql_address=MYSQL_ADDRESS,
            mysql_username=MYSQL_USERNAME,
            mysql_password=MYSQL_PASSWORD,
            mysql_database=MYSQL_DATABASE,
            mysql_table=MYSQL_STATE_TABLE,
        )
    return _state_store


def load_beta_state() -> Dict[str, Any]:
    data = get_state_store().load()
    data.setdefault("schema_version", 2)
    data.setdefault("users", {})
    posts = data.setdefault("community_posts", default_community_posts())
    # Remove the original seed personas. They looked like real users and must not
    # survive upgrades as apparently organic community activity.
    legacy_seed_ids = {"post-1", "post-2", "post-3"}
    if any(post.get("id") in legacy_seed_ids for post in posts):
        real_posts = [post for post in posts if post.get("id") not in legacy_seed_ids]
        existing_ids = {post.get("id") for post in real_posts}
        posts[:] = real_posts + [post for post in default_community_posts() if post["id"] not in existing_ids]
    data.setdefault("events", [])
    data.setdefault("orders", [])
    data.setdefault("expert_applications", [])
    experts = data.setdefault("experts", [])
    existing_expert_ids = {item.get("id") for item in experts}
    experts.extend(item for item in default_expert_profiles() if item["id"] not in existing_expert_ids)
    data.setdefault("expert_bookings", [])
    data.setdefault("expert_reviews", [])
    data.setdefault("membership_interests", [])
    data.setdefault("pilot_feedback", [])
    data.setdefault("community_reports", [])
    data.setdefault("point_ledger", [])
    return data

def save_beta_state(state: Dict[str, Any]) -> None:
    get_state_store().save(state)

def ensure_user(state: Dict[str, Any], device_id: str, nickname: Optional[str], platform: str, code: Optional[str] = None) -> Dict[str, Any]:
    wechat_session = exchange_wechat_code(code)
    openid = (wechat_session or {}).get("openid")
    legacy_user_id = stable_user_id(device_id)
    device_user_id = stable_user_id(f"device:{device_id}")
    user_id = stable_user_id(f"wechat:{openid}") if openid else device_user_id
    users = state.setdefault("users", {})
    if device_user_id not in users and legacy_user_id in users:
        users[device_user_id] = users.pop(legacy_user_id)
    if openid and user_id not in users:
        migration_source = device_user_id if device_user_id in users else legacy_user_id
        if migration_source in users:
            users[user_id] = users.pop(migration_source)
    if user_id not in users:
        users[user_id] = {
            "profile": {
                "user_id": user_id,
                "nickname": nickname or f"Pinco 用户 {user_id[-4:]}",
                "platform": platform,
                "wechat_bound": bool(openid),
                "auth_level": "wechat" if openid else "device",
                # Required by WeChat Pay JSAPI. This value never leaves the
                # backend bootstrap/export APIs and is deleted with the user.
                "wechat_openid": openid or "",
                "wechat_openid_hint": (openid or "")[-6:],
                "created_at": now_iso(),
                "last_seen_at": now_iso(),
            },
            "messages": default_messages(),
            "bookings": [],
            "service_timeline": default_timeline(),
        }
    else:
        users[user_id]["profile"]["last_seen_at"] = now_iso()
        users[user_id]["profile"]["platform"] = platform
        if nickname:
            users[user_id]["profile"]["nickname"] = nickname
        if wechat_session and wechat_session.get("openid"):
            users[user_id]["profile"]["wechat_bound"] = True
            users[user_id]["profile"]["auth_level"] = "wechat"
            users[user_id]["profile"]["wechat_openid"] = wechat_session["openid"]
            users[user_id]["profile"]["wechat_openid_hint"] = wechat_session["openid"][-6:]
    return users[user_id]

def issue_user_session(user: Dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    profile = user["profile"]
    hashes = list(profile.get("session_token_hashes", []))
    legacy_hash = profile.pop("session_token_hash", "")
    if legacy_hash and not any(item.get("hash") == legacy_hash for item in hashes if isinstance(item, dict)):
        hashes.append({"hash": legacy_hash, "issued_at": profile.get("session_issued_at")})
    hashes.append({"hash": token_hash, "issued_at": now_iso()})
    profile["session_token_hashes"] = hashes[-5:]
    user["profile"]["session_issued_at"] = now_iso()
    return token

def serialize_post(post: Dict[str, Any], user_id: Optional[str]) -> Dict[str, Any]:
    liked_by = post.get("liked_by", [])
    hugged_by = post.get("hugged_by", [])
    comments = post.get("comments", [])
    is_treehole = post.get("postType") == "treehole"
    return {
        "id": post["id"],
        "author": post["author"],
        "roleTag": post["roleTag"],
        "time": community_time_label(post.get("created_at"), post.get("time")),
        "title": post["title"],
        "content": post["content"],
        "likes": len(liked_by),
        "isLiked": bool(user_id and user_id in liked_by),
        "hugs": len(hugged_by),
        "isHugged": bool(user_id and user_id in hugged_by),
        "aiCommentLoading": False,
        "hasAiComment": any(comment.get("isAi") for comment in comments),
        "comments": comments,
        "postType": post.get("postType", "share"),
        "isExample": bool(post.get("is_example")),
        "moderationStatus": post.get("moderation_status", "published"),
        "boundJobId": post.get("job_id") if post.get("created_by") == user_id else None,
        "boundJobLabel": post.get("job_label"),
        "experienceRound": post.get("interview_round") or None,
        "experienceDate": post.get("experience_date") or None,
        "isFeatured": bool(post.get("is_featured")),
        "actionStarts": len(post.get("action_started_by", [])),
    }

def community_time_label(created_at: Optional[str], fallback: Optional[str] = None) -> str:
    if not created_at:
        return fallback or "刚刚"
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
        seconds = max(0, int((datetime.utcnow() - created).total_seconds()))
        if seconds < 60:
            return "刚刚"
        if seconds < 3600:
            return f"{seconds // 60} 分钟前"
        if seconds < 86400:
            return f"{seconds // 3600} 小时前"
        return f"{seconds // 86400} 天前"
    except (TypeError, ValueError):
        return fallback or "刚刚"

def community_user(state: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    user = state.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="社区身份尚未准备好，请稍后重试")
    return user


def award_contribution_points(
    state: Dict[str, Any],
    user_id: Optional[str],
    idempotency_key: str,
    points: int,
    reason: str,
    post_id: Optional[str] = None,
    source_user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not user_id or points <= 0 or user_id not in state.get("users", {}):
        return None
    ledger = state.setdefault("point_ledger", [])
    existing = next((item for item in ledger if item.get("idempotency_key") == idempotency_key), None)
    if existing:
        return existing
    entry = {
        "id": f"points-{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "points": points,
        "reason": reason,
        "post_id": post_id,
        "source_user_id": source_user_id,
        "idempotency_key": idempotency_key,
        "created_at": now_iso(),
    }
    ledger.append(entry)
    state["point_ledger"] = ledger[-20000:]
    return entry


def contribution_status(state: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    community_user(state, user_id)
    entries = [item for item in state.get("point_ledger", []) if item.get("user_id") == user_id]
    balance = sum(int(item.get("points", 0)) for item in entries)
    level = "同行者" if balance < 20 else "热心同路人" if balance < 60 else "学社贡献者"
    return {
        "balance": balance,
        "level": level,
        "ledger": [
            {key: item.get(key) for key in ("id", "points", "reason", "post_id", "created_at")}
            for item in reversed(entries[-20:])
        ],
        "rules": [
            "别人把你的真实帖子转成一次行动：+3（每位用户每帖一次）",
            "内容经人工审核选为精品：+20（每帖一次）",
        ],
        "disclaimer": "贡献积分只记录真实帮助，不可购买、转让、提现或兑换；未来权益另行确认，不会追溯扣减。",
    }

def user_session_is_valid(user_id: str, supplied: str) -> bool:
    state = load_beta_state()
    user = state.get("users", {}).get(str(user_id))
    profile = (user or {}).get("profile", {})
    expected_hashes = [
        item.get("hash") for item in profile.get("session_token_hashes", []) if isinstance(item, dict)
    ]
    if profile.get("session_token_hash"):
        expected_hashes.append(profile["session_token_hash"])
    supplied_hash = hashlib.sha256(supplied.encode("utf-8")).hexdigest() if supplied else ""
    return bool(user and supplied_hash and any(secrets.compare_digest(value, supplied_hash) for value in expected_hashes if value))

@app.middleware("http")
async def require_user_session(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/v1/") or path == "/api/v1/miniapp/bootstrap":
        return await call_next(request)

    claimed_user_id = request.query_params.get("user_id") or request.query_params.get("expert_user_id")
    if not claimed_user_id and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type.lower():
            try:
                body = await request.json()
                if isinstance(body, dict):
                    claimed_user_id = body.get("user_id") or body.get("expert_user_id")
            except Exception:
                claimed_user_id = None

    # Read-only public catalog/health calls and legacy LLM endpoints without a
    # user identity remain callable. Any request claiming a user must prove the
    # current bootstrap session, so knowing a user id alone is insufficient.
    if not claimed_user_id:
        return await call_next(request)

    supplied = request.headers.get("x-pinco-session", "")
    if not user_session_is_valid(str(claimed_user_id), supplied):
        return JSONResponse(
            status_code=401,
            content={"detail": {"code": "SESSION_REQUIRED", "message": "用户会话已过期，请重新进入小程序"}},
        )
    return await call_next(request)

def build_service_health_summary() -> Dict[str, Any]:
    probe = probe_llm()
    return {
        "online": probe["online"],
        "model": DEFAULT_MODEL,
        "provider": LLM_PROVIDER,
        "mockMode": MOCK_MODE,
        "summary": f"{probe['message']} · {DEFAULT_MODEL}",
        "status": probe["status"],
        "code": probe["code"],
        "baseUrl": probe.get("base_url"),
    }

def build_state_health_summary() -> Dict[str, Any]:
    try:
        return get_state_store().health()
    except Exception as error:
        return {
            "backend": PINCO_STATE_BACKEND,
            "durable": PINCO_STATE_BACKEND in {"mongodb", "mysql"},
            "online": False,
            "detail": str(error),
        }

def build_miniapp_readiness() -> Dict[str, Any]:
    service_health = build_service_health_summary()
    state_health = build_state_health_summary()
    payment_issue = get_wechat_pay_config_issue()
    payment_configured = payment_issue is None
    payment_ready = bool(
        payment_configured
        and WECHAT_PAY_ENABLED
        and WECHAT_PAY_LIVE_VERIFIED
        and (MEMBERSHIP_SALES_ENABLED or EXPERT_PAYMENTS_ENABLED)
    )
    asr_configured = (
        (ASR_PROVIDER == "aliyun" and bool(ALIYUN_NLS_APP_KEY and ALIYUN_AK_ID and ALIYUN_AK_SECRET))
        or (ASR_PROVIDER == "openai" and bool(ASR_API_KEY))
        or (ASR_PROVIDER == "local" and ENABLE_LOCAL_WHISPER)
    )
    asr_ready = asr_configured and ASR_DEVICE_VERIFIED
    items = [
        {
            "key": "appid",
            "label": "微信 AppID",
            "ready": bool(WECHAT_APP_ID),
            "detail": "已配置" if WECHAT_APP_ID else "还没填 WECHAT_APP_ID",
        },
        {
            "key": "app_secret",
            "label": "微信 AppSecret",
            "ready": bool(WECHAT_APP_SECRET),
            "detail": "已配置" if WECHAT_APP_SECRET else "还没填 WECHAT_APP_SECRET",
        },
        {
            "key": "request_domain",
            "label": "合法请求域名",
            "ready": bool(WECHAT_REQUEST_DOMAIN),
            "detail": WECHAT_REQUEST_DOMAIN or "还没填 WECHAT_REQUEST_DOMAIN",
        },
        {
            "key": "model_service",
            "label": "模型服务",
            "ready": service_health["online"],
            "detail": service_health["summary"],
        },
        {
            "key": "durable_state",
            "label": "云端持久化",
            "ready": bool(state_health["durable"] and state_health["online"]),
            "detail": state_health["detail"],
        },
        {
            "key": "voice_asr",
            "label": "语音识别",
            "ready": asr_ready,
            "detail": (
                "已完成开发者工具与真机验证"
                if asr_ready
                else "凭证已配置，尚未完成开发者工具与 iOS/Android 各三次实录验证"
                if asr_configured
                else f"ASR_PROVIDER={ASR_PROVIDER}，凭证或运行能力不完整"
            ),
            "blocking": True,
        },
        {
            "key": "admin_governance",
            "label": "专家与内容审核",
            "ready": bool(PINCO_ADMIN_TOKEN and len(PINCO_ADMIN_TOKEN) >= 32),
            "detail": "管理员令牌已配置" if PINCO_ADMIN_TOKEN and len(PINCO_ADMIN_TOKEN) >= 32 else "PINCO_ADMIN_TOKEN 未配置或少于 32 位",
        },
        {
            "key": "wechat_pay",
            "label": "微信支付",
            "ready": payment_ready,
            "detail": (
                "已完成商户配置、实付回调与退款验收"
                if payment_ready
                else f"配置未完成：{payment_issue}"
                if payment_issue
                else "代码与商户配置已就绪，尚未完成小额实付、异步回调和退款真机验收"
                if not WECHAT_PAY_LIVE_VERIFIED
                else "实付已验收，但会员和专家服务售卖开关均未开启"
            ),
            "blocking": False,
        },
    ]
    for item in items:
        item.setdefault("blocking", True)
    blockers = [item for item in items if item["blocking"]]
    ready_count = sum(1 for item in blockers if item["ready"])
    next_steps = []
    if not WECHAT_APP_ID:
        next_steps.append("先注册并配置真实微信 AppID，再替换小程序工程里的 touristappid。")
    if not WECHAT_APP_SECRET:
        next_steps.append("把 WECHAT_APP_SECRET 配到后端，用 code 换取微信用户态。")
    if not WECHAT_REQUEST_DOMAIN:
        next_steps.append("准备一个可备案的 HTTPS API 域名，同时配置到微信后台合法请求域名和 PINCO_API_BASE_URL。")
    if MOCK_MODE:
        next_steps.append("把模型服务切到真实可用状态，避免内测和提审时仍停留在演示模式。")
    if not state_health["durable"]:
        next_steps.append("生产环境启用微信云托管 MySQL 或 MongoDB 持久化，避免云托管重启丢数据。")
    elif not state_health["online"]:
        if state_health["backend"] == "mysql":
            next_steps.append("检查 MYSQL_ADDRESS、数据库账号权限和 pinco 数据库是否可用。")
        else:
            next_steps.append("检查 MongoDB URI、VPC/安全组和数据库账号权限。")
    if not asr_configured:
        next_steps.append("补齐 ASR_PROVIDER 对应凭证。")
    elif not ASR_DEVICE_VERIFIED:
        next_steps.append("用开发者工具、iOS 和 Android 的真实录音格式各连续转写三次；通过后再设置 ASR_DEVICE_VERIFIED=true。")
    if not PINCO_ADMIN_TOKEN or len(PINCO_ADMIN_TOKEN) < 32:
        next_steps.append("配置至少 32 位 PINCO_ADMIN_TOKEN，启用专家和学社内容人工审核。")
    if payment_issue:
        next_steps.append("在云托管密钥/环境变量中补齐微信支付商户私钥、APIv3 密钥、平台公钥和两类 HTTPS 回调地址；不要把密钥打进上传包。")
    elif not WECHAT_PAY_ENABLED:
        next_steps.append("先只为 WECHAT_PAY_TEST_USER_IDS 开启 WECHAT_PAY_ENABLED，完成一笔小额实付、回调、查询与退款。")
    elif not WECHAT_PAY_LIVE_VERIFIED:
        next_steps.append("使用白名单账号完成小额实付、异步回调和全额退款，核对商户平台后再设置 WECHAT_PAY_LIVE_VERIFIED=true。")
    elif not (MEMBERSHIP_SALES_ENABLED or EXPERT_PAYMENTS_ENABLED):
        next_steps.append("确认价格、权益和退款规则后，再分别开启会员或专家服务售卖开关。")
    return {
        "ready": ready_count == len(blockers),
        "ready_count": ready_count,
        "total_count": len(blockers),
        "summary": "已满足首批内测技术门槛（支付仍未开放）" if ready_count == len(blockers) else f"还差 {len(blockers) - ready_count} 项首批内测门槛",
        "items": items,
        "next_steps": next_steps,
    }

def build_scenario_instruction(scenario: str) -> str:
    if scenario == "resume":
        return "你是 Pinco 学姐，擅长用人话做简历诊断。先抓最影响过简历筛选的一两个问题，再给可直接改写的建议。"
    if scenario == "interview":
        return "你是 Pinco 学姐，擅长做模拟面试。你要一题一题带用户练，并及时指出回答中的空泛、跑题和不够具体。"
    if scenario == "emotion":
        return "你是 Pinco 学姐，擅长接住求职中的情绪。先安慰，再把用户拉回今天能执行的动作，不灌鸡汤。"
    if scenario == "expert":
        return "你是 Pinco 学姐，擅长帮用户准备专家连线。重点是帮用户整理问题、目标和希望拿到的结果。"
    if scenario == "garden":
        return "你是 Pinco 学姐，擅长把知识文章转成实战动作。回复要围绕如何落地。"
    if scenario == "jd":
        return "你是 Pinco 学姐，擅长解读岗位描述。帮用户提取核心要求、面试重点和谈薪建议，说人话、给可执行动作。"
    return "你是 Pinco 学姐，面向 0-5 年职场人。说人话，温柔但不敷衍，优先给明确判断和可执行建议。"

def generate_community_reply(title: str, content: str) -> str:
    normalized_content = re.sub(r"抑郁|想死|不想活|活不下去", "非常难受", content).strip()
    primary_prompt = f"""你要以 Pinco 学姐的身份，在职场社区评论区回复一条吐槽帖。

要求：
1. 先用一句话接住情绪，不要说教；
2. 再给 2 条实用、可执行的建议；
3. 语气温暖、有人味，不要像客服；
4. 控制在 80-120 字；
5. 不做医疗或风险判断，只聚焦求职/职场支持。

【帖子标题】{title}
【帖子内容】{normalized_content}"""
    safe_system = "你是 Pinco 学姐，擅长在职场社区里安慰人并给出实用建议。回复要温柔、具体、克制，像真实学姐留言。"
    try:
        return llm_chat_with_fallback([{"role": "user", "content": primary_prompt}], temperature=0.75, system_prompt=safe_system, max_tokens=220)
    except Exception:
        fallback_prompt = f"""请根据下面这条职场吐槽，生成一条温暖、克制、实用的社区回复。

要求：
- 先安慰，再建议；
- 不要夸张，不要灌鸡汤；
- 给出 2 条具体建议；
- 控制在 120 字内。

标题：{title}
内容：{normalized_content}"""
        return llm_chat_with_fallback([{"role": "user", "content": fallback_prompt}], temperature=0.7, system_prompt=safe_system, max_tokens=220)

# --- Routes ---

@app.get("/health")
def health_check():
    return {
        "status": "online",
        "model": DEFAULT_MODEL,
        "version": "0.7.0",
        "release_sha": PINCO_RELEASE_SHA,
        "mock_mode": MOCK_MODE,
        "provider": LLM_PROVIDER,
        "llm": probe_llm(),
        "state": build_state_health_summary(),
    }

@app.get("/api/v1/llm/health")
def llm_health(force: bool = False):
    return probe_llm(force=force)

@app.get("/pinco.html")
def serve_pinco_demo():
    return FileResponse(os.path.join(DEMO_DIR, "pinco.html"))

if os.path.isdir(DEMO_DIR):
    app.mount("/assets", StaticFiles(directory=DEMO_DIR), name="demo-assets")

@app.get("/api/v1/config", response_model=ConfigResponse)
def get_config():
    base = None
    if LLM_PROVIDER == "anthropic":
        base = ANTHROPIC_BASE_URL
    elif LLM_PROVIDER == "openai":
        base = OPENAI_BASE_URL
    return ConfigResponse(provider=LLM_PROVIDER, mock_mode=MOCK_MODE, base_url=base, model=DEFAULT_MODEL)

@app.post("/api/v1/config")
def update_config(request: ConfigUpdateRequest, x_pinco_admin_token: Optional[str] = Header(default=None)):
    require_admin_token(x_pinco_admin_token)
    global LLM_PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL, ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, DEFAULT_MODEL, MOCK_MODE, _openai_client, _anthropic_client, _llm_probe_cache
    LLM_PROVIDER = request.provider.strip().lower()
    DEFAULT_MODEL = request.model or DEFAULT_MODEL
    if LLM_PROVIDER == "anthropic":
        ANTHROPIC_API_KEY = request.api_key
        if request.base_url:
            ANTHROPIC_BASE_URL = request.base_url.rstrip("/")
        _anthropic_client = None
    else:
        OPENAI_API_KEY = request.api_key
        if request.base_url:
            OPENAI_BASE_URL = request.base_url.rstrip("/")
        _openai_client = None
    MOCK_MODE = False
    _llm_probe_cache = {"checked_at": 0, "status": None}
    return {"status": "updated", "provider": LLM_PROVIDER, "mock_mode": MOCK_MODE, "model": DEFAULT_MODEL}

@app.post("/api/v1/miniapp/bootstrap")
def miniapp_bootstrap(request: MiniappBootstrapRequest):
    readiness = build_miniapp_readiness()
    with _state_lock:
        state = load_beta_state()
        user = ensure_user(state, request.device_id, request.nickname, request.platform, request.code)
        session_token = issue_user_session(user)
        save_beta_state(state)
    membership_data = _membership_to_response(user.get("membership", {"plan_id": "free"})).model_dump()
    return {
        "user": {
            key: value for key, value in user["profile"].items()
            if key not in {"session_token_hash", "session_token_hashes", "wechat_openid"}
        },
        "session_token": session_token,
        "messages": user["messages"],
        "bookings": user["bookings"],
        "service_timeline": user["service_timeline"],
        "service_health": build_service_health_summary(),
        "wechat_ready": bool(user["profile"].get("wechat_bound")),
        "miniapp_readiness": readiness,
        "community_posts": [serialize_post(post, user["profile"]["user_id"]) for post in state.get("community_posts", [])],
        "membership": membership_data,
        "workspace": serialize_workspace(user),
        "support_due": due_support_follow_ups(user),
    }

@app.get("/api/v1/miniapp/readiness")
def miniapp_readiness():
    return build_miniapp_readiness()

@app.get("/admin", include_in_schema=False)
def admin_console():
    """Serve the operator console without ever embedding the admin token."""
    console_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_console.html")
    if not os.path.exists(console_path):
        raise HTTPException(status_code=404, detail="运营工作台文件不存在")
    return FileResponse(
        console_path,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Content-Security-Policy": (
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
    )

def sanitize_event_properties(properties: Dict[str, Any]) -> Dict[str, Any]:
    """Keep analytics useful without storing resumes, recordings, or chat bodies."""
    safe: Dict[str, Any] = {}
    blocked_keys = {"content", "text", "message", "resume", "jd_text", "audio", "file_content"}
    for key, value in list(properties.items())[:20]:
        normalized_key = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(key))[:60]
        if normalized_key.lower() in blocked_keys:
            continue
        if isinstance(value, (bool, int, float)) or value is None:
            safe[normalized_key] = value
        elif isinstance(value, str):
            safe[normalized_key] = value[:160]
    return safe

def append_product_event_to_state(
    state: Dict[str, Any], name: str, user_id: Optional[str], properties: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    event = {
        "id": f"event-{uuid.uuid4().hex[:12]}",
        "name": name,
        "user_id": user_id,
        "session_id": None,
        "properties": sanitize_event_properties(properties or {}),
        "created_at": now_iso(),
    }
    events = state.setdefault("events", [])
    events.append(event)
    state["events"] = events[-20000:]
    return event

AGENT_MEMORY_KEYS = {
    "target_role", "years_experience", "target_city", "current_role", "current_company",
    "key_skills", "salary_expectation", "job_search_stage", "preferred_industry",
    "education", "graduation_year", "work_preference", "interview_preference",
}
AGENT_MEMORY_KEY_ALIASES = {
    "目标岗位": "target_role", "求职目标": "target_role", "岗位": "target_role",
    "工作年限": "years_experience", "经验年限": "years_experience", "工作经验": "years_experience",
    "目标城市": "target_city", "所在城市": "target_city", "城市": "target_city",
    "当前岗位": "current_role", "目前岗位": "current_role", "当前职位": "current_role",
    "当前公司": "current_company", "目前公司": "current_company",
    "核心技能": "key_skills", "关键技能": "key_skills",
    "期望薪资": "salary_expectation", "薪资期望": "salary_expectation",
    "求职阶段": "job_search_stage", "目标行业": "preferred_industry",
    "学历": "education", "毕业年份": "graduation_year",
    "工作偏好": "work_preference", "面试偏好": "interview_preference",
}
AGENT_PROGRESS_MILESTONES = {"resume_completed", "mock_interview_completed", "interview_feedback", "offer_decision"}
AGENT_JOB_STATUSES = {"saved", "applied", "written", "interview1", "interview2", "hr", "offer", "rejected"}


def normalize_agent_memory_key(value: Any) -> str:
    raw = str(value or "").strip()
    ascii_key = re.sub(r"[^a-z0-9_]", "", raw.lower())
    if ascii_key in AGENT_MEMORY_KEYS:
        return ascii_key
    compact = re.sub(r"[\s：:，,。.]", "", raw)
    return AGENT_MEMORY_KEY_ALIASES.get(compact, "")


def should_extract_agent_memory(user_text: str) -> bool:
    compact = re.sub(r"\s+", "", user_text or "")
    profile_terms = [
        "目标岗位", "工作年限", "经验年限", "目标城市", "当前岗位", "当前公司",
        "核心技能", "期望薪资", "求职阶段", "目标行业", "毕业年份", "工作偏好",
    ]
    declaration_terms = ["请记住", "记住", "我的", "我是", "我有", "目前", "现在", "目标"]
    return any(term in compact for term in profile_terms) and any(term in compact for term in declaration_terms)


def extract_agent_memory_updates(user_text: str) -> List[Dict[str, Any]]:
    """Use the real model as a bounded structured-memory extractor."""
    raw = llm_chat_with_fallback(
        [{"role": "user", "content": user_text[:3000]}],
        temperature=0.1,
        system_prompt=f"""你是 Pinco 的职业记忆提取器。只提取用户明确陈述、后续求职有用且非敏感的信息。
只输出合法 JSON：{{"memory_updates":[{{"key":"target_role","value":"AI产品经理","confidence":0.95}}]}}
key 只能从这些英文值中选择：{','.join(sorted(AGENT_MEMORY_KEYS))}。
不要推测；电话、地址、身份证、健康、家庭信息绝不保存。没有可保存内容时输出 {{"memory_updates":[]}}。""",
        max_tokens=600,
    )
    parsed = json.loads(clean_json_response(raw))
    return sanitize_agent_result({
        "response": "memory extraction",
        "memory_updates": parsed.get("memory_updates") or [],
    })["memory_updates"]


def get_agent_user_context(user_id: Optional[str]) -> Dict[str, Any]:
    if not user_id:
        return {}
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(user_id)
        return deepcopy(user) if user else {}


def build_agent_memory_context(user: Dict[str, Any]) -> str:
    if not user:
        return "当前没有已绑定的用户记忆。只使用本轮明确提供的信息，不要假装记得。"
    profile = user.get("career_profile") or {}
    facts = user.get("career_memory") or {}
    resume = user.get("resume_memory") or {}
    jobs = [
        {
            "company": item.get("company", ""),
            "position": item.get("title", ""),
            "status": item.get("status", ""),
        }
        for item in user.get("jobs", [])[:8]
    ]
    completed_interviews = [
        {
            "position": item.get("position", ""),
            "company": item.get("company", ""),
            "overall_score": (item.get("report") or {}).get("overall_score"),
            "improvements": ((item.get("report") or {}).get("improvements") or [])[:3],
        }
        for item in user.get("interview_sessions", [])
        if item.get("status") == "completed"
    ][:3]
    context = {
        "career_profile": profile,
        "remembered_facts": facts,
        "latest_resume": {
            "filename": resume.get("filename", ""),
            "analysis_summary": resume.get("analysis_summary", ""),
            "text_excerpt": str(resume.get("text_excerpt") or "")[:6000],
            "updated_at": resume.get("updated_at", ""),
        } if resume else None,
        "job_progress": jobs,
        "recent_completed_practice": completed_interviews,
        "already_prompted_milestones": list((user.get("agent_prompt_history") or {}).keys())[-20:],
    }
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))


def sanitize_agent_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    response = str(raw.get("response") or "").strip()
    if not response:
        raise RuntimeError("AGENT_RESPONSE_EMPTY")
    memory_updates: List[Dict[str, Any]] = []
    for item in raw.get("memory_updates") or []:
        if not isinstance(item, dict):
            continue
        key = normalize_agent_memory_key(item.get("key"))
        value = str(item.get("value") or "").strip()
        confidence = float(item.get("confidence") or 0)
        if key in AGENT_MEMORY_KEYS and value and confidence >= 0.8:
            memory_updates.append({"key": key, "value": value[:240], "confidence": min(confidence, 1.0)})

    progress = raw.get("progress_suggestion") if isinstance(raw.get("progress_suggestion"), dict) else None
    if progress:
        milestone = str(progress.get("milestone") or "")
        status = str(progress.get("status") or "")
        company = str(progress.get("company") or "").strip()[:80]
        position = str(progress.get("position") or "").strip()[:100]
        if milestone not in AGENT_PROGRESS_MILESTONES:
            progress = None
        elif status and status not in AGENT_JOB_STATUSES:
            progress = None
        else:
            progress = {
                "milestone": milestone,
                "company": company,
                "position": position,
                "status": status,
                "prompt": str(progress.get("prompt") or "").strip()[:160],
            }
    return {
        "response": response,
        "intent": str(raw.get("intent") or "general")[:60],
        "next_action": str(raw.get("next_action") or "")[:200],
        "used_memory_keys": [
            normalize_agent_memory_key(item) or str(item)[:60]
            for item in (raw.get("used_memory_keys") or [])[:12]
        ],
        "memory_updates": memory_updates,
        "progress_suggestion": progress,
    }


def persist_chat_turn(
    user_id: Optional[str],
    user_text: str,
    assistant_text: str,
    memory_updates: Optional[List[Dict[str, Any]]] = None,
    progress_suggestion: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not user_id:
        return progress_suggestion
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在，请重新进入小程序")
        messages = user.setdefault("messages", [])
        latest = messages[-1] if messages else None
        if not latest or latest.get("role") != "user" or latest.get("content") != user_text:
            messages.append({
                "id": f"user-{uuid.uuid4().hex[:10]}",
                "role": "user",
                "content": user_text,
                "createdAt": now_time_label(),
            })
        messages.append({
            "id": f"assistant-{uuid.uuid4().hex[:10]}",
            "role": "assistant",
            "content": assistant_text,
            "createdAt": now_time_label(),
        })
        user["messages"] = messages[-200:]
        facts = user.setdefault("career_memory", {})
        for item in memory_updates or []:
            facts[item["key"]] = {
                "value": item["value"],
                "confidence": item["confidence"],
                "source": "conversation",
                "updated_at": now_iso(),
            }
        accepted_progress = progress_suggestion
        if progress_suggestion:
            signature_source = "|".join([
                str(progress_suggestion.get("milestone") or ""),
                str(progress_suggestion.get("company") or "").lower(),
                str(progress_suggestion.get("position") or "").lower(),
                str(progress_suggestion.get("status") or ""),
            ])
            signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()[:16]
            history = user.setdefault("agent_prompt_history", {})
            if signature in history:
                accepted_progress = None
            else:
                history[signature] = {"shown_at": now_iso(), "milestone": progress_suggestion.get("milestone")}
                user["agent_prompt_history"] = dict(list(history.items())[-50:])
        save_beta_state(state)
        return accepted_progress

@app.post("/api/v1/events")
def capture_product_event(request: ProductEventRequest):
    name = request.name.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,63}", name):
        raise HTTPException(status_code=400, detail="事件名格式无效")
    with _state_lock:
        state = load_beta_state()
        event = append_product_event_to_state(state, name, request.user_id, request.properties)
        event["session_id"] = request.session_id
        save_beta_state(state)
    return {"accepted": True, "event_id": event["id"]}

@app.get("/api/v1/pilot/feedback")
def get_pilot_feedback(user_id: str):
    state = load_beta_state()
    if user_id not in state.get("users", {}):
        raise HTTPException(status_code=404, detail="用户不存在")
    feedback = next((
        item for item in state.get("pilot_feedback", [])
        if item.get("user_id") == user_id
    ), None)
    return {"feedback": deepcopy(feedback) if feedback else None}

@app.post("/api/v1/pilot/feedback")
def submit_pilot_feedback(request: PilotFeedbackRequest):
    return_intent = request.return_intent.strip().lower()
    if return_intent not in {"yes", "unsure", "no"}:
        raise HTTPException(status_code=422, detail="继续使用意愿无效")
    with _state_lock:
        state = load_beta_state()
        if request.user_id not in state.get("users", {}):
            raise HTTPException(status_code=404, detail="用户不存在")
        rows = state.setdefault("pilot_feedback", [])
        previous = next((item for item in rows if item.get("user_id") == request.user_id), None)
        submitted_at = now_iso()
        feedback = {
            "id": previous.get("id") if previous else f"pilot-feedback-{uuid.uuid4().hex[:12]}",
            "user_id": request.user_id,
            "professional_value_score": request.professional_value_score,
            "emotional_value_score": request.emotional_value_score,
            "return_intent": return_intent,
            "most_helpful": request.most_helpful.strip(),
            "biggest_blocker": request.biggest_blocker.strip(),
            "created_at": previous.get("created_at") if previous else submitted_at,
            "updated_at": submitted_at,
        }
        state["pilot_feedback"] = [
            item for item in rows if item.get("user_id") != request.user_id
        ] + [feedback]
        append_product_event_to_state(state, "pilot.feedback.submitted", request.user_id, {
            "professional_value_score": request.professional_value_score,
            "emotional_value_score": request.emotional_value_score,
            "return_intent": return_intent,
            "has_most_helpful": bool(feedback["most_helpful"]),
            "has_biggest_blocker": bool(feedback["biggest_blocker"]),
        })
        save_beta_state(state)
    return {"accepted": True, "feedback": deepcopy(feedback)}

@app.get("/api/v1/admin/metrics/pmf")
def get_pmf_metrics(x_pinco_admin_token: Optional[str] = Header(default=None)):
    require_admin_token(x_pinco_admin_token)
    state = load_beta_state()
    events = state.get("events", [])
    tracked_names = [
        "activation.workspace.ready", "workspace.job.saved", "workspace.materials.generated",
        "workspace.materials.feedback",
        "interview.practice.completed", "workspace.job.status_updated", "community.action_started",
        "workspace.learning_plan.day_updated", "interview.report.published",
        "expert.booking.created", "expert.booking.completed", "emotion.support_feedback",
        "emotion.follow_up.responded",
        "pilot.feedback.submitted",
        "membership.interest.created", "payment.fulfilled", "payment.refunded",
    ]
    counts = {
        name: {
            "events": sum(1 for item in events if item.get("name") == name),
            "users": len({item.get("user_id") for item in events if item.get("name") == name and item.get("user_id")}),
        }
        for name in tracked_names
    }
    orders = state.get("orders", [])
    settled_orders = [item for item in orders if item.get("status") in {"paid", "refund_processing", "refunded"}]
    refunded_orders = [item for item in orders if item.get("status") == "refunded"]
    gross_fen = sum(int(item.get("amount_total", 0)) for item in settled_orders)
    refunded_fen = sum(int(item.get("amount_total", 0)) for item in refunded_orders)
    def parse_time(value: Any) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            return None

    now = datetime.now()
    event_rows = [(item, parse_time(item.get("created_at"))) for item in events]
    wjpu_event_names = {
        "workspace.job.saved", "workspace.materials.generated", "interview.practice.completed",
        "workspace.job.status_updated", "expert.booking.completed",
    }
    wjpu_users = {
        item.get("user_id") for item, created_at in event_rows
        if created_at and created_at >= now - timedelta(days=7) and item.get("name") in wjpu_event_names and item.get("user_id")
    }
    feedback_events = [item for item in events if item.get("name") == "workspace.materials.feedback"]
    usable_feedback = [
        item for item in feedback_events if (item.get("properties") or {}).get("rating") in {"direct_use", "minor_edit"}
    ]
    fabrication_reports = [
        item for item in feedback_events if (item.get("properties") or {}).get("fabrication_reported") is True
    ]
    support_feedback = [item for item in events if item.get("name") == "emotion.support_feedback"]
    helpful_support = [item for item in support_feedback if (item.get("properties") or {}).get("helpful") is True]
    understood_scores = [
        int((item.get("properties") or {}).get("understood_score"))
        for item in support_feedback
        if isinstance((item.get("properties") or {}).get("understood_score"), int)
    ]
    follow_up_events = [item for item in events if item.get("name") == "emotion.follow_up.responded"]
    micro_action_answers = [
        (item.get("properties") or {}).get("micro_action_completed")
        for item in follow_up_events
        if isinstance((item.get("properties") or {}).get("micro_action_completed"), bool)
    ]
    completed_micro_actions = sum(1 for answer in micro_action_answers if answer)
    pilot_feedback = state.get("pilot_feedback", [])
    pilot_professional_scores = [
        int(item.get("professional_value_score")) for item in pilot_feedback
        if isinstance(item.get("professional_value_score"), int)
    ]
    pilot_emotional_scores = [
        int(item.get("emotional_value_score")) for item in pilot_feedback
        if isinstance(item.get("emotional_value_score"), int)
    ]
    pilot_return_yes = sum(1 for item in pilot_feedback if item.get("return_intent") == "yes")

    users = state.get("users", {})
    activation_durations = []
    for user_id, user in users.items():
        created_at = parse_time(user.get("profile", {}).get("created_at"))
        activated_at = next((
            event_time for item, event_time in event_rows
            if item.get("user_id") == user_id and item.get("name") == "activation.workspace.ready" and event_time
        ), None)
        if created_at and activated_at and activated_at >= created_at:
            activation_durations.append((activated_at - created_at).total_seconds() / 60)

    second_job_eligible = 0
    second_job_reused = 0
    for user_id in users:
        saved = sorted((
            (event_time, (item.get("properties") or {}).get("job_id"))
            for item, event_time in event_rows
            if item.get("user_id") == user_id and item.get("name") == "workspace.job.saved" and event_time
        ), key=lambda pair: pair[0])
        if not saved or saved[0][0] > now - timedelta(days=14):
            continue
        second_job_eligible += 1
        first_time = saved[0][0]
        distinct_jobs = {
            job_id for event_time, job_id in saved
            if job_id and event_time <= first_time + timedelta(days=14)
        }
        if len(distinct_jobs) >= 2:
            second_job_reused += 1

    paid_expert_bookings = [item for item in state.get("expert_bookings", []) if item.get("payment_status") == "paid"]
    completed_paid_expert = [item for item in paid_expert_bookings if item.get("status_code") == "completed"]
    completed_learning_plans = {
        ((item.get("properties") or {}).get("plan_id"), item.get("user_id"))
        for item in events
        if item.get("name") == "workspace.learning_plan.day_updated"
        and (item.get("properties") or {}).get("completed_count") == 7
        and item.get("user_id")
    }
    return {
        "generated_at": now_iso(),
        "total_users": len(state.get("users", {})),
        "event_counts": counts,
        "payments": {
            "created_orders": len(orders),
            "server_confirmed_orders": len(settled_orders),
            "membership_confirmed_orders": sum(1 for item in settled_orders if item.get("product_type") == "membership"),
            "expert_confirmed_orders": sum(1 for item in settled_orders if item.get("product_type") == "expert"),
            "refunded_orders": len(refunded_orders),
            "gross_fen": gross_fen,
            "refunded_fen": refunded_fen,
            "net_fen": gross_fen - refunded_fen,
        },
        "decision_metrics": {
            "weekly_job_progress_users": {"value": len(wjpu_users), "window_days": 7},
            "first_trusted_output_minutes": {
                "sample": len(activation_durations),
                "median": round(statistics.median(activation_durations), 1) if activation_durations else None,
                "definition": "注册至完成简历 + 真实 JD + 证据材料闭环",
            },
            "second_job_reuse_14d": {
                "eligible_users": second_job_eligible,
                "reused_users": second_job_reused,
                "rate": round(second_job_reused / second_job_eligible, 4) if second_job_eligible else None,
            },
            "material_directly_usable": {
                "feedback_count": len(feedback_events),
                "direct_or_minor_edit": len(usable_feedback),
                "rate": round(len(usable_feedback) / len(feedback_events), 4) if feedback_events else None,
                "fabrication_reports": len(fabrication_reports),
            },
            "community_action_starts": counts["community.action_started"],
            "learning_plan_completed": {
                "plans": len(completed_learning_plans),
                "day_updates": counts["workspace.learning_plan.day_updated"]["events"],
            },
            "interview_reports_published": counts["interview.report.published"],
            "expert_paid_completion": {
                "paid_bookings": len(paid_expert_bookings),
                "completed": len(completed_paid_expert),
                "rate": round(len(completed_paid_expert) / len(paid_expert_bookings), 4) if paid_expert_bookings else None,
                "on_time_rate": None,
                "note": "当前档期是文本，未形成可校验时区时间前不计算按时履约率。",
            },
            "emotional_support_helpful": {
                "feedback_count": len(support_feedback),
                "helpful": len(helpful_support),
                "rate": round(len(helpful_support) / len(support_feedback), 4) if support_feedback else None,
                "understood_score_sample": len(understood_scores),
                "understood_score_average": round(statistics.mean(understood_scores), 2) if understood_scores else None,
                "understood_score_at_least_4_rate": (
                    round(sum(1 for score in understood_scores if score >= 4) / len(understood_scores), 4)
                    if understood_scores else None
                ),
                "micro_action_sample": len(micro_action_answers),
                "micro_action_completed_rate": (
                    round(completed_micro_actions / len(micro_action_answers), 4)
                    if micro_action_answers else None
                ),
                "note": "仅统计用户明确回答；没有真实回答时返回空值，不估算。",
            },
            "pilot_feedback": {
                "responses": len(pilot_feedback),
                "professional_value_average": (
                    round(statistics.mean(pilot_professional_scores), 2)
                    if pilot_professional_scores else None
                ),
                "emotional_value_average": (
                    round(statistics.mean(pilot_emotional_scores), 2)
                    if pilot_emotional_scores else None
                ),
                "return_yes": pilot_return_yes,
                "return_yes_rate": (
                    round(pilot_return_yes / len(pilot_feedback), 4)
                    if pilot_feedback else None
                ),
                "note": "每位用户只保留最近一次共创反馈；没有真实回答时返回空值。",
            },
        },
        "note": "这里只报告真实记录数；样本不足时不计算或包装 PMF 成功率。",
    }

SUPPORT_MODES = {
    "listen": "先陪用户把感受说完，不急着给方案；最后只问一个温和问题。",
    "listen_then_action": "先准确接住情绪，再给一个今天能完成的小动作。",
    "action": "少安慰，直接给 1-3 个可执行动作，但语气不能责备。",
    "direct": "坦率指出关键卡点和取舍，不攻击、不羞辱用户。",
}
CRISIS_PATTERNS = re.compile(r"想死|不想活|自杀|结束生命|伤害自己|活不下去")

def default_support_preferences() -> Dict[str, Any]:
    return {"mode": "listen_then_action", "follow_up_enabled": True, "memory_consent": False}

@app.get("/api/v1/support/preferences")
def get_support_preferences(user_id: str):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user.get("support_preferences", default_support_preferences())

@app.put("/api/v1/support/preferences")
@app.post("/api/v1/support/preferences")
def update_support_preferences(request: SupportPreferenceRequest):
    if request.mode not in SUPPORT_MODES:
        raise HTTPException(status_code=400, detail="不支持的陪伴方式")
    preferences = {
        "mode": request.mode,
        "follow_up_enabled": request.follow_up_enabled,
        "memory_consent": request.memory_consent,
        "updated_at": now_iso(),
    }
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        user["support_preferences"] = preferences
        save_beta_state(state)
    return preferences

@app.post("/api/v1/support/check-ins")
def create_emotional_check_in(request: EmotionalCheckInRequest):
    if request.intensity < 1 or request.intensity > 5:
        raise HTTPException(status_code=400, detail="状态强度应为 1-5")
    note = (request.note or "").strip()
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        preferences = user.get("support_preferences", default_support_preferences())

    crisis = bool(CRISIS_PATTERNS.search(note))
    if crisis:
        # 12356 is the unified national mental-health assistance hotline per NHC.
        response = (
            "我很在意你刚才说的这些。现在先不要一个人扛，也先不要伤害自己。"
            "请马上联系一个你信任、能来到你身边的人，并拨打全国心理援助热线 12356。"
            "如果你已经准备伤害自己或正处在危险中，请立即拨打 120/110，或直接去最近的急诊。"
            "Pinco 不是医疗或危机干预服务，但我可以留在这里陪你把下一步做完。"
        )
    else:
        prompt = f"""用户正在求职，刚做了一次状态打卡。
事件：{request.event_type}
状态强度：{request.intensity}/5（1 表示很难受，5 表示有力量）
用户补充：{note or '没有补充'}
用户偏好的支持方式：{SUPPORT_MODES[preferences['mode']]}

请用 80-180 字回应。准确回应感受，不诊断疾病，不承诺一定成功；最多给一个小动作，并以一个容易回答的问题结尾。"""
        try:
            response = llm_chat_with_fallback(
                [{"role": "user", "content": prompt}],
                temperature=0.55,
                system_prompt="你是 Pinco 温柔学姐。情绪支持不是鸡汤，也不能替代专业医疗服务。",
                max_tokens=500,
            )
        except Exception as error:
            print(f"Emotional Check-in Error: {error}")
            raise llm_http_exception(error)

    check_in = {
        "id": f"checkin-{uuid.uuid4().hex[:12]}",
        "intensity": request.intensity,
        "event_type": request.event_type[:40],
        "note": note[:500] if preferences.get("memory_consent") else None,
        "crisis": crisis,
        "created_at": now_iso(),
        "follow_up_due_at": (datetime.utcnow() + timedelta(hours=24)).isoformat()
            if preferences.get("follow_up_enabled") and request.intensity <= 2 else None,
    }
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        check_ins = user.setdefault("emotional_check_ins", [])
        check_ins.insert(0, check_in)
        user["emotional_check_ins"] = check_ins[:100]
        save_beta_state(state)
    return {"check_in": check_in, "response": response, "preferences": preferences}

def due_support_follow_ups(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = datetime.utcnow()
    due = []
    for check_in in user.get("emotional_check_ins", []):
        due_at = check_in.get("follow_up_due_at")
        if not due_at or check_in.get("follow_up_status") in {"responded", "dismissed"}:
            continue
        try:
            if datetime.fromisoformat(due_at.replace("Z", "+00:00")).replace(tzinfo=None) > now:
                continue
        except (TypeError, ValueError):
            continue
        due.append({
            "check_in_id": check_in["id"],
            "event_type": check_in.get("event_type", "daily"),
            "previous_intensity": check_in.get("intensity", 0),
            "due_at": due_at,
            "message": "昨天你状态不太好，学姐回来看看你。今天比昨天好一些、差不多，还是更难受？",
        })
    return due[:3]

@app.get("/api/v1/support/follow-ups/due")
def get_due_support_follow_ups(user_id: str):
    state = load_beta_state()
    user = state.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"follow_ups": due_support_follow_ups(user)}

@app.post("/api/v1/support/check-ins/{check_in_id}/feedback")
def submit_support_feedback(check_in_id: str, request: SupportFeedbackRequest):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        check_in = next(
            (item for item in user.get("emotional_check_ins", []) if item.get("id") == check_in_id), None
        )
        if not check_in:
            raise HTTPException(status_code=404, detail="状态打卡不存在")
        check_in["helpful"] = request.helpful
        check_in["understood_score"] = request.understood_score
        check_in["feedback_at"] = now_iso()
        append_product_event_to_state(state, "emotion.support_feedback", request.user_id, {
            "helpful": request.helpful,
            "understood_score": request.understood_score,
        })
        save_beta_state(state)
    return {
        "accepted": True,
        "helpful": request.helpful,
        "understood_score": request.understood_score,
    }

@app.post("/api/v1/support/follow-ups/{check_in_id}/respond")
def respond_to_support_follow_up(check_in_id: str, request: SupportFollowUpResponseRequest):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        check_in = next(
            (item for item in user.get("emotional_check_ins", []) if item.get("id") == check_in_id), None
        )
        if not check_in:
            raise HTTPException(status_code=404, detail="回访不存在")
        if check_in.get("follow_up_status") in {"responded", "dismissed"}:
            raise HTTPException(status_code=409, detail="这次回访已经处理")
        check_in["follow_up_status"] = "responded"
        check_in["follow_up_intensity"] = request.current_intensity
        check_in["micro_action_completed"] = request.micro_action_completed
        check_in["follow_up_responded_at"] = now_iso()
        append_product_event_to_state(state, "emotion.follow_up.responded", request.user_id, {
            "previous_intensity": check_in.get("intensity"),
            "current_intensity": request.current_intensity,
            "micro_action_completed": request.micro_action_completed,
        })
        save_beta_state(state)
    return {"accepted": True, "micro_action_completed": request.micro_action_completed}

JOB_PIPELINE_STATUSES = {"saved", "applied", "written", "interview1", "interview2", "hr", "offer", "rejected"}

def build_capability_radar(user: Dict[str, Any]) -> Dict[str, Any]:
    evidence = user.get("evidence", [])
    completed = [
        item for item in user.get("interview_sessions", [])
        if item.get("status") == "completed" and item.get("report")
    ]
    profile = user.get("career_profile", {})
    jobs = user.get("jobs", [])
    target_text = " ".join(profile.get("target_roles", []) or []) or (jobs[0].get("title", "") if jobs else "")
    if re.search(r"应用工程|开发|工程师", target_text, re.I):
        target_track = "AI 应用工程师"
    elif re.search(r"运营|解决方案|售前", target_text, re.I):
        target_track = "AI 运营 / 解决方案"
    elif re.search(r"产品", target_text, re.I):
        target_track = "AI 产品经理"
    else:
        target_track = "通用 AI 岗位"

    dimensions = [
        ("business_problem", "业务问题", r"业务|用户|需求|痛点|场景|增长|留存|转化"),
        ("llm_foundation", "模型与 LLM 基础", r"LLM|大模型|模型|Prompt|提示词|Token|Embedding|微调|推理"),
        ("rag_agent_multimodal", "RAG / Agent / 多模态", r"RAG|检索增强|Agent|智能体|工作流|多模态|向量|知识库|工具调用"),
        ("data_evaluation", "数据与评测", r"数据|评测|指标|A/B|实验|准确率|召回率|幻觉|基准|监控"),
        ("productization", "产品化与交付", r"产品化|上线|发布|交付|迭代|灰度|工程|稳定性|SLA|反馈闭环"),
        ("roi", "ROI 与商业价值", r"ROI|成本|收入|营收|商业化|效率|节省|付费|客单|利润"),
        ("safety", "安全与责任", r"安全|隐私|合规|权限|风控|红队|内容治理|可解释|偏见"),
        ("project_expression", "项目表达", r"STAR|背景|目标|行动|结果|复盘|协作|推动|负责|主导"),
    ]
    answer_texts = [
        str(answer.get("answer") or "")
        for session in completed[:5]
        for answer in session.get("answers", [])
    ]
    radar_dimensions = []
    for key, label, pattern in dimensions:
        matched_ids = []
        for item in evidence:
            text = " ".join(
                str(item.get(field) or "")
                for field in ("title", "situation", "action", "result", "metrics", "skills")
            )
            if re.search(pattern, text, re.I):
                matched_ids.append(item.get("id"))
        matched_answers = sum(1 for text in answer_texts if re.search(pattern, text, re.I))
        if key == "project_expression":
            structured_items = [
                item for item in evidence
                if item.get("action") and item.get("result") and (item.get("situation") or item.get("metrics"))
            ]
            matched_ids = [item.get("id") for item in structured_items]
        score = min(100, len(matched_ids) * 25 + min(25, matched_answers * 5))
        radar_dimensions.append({
            "key": key,
            "label": label,
            "score": score,
            "source": f"{len(matched_ids)} 条真实证据 + {matched_answers} 条练习回答",
            "evidence_ids": [value for value in matched_ids if value],
        })
    lowest = min(radar_dimensions, key=lambda item: item["score"]) if radar_dimensions else None
    return {
        "target_track": target_track,
        "dimensions": radar_dimensions,
        "next_gap": {"key": lowest["key"], "label": lowest["label"], "score": lowest["score"]} if lowest else None,
        "disclaimer": "这是 AI 岗八个维度的证据覆盖度，不是能力鉴定。只统计你提交的真实证据和练习回答；0 分表示尚无证据，不代表没有能力。",
    }

def build_learning_plan(user: Dict[str, Any], radar: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    radar = radar or build_capability_radar(user)
    gap = radar.get("next_gap") or {"key": "project_expression", "label": "项目表达", "score": 0}
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    plan_id = f"learning-{week_start.isoformat()}-{gap['key']}"
    progress = (user.get("learning_plan_progress") or {}).get(plan_id, {})
    completed_days = {
        int(value) for value in progress.get("completed_days", [])
        if str(value).isdigit() and 1 <= int(value) <= 7
    }
    gap_outputs = {
        "business_problem": "一条包含用户、场景、问题规模和业务目标的证据",
        "llm_foundation": "一张解释模型选择、Prompt/Token 约束和失败边界的项目卡",
        "rag_agent_multimodal": "一张 RAG/Agent/多模态链路图及一次真实取舍记录",
        "data_evaluation": "一套含样本、指标、基线和误差分析的评测证据",
        "productization": "一条从灰度、监控到反馈闭环的上线证据",
        "roi": "一条把成本、效率或收入变化量化的 ROI 证据",
        "safety": "一条包含隐私、权限、内容风险和处置方案的安全证据",
        "project_expression": "一个不编造、可连续深挖 10 分钟的 STAR 项目故事",
    }
    output = gap_outputs.get(gap["key"], "一条可核验的岗位证据")
    days = [
        (1, "只盘点事实", f"从现有经历中找出与“{gap['label']}”最接近的一件事；不知道的地方标记待补，不补写。", "事实与待补清单"),
        (2, "对照真实 JD", f"从已保存岗位里摘出 3 条与“{gap['label']}”相关的原文要求。", "3 条 JD 原文及来源岗位"),
        (3, "补行动细节", "写清当时你亲自做了什么、和谁协作、为什么这样取舍。", "5–8 句行动记录"),
        (4, "补结果与边界", "补一个可核验结果；没有数字就写可验证现象，并说明仍缺什么数据。", "结果、指标或待验证假设"),
        (5, "做一次短练习", f"围绕“{gap['label']}”完成一次 5–10 分钟练习，只使用前四天确认的事实。", "一轮练习报告"),
        (6, "拿真实反馈", "把证据或回答给一位同行/专家看，只问：哪里不可信、哪里听不懂、最想追问什么。", "三条外部反馈"),
        (7, "更新证据并投一批", f"把反馈改进到证据库，产出“{output}”，再优先处理 GO 岗位和补齐后的 MAYBE 岗位。", output),
    ]
    decisions = {"GO": 0, "MAYBE": 0, "NO_GO": 0, "UNASSESSED": 0}
    for job in user.get("jobs", []):
        decision = (job.get("materials") or {}).get("fit_decision")
        decisions[decision if decision in decisions else "UNASSESSED"] += 1
    if decisions["GO"]:
        batch_strategy = f"先推进 {decisions['GO']} 个 GO 岗位；MAYBE 岗位只在补齐关键证据后进入下一批。"
    elif decisions["MAYBE"]:
        batch_strategy = f"当前有 {decisions['MAYBE']} 个 MAYBE 岗位；本周先补最低证据维度，再重新生成材料判断。"
    else:
        batch_strategy = "先完成一份真实 JD、至少一条职业证据和材料判断，再决定下一批岗位；不要用无来源岗位填数量。"
    return {
        "id": plan_id,
        "week_start": week_start.isoformat(),
        "target_track": radar.get("target_track"),
        "focus_dimension": gap,
        "target_output": output,
        "days": [
            {"day": day, "title": title, "action": action, "evidence_output": evidence_output, "completed": day in completed_days}
            for day, title, action, evidence_output in days
        ],
        "completed_count": len(completed_days),
        "decision_counts": decisions,
        "next_batch_strategy": batch_strategy,
        "disclaimer": "这是基于真实证据覆盖缺口生成的行动计划，不是能力诊断；完成状态由你主动确认。",
    }

def serialize_workspace(user: Dict[str, Any]) -> Dict[str, Any]:
    radar = build_capability_radar(user)
    return {
        "career_profile": user.get("career_profile", {
            "target_roles": [], "years_experience": 0, "cities": [], "strengths": []
        }),
        "evidence": user.get("evidence", []),
        "jobs": user.get("jobs", []),
        "interview_sessions": user.get("interview_sessions", [])[:20],
        "resume_analyses": user.get("resume_analyses", [])[:20],
        "capability_radar": radar,
        "learning_plan": build_learning_plan(user, radar),
    }

@app.get("/api/v1/workspace")
def get_workspace(user_id: str):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return serialize_workspace(user)

@app.post("/api/v1/workspace/learning-plan/progress")
def update_learning_plan_progress(request: LearningPlanProgressRequest):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        current_plan = build_learning_plan(user)
        if request.plan_id != current_plan["id"]:
            raise HTTPException(status_code=409, detail="能力证据已变化，请刷新后使用最新计划")
        all_progress = user.setdefault("learning_plan_progress", {})
        progress = all_progress.setdefault(request.plan_id, {"completed_days": [], "created_at": now_iso()})
        completed = {int(value) for value in progress.get("completed_days", []) if str(value).isdigit()}
        if request.completed:
            completed.add(request.day)
        else:
            completed.discard(request.day)
        progress["completed_days"] = sorted(completed)
        progress["updated_at"] = now_iso()
        append_product_event_to_state(state, "workspace.learning_plan.day_updated", request.user_id, {
            "plan_id": request.plan_id,
            "day": request.day,
            "completed": request.completed,
            "completed_count": len(completed),
        })
        save_beta_state(state)
        updated = build_learning_plan(user)
    return {"learning_plan": updated}

@app.get("/api/v1/account/export")
def export_account(user_id: str):
    """Return the user's own portable JSON without internal auth material."""
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        profile = {
            key: value for key, value in user.get("profile", {}).items()
            if key not in {
                "session_token_hash", "session_token_hashes", "session_issued_at",
                "wechat_openid", "wechat_openid_hint",
            }
        }
        own_posts = [
            serialize_post(post, user_id)
            for post in state.get("community_posts", [])
            if post.get("created_by") == user_id
        ]
        payload = {
            "export_version": 1,
            "exported_at": now_iso(),
            "profile": profile,
            "career_memory": deepcopy(user.get("career_memory", {})),
            "resume_memory": deepcopy(user.get("resume_memory", {})),
            "workspace": serialize_workspace(user),
            "messages": user.get("messages", []),
            "bookings": user.get("bookings", []),
            "support_preferences": user.get("support_preferences", {}),
            "emotional_check_ins": user.get("emotional_check_ins", []),
            "community_posts": own_posts,
            "pilot_feedback": next((
                deepcopy(item) for item in state.get("pilot_feedback", [])
                if item.get("user_id") == user_id
            ), None),
            "membership": _membership_to_response(user.get("membership", {"plan_id": "free"})).model_dump(),
            "contribution": contribution_status(state, user_id),
        }
    return payload

@app.delete("/api/v1/account")
def delete_account(request: AccountDeleteRequest):
    if request.confirmation != "DELETE":
        raise HTTPException(status_code=422, detail="删除确认文字不正确")
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        active_payment_orders = [
            item for item in state.get("orders", [])
            if item.get("user_id") == request.user_id
            and item.get("status") in {"creating", "unpaid", "refund_processing"}
        ]
        if active_payment_orders:
            raise HTTPException(
                status_code=409,
                detail="仍有待支付确认或退款中的订单，请先等待订单结束后再删除账号",
            )
        unfinished_paid_expert_orders = []
        for order in state.get("orders", []):
            if order.get("user_id") != request.user_id or order.get("product_type") != "expert" or order.get("status") != "paid":
                continue
            booking_id = order.get("metadata", {}).get("booking_id")
            booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
            if booking and booking.get("status_code") not in {"completed", "cancelled"}:
                unfinished_paid_expert_orders.append(order)
        if unfinished_paid_expert_orders:
            raise HTTPException(
                status_code=409,
                detail="仍有已支付但未完成或退款的专家服务，请先完成服务或退款后再删除账号",
            )
        owned_expert_ids = {
            item.get("id") for item in state.get("experts", [])
            if item.get("owner_user_id") == request.user_id and item.get("id")
        }
        unsettled_owned_bookings = [
            item for item in state.get("expert_bookings", [])
            if item.get("expert_owner_user_id") == request.user_id
            and item.get("status_code") not in {"completed", "cancelled", "rejected"}
            and item.get("payment_status") in {"unpaid", "paid", "refund_processing"}
        ]
        if unsettled_owned_bookings:
            raise HTTPException(
                status_code=409,
                detail="仍有买方待支付、已支付未交付或退款中的专家服务，请先完成关单、履约或退款",
            )
        deleted_ref = hashlib.sha256(f"deleted:{request.user_id}".encode("utf-8")).hexdigest()
        # Remove authored content and personally-linked interactions. Official
        # examples and other users' content remain intact.
        kept_posts = []
        for post in state.get("community_posts", []):
            if post.get("created_by") == request.user_id:
                continue
            post["liked_by"] = [value for value in post.get("liked_by", []) if value != request.user_id]
            post["hugged_by"] = [value for value in post.get("hugged_by", []) if value != request.user_id]
            post["action_started_by"] = [
                value for value in post.get("action_started_by", []) if value != request.user_id
            ]
            post["comments"] = [
                comment for comment in post.get("comments", [])
                if comment.get("created_by") != request.user_id
            ]
            kept_posts.append(post)
        state["community_posts"] = kept_posts
        state["events"] = [item for item in state.get("events", []) if item.get("user_id") != request.user_id]
        state["membership_interests"] = [
            item for item in state.get("membership_interests", []) if item.get("user_id") != request.user_id
        ]
        state["pilot_feedback"] = [
            item for item in state.get("pilot_feedback", []) if item.get("user_id") != request.user_id
        ]
        state["point_ledger"] = [
            item for item in state.get("point_ledger", [])
            if item.get("user_id") != request.user_id
            and item.get("source_user_id") != request.user_id
            and request.user_id not in str(item.get("idempotency_key", ""))
        ]
        kept_bookings = []
        for booking in state.get("expert_bookings", []):
            buyer_deleted = booking.get("user_id") == request.user_id
            expert_deleted = booking.get("expert_owner_user_id") == request.user_id
            if not buyer_deleted and not expert_deleted:
                kept_bookings.append(booking)
                continue
            retain_financial_record = (
                booking.get("payment_status") in {"paid", "refunded"}
                or booking.get("status_code") == "completed"
            )
            if buyer_deleted and not retain_financial_record:
                continue
            sanitized = dict(booking)
            if buyer_deleted:
                sanitized.pop("user_id", None)
                sanitized["deleted_buyer_ref"] = deleted_ref
            if expert_deleted:
                sanitized.pop("expert_owner_user_id", None)
                sanitized["deleted_expert_ref"] = deleted_ref
                sanitized["expertId"] = f"deleted-expert-{deleted_ref[:12]}"
                sanitized["expertName"] = "已注销专家"
                if not retain_financial_record:
                    sanitized.update({
                        "status_code": "cancelled",
                        "status": "专家账号已注销，预约自动取消",
                        "cancelled_at": now_iso(),
                        "updated_at": now_iso(),
                    })
                if not buyer_deleted:
                    update_user_booking_copy(state, sanitized)
            kept_bookings.append(sanitized)
        state["expert_bookings"] = kept_bookings
        state["expert_reviews"] = [
            item for item in state.get("expert_reviews", [])
            if item.get("user_id") != request.user_id and item.get("expert_id") not in owned_expert_ids
        ]
        state["expert_applications"] = [
            item for item in state.get("expert_applications", []) if item.get("user_id") != request.user_id
        ]
        state["experts"] = [
            item for item in state.get("experts", []) if item.get("owner_user_id") != request.user_id
        ]
        # Unpaid/failed orders can be removed. Completed financial records keep
        # only an irreversible reference so later merchant reconciliation does
        # not retain the deleted Pinco account id.
        anonymized_ref = deleted_ref
        kept_orders = []
        for order in state.get("orders", []):
            if order.get("user_id") != request.user_id:
                if order.get("product_type") == "expert" and (order.get("metadata") or {}).get("expert_id") in owned_expert_ids:
                    order = dict(order)
                    order["metadata"] = dict(order.get("metadata") or {})
                    order["metadata"]["expert_id"] = f"deleted-expert-{deleted_ref[:12]}"
                kept_orders.append(order)
            elif order.get("status") in {"paid", "refunded"}:
                anonymized = dict(order)
                anonymized.pop("user_id", None)
                anonymized["deleted_user_ref"] = anonymized_ref
                kept_orders.append(anonymized)
        state["orders"] = kept_orders
        del state["users"][request.user_id]
        save_beta_state(state)
    return {"deleted": True}

@app.post("/api/v1/account/messages/clear")
def clear_account_messages(request: CommunityActionRequest):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        user["messages"] = default_messages()
        append_product_event_to_state(state, "account.messages.cleared", request.user_id)
        save_beta_state(state)
    return {"messages": user["messages"]}

@app.post("/api/v1/workspace/profile")
def update_career_profile(request: CareerProfileRequest):
    if request.years_experience < 0 or request.years_experience > 50:
        raise HTTPException(status_code=400, detail="工作年限范围无效")
    profile = {
        "target_roles": [item.strip() for item in request.target_roles if item.strip()][:8],
        "years_experience": request.years_experience,
        "cities": [item.strip() for item in request.cities if item.strip()][:8],
        "strengths": [item.strip() for item in request.strengths if item.strip()][:20],
        "job_search_deadline": request.job_search_deadline.strip(),
        "updated_at": now_iso(),
    }
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        user["career_profile"] = profile
        save_beta_state(state)
    return {"career_profile": profile}

@app.post("/api/v1/workspace/evidence")
def create_evidence(request: EvidenceCreateRequest):
    if len(request.title.strip()) < 2 or len(request.action.strip()) < 5 or len(request.result.strip()) < 2:
        raise HTTPException(status_code=400, detail="请至少填写证据标题、做了什么和结果")
    evidence = {
        "id": f"evidence-{uuid.uuid4().hex[:12]}",
        "title": request.title.strip()[:100],
        "situation": request.situation.strip()[:1200],
        "action": request.action.strip()[:2000],
        "result": request.result.strip()[:1200],
        "metrics": request.metrics.strip()[:500],
        "skills": [item.strip() for item in request.skills if item.strip()][:20],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        items = user.setdefault("evidence", [])
        items.insert(0, evidence)
        user["evidence"] = items[:100]
        append_product_event_to_state(state, "workspace.evidence.created", request.user_id, {"has_metric": bool(evidence["metrics"])})
        save_beta_state(state)
    return {"evidence": evidence}

@app.post("/api/v1/workspace/jobs")
def create_workspace_job(request: WorkspaceJobCreateRequest):
    if request.status not in JOB_PIPELINE_STATUSES:
        raise HTTPException(status_code=400, detail="岗位状态无效")
    if request.source != "manual" and not (request.source_url and re.match(r"^https?://", request.source_url)):
        raise HTTPException(status_code=400, detail="公开来源岗位必须包含可打开链接")
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        jobs = user.setdefault("jobs", [])
        existing = next((
            item for item in jobs
            if (request.source_url and item.get("source_url") == request.source_url)
            or (
                request.source == "manual"
                and item.get("source") == "manual"
                and item.get("company", "").strip().lower() == request.company.strip().lower()
                and item.get("title", "").strip().lower() == request.title.strip().lower()
            )
        ), None)
        if existing:
            if request.status != "saved":
                existing["status"] = request.status
                existing["updated_at"] = now_iso()
                save_beta_state(state)
            return {"job": existing, "created": False}
        job = {
            "id": f"job-{uuid.uuid4().hex[:12]}",
            "title": request.title.strip()[:120],
            "company": request.company.strip()[:100],
            "location": request.location.strip()[:100],
            "source": request.source.strip()[:80],
            "source_url": request.source_url,
            "source_checked_at": now_iso() if request.source_url else None,
            "source_status": "linked_at_save" if request.source_url else "user_provided",
            "jd_text": request.jd_text.strip()[:12000],
            "status": request.status,
            "materials": {},
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        jobs.insert(0, job)
        user["jobs"] = jobs[:200]
        append_product_event_to_state(state, "workspace.job.saved", request.user_id, {
            "job_id": job["id"], "source": job["source"], "has_jd": bool(job["jd_text"])
        })
        save_beta_state(state)
    return {"job": job, "created": True}

def job_status_support_action(job: Dict[str, Any], status: str) -> Optional[Dict[str, str]]:
    label = f"{job.get('company', '')} {job.get('title', '')}".strip() or "这个岗位"
    actions = {
        "applied": {
            "title": "投出去以后，先把注意力拿回来",
            "message": "等待回复很磨人。可以定一个跟进时间，然后把精力切到下一份高匹配岗位。",
            "action_label": "安排一步",
            "prompt": f"我刚投递了{label}。请帮我区分现在可控和不可控的事，定一次合适的跟进时间，再只安排今天一个小行动。",
        },
        "interview1": {
            "title": "进入一面，紧张和期待都正常",
            "message": "先确认一条真实优势，再用 5–10 分钟热身，不需要一次把所有题练完。",
            "action_label": "陪我热身",
            "prompt": f"我进入了{label}的一面。请先帮我确认一条真实优势，再问我想轻松热身还是按真实强度练习。",
        },
        "interview2": {
            "title": "走到二面已经说明了一些事实",
            "message": "别急着证明自己什么都会，先把上一轮最容易被追问的证据讲扎实。",
            "action_label": "复练弱项",
            "prompt": f"我进入了{label}的二面。请先肯定我已经走到这里的事实，再帮我选上一轮一个最弱问题做 10 分钟复练。",
        },
        "hr": {
            "title": "到了 HR 面，先稳住节奏",
            "message": "把动机、稳定性、期望和事实条件分开准备，避免临场被焦虑带着走。",
            "action_label": "准备 HR 面",
            "prompt": f"我进入了{label}的 HR 面。请按我的陪伴偏好接住紧张，再帮我准备动机、期望和风险问题。",
        },
        "offer": {
            "title": "拿到 Offer，开心和担心可以同时存在",
            "message": "先不催自己马上决定，把薪资、成长、团队和风险事实列清楚；复杂谈薪再找专家。",
            "action_label": "一起做决定",
            "prompt": f"我拿到了{label}的 Offer。请允许兴奋和担心同时存在，再帮我把事实条件、个人偏好和风险红线分开排序。",
        },
        "rejected": {
            "title": "结果不等于你的价值",
            "message": "今天不必强迫自己深度复盘。先选想被陪伴，还是只记录一个事实，准备好后再行动。",
            "action_label": "先找学姐",
            "prompt": f"我收到{label}未通过的结果。请先按我的陪伴偏好接住情绪，问我现在是否适合复盘；如果不适合，就只陪我稳住状态。",
        },
    }
    action = actions.get(status)
    return {**action, "scenario": "emotion"} if action else None

@app.post("/api/v1/workspace/jobs/{job_id}/status")
def update_workspace_job_status(job_id: str, request: WorkspaceJobStatusRequest):
    if request.status not in JOB_PIPELINE_STATUSES:
        raise HTTPException(status_code=400, detail="岗位状态无效")
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        job = next((item for item in user.get("jobs", []) if item.get("id") == job_id), None)
        if not job:
            raise HTTPException(status_code=404, detail="岗位不存在")
        job["status"] = request.status
        job["updated_at"] = now_iso()
        append_product_event_to_state(state, "workspace.job.status_updated", request.user_id, {"job_id": job_id, "status": request.status})
        save_beta_state(state)
    return {"job": job, "support_action": job_status_support_action(job, request.status)}

@app.post("/api/v1/workspace/jobs/{job_id}/materials")
def generate_job_materials(job_id: str, request: JobMaterialGenerateRequest):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        job = next((item for item in user.get("jobs", []) if item.get("id") == job_id), None)
        if not job:
            raise HTTPException(status_code=404, detail="岗位不存在")
        selected = [
            item for item in user.get("evidence", [])
            if not request.evidence_ids or item.get("id") in request.evidence_ids
        ][:10]
    if not job.get("jd_text"):
        raise HTTPException(status_code=400, detail="请先为岗位补充完整 JD，再生成定制材料")
    if not selected:
        raise HTTPException(status_code=400, detail="请先在职业证据库添加至少一条真实经历")
    prompt = f"""基于真实 JD 和候选人证据，为单个岗位生成定制求职材料。不得编造经历、数字、公司或技术栈。
岗位：{job['company']} - {job['title']}
JD：{job['jd_text'][:7000]}
候选人证据：{json.dumps(selected, ensure_ascii=False)[:9000]}

只输出合法 JSON：
{{"fit_decision":"GO 或 MAYBE 或 NO_GO","fit_reasons":["只引用 JD 与真实证据的理由"],"match_summary":"匹配与缺口","resume_bullets":["3-5条可直接改写的简历要点"],"outreach_message":"80-150字投递/内推话术","interview_stories":[{{"question":"可能问题","evidence_id":"证据ID","answer_outline":"只用证据事实的回答框架"}}],"gaps":["缺失证据"]}}"""
    try:
        raw = llm_chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            system_prompt="你是求职材料教练。只能重组用户提供的事实；没有证据就明确写进 gaps。",
            max_tokens=2200,
        )
        materials = json.loads(clean_json_response(raw))
        if (
            materials.get("fit_decision") not in {"GO", "MAYBE", "NO_GO"}
            or not isinstance(materials.get("fit_reasons"), list)
            or not materials.get("fit_reasons")
            or not materials.get("match_summary")
            or not isinstance(materials.get("resume_bullets"), list)
        ):
            raise RuntimeError("INVALID_JOB_MATERIALS")
    except Exception as error:
        print(f"Job Materials Error: {error}")
        raise llm_http_exception(error)
    materials["generated_at"] = now_iso()
    materials["evidence_ids"] = [item["id"] for item in selected]
    with _state_lock:
        state = load_beta_state()
        _, current_job = _workspace_job_for_user(state, request.user_id, job_id)
        current_job["materials"] = materials
        current_job["updated_at"] = now_iso()
        append_product_event_to_state(state, "workspace.materials.generated", request.user_id, {"job_id": job_id, "evidence_count": len(selected)})
        if user.get("resume_analyses") and not any(
            item.get("name") == "activation.workspace.ready" and item.get("user_id") == request.user_id
            for item in state.get("events", [])
        ):
            append_product_event_to_state(state, "activation.workspace.ready", request.user_id, {"job_id": job_id})
        save_beta_state(state)
    return {"job_id": job_id, "materials": materials}

@app.put("/api/v1/workspace/jobs/{job_id}/materials")
def update_job_materials(job_id: str, request: JobMaterialsUpdateRequest):
    bullets = [item.strip() for item in request.resume_bullets if item.strip()][:8]
    outreach = request.outreach_message.strip()
    if not bullets and not outreach:
        raise HTTPException(status_code=422, detail="请至少保留一条简历要点或投递话术")
    with _state_lock:
        state = load_beta_state()
        _, job = _workspace_job_for_user(state, request.user_id, job_id)
        materials = job.get("materials")
        if not isinstance(materials, dict):
            raise HTTPException(status_code=409, detail="请先基于真实证据生成材料，再编辑")
        materials["resume_bullets"] = bullets
        materials["outreach_message"] = outreach
        materials["user_edited"] = True
        materials["updated_at"] = now_iso()
        job["updated_at"] = now_iso()
        save_beta_state(state)
    return {"job_id": job_id, "materials": materials}

@app.post("/api/v1/workspace/jobs/{job_id}/materials/feedback")
def submit_job_material_feedback(job_id: str, request: JobMaterialFeedbackRequest):
    rating = request.rating.strip().lower()
    if rating not in {"direct_use", "minor_edit", "major_rework", "fabricated"}:
        raise HTTPException(status_code=422, detail="不支持的材料反馈")
    with _state_lock:
        state = load_beta_state()
        _, job = _workspace_job_for_user(state, request.user_id, job_id)
        if not job.get("materials", {}).get("generated_at"):
            raise HTTPException(status_code=409, detail="请先生成岗位材料再反馈")
        feedback = {
            "rating": rating,
            "note": request.note.strip(),
            "created_at": now_iso(),
        }
        job["materials"]["user_feedback"] = feedback
        append_product_event_to_state(state, "workspace.materials.feedback", request.user_id, {
            "job_id": job_id,
            "rating": rating,
            "fabrication_reported": rating == "fabricated",
        })
        save_beta_state(state)
    return {"accepted": True, "feedback": feedback}

def _workspace_job_for_user(state: Dict[str, Any], user_id: str, job_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    user = state.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    job = next((item for item in user.get("jobs", []) if item.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return user, job

@app.post("/api/v1/miniapp/message")
def miniapp_message(request: MiniappMessageRequest):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在，请重新进入小程序")
        enforce_membership_quota(state, request.user_id, "ai_chat_used")
        user_message = {
            "id": f"user-{uuid.uuid4().hex[:10]}",
            "role": "user",
            "content": request.content.strip(),
            "createdAt": now_time_label(),
        }
        user["messages"].append(user_message)
        save_beta_state(state)
    try:
        reply = llm_chat_with_fallback(
            [{"role": msg["role"], "content": msg["content"]} for msg in user["messages"][-8:]],
            temperature=0.7,
            system_prompt=build_scenario_instruction(request.scenario),
            max_tokens=800,
        )
    except Exception as e:
        print(f"Miniapp Message Error: {e}")
        raise llm_http_exception(e)
    assistant_message = {
        "id": f"assistant-{uuid.uuid4().hex[:10]}",
        "role": "assistant",
        "content": reply,
        "createdAt": now_time_label(),
    }
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在，请重新进入小程序")
        user["messages"].append(assistant_message)
        record_membership_usage(state, request.user_id, "ai_chat_used")
        save_beta_state(state)
    return {"reply": reply, "messages": user["messages"]}

def serialize_expert(state: Dict[str, Any], expert: Dict[str, Any]) -> Dict[str, Any]:
    reviews = [
        review for review in state.get("expert_reviews", [])
        if review.get("expert_id") == expert.get("id") and review.get("status", "published") == "published"
    ]
    rating = round(sum(review["score"] for review in reviews) / len(reviews), 1) if reviews else 0
    completed_count = sum(
        1 for booking in state.get("expert_bookings", [])
        if booking.get("expertId") == expert.get("id") and booking.get("status_code") == "completed"
    )
    slots = [slot for slot in expert.get("slots", []) if isinstance(slot, str) and slot.strip()]
    return {
        "id": expert["id"],
        "name": expert["name"],
        "title": expert["title"],
        "intro": expert["intro"],
        "tags": expert.get("tags", []),
        "price": expert.get("reference_price", 0),
        "nextSlot": slots[0] if slots else "暂无可约时段",
        "slots": slots,
        "rating": rating,
        "servedCount": completed_count,
        "verificationStatus": (
            "内测需求画像·尚未指定真人"
            if expert.get("is_demo") else "平台已审核"
        ),
        "isDemo": bool(expert.get("is_demo")),
        "serviceName": expert.get("service_name", "30分钟求职问题诊断"),
        "deliverables": expert.get("service_deliverables", ["问题诊断", "下一步行动清单"]),
        "durationMinutes": int(expert.get("duration_minutes", 30)),
        "reviews": [
            {
                "id": review["id"],
                "score": review["score"],
                "comment": review["comment"],
                "created_at": review["created_at"],
            }
            for review in reviews[-10:]
        ],
    }

def require_admin_token(token: Optional[str]) -> None:
    if not PINCO_ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="专家审核后台尚未配置 PINCO_ADMIN_TOKEN")
    if not token or not secrets_compare(token, PINCO_ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="管理员凭证无效")

def secrets_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))

@app.get("/api/v1/experts")
def list_experts():
    state = load_beta_state()
    experts = [item for item in state.get("experts", []) if item.get("status") == "approved"]
    return {"experts": [serialize_expert(state, item) for item in experts]}

@app.post("/api/v1/experts/applications")
def apply_as_expert(request: ExpertApplicationRequest):
    proof_urls = [url.strip() for url in request.proof_urls if re.match(r"^https?://", url.strip())][:5]
    if not proof_urls:
        raise HTTPException(status_code=422, detail="至少提供一个可核验的履历或作品链接")
    tags = [tag.strip() for tag in request.tags if tag.strip()][:8]
    slots = list(dict.fromkeys(slot.strip() for slot in request.slots if slot.strip()))[:30]
    deliverables = [item.strip() for item in request.service_deliverables if item.strip()][:6]
    if not deliverables:
        raise HTTPException(status_code=422, detail="请至少说明一项固定交付物")
    with _state_lock:
        state = load_beta_state()
        community_user(state, request.user_id)
        existing = next(
            (item for item in state.get("expert_applications", []) if item.get("user_id") == request.user_id),
            None,
        )
        if existing and existing.get("status") in {"pending", "approved"}:
            raise HTTPException(status_code=409, detail="你已有审核中或已通过的专家申请")
        application = {
            "id": f"expert-application-{uuid.uuid4().hex[:12]}",
            "user_id": request.user_id,
            "real_name": request.real_name.strip(),
            "title": request.title.strip(),
            "intro": request.intro.strip(),
            "tags": tags,
            "experience_summary": request.experience_summary.strip() or request.intro.strip(),
            "proof_urls": proof_urls,
            "reference_price": request.reference_price,
            "slots": slots,
            "service_name": request.service_name.strip(),
            "service_deliverables": deliverables,
            "status": "pending",
            "review_note": "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        state.setdefault("expert_applications", []).append(application)
        save_beta_state(state)
    return {"application": {k: v for k, v in application.items() if k != "proof_urls"}}

@app.get("/api/v1/experts/applications/status")
def get_expert_application_status(user_id: str):
    state = load_beta_state()
    community_user(state, user_id)
    application = next(
        (item for item in reversed(state.get("expert_applications", [])) if item.get("user_id") == user_id),
        None,
    )
    if not application:
        return {"application": None}
    return {"application": {k: v for k, v in application.items() if k not in {"proof_urls", "experience_summary"}}}

@app.get("/api/v1/experts/me")
def get_my_expert_workspace(user_id: str):
    state = load_beta_state()
    community_user(state, user_id)
    expert = next(
        (item for item in state.get("experts", []) if item.get("owner_user_id") == user_id and item.get("status") == "approved"),
        None,
    )
    bookings = [
        item for item in state.get("expert_bookings", [])
        if item.get("expert_owner_user_id") == user_id
    ]
    return {
        "expert": serialize_expert(state, expert) if expert else None,
        "bookings": bookings,
    }

@app.get("/api/v1/admin/expert-applications")
def list_expert_applications(x_pinco_admin_token: Optional[str] = Header(default=None)):
    require_admin_token(x_pinco_admin_token)
    state = load_beta_state()
    return {"applications": state.get("expert_applications", [])}

@app.post("/api/v1/admin/expert-applications/{application_id}/review")
def review_expert_application(
    application_id: str,
    request: ExpertApplicationReviewRequest,
    x_pinco_admin_token: Optional[str] = Header(default=None),
):
    require_admin_token(x_pinco_admin_token)
    decision = request.decision.strip().lower()
    if decision not in {"approved", "rejected", "changes_requested"}:
        raise HTTPException(status_code=422, detail="decision 必须是 approved、rejected 或 changes_requested")
    with _state_lock:
        state = load_beta_state()
        application = next(
            (item for item in state.get("expert_applications", []) if item.get("id") == application_id), None
        )
        if not application:
            raise HTTPException(status_code=404, detail="专家申请不存在")
        application["status"] = decision
        application["review_note"] = request.review_note.strip()
        application["updated_at"] = now_iso()
        if decision == "approved":
            expert = next(
                (item for item in state.get("experts", []) if item.get("owner_user_id") == application["user_id"]),
                None,
            )
            if not expert:
                expert = {
                    "id": f"expert-{uuid.uuid4().hex[:12]}",
                    "owner_user_id": application["user_id"],
                    "created_at": now_iso(),
                }
                state.setdefault("experts", []).append(expert)
            expert.update({
                "name": application["real_name"],
                "title": application["title"],
                "intro": application["intro"],
                "tags": application["tags"],
                "reference_price": application["reference_price"],
                "slots": application["slots"],
                "service_name": application["service_name"],
                "service_deliverables": application["service_deliverables"],
                "duration_minutes": 30,
                "status": "approved",
                "application_id": application["id"],
                "updated_at": now_iso(),
            })
        save_beta_state(state)
    return {"application": application}

@app.post("/api/v1/experts/{expert_id}/availability")
def update_expert_availability(expert_id: str, request: ExpertAvailabilityRequest):
    slots = list(dict.fromkeys(slot.strip() for slot in request.slots if slot.strip()))[:30]
    with _state_lock:
        state = load_beta_state()
        expert = next((item for item in state.get("experts", []) if item.get("id") == expert_id), None)
        if not expert or expert.get("status") != "approved":
            raise HTTPException(status_code=404, detail="专家不存在")
        if expert.get("owner_user_id") != request.user_id:
            raise HTTPException(status_code=403, detail="只能维护自己的可约时段")
        expert["slots"] = slots
        expert["updated_at"] = now_iso()
        save_beta_state(state)
        serialized = serialize_expert(state, expert)
    return {"expert": serialized}

def build_expert_briefing(user: Dict[str, Any], job: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Build a consented, bounded brief without exposing the full account export."""
    materials = job.get("materials") if isinstance(job.get("materials"), dict) else {}
    evidence_ids = set(materials.get("evidence_ids") or [])
    evidence = [
        {
            "title": item.get("title", ""),
            "action": item.get("action", ""),
            "result": item.get("result", ""),
            "metrics": item.get("metrics", ""),
        }
        for item in user.get("evidence", [])
        if not evidence_ids or item.get("id") in evidence_ids
    ][:5]
    sessions = [
        item for item in user.get("interview_sessions", [])
        if item.get("job_id") == job.get("id") and item.get("status") == "completed" and item.get("report")
    ]
    latest_session = sessions[0] if sessions else None
    report = latest_session.get("report", {}) if latest_session else {}
    gaps = [str(item).strip() for item in materials.get("gaps", []) if str(item).strip()][:3]
    key_questions = [question.strip()] if question.strip() else []
    key_questions.extend(f"如何补齐：{gap}" for gap in gaps)
    return {
        "consented_at": now_iso(),
        "job": {
            "label": f"{job.get('company', '')} · {job.get('title', '')}".strip(" ·"),
            "jd_excerpt": str(job.get("jd_text") or "")[:1500],
            "fit_decision": materials.get("fit_decision"),
            "fit_reasons": list(materials.get("fit_reasons") or [])[:3],
            "gaps": gaps,
        },
        "evidence": evidence,
        "latest_practice": {
            "position": latest_session.get("position", "") if latest_session else "",
            "overall_score": report.get("overall_score") if latest_session else None,
            "priority_improvements": list(
                report.get("priority_improvements") or report.get("improvements") or []
            )[:3],
        } if latest_session else None,
        "key_questions": list(dict.fromkeys(key_questions))[:3],
        "privacy_note": "仅包含用户本次明确授权分享的关联岗位、已确认职业证据和关联练习摘要。",
    }

@app.post("/api/v1/bookings")
def create_booking(request: BookingCreateRequest):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在，请重新进入小程序")
        expert = next(
            (item for item in state.get("experts", []) if item.get("id") == request.expert_id and item.get("status") == "approved"),
            None,
        )
        if not expert:
            raise HTTPException(status_code=404, detail="该专家尚未通过平台审核")
        if request.slot not in expert.get("slots", []):
            raise HTTPException(status_code=409, detail="该时段已不可约，请刷新后重选")
        bound_job = None
        if request.job_id:
            bound_job = next((item for item in user.get("jobs", []) if item.get("id") == request.job_id), None)
            if not bound_job:
                raise HTTPException(status_code=404, detail="要关联的岗位不存在")
        if request.share_context_with_expert and not bound_job:
            raise HTTPException(status_code=422, detail="授权会前摘要前请先关联一个岗位")
        booking = {
            "id": f"booking-{uuid.uuid4().hex[:10]}",
            "user_id": request.user_id,
            "expert_owner_user_id": expert.get("owner_user_id"),
            "expertId": expert["id"],
            "expertName": expert["name"],
            "topic": expert.get("service_name", "30分钟求职问题诊断"),
            "slot": request.slot,
            "desc": request.desc.strip(),
            "status": "平台匹配中" if expert.get("is_demo") else "待专家确认",
            "status_code": "intent_submitted",
            "payment_status": (
                "awaiting_expert_confirmation"
                if can_user_initiate_payment(request.user_id, "expert")
                else "not_charged_beta"
            ),
            "reference_price": expert.get("reference_price", 0),
            "job_id": bound_job.get("id") if bound_job else None,
            "job_label": f"{bound_job.get('company', '')} · {bound_job.get('title', '')}" if bound_job else None,
            "expert_briefing": (
                build_expert_briefing(user, bound_job, request.desc)
                if request.share_context_with_expert and bound_job else None
            ),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        state.setdefault("expert_bookings", []).insert(0, booking)
        user["bookings"] = [booking] + user.get("bookings", [])
        user["service_timeline"] = [
            {
                "id": f"timeline-{uuid.uuid4().hex[:10]}",
                "title": f"已预约 {expert['name']}",
                "desc": f"{request.slot} · 去准备你最想解决的问题",
                "status": "active",
            }
        ] + [
            {**item, "status": "done" if index == 0 else item.get("status", "pending")}
            for index, item in enumerate(user.get("service_timeline", []))
        ]
        user["service_timeline"] = user["service_timeline"][:4]
        append_product_event_to_state(state, "expert.booking.created", request.user_id, {"expert_id": expert["id"]})
        save_beta_state(state)
    return {"booking": booking, "bookings": user["bookings"], "service_timeline": user["service_timeline"]}

@app.get("/api/v1/bookings")
def list_user_bookings(user_id: str):
    state = load_beta_state()
    user = state.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"bookings": user.get("bookings", [])}

def update_user_booking_copy(state: Dict[str, Any], booking: Dict[str, Any]) -> None:
    user = state.get("users", {}).get(booking.get("user_id"))
    if not user:
        return
    copies = user.setdefault("bookings", [])
    index = next((i for i, item in enumerate(copies) if item.get("id") == booking.get("id")), None)
    if index is None:
        copies.insert(0, dict(booking))
    else:
        copies[index] = dict(booking)

@app.post("/api/v1/bookings/{booking_id}/cancel")
def cancel_expert_booking(booking_id: str, request: BookingCancelRequest):
    with _state_lock:
        state = load_beta_state()
        booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
        if not booking:
            raise HTTPException(status_code=404, detail="预约不存在")
        if booking.get("user_id") != request.user_id:
            raise HTTPException(status_code=403, detail="只能取消自己的预约")
        if booking.get("status_code") not in {"intent_submitted", "confirmed"}:
            raise HTTPException(status_code=409, detail="当前状态不能取消")
        if booking.get("payment_status") in {"unpaid", "paid", "refund_processing"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PAYMENT_SETTLEMENT_REQUIRED",
                    "message": "该预约仍有关联支付订单，请先关闭待支付订单或发起全额退款。",
                },
            )
        if booking.get("status_code") == "confirmed":
            expert = next((item for item in state.get("experts", []) if item.get("id") == booking.get("expertId")), None)
            if expert and booking.get("slot") and booking["slot"] not in expert.setdefault("slots", []):
                expert["slots"].append(booking["slot"])
        booking["status_code"] = "cancelled"
        booking["status"] = "已取消"
        booking["cancel_reason"] = request.reason.strip()
        booking["cancelled_at"] = now_iso()
        booking["updated_at"] = now_iso()
        booking["refund_status"] = "not_applicable_not_charged"
        update_user_booking_copy(state, booking)
        save_beta_state(state)
    return {"booking": booking, "message": "预约已取消；本次意向未扣款，因此无需退款。"}

@app.get("/api/v1/experts/bookings")
def get_expert_bookings(expert_user_id: str):
    state = load_beta_state()
    bookings = [
        item for item in state.get("expert_bookings", [])
        if item.get("expert_owner_user_id") == expert_user_id
    ]
    return {"bookings": bookings}

@app.post("/api/v1/experts/bookings/{booking_id}/decision")
def decide_expert_booking(booking_id: str, request: ExpertBookingDecisionRequest):
    decision = request.decision.strip().lower()
    if decision not in {"confirmed", "rejected"}:
        raise HTTPException(status_code=422, detail="decision 必须是 confirmed 或 rejected")
    with _state_lock:
        state = load_beta_state()
        booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
        if not booking:
            raise HTTPException(status_code=404, detail="预约不存在")
        if booking.get("expert_owner_user_id") != request.expert_user_id:
            raise HTTPException(status_code=403, detail="只能处理自己的预约")
        if booking.get("status_code") != "intent_submitted":
            raise HTTPException(status_code=409, detail="该预约已处理")
        booking["status_code"] = decision
        if decision == "confirmed" and booking.get("payment_status") == "awaiting_expert_confirmation":
            booking["payment_status"] = "payment_required"
        booking["status"] = (
            "待付款" if decision == "confirmed" and booking.get("payment_status") == "payment_required"
            else "待服务" if decision == "confirmed"
            else "专家未接单"
        )
        booking["expert_note"] = request.note.strip()
        booking["updated_at"] = now_iso()
        if decision == "confirmed":
            expert = next((item for item in state.get("experts", []) if item.get("id") == booking["expertId"]), None)
            if expert and booking["slot"] in expert.get("slots", []):
                expert["slots"].remove(booking["slot"])
        update_user_booking_copy(state, booking)
        save_beta_state(state)
    return {"booking": booking}

@app.post("/api/v1/experts/bookings/{booking_id}/complete")
def complete_expert_booking(booking_id: str, request: ExpertBookingCompleteRequest):
    next_actions = list(dict.fromkeys(
        str(item).strip()[:200] for item in request.next_actions if str(item).strip()
    ))[:5]
    if not next_actions:
        raise HTTPException(status_code=422, detail="请至少填写一条用户下一步行动")
    with _state_lock:
        state = load_beta_state()
        booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
        if not booking:
            raise HTTPException(status_code=404, detail="预约不存在")
        if booking.get("expert_owner_user_id") != request.expert_user_id:
            raise HTTPException(status_code=403, detail="只能完成自己的服务")
        if booking.get("status_code") != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认的预约可以完成")
        if booking.get("payment_status") in {"payment_required", "unpaid", "refund_processing", "refunded"}:
            raise HTTPException(status_code=409, detail="该预约尚未完成有效支付，不能标记为已交付")
        booking["status_code"] = "completed"
        booking["status"] = "待评价"
        booking["delivery_summary"] = request.delivery_summary.strip()
        booking["next_actions"] = next_actions
        booking["completed_at"] = now_iso()
        booking["updated_at"] = now_iso()
        update_user_booking_copy(state, booking)
        append_product_event_to_state(state, "expert.booking.completed", booking.get("user_id"), {"expert_id": booking.get("expertId")})
        save_beta_state(state)
    return {"booking": booking}

@app.post("/api/v1/bookings/{booking_id}/review")
def review_expert_booking(booking_id: str, request: ExpertBookingReviewRequest):
    with _state_lock:
        state = load_beta_state()
        booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
        if not booking:
            raise HTTPException(status_code=404, detail="预约不存在")
        if booking.get("user_id") != request.user_id:
            raise HTTPException(status_code=403, detail="只能评价自己的预约")
        if booking.get("status_code") != "completed":
            raise HTTPException(status_code=409, detail="服务完成后才能评价")
        if any(item.get("booking_id") == booking_id for item in state.get("expert_reviews", [])):
            raise HTTPException(status_code=409, detail="该服务已经评价")
        review = {
            "id": f"expert-review-{uuid.uuid4().hex[:12]}",
            "booking_id": booking_id,
            "expert_id": booking["expertId"],
            "user_id": request.user_id,
            "score": request.score,
            "comment": request.comment.strip(),
            "status": "published",
            "created_at": now_iso(),
        }
        state.setdefault("expert_reviews", []).append(review)
        booking["status"] = "已完成"
        booking["review_id"] = review["id"]
        update_user_booking_copy(state, booking)
        save_beta_state(state)
    return {"review": review, "booking": booking}

@app.get("/api/v1/community/posts")
def get_community_posts(user_id: Optional[str] = None):
    state = load_beta_state()
    visible = [
        post for post in state.get("community_posts", [])
        if post.get("moderation_status", "published") == "published" or post.get("created_by") == user_id
    ]
    return {"posts": [serialize_post(post, user_id) for post in visible]}

@app.post("/api/v1/community/posts")
def create_community_post(request: CommunityPostCreateRequest):
    post_type = request.post_type.strip().lower()
    if post_type not in {"treehole", "help", "share", "success"}:
        raise HTTPException(status_code=422, detail="不支持的帖子类型")
    with _state_lock:
        state = load_beta_state()
        user = community_user(state, request.user_id)
        bound_job = None
        if request.job_id:
            bound_job = next((item for item in user.get("jobs", []) if item.get("id") == request.job_id), None)
            if not bound_job:
                raise HTTPException(status_code=404, detail="要关联的岗位不存在")
        nickname = user.get("profile", {}).get("nickname") or "Pinco 用户"
        is_treehole = post_type == "treehole"
        post = {
            "id": f"post-{uuid.uuid4().hex[:12]}",
            "author": "匿名求职者" if is_treehole else nickname,
            "roleTag": "树洞" if is_treehole else "求职同行者",
            "created_at": now_iso(),
            "title": request.title.strip(),
            "content": request.content.strip(),
            "liked_by": [],
            "hugged_by": [],
            "postType": post_type,
            "comments": [],
            "created_by": request.user_id,
            "is_example": False,
            "moderation_status": "published",
            "job_id": bound_job.get("id") if bound_job else None,
            "job_label": f"{bound_job.get('company', '')} · {bound_job.get('title', '')}" if bound_job else None,
            "interview_round": request.interview_round.strip(),
            "experience_date": request.experience_date.strip(),
            "action_started_by": [],
            "is_featured": False,
        }
        state.setdefault("community_posts", []).insert(0, post)
        save_beta_state(state)
        serialized = serialize_post(post, request.user_id)
    return {"post": serialized}

@app.post("/api/v1/community/posts/{post_id}/report")
def report_community_post(post_id: str, request: CommunityReportRequest):
    with _state_lock:
        state = load_beta_state()
        community_user(state, request.user_id)
        target = next((post for post in state.get("community_posts", []) if post["id"] == post_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="帖子不存在")
        if target.get("is_example") or target.get("created_by") == request.user_id:
            raise HTTPException(status_code=409, detail="这条内容不能由当前用户举报")
        reports = state.setdefault("community_reports", [])
        existing = next(
            (item for item in reports if item.get("post_id") == post_id and item.get("user_id") == request.user_id),
            None,
        )
        if existing:
            raise HTTPException(status_code=409, detail="你已经举报过这条内容")
        report = {
            "id": f"community-report-{uuid.uuid4().hex[:12]}",
            "post_id": post_id,
            "user_id": request.user_id,
            "reason": request.reason.strip(),
            "status": "pending",
            "created_at": now_iso(),
        }
        reports.append(report)
        unique_reporters = {
            item.get("user_id") for item in reports
            if item.get("post_id") == post_id and item.get("status") == "pending"
        }
        if len(unique_reporters) >= 3:
            target["moderation_status"] = "pending_review"
        save_beta_state(state)
    return {"accepted": True, "pending_review": target.get("moderation_status") == "pending_review"}

@app.get("/api/v1/admin/community/reports")
def list_community_reports(x_pinco_admin_token: Optional[str] = Header(default=None)):
    require_admin_token(x_pinco_admin_token)
    state = load_beta_state()
    posts = {item.get("id"): item for item in state.get("community_posts", [])}
    reports = []
    for item in state.get("community_reports", []):
        report = deepcopy(item)
        post = posts.get(item.get("post_id"))
        if post:
            report["post"] = {
                "id": post.get("id"),
                "title": post.get("title", ""),
                "content": post.get("content", ""),
                "post_type": post.get("post_type", ""),
                "author_name": post.get("author_name", ""),
                "moderation_status": post.get("moderation_status", "published"),
                "is_featured": bool(post.get("is_featured")),
                "created_at": post.get("created_at"),
            }
        reports.append(report)
    return {"reports": reports}

@app.post("/api/v1/admin/community/posts/{post_id}/moderate")
def moderate_community_post(
    post_id: str,
    request: CommunityModerationRequest,
    x_pinco_admin_token: Optional[str] = Header(default=None),
):
    require_admin_token(x_pinco_admin_token)
    decision = request.decision.strip().lower()
    if decision not in {"published", "featured", "hidden"}:
        raise HTTPException(status_code=422, detail="decision 必须是 published、featured 或 hidden")
    with _state_lock:
        state = load_beta_state()
        target = next((post for post in state.get("community_posts", []) if post["id"] == post_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="帖子不存在")
        target["moderation_status"] = "published" if decision in {"published", "featured"} else "hidden"
        target["is_featured"] = decision == "featured"
        target["moderation_note"] = request.note.strip()
        target["moderated_at"] = now_iso()
        for report in state.get("community_reports", []):
            if report.get("post_id") == post_id and report.get("status") == "pending":
                report["status"] = "resolved"
                report["resolution"] = decision
        if decision == "featured" and not target.get("is_example"):
            award_contribution_points(
                state,
                target.get("created_by"),
                f"featured:{post_id}",
                20,
                "真实内容经人工审核选为精品",
                post_id,
            )
        save_beta_state(state)
    return {"post_id": post_id, "moderation_status": target["moderation_status"], "featured": bool(target.get("is_featured"))}


@app.post("/api/v1/community/posts/{post_id}/action")
def record_community_action(post_id: str, request: CommunityActionAttributionRequest):
    action = request.action.strip().lower()
    if action not in {"practice", "save_job", "update_progress"}:
        raise HTTPException(status_code=422, detail="不支持的学社行动类型")
    with _state_lock:
        state = load_beta_state()
        user = community_user(state, request.user_id)
        target = next((post for post in state.get("community_posts", []) if post.get("id") == post_id), None)
        if not target or target.get("moderation_status", "published") != "published":
            raise HTTPException(status_code=404, detail="帖子不存在或正在审核")
        bound_job = None
        if request.job_id:
            bound_job = next((item for item in user.get("jobs", []) if item.get("id") == request.job_id), None)
            if not bound_job:
                raise HTTPException(status_code=404, detail="要关联的岗位不存在")
        actors = target.setdefault("action_started_by", [])
        first_action = request.user_id not in actors
        if first_action:
            actors.append(request.user_id)
        append_product_event_to_state(state, "community.action_started", request.user_id, {
            "post_id": post_id,
            "post_type": target.get("postType"),
            "action": action,
            "job_id": bound_job.get("id") if bound_job else None,
            "source_author_user_id": target.get("created_by"),
        })
        point_entry = None
        if first_action and target.get("created_by") and target.get("created_by") != request.user_id:
            point_entry = award_contribution_points(
                state,
                target.get("created_by"),
                f"community-action:{post_id}:{request.user_id}",
                3,
                "真实帖子帮助另一位用户启动行动",
                post_id,
                source_user_id=request.user_id,
            )
        save_beta_state(state)
    return {"accepted": True, "first_action": first_action, "author_points_awarded": int((point_entry or {}).get("points", 0))}


@app.get("/api/v1/contributions/status")
def get_contribution_status(user_id: str):
    state = load_beta_state()
    return contribution_status(state, user_id)

@app.post("/api/v1/community/posts/{post_id}/like")
def toggle_community_like(post_id: str, request: CommunityActionRequest):
    with _state_lock:
        state = load_beta_state()
        community_user(state, request.user_id)
        target = next((post for post in state.get("community_posts", []) if post["id"] == post_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="帖子不存在")
        liked_by = target.setdefault("liked_by", [])
        if request.user_id in liked_by:
            liked_by.remove(request.user_id)
        else:
            liked_by.append(request.user_id)
        save_beta_state(state)
        serialized = serialize_post(target, request.user_id)
    return {"post": serialized}

@app.post("/api/v1/community/posts/{post_id}/hug")
def toggle_community_hug(post_id: str, request: CommunityActionRequest):
    with _state_lock:
        state = load_beta_state()
        community_user(state, request.user_id)
        target = next((post for post in state.get("community_posts", []) if post["id"] == post_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="帖子不存在")
        hugged_by = target.setdefault("hugged_by", [])
        if request.user_id in hugged_by:
            hugged_by.remove(request.user_id)
        else:
            hugged_by.append(request.user_id)
        save_beta_state(state)
        serialized = serialize_post(target, request.user_id)
    return {"post": serialized}

@app.post("/api/v1/community/posts/{post_id}/comments")
def create_community_comment(post_id: str, request: CommunityCommentCreateRequest):
    with _state_lock:
        state = load_beta_state()
        user = community_user(state, request.user_id)
        target = next((post for post in state.get("community_posts", []) if post["id"] == post_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="帖子不存在")
        comment = {
            "id": f"comment-{uuid.uuid4().hex[:12]}",
            "author": user.get("profile", {}).get("nickname") or "Pinco 用户",
            "text": request.text.strip(),
            "isAi": False,
            "created_at": now_iso(),
            "created_by": request.user_id,
        }
        target.setdefault("comments", []).append(comment)
        save_beta_state(state)
        serialized = serialize_post(target, request.user_id)
    return {"post": serialized}

@app.post("/api/v1/community/posts/{post_id}/summon")
def summon_community_reply(post_id: str, request: CommunityActionRequest):
    with _state_lock:
        state = load_beta_state()
        community_user(state, request.user_id)
        target = next((post for post in state.get("community_posts", []) if post["id"] == post_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="帖子不存在")
    try:
        reply = generate_community_reply(target["title"], target["content"])
    except Exception as e:
        print(f"Community Summon Error: {e}")
        raise llm_http_exception(e)
    comment = {
        "id": f"comment-{uuid.uuid4().hex[:10]}",
        "author": "Pinco 学姐",
        "text": reply,
        "isAi": True,
    }
    with _state_lock:
        state = load_beta_state()
        target = next((post for post in state.get("community_posts", []) if post["id"] == post_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="帖子不存在")
        target.setdefault("comments", []).append(comment)
        save_beta_state(state)
        serialized = serialize_post(target, request.user_id)
    return {"post": serialized}

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        user_snapshot = get_agent_user_context(request.user_id)
        latest_user_text = next((msg.content for msg in reversed(request.messages) if msg.role == "user"), "")
        # 以服务端持久化历史为主，不依赖当前页面是否还留着旧消息。
        conversation = [
            {"role": item.get("role"), "content": item.get("content", "")}
            for item in (user_snapshot.get("messages") or [])[-16:]
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        if latest_user_text and (
            not conversation
            or conversation[-1].get("role") != "user"
            or conversation[-1].get("content") != latest_user_text
        ):
            conversation.append({"role": "user", "content": latest_user_text})
        if not conversation:
            conversation = [
                {"role": "user" if msg.role == "user" else "assistant", "content": msg.content}
                for msg in request.messages[-16:]
            ]

        search_query = detect_search_intent(conversation)
        search_results = None
        query_analysis = None

        if search_query:
            try:
                result = await search_jobs(JobSearchRequest(query=search_query, limit=8, user_id=request.user_id))
                search_results = [job.model_dump() for job in result.jobs]
                query_analysis = result.query_analysis
            except Exception as e:
                print(f"[Chat] Auto search failed: {e}")

        system = PINCO_PERSONA
        if search_results:
            jobs_text = "\n".join([
                f"{i+1}. {job.get('title', '未知职位')} @ {job.get('company', '未知公司')} | {job.get('location', '')} | {job.get('salary', job.get('predicted_salary', ''))}\n   来源链接: {job.get('url', '无')}\n   核验说明: {job.get('verification_note', '请打开原页面确认仍在招聘')}"
                for i, job in enumerate(search_results[:5])
            ])
            # These are source-linked candidates, not proof that the opening is
            # still active. Keep that boundary visible to the model and user.
            if conversation and conversation[-1]["role"] == "user":
                original = conversation[-1]["content"]
                conversation[-1]["content"] = f"【用户请求】{original}\n\n【系统检索到的带来源岗位候选】\n{jobs_text}\n\n请基于候选给出匹配分析并附来源链接，同时明确提醒用户打开原页面确认仍在招聘。不得称为已核实在招或真实在招，也不得补写来源中没有的薪资、公司或职责。"
            else:
                system += f"\n\n【带来源岗位候选】以下结果只确认了来源和职位信号，不保证此刻仍在招聘：\n{jobs_text}\n\n请自然引用并分析匹配度，同时提醒用户打开原页面确认有效期；不得补写来源中没有的信息。"

        memory_context = build_agent_memory_context(user_snapshot)
        system = build_scenario_instruction(request.scenario) + "\n\n" + system + f"""

【Pinco 会话 Agent】
你需要在内部先判断用户意图、已知上下文和最合适的下一步，但不展示隐藏推理过程。
已知信息必须直接使用，不要再问用户已经提供的工作年限、目标岗位、城市或简历内容。
只有在以下真实节点成立时才可以询问是否记录进度：完成一版简历、完成模拟面试、用户在复盘一次真实面试、比较或决策 Offer。
普通问答、仅提到“面试”或已经提示过的同一节点，progress_suggestion 必须为 null。
只保存后续求职有用且用户明确说出的职业信息；不保存身份证、电话、住址、健康、家庭等敏感信息。
memory_updates 和 used_memory_keys 中的 key 必须严格使用以下英文值，不得翻译成中文：
{','.join(sorted(AGENT_MEMORY_KEYS))}
当用户明确说“请记住”并提供上述职业信息时，必须写入 memory_updates；口头说记住但不写入是不允许的。

【已持久化的用户上下文】
{memory_context}

只输出一个合法 JSON 对象，不要 markdown 代码块，结构为：
{{"response":"给用户看的完整回答","intent":"简短意图","next_action":"下一步","used_memory_keys":[],"memory_updates":[{{"key":"target_role","value":"AI产品经理","confidence":0.95}}],"progress_suggestion":null}}
若达到关键节点，progress_suggestion 可为：
{{"milestone":"resume_completed|mock_interview_completed|interview_feedback|offer_decision","company":"","position":"","status":"saved|applied|written|interview1|interview2|hr|offer|rejected|空字符串","prompt":"一句轻量确认"}}
"""
        raw_agent = llm_chat_with_fallback(conversation, system_prompt=system, max_tokens=2600)
        try:
            agent_result = sanitize_agent_result(json.loads(clean_json_response(raw_agent)))
        except Exception as parse_error:
            print(f"[Chat Agent] JSON repair triggered: {parse_error}")
            repair = llm_chat_with_fallback(
                [{"role": "user", "content": f"将下面内容修复为符合指定结构的合法 JSON，不要改写 response 的实质内容：\n{raw_agent}"}],
                temperature=0.1,
                system_prompt="你是 JSON 格式修复器。只输出 JSON 对象，必须包含 response、intent、next_action、used_memory_keys、memory_updates、progress_suggestion。",
                max_tokens=2600,
            )
            agent_result = sanitize_agent_result(json.loads(clean_json_response(repair)))
        if not agent_result["memory_updates"] and should_extract_agent_memory(latest_user_text):
            try:
                agent_result["memory_updates"] = extract_agent_memory_updates(latest_user_text)
            except Exception as memory_error:
                print(f"[Chat Agent] memory extraction skipped after provider error: {memory_error}")
        response_text = agent_result["response"]
        # If search results exist but LLM didn't reference them, force inject
        if search_results:
            has_reference = any(
                (job.get('company', '') and job.get('company', '') in response_text) or
                (job.get('title', '') and job.get('title', '') in response_text)
                for job in search_results
            )
            if not has_reference:
                jobs_text = "\n".join([
                    f"{i+1}. {job.get('title', '未知职位')} @ {job.get('company', '来源页内查看')} | {job.get('location', '')} | {job.get('salary') or '薪资见来源页'}\n   链接: {job.get('url')}"
                    for i, job in enumerate(search_results[:5])
                ])
                response_text = f"我检索到了以下带来源岗位候选，请先打开原页面确认仍在招聘：\n\n{jobs_text}\n\n下面再按现有信息分析匹配度；来源中没有的条件我不会补写。\n\n{response_text}"
        accepted_progress = persist_chat_turn(
            request.user_id,
            latest_user_text,
            response_text,
            memory_updates=agent_result["memory_updates"],
            progress_suggestion=agent_result["progress_suggestion"],
        )
        return ChatResponse(
            response=response_text,
            search_results=search_results,
            query_analysis=query_analysis,
            agent={
                "intent": agent_result["intent"],
                "next_action": agent_result["next_action"],
                "used_memory_keys": agent_result["used_memory_keys"],
                "memory_updated": bool(agent_result["memory_updates"]),
            },
            progress_suggestion=accepted_progress,
        )

    except Exception as e:
        print(f"LLM Chat Error: {e}")
        raise llm_http_exception(e)


@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat response via SSE."""
    async def event_generator():
        conversation = []
        for msg in request.messages:
            prefix = "user" if msg.role == "user" else "assistant"
            conversation.append({"role": prefix, "content": msg.content})

        # Detect search intent and execute search before streaming
        search_query = detect_search_intent(conversation)
        search_results = None
        if search_query:
            try:
                result = await search_jobs(JobSearchRequest(query=search_query, limit=8, user_id=request.user_id))
                search_results = [job.model_dump() for job in result.jobs]
            except Exception as e:
                print(f"[Chat Stream] Auto search failed: {e}")

        # Choose system prompt based on mode and content type
        content_type = detect_content_type(conversation)
        if request.interview_mode:
            system = INTERVIEWER_PERSONA
            if request.interview_position:
                system += f"\n\n【目标岗位】{request.interview_position}\n请围绕该岗位设计面试问题。"
        elif content_type == "resume":
            system = RESUME_ANALYSIS_PERSONA
        elif content_type == "jd":
            system = JD_ANALYSIS_PERSONA
        else:
            system = PINCO_PERSONA

        # Inject search results into user message for better LLM awareness
        if search_results:
            jobs_text = "\n".join([
                f"{i+1}. {job.get('title', '未知职位')} @ {job.get('company', '未知公司')} | {job.get('location', '')} | {job.get('salary', job.get('predicted_salary', ''))}\n   链接: {job.get('url', '无')}"
                for i, job in enumerate(search_results[:5])
            ])
            if conversation and conversation[-1]["role"] == "user":
                original = conversation[-1]["content"]
                conversation[-1]["content"] = f"【用户请求】{original}\n\n【系统已自动搜索到的真实岗位信息】\n{jobs_text}\n\n请直接基于以上搜索结果回答用户，展示具体岗位名称、公司、薪资和链接，并给出匹配度分析。禁止说\"无法搜索\"或\"没法联网\"。"
            else:
                system += f"\n\n【实时搜索结果】用户正在找工作，以下是我刚搜到的真实岗位（来自各大公司官网）：\n{jobs_text}\n\n请在回复中自然引用这些岗位信息，帮用户分析匹配度，并给出投递建议。"

        try:
            async for chunk in llm_chat_stream_with_fallback(conversation, system_prompt=system):
                # SSE format: data: <json>\n\n
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            if search_results:
                yield f"data: {json.dumps({'search_results': search_results}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as error:
            if is_rate_limit_error(error):
                status_code = 429
                error_code = "LLM_RATE_LIMITED"
                message = "模型服务额度已用完或被限流，请稍后重试或更换可用 API Key。"
            elif is_auth_error(error):
                status_code = 401
                error_code = "LLM_AUTH_FAILED"
                message = "模型服务 API Key 无效或已过期，请更换可用 Key 后重试。"
            else:
                status_code = 502
                error_code = "LLM_UPSTREAM_ERROR"
                message = "模型上游服务暂时不可用，请检查模型服务配置。"
            payload = {
                "error": {
                    "code": error_code,
                    "message": message,
                    "statusCode": status_code,
                    "provider": LLM_PROVIDER,
                    "model": DEFAULT_MODEL,
                }
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/llm", response_model=ChatResponse)
async def generic_llm(request: GenericLLMRequest):
    try:
        conversation = []
        for msg in request.messages:
            conversation.append({
                "role": "user" if msg.role == "user" else "assistant",
                "content": msg.content,
            })

        response_text = llm_chat_with_fallback(
            conversation,
            temperature=request.temperature,
            system_prompt=request.system,
            max_tokens=request.max_tokens,
        )
        return ChatResponse(response=response_text)
    except Exception as e:
        print(f"Generic LLM Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def get_uploaded_file(request: Request):
    import base64
    content_type = request.headers.get("content-type", "")

    if content_type and "application/json" in content_type.lower():
        body = await request.json()
        if body and "content" in body:
            filename = body.get("filename", "uploaded_file")
            try:
                content = base64.b64decode(body["content"], validate=True)
            except Exception:
                raise HTTPException(status_code=400, detail="文件内容不是有效的 Base64 数据")
            if len(content) > 4 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="文件不能超过 4MB")
            metadata = {key: value for key, value in body.items() if key not in {"content", "filename"}}
            return filename, content, metadata

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="未找到文件")
    content = await file.read()
    if len(content) > 4 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 4MB")
    metadata = {
        key: value for key, value in form.items()
        if key != "file" and isinstance(value, str)
    }
    return file.filename, content, metadata

def extract_text_from_resume(filename: str, content: bytes) -> str:
    """Extract text from the file formats exposed by the mini-program picker."""
    suffix = os.path.splitext(filename)[1].lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(content)
    if suffix == ".docx":
        from io import BytesIO
        from docx import Document
        document = Document(BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
    raise HTTPException(status_code=400, detail="仅支持 PDF 或 DOCX 格式")

@app.post("/api/v1/resume/upload", response_model=ResumeAnalysisResponse)
async def upload_resume(request: Request):
    filename, content, metadata = await get_uploaded_file(request)
    text = extract_text_from_resume(filename, content)

    if not text or len(text) < 50:
        raise HTTPException(status_code=400, detail="简历文本太短或无法读取，请确认是文本型 PDF。")

    user_id = str(metadata.get("user_id") or "").strip()
    if user_id:
        supplied = request.headers.get("x-pinco-session", "")
        if not user_session_is_valid(user_id, supplied):
            raise HTTPException(status_code=401, detail={"code": "SESSION_REQUIRED", "message": "用户会话已过期，请重新进入小程序"})
        with _state_lock:
            state = load_beta_state()
            enforce_membership_quota(state, user_id, "resume_used")
            save_beta_state(state)

    try:
        prompt = f"{RESUME_ANALYSIS_PROMPT}\n{text[:3000]}"
        messages = [{"role": "system", "content": "你是一位资深 HR 和简历优化专家。"}, {"role": "user", "content": prompt}]
        response_text = llm_chat_with_fallback(messages, temperature=0.3)

        raw_text = clean_json_response(response_text)
        data = json.loads(raw_text)

        metrics_data = data.get("metrics", {})
        required_text = [data.get("summary")]
        required_lists = [data.get("strengths"), data.get("weaknesses"), data.get("suggestions")]
        required_metric_keys = {"completeness", "matching", "quantification", "keyword"}
        if (
            not all(isinstance(item, str) and item.strip() for item in required_text)
            or not all(isinstance(item, list) and item for item in required_lists)
            or not isinstance(data.get("score"), (int, float))
            or not required_metric_keys.issubset(metrics_data)
        ):
            raise RuntimeError("INVALID_RESUME_ANALYSIS")

        result = ResumeAnalysisResponse(
            filename=filename,
            score=max(0, min(100, int(data["score"]))),
            summary=data["summary"],
            metrics=ResumeMetrics(
                completeness=max(0, min(100, int(metrics_data["completeness"]))),
                matching=max(0, min(100, int(metrics_data["matching"]))),
                quantification=max(0, min(100, int(metrics_data["quantification"]))),
                keyword=max(0, min(100, int(metrics_data["keyword"]))),
            ),
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            suggestions=data["suggestions"]
        )
        if user_id:
            with _state_lock:
                state = load_beta_state()
                user = state.get("users", {}).get(user_id)
                if user:
                    artifact = result.model_dump()
                    artifact.update({"id": f"resume-analysis-{uuid.uuid4().hex[:12]}", "created_at": now_iso()})
                    analyses = user.setdefault("resume_analyses", [])
                    analyses.insert(0, artifact)
                    user["resume_analyses"] = analyses[:20]
                    # 简历由用户主动上传，保留最新一份的有界上下文，用于后续新会话。
                    # 它属于用户账号数据，随账号删除，不写入分析日志。
                    user["resume_memory"] = {
                        "filename": filename,
                        "analysis_summary": result.summary,
                        "text_excerpt": text[:8000],
                        "updated_at": now_iso(),
                    }
                record_membership_usage(state, user_id, "resume_used")
                save_beta_state(state)
        return result

    except Exception as e:
        print(f"Analysis Error: {e}")
        raise llm_http_exception(e)

@app.post("/api/v1/image/upload")
async def upload_image(request: Request):
    """Validate a real image upload without pretending it was stored or understood."""
    try:
        filename, content, _ = await get_uploaded_file(request)
        # 验证图片格式
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        if not filename.lower().endswith(image_extensions):
            raise HTTPException(status_code=400, detail="仅支持图片格式")

        signatures = (
            content.startswith(b"\xff\xd8\xff"),
            content.startswith(b"\x89PNG\r\n\x1a\n"),
            content.startswith((b"GIF87a", b"GIF89a")),
            content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        )
        if not any(signatures):
            raise HTTPException(status_code=400, detail="图片内容与扩展名不匹配或文件已损坏")
        upload_id = f"image-{hashlib.sha256(content).hexdigest()[:16]}"

        return {
            "upload_id": upload_id,
            "filename": filename,
            "size": len(content),
            "uploaded_at": int(time.time()),
            "stored": False,
            "analysis_available": False,
            "message": "图片已通过完整性校验；当前模型不支持读取画面，图片只在本次微信页面本地预览。",
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Image Upload] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/jd/analyze", response_model=JDAnalyzeResponse)
async def analyze_jd(request: JDAnalyzeRequest):
    try:
        prompt = f"{JD_ANALYSIS_PROMPT}\n{request.jd_text[:3000]}"
        if request.target_position:
            prompt += f"\n\n候选人目标岗位：{request.target_position}"

        messages = [{"role": "system", "content": "你是一位资深猎头 + 大厂 HR。"}, {"role": "user", "content": prompt}]
        response_text = llm_chat_with_fallback(messages, temperature=0.3)

        raw_text = clean_json_response(response_text)
        data = json.loads(raw_text)
        required_lists = ["core_requirements", "hidden_requirements", "interview_focus", "salary_negotiation_tips"]
        if not isinstance(data.get("summary"), str) or not data["summary"].strip() or not all(
            isinstance(data.get(key), list) and data[key] for key in required_lists
        ):
            raise RuntimeError("INVALID_JD_ANALYSIS")

        return JDAnalyzeResponse(
            summary=data["summary"],
            core_requirements=data["core_requirements"],
            hidden_requirements=data["hidden_requirements"],
            interview_focus=data["interview_focus"],
            salary_negotiation_tips=data["salary_negotiation_tips"]
        )
    except Exception as e:
        print(f"JD Analysis Error: {e}")
        raise llm_http_exception(e)

@app.post("/api/v1/interview/start", response_model=InterviewStartResponse)
async def start_interview(request: InterviewStartRequest):
    try:
        focus = ", ".join(request.focus_areas) if request.focus_areas else "通用考察"
        resume_summary = request.resume_summary or "未提供简历摘要"

        prompt = INTERVIEW_START_PROMPT.format(
            position=request.position,
            resume_summary=resume_summary,
            focus_areas=focus
        )

        messages = [{"role": "system", "content": "你是一位经验丰富的大厂面试官。"}, {"role": "user", "content": prompt}]
        response_text = llm_chat_with_fallback(messages, temperature=0.7)

        raw_text = clean_json_response(response_text)
        data = json.loads(raw_text)
        if (
            not isinstance(data.get("first_question"), str)
            or not data["first_question"].strip()
            or not isinstance(data.get("interview_context"), str)
            or not data["interview_context"].strip()
            or not isinstance(data.get("suggested_focus"), list)
            or not data["suggested_focus"]
        ):
            raise RuntimeError("INVALID_INTERVIEW_START")

        return InterviewStartResponse(
            first_question=data["first_question"],
            interview_context=data["interview_context"],
            suggested_focus=data["suggested_focus"]
        )
    except Exception as e:
        print(f"Interview Start Error: {e}")
        raise llm_http_exception(e)

INTERVIEW_DURATION_QUESTIONS = {5: 3, 10: 3, 20: 5, 30: 8}

def interview_practice_mode(duration: int) -> str:
    return {
        5: "快速诊断",
        10: "弱项复练",
        20: "项目深挖",
        30: "全真模拟",
    }[duration]

def _practice_session_for_user(state: Dict[str, Any], user_id: str, session_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    user = state.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在，请重新进入小程序")
    session = next((item for item in user.get("interview_sessions", []) if item.get("id") == session_id), None)
    if not session:
        raise HTTPException(status_code=404, detail="练习不存在或已过期")
    return user, session

@app.post("/api/v1/interview/practice/start")
async def start_interview_practice(request: InterviewPracticeStartRequest):
    duration = request.duration_minutes
    if duration not in INTERVIEW_DURATION_QUESTIONS:
        raise HTTPException(status_code=400, detail="练习时长只支持 5、10、20、30 分钟")
    practice_styles = {
        "warmup": "陪我热身：先降低启动压力，问题由浅入深，不降低事实标准",
        "real": "真实强度：按目标轮次自然追问，不额外放水或施压",
        "pressure": "压力追问：更直接追问证据、边界和取舍，但不羞辱用户",
    }
    if request.practice_style not in practice_styles:
        raise HTTPException(status_code=400, detail="练习强度只支持 warmup、real、pressure")
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在，请重新进入小程序")
        enforce_membership_quota(state, request.user_id, "interview_used")
        bound_job = None
        if request.job_id:
            bound_job = next((item for item in user.get("jobs", []) if item.get("id") == request.job_id), None)
            if not bound_job:
                raise HTTPException(status_code=404, detail="要关联的岗位不存在")
        source_post = None
        if request.source_post_id:
            source_post = next(
                (
                    item for item in state.get("community_posts", [])
                    if item.get("id") == request.source_post_id and item.get("moderation_status", "published") == "published"
                ),
                None,
            )
            if not source_post:
                raise HTTPException(status_code=404, detail="练习来源帖子不存在或正在审核")
    effective_position = str((bound_job or {}).get("title") or request.position).strip()
    if not effective_position:
        raise HTTPException(status_code=400, detail="请填写目标岗位")
    total_questions = INTERVIEW_DURATION_QUESTIONS[duration]
    mode = interview_practice_mode(duration)
    effective_company = request.company.strip() or str((bound_job or {}).get("company") or "")
    effective_jd = request.jd_text or str((bound_job or {}).get("jd_text") or "")
    source_post_text = ""
    if source_post:
        source_post_text = (
            f"标题：{source_post.get('title', '')}\n"
            f"轮次/场景：{source_post.get('interview_round') or '未标注'}\n"
            f"发生时间：{source_post.get('experience_date') or '未标注'}\n"
            f"内容：{source_post.get('content', '')}"
        )[:1800]
    source_labels = []
    if effective_jd:
        source_labels.append("用户提供的 JD")
    if request.resume_summary:
        source_labels.append("用户提供的简历摘要")
    if request.focus_areas:
        source_labels.append("用户选择的练习重点")
    if bound_job:
        source_labels.append(f"岗位工作区：{bound_job.get('company', '')} · {bound_job.get('title', '')}")
    if source_post:
        source_labels.append(f"学社真实内容：{source_post.get('title', '')}")
    if not source_labels:
        source_labels.append("目标岗位通用能力（未提供 JD/简历）")
    taxonomy_focus = role_interview_focus(effective_position)
    prompt = f"""为一名 0-5 年经验的中文求职者设计面试前练习计划。
目标岗位：{effective_position}
目标公司：{effective_company or '未提供'}
面试轮次：{request.interview_round.strip() or '未提供'}
面试日期：{request.interview_date.strip() or '未提供'}
用户最焦虑的点：{request.anxiety_focus.strip() or '未提供'}
练习强度：{practice_styles[request.practice_style]}
练习模式：{mode}
练习时长：{duration} 分钟
题目数：{total_questions}
简历摘要：{(request.resume_summary or '未提供')[:1200]}
JD：{(effective_jd or '未提供')[:1600]}
学社练习来源：{source_post_text or '未提供'}
重点：{', '.join(request.focus_areas or taxonomy_focus) or '岗位匹配、表达结构、案例证据'}

只输出合法 JSON：
{{"plan_summary":"本轮练习重点","questions":["问题1"],"focus":["评分重点1","评分重点2"]}}
questions 必须刚好 {total_questions} 题，从最影响临场表现的问题开始；不要输出答案。
5 分钟覆盖自我介绍、动机、项目概述；10 分钟围绕一个弱项递进复练；20 分钟追问业务、技术、数据、ROI 与复盘；30 分钟按真实轮次完整模拟。"""
    try:
        raw = llm_chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
            system_prompt="你是 Pinco 面试教练。只设计真实模型生成的练习，不使用固定题库冒充个性化结果。",
            max_tokens=1400,
        )
        data = json.loads(clean_json_response(raw))
        questions = [str(item).strip() for item in data.get("questions", []) if str(item).strip()]
        if len(questions) != total_questions:
            raise RuntimeError("INVALID_INTERVIEW_PLAN")
    except Exception as error:
        print(f"Interview Practice Start Error: {error}")
        raise llm_http_exception(error)

    session = {
        "id": f"practice-{uuid.uuid4().hex[:12]}",
        "position": effective_position,
        "company": effective_company,
        "interview_round": request.interview_round.strip(),
        "interview_date": request.interview_date.strip(),
        "anxiety_focus": request.anxiety_focus.strip(),
        "practice_style": request.practice_style,
        "question_sources": source_labels,
        "job_id": bound_job.get("id") if bound_job else None,
        "source_post_id": source_post.get("id") if source_post else None,
        "duration_minutes": duration,
        "mode": mode,
        "total_questions": total_questions,
        "questions": questions,
        "focus": data.get("focus", []),
        "plan_summary": data.get("plan_summary", ""),
        "current_index": 0,
        "answers": [],
        "status": "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在，请重新进入小程序")
        sessions = user.setdefault("interview_sessions", [])
        sessions.insert(0, session)
        user["interview_sessions"] = sessions[:50]
        record_membership_usage(state, request.user_id, "interview_used")
        append_product_event_to_state(state, "interview.practice.started", request.user_id, {
            "duration_minutes": duration,
            "mode": mode,
            "practice_style": request.practice_style,
            "job_id": session.get("job_id"),
            "source_post_id": session.get("source_post_id"),
        })
        save_beta_state(state)
    return {
        "session_id": session["id"],
        "position": session["position"],
        "mode": session["mode"],
        "practice_style": session["practice_style"],
        "job_id": session.get("job_id"),
        "source_post_id": session.get("source_post_id"),
        "duration_minutes": duration,
        "total_questions": total_questions,
        "question_index": 1,
        "question": questions[0],
        "plan_summary": session["plan_summary"],
        "focus": session["focus"],
    }

@app.post("/api/v1/interview/practice/{session_id}/rescue")
def rescue_interview_practice(session_id: str, request: InterviewPracticeRescueRequest):
    """Give a bounded thinking scaffold without consuming the current question."""
    with _state_lock:
        state = load_beta_state()
        _, session = _practice_session_for_user(state, request.user_id, session_id)
        if session.get("status") != "active":
            raise HTTPException(status_code=409, detail="这轮练习已经结束")
        current_index = int(session.get("current_index", 0))
        question = str(session["questions"][current_index])
        position = str(session.get("position") or "")
    prompt = f"""用户正在进行 {position} 面试练习，卡在这道题：
{question}

只输出合法 JSON：
{{"framework":"不超过120字的三步回答骨架","first_prompt":"一个帮助用户想起真实经历的短问题"}}
只提供思考结构和回忆提示，不替用户编答案、经历或指标。"""
    try:
        raw = llm_chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            system_prompt="你是温暖但严格的面试教练。救场不代答，也不推进题目。",
            max_tokens=300,
        )
        data = json.loads(clean_json_response(raw))
        framework = str(data.get("framework") or "").strip()
        first_prompt = str(data.get("first_prompt") or "").strip()
        if not framework or not first_prompt:
            raise RuntimeError("INVALID_INTERVIEW_RESCUE")
    except Exception as error:
        print(f"Interview Practice Rescue Error: {error}")
        raise llm_http_exception(error)
    with _state_lock:
        state = load_beta_state()
        _, session = _practice_session_for_user(state, request.user_id, session_id)
        session.setdefault("rescue_uses", []).append({
            "question_index": current_index + 1,
            "created_at": now_iso(),
        })
        append_product_event_to_state(state, "interview.practice.rescue_used", request.user_id, {
            "session_id": session_id,
            "question_index": current_index + 1,
        })
        save_beta_state(state)
    return {
        "question_index": current_index + 1,
        "framework": framework,
        "first_prompt": first_prompt,
        "question_advanced": False,
    }

@app.post("/api/v1/interview/practice/{session_id}/answer")
async def answer_interview_practice(session_id: str, request: InterviewPracticeAnswerRequest):
    answer = request.answer.strip()
    if len(answer) < 5:
        raise HTTPException(status_code=400, detail="回答太短，请至少说清一个具体观点或例子")
    with _state_lock:
        state = load_beta_state()
        _, session = _practice_session_for_user(state, request.user_id, session_id)
        if session.get("status") != "active":
            raise HTTPException(status_code=409, detail="这轮练习已经结束")
        current_index = int(session.get("current_index", 0))
        question = session["questions"][current_index]
        prior_answers = list(session.get("answers", []))
        is_final = current_index + 1 >= session["total_questions"]

    transcript = "\n".join(
        f"Q{i + 1}: {item['question']}\nA{i + 1}: {item['answer']}\n反馈: {item.get('feedback', '')}"
        for i, item in enumerate(prior_answers)
    )
    weak_retry_instruction = ""
    if session.get("mode") == "弱项复练" and not is_final:
        weak_retry_instruction = "follow_up 必须要求用户围绕当前同一问题重新回答，只聚焦本次最弱的一项；不要换成无关的新题。"
    prompt = f"""你是 Pinco 中文面试教练。评价当前回答，并保持温暖、具体、不打击用户。
岗位：{session['position']}
第 {current_index + 1}/{session['total_questions']} 题：{question}
用户回答：{answer[:4000]}
此前记录：{transcript[-5000:] or '无'}

只输出合法 JSON：
{{
  "feedback":"先肯定有效部分，再指出一个最关键缺口",
  "scores":{{"content":0,"structure":0,"evidence":0,"role_fit":0,"clarity":0,"adaptability":0}},
  "better_answer":"给出保留用户事实边界的改写框架，不虚构经历",
  "follow_up":"{'' if is_final else '结合这次回答对下一题做一句自适应追问'}"{', "report":{"overall_score":0,"dimension_scores":{"content":0,"structure":0,"evidence":0,"role_fit":0,"clarity":0,"adaptability":0},"strengths":[""],"improvements":[""],"next_drill":""}' if is_final else ''}
}}
六项分数均为 0-100。{'report 必须总结整轮进步方向，并给出六维汇总。' if is_final else 'follow_up 不得为空。'}
{weak_retry_instruction}"""
    try:
        raw = llm_chat_with_fallback(
            [{"role": "user", "content": prompt}],
            temperature=0.35,
            system_prompt="你只依据用户真实回答评分；信息不足要指出，不得编造候选人经历。",
            max_tokens=1800,
        )
        evaluation = json.loads(clean_json_response(raw))
        required_score_keys = {"content", "structure", "evidence", "role_fit", "clarity", "adaptability"}
        scores = evaluation.get("scores")
        if (
            not evaluation.get("feedback")
            or not isinstance(scores, dict)
            or not required_score_keys.issubset(scores)
            or any(not isinstance(scores[key], (int, float)) or scores[key] < 0 or scores[key] > 100 for key in required_score_keys)
        ):
            raise RuntimeError("INVALID_INTERVIEW_EVALUATION")
        if is_final and (
            not isinstance(evaluation.get("report"), dict)
            or not required_score_keys.issubset((evaluation["report"].get("dimension_scores") or {}))
        ):
            raise RuntimeError("INVALID_INTERVIEW_REPORT")
    except Exception as error:
        print(f"Interview Practice Answer Error: {error}")
        raise llm_http_exception(error)

    answer_record = {
        "question": question,
        "answer": answer,
        "feedback": evaluation["feedback"],
        "scores": evaluation["scores"],
        "better_answer": evaluation.get("better_answer", ""),
        "created_at": now_iso(),
    }
    comparison = None
    if prior_answers:
        previous_scores = prior_answers[-1].get("scores") or {}
        current_scores = answer_record["scores"]
        dimension_delta = {
            key: round(float(current_scores[key]) - float(previous_scores.get(key, current_scores[key])), 1)
            for key in required_score_keys
        }
        previous_average = round(sum(float(previous_scores.get(key, 0)) for key in required_score_keys) / len(required_score_keys), 1)
        current_average = round(sum(float(current_scores[key]) for key in required_score_keys) / len(required_score_keys), 1)
        comparison = {
            "previous_average": previous_average,
            "current_average": current_average,
            "average_delta": round(current_average - previous_average, 1),
            "dimension_delta": dimension_delta,
            "basis": "同一练习中相邻两次真实回答的模型六维评分",
        }
        answer_record["comparison"] = comparison
    with _state_lock:
        state = load_beta_state()
        _, session = _practice_session_for_user(state, request.user_id, session_id)
        session.setdefault("answers", []).append(answer_record)
        session["updated_at"] = now_iso()
        if is_final:
            session["status"] = "completed"
            session["report"] = evaluation["report"]
            if session.get("mode") == "弱项复练" and session.get("answers"):
                first_scores = session["answers"][0].get("scores") or {}
                latest_scores = answer_record["scores"]
                first_average = round(sum(float(first_scores.get(key, 0)) for key in required_score_keys) / len(required_score_keys), 1)
                latest_average = round(sum(float(latest_scores.get(key, 0)) for key in required_score_keys) / len(required_score_keys), 1)
                retry_comparison = {
                    "first_average": first_average,
                    "latest_average": latest_average,
                    "average_delta": round(latest_average - first_average, 1),
                    "dimension_delta": {
                        key: round(float(latest_scores.get(key, 0)) - float(first_scores.get(key, 0)), 1)
                        for key in required_score_keys
                    },
                    "basis": "本轮第一次与最后一次真实回答的模型六维评分",
                }
                session["retry_comparison"] = retry_comparison
                session["report"]["retry_comparison"] = retry_comparison
            append_product_event_to_state(state, "interview.practice.completed", request.user_id, {
                "duration_minutes": session.get("duration_minutes"),
                "mode": session.get("mode"),
                "score": evaluation["report"].get("overall_score"),
            })
            next_question = None
        else:
            session["current_index"] = current_index + 1
            adaptive = str(evaluation.get("follow_up") or "").strip()
            if adaptive:
                session["questions"][current_index + 1] = adaptive
            next_question = session["questions"][current_index + 1]
        save_beta_state(state)
    return {
        "completed": is_final,
        "question_index": current_index + 1,
        "feedback": answer_record["feedback"],
        "scores": answer_record["scores"],
        "better_answer": answer_record["better_answer"],
        "comparison": comparison,
        "next_question": next_question,
        "report": evaluation.get("report") if is_final else None,
    }

@app.post("/api/v1/interview/practice/{session_id}/publish")
def publish_interview_practice_report(session_id: str, request: InterviewReportPublishRequest):
    """Publish only the structured learning summary; raw answers remain private."""
    with _state_lock:
        state = load_beta_state()
        user, session = _practice_session_for_user(state, request.user_id, session_id)
        if session.get("status") != "completed" or not session.get("report"):
            raise HTTPException(status_code=409, detail="练习完成并生成报告后才能发布复盘")
        existing_id = session.get("community_post_id")
        if existing_id:
            existing = next((item for item in state.get("community_posts", []) if item.get("id") == existing_id), None)
            if existing:
                return {"post": serialize_post(existing, request.user_id), "created": False}
        report = session["report"]
        dimensions = report.get("dimension_scores") or {}
        dimension_text = " · ".join(f"{key} {value}" for key, value in dimensions.items())
        content = "\n".join(filter(None, [
            f"练习模式：{session.get('mode', '')}（{session.get('duration_minutes', '')}分钟）",
            f"六维记录：{dimension_text}" if dimension_text else "",
            f"做得好的：{'、'.join(str(item) for item in report.get('strengths', []) if str(item).strip())}",
            f"优先改进：{'、'.join(str(item) for item in report.get('improvements', []) if str(item).strip())}",
            f"下一次练习：{report.get('next_drill', '')}",
            "说明：这是一次练习复盘，不代表真实录用结果；原始回答未公开。",
        ]))[:1000]
        post = {
            "id": f"post-{uuid.uuid4().hex[:12]}",
            "author": "匿名求职者",
            "roleTag": "匿名练习复盘",
            "created_at": now_iso(),
            "title": f"{session.get('position', 'AI 求职')} · 一次真实练习复盘"[:100],
            "content": content,
            "liked_by": [],
            "hugged_by": [],
            "postType": "share",
            "comments": [],
            "created_by": request.user_id,
            "is_example": False,
            "moderation_status": "published",
            "job_id": session.get("job_id"),
            "job_label": (
                f"{session.get('company', '')} · {session.get('position', '')}".strip(" ·")
                if session.get("job_id") else None
            ),
            "interview_round": session.get("interview_round", ""),
            "experience_date": session.get("interview_date", ""),
            "source_interview_session_id": session_id,
            "action_started_by": [],
            "is_featured": False,
        }
        state.setdefault("community_posts", []).insert(0, post)
        session["community_post_id"] = post["id"]
        session["report_published_at"] = now_iso()
        append_product_event_to_state(state, "interview.report.published", request.user_id, {
            "session_id": session_id,
            "job_id": session.get("job_id"),
        })
        save_beta_state(state)
    return {"post": serialize_post(post, request.user_id), "created": True}

@app.get("/api/v1/interview/practice/history")
def get_interview_practice_history(user_id: str):
    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        sessions = list(user.get("interview_sessions", []))
    return {"sessions": sessions[:20]}

PLATFORM_SITE_MAP = {
    "maimai": {"site": "site:maimai.cn", "label": "脉脉"},
    "liepin": {"site": "site:liepin.com", "label": "猎聘"},
    "jike": {"site": "site:okjk.co OR site:jike.city", "label": "即刻"},
}

def _parse_platforms(platforms_str: Optional[str]) -> List[str]:
    if not platforms_str:
        return []
    parts = [p.strip().lower() for p in platforms_str.split(",") if p.strip()]
    return [p for p in parts if p in PLATFORM_SITE_MAP] or []

def _build_platform_query(query: str, city: Optional[str], platform_key: str) -> str:
    site_part = PLATFORM_SITE_MAP[platform_key]["site"]
    base = f"{site_part} {query}"
    if city:
        base = f"{base} {city}"
    base = f"{base} 招聘"
    return base

COMPANY_SITE_MAP = {
    "bytedance": "字节跳动", "tencent": "腾讯", "meituan": "美团",
    "xiaohongshu": "小红书", "baidu": "百度", "jd": "京东",
    "kuaishou": "快手", "didi": "滴滴", "xiaomi": "小米",
    "bilibili": "哔哩哔哩", "netease": "网易", "ctrip": "携程",
    "huawei": "华为", "dji": "大疆", "ant": "蚂蚁集团",
    "mihoyo": "米哈游", "minimax": "MiniMax", "moonshot": "月之暗面",
    "zhipu": "智谱AI", "alibaba-intl": "阿里国际", "aliyun": "阿里云",
    "tongyi": "通义实验室", "taotian": "淘天集团", "dingtalk": "钉钉",
    "amap": "高德", "cainiao": "菜鸟", "dewu": "得物",
}

def _jsearch_api_search(query: str, city: Optional[str], limit: int = 10) -> List[JobResult]:
    if not JSEARCH_API_KEY:
        return []
    import urllib.request
    import urllib.parse

    def _do_jsearch(search_query: str) -> List[dict]:
        params = urllib.parse.urlencode({
            "query": search_query,
            "page": "1",
            "num_pages": "1",
            "date_posted": "month",
        })
        url = f"{JSEARCH_BASE_URL}/search?{params}"
        req = urllib.request.Request(url, headers={
            "X-RapidAPI-Key": JSEARCH_API_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") != "OK" or not data.get("data"):
            return []
        return data["data"]

    try:
        city_en_map = {
            "北京": "Beijing", "上海": "Shanghai", "广州": "Guangzhou",
            "深圳": "Shenzhen", "杭州": "Hangzhou", "成都": "Chengdu",
            "武汉": "Wuhan", "西安": "Xi'an", "南京": "Nanjing",
            "苏州": "Suzhou", "长沙": "Changsha", "重庆": "Chongqing",
            "厦门": "Xiamen", "青岛": "Qingdao", "大连": "Dalian",
            "天津": "Tianjin", "合肥": "Hefei", "郑州": "Zhengzhou",
        }
        cn_keywords_map = {
            "产品经理": "product manager", "前端开发": "frontend developer",
            "后端开发": "backend developer", "算法工程师": "algorithm engineer",
            "数据分析师": "data analyst", "运营": "operations",
            "设计师": "designer", "测试工程师": "QA engineer",
            "Java开发": "Java developer", "Python开发": "Python developer",
            "AI产品": "AI product manager", "大模型": "LLM engineer",
        }
        query_en = translate_job_query(query)
        if query_en == query:
            query_en = cn_keywords_map.get(query, query)
        location_str = ""
        if city:
            location_str = city_en_map.get(city, city) + ", China"
        search_query = f"{query} in {location_str}" if location_str else f"{query} in China"
        raw_data = _do_jsearch(search_query)
        if not raw_data and query_en != query:
            search_query2 = f"{query_en} in {location_str}" if location_str else f"{query_en} in China"
            raw_data = _do_jsearch(search_query2)
        if not raw_data:
            search_query3 = f"{query_en}" + (f" in {city_en_map.get(city, city)}" if city else "")
            raw_data = _do_jsearch(search_query3)
        if not raw_data:
            return []

        jobs = []
        for item in raw_data[:limit]:
            title = item.get("job_title", "未知职位")
            company = item.get("employer_name", "未知公司")
            location = item.get("job_city", "") or city or "未知"
            if item.get("job_country") and location != item.get("job_country"):
                location = f"{location}, {item['job_country']}"
            salary_min = item.get("job_min_salary")
            salary_max = item.get("job_max_salary")
            salary_currency = item.get("job_salary_currency", "")
            salary = None
            if salary_min and salary_max:
                salary = f"{int(salary_min)}-{int(salary_max)} {salary_currency}"
            elif item.get("job_salary_range"):
                salary = item["job_salary_range"]
            desc = (item.get("job_description") or "")[:100].replace("\n", " ").strip()
            apply_link = item.get("job_apply_link") or item.get("job_google_link", "")
            publisher = item.get("job_publisher", "Google Jobs")
            source_parts = []
            if publisher:
                source_parts.append(publisher)
            for ao in (item.get("apply_options") or [])[:2]:
                if ao.get("publisher") and ao["publisher"] != publisher:
                    source_parts.append(ao["publisher"])
            source_label = " · ".join(source_parts[:3]) if source_parts else "Google Jobs"
            posted = item.get("job_posted_at_datetime_utc") or item.get("job_offer_expiration_datetime_utc")
            jobs.append(JobResult(
                title=title,
                company=company,
                location=location,
                salary=salary,
                summary=desc if desc else f"{title} at {company}",
                url=apply_link,
                source=source_label,
                posted_at=posted,
                platform="Google Jobs",
            ))
        return jobs
    except Exception as e:
        print(f"[Jobs] JSearch API failed: {e}")
        return []

def _baidu_search_jobs(query: str, city: Optional[str], platform_key: str, limit: int = 5) -> List[dict]:
    site_map = {
        "maimai": "site:maimai.cn",
        "liepin": "site:liepin.com",
        "jike": "site:okjk.co OR site:jike.city",
    }
    site_filter = site_map.get(platform_key, "")
    search_query = f"{query} {city or ''} 招聘 {site_filter}".strip()
    try:
        from baidusearch.baidusearch import search as baidu_search
        raw_results = baidu_search(search_query, num_results=limit + 3)
        cleaned = []
        for r in raw_results:
            url = r.get("url", r.get("href", ""))
            # Keep baidu redirect links - they work when opened
            if "/s?" in url and "wd=" in url:
                continue
            title = r.get("title", "")
            for suffix in [" - 脉脉", " - 猎聘", "_猎聘网", " - 即刻", "_百度搜索", " - 百度"]:
                title = title.replace(suffix, "")
            snippet = r.get("abstract", r.get("snippet", r.get("body", "")))
            if title and len(title) > 3:
                cleaned.append({"title": title, "url": url, "snippet": snippet})
        return cleaned[:limit]
    except Exception as e:
        print(f"[Jobs] Baidu search failed for {platform_key}: {e}")
        return []

JOB_ARTICLE_INDICATORS = {
    "什么是", "怎么做", "如何做", "趋势", "报告", "观察", "新闻", "资讯", "百科",
    "指南", "攻略", "经验分享", "求职经验", "面试经验", "被ai改变", "薪资报告",
    "岗位解读", "职业发展", "干货", "盘点", "榜单", "合集",
}
JOB_OPENING_INDICATORS = {
    "招聘", "急聘", "诚聘", "热招", "社会招聘", "校园招聘", "立即申请", "投递简历",
    "任职要求", "职位描述", "工作职责", "岗位职责", "工作内容", "职位详情",
}


def is_probable_job_posting(title: str, snippet: str, company: str, url: str) -> bool:
    """Apply a conservative JobPosting-inspired gate to search snippets.

    This never proves that a posting is still open. It only prevents obvious
    editorial/search content from being promoted to a job card.
    """
    content = re.sub(r"\s+", "", f"{title} {snippet}").lower()
    if not re.match(r"^https?://", url):
        return False
    if not company or company == "来源页内查看":
        return False
    if any(indicator in content for indicator in JOB_ARTICLE_INDICATORS):
        return False
    return any(indicator in content for indicator in JOB_OPENING_INDICATORS)


def _jobs_from_search_results(query: str, city: Optional[str], platform_label: str, raw_results: List[dict]) -> List[JobResult]:
    """Convert source results without asking an LLM to invent missing job fields."""
    jobs: List[JobResult] = []
    for result in raw_results:
        title = re.sub(r"\s+", " ", str(result.get("title") or "")).strip()
        url = str(result.get("url") or "").strip()
        snippet = re.sub(r"\s+", " ", str(result.get("snippet") or "")).strip()
        if len(title) < 3 or not re.match(r"^https?://", url):
            continue
        lowered = f"{title} {snippet}".lower()
        if query.lower() not in lowered and not any(token.lower() in lowered for token in re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]{2,}", query)):
            continue
        parts = [part.strip() for part in re.split(r"\s*[-_|·｜]\s*", title) if part.strip()]
        company = "来源页内查看"
        if len(parts) >= 2:
            candidates = [part for part in parts[1:] if platform_label not in part and "招聘" not in part]
            if candidates:
                company = candidates[0][:40]
        if not is_probable_job_posting(title, snippet, company, url):
            continue
        job_title = re.sub(r"(?:招聘|急聘|诚聘|热招|招聘信息)$", "", parts[0]).strip() or parts[0]
        jobs.append(JobResult(
            title=job_title[:80],
            company=company,
            location=city or "地点见来源页",
            salary=None,
            summary=snippet[:140] or "请打开来源页查看完整岗位描述",
            url=url,
            source=platform_label,
            platform=platform_label,
            verified_source=True,
            retrieved_at=now_iso(),
            source_status="listing_signals_verified",
            verification_note="来源摘要包含招聘主体和职位信号；请打开原页面确认仍在招聘",
        ))
    return jobs

@app.post("/api/v1/jobs/search", response_model=JobSearchResponse)
async def search_jobs(request: JobSearchRequest):
    query = request.query.strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="请至少输入 2 个字的岗位关键词")
    platforms = _parse_platforms(request.platforms) or ["liepin", "maimai", "jike"]
    limit = min(max(request.limit, 1), 20)
    jobs: List[JobResult] = []
    provider_status: List[Dict[str, Any]] = []

    if JSEARCH_API_KEY:
        found = await asyncio.get_event_loop().run_in_executor(None, _jsearch_api_search, query, request.city, limit)
        for job in found:
            job.verified_source = bool(
                job.url
                and re.match(r"^https?://", job.url)
                and job.title.strip()
                and job.company.strip()
                and job.company not in {"未知公司", "来源页内查看"}
                and job.summary.strip()
            )
            job.retrieved_at = now_iso()
            job.source_status = "provider_listing"
            job.verification_note = "岗位提供方返回的带来源候选；请打开原页面确认仍在招聘"
        jobs.extend(job for job in found if job.verified_source)
        provider_status.append({"provider": "jsearch", "count": len(found), "ok": True})

    for platform_key in platforms:
        label = PLATFORM_SITE_MAP[platform_key]["label"]
        try:
            raw = await asyncio.get_event_loop().run_in_executor(
                None, _baidu_search_jobs, query, request.city, platform_key, min(limit, 8)
            )
            converted = _jobs_from_search_results(query, request.city, label, raw)
            jobs.extend(converted)
            provider_status.append({"provider": platform_key, "count": len(converted), "ok": True})
        except Exception as error:
            provider_status.append({"provider": platform_key, "count": 0, "ok": False, "error": type(error).__name__})

    deduplicated: List[JobResult] = []
    seen_urls = set()
    for job in jobs:
        if not job.url or job.url in seen_urls:
            continue
        seen_urls.add(job.url)
        deduplicated.append(job)
        if len(deduplicated) >= limit:
            break

    return JobSearchResponse(
        query=query,
        total=len(deduplicated),
        query_analysis={
            "status": "source_linked_candidates" if deduplicated else "no_qualified_candidates",
            "providers": provider_status,
            "message": "仅展示含招聘主体、职位信号和来源链接的候选；仍需打开确认有效期" if deduplicated else "当前没有拿到足够可信的岗位候选，请调整关键词或稍后重试",
        },
        jobs=deduplicated,
    )


MEMBERSHIP_PLANS = [
    MembershipPlan(
        id="free",
        name="内测版",
        price=0,
        price_yearly=None,
        features=["内测期 AI 对话不限量", "真实模型简历诊断", "5/10/20/30分钟面试练习", "审核专家预约意向", "带来源链接的岗位搜索"],
        ai_chat_limit=-1,
        resume_analysis_limit=-1,
        mock_interview_limit=-1,
        expert_discount=1.0,
        job_search_platforms=["liepin"],
        purchasable=False,
        billing_note="当前首批内测用户免费使用；用量会真实记录但不限制。",
    ),
    MembershipPlan(
        id="pro",
        name="Pro版",
        price=29.9,
        price_yearly=299,
        features=["方案假设：无限AI对话", "方案假设：月10次简历诊断", "方案假设：月5次模拟面试", "方案假设：专家8折", "方案假设：扩展岗位来源"],
        ai_chat_limit=-1,
        resume_analysis_limit=10,
        mock_interview_limit=5,
        expert_discount=0.8,
        job_search_platforms=["liepin", "maimai"],
        purchasable=False,
        billing_note="价格与权益正在用户验证；微信支付未接入，可登记意向但不会扣款。",
    ),
    MembershipPlan(
        id="premium",
        name="尊享版",
        price=59.9,
        price_yearly=599,
        features=["方案假设：全部不限量", "方案假设：专家6折", "方案假设：全平台搜索", "方案假设：人工服务通道", "方案假设：优先匹配专家"],
        ai_chat_limit=-1,
        resume_analysis_limit=-1,
        mock_interview_limit=-1,
        expert_discount=0.6,
        job_search_platforms=["liepin", "maimai", "jike"],
        purchasable=False,
        billing_note="价格与权益正在用户验证；微信支付未接入，可登记意向但不会扣款。",
    ),
]

EXPERT_BASE_PRICE = 199.0

def _get_plan_by_id(plan_id: str) -> Optional[MembershipPlan]:
    for p in MEMBERSHIP_PLANS:
        if p.id == plan_id:
            return p
    return None

def _get_user_membership(state: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    users = state.get("users", {})
    user = users.get(user_id)
    if not user:
        return None
    membership = user.get("membership", {
        "plan_id": "free",
        "plan_name": "免费版",
        "expire_at": None,
        "ai_chat_used": 0,
        "resume_used": 0,
        "interview_used": 0,
    })
    if "membership" not in user:
        user["membership"] = membership
    expire_at = membership.get("expire_at")
    if membership.get("plan_id", "free") != "free" and expire_at:
        try:
            expires = datetime.fromisoformat(str(expire_at).replace("Z", "+00:00")).replace(tzinfo=None)
            if expires <= datetime.utcnow():
                membership.update({"plan_id": "free", "plan_name": "内测版", "expire_at": None})
                membership.pop("activated_by_order_id", None)
                membership.pop("usage_reset_at", None)
        except ValueError:
            membership.update({"plan_id": "free", "plan_name": "内测版", "expire_at": None})
            membership.pop("usage_reset_at", None)
    return membership

def _membership_to_response(membership: Dict[str, Any]) -> UserMembership:
    plan = _get_plan_by_id(membership.get("plan_id", "free"))
    if not plan:
        plan = MEMBERSHIP_PLANS[0]
    return UserMembership(
        plan_id=plan.id,
        plan_name=plan.name,
        expire_at=membership.get("expire_at"),
        ai_chat_used=membership.get("ai_chat_used", 0),
        ai_chat_limit=plan.ai_chat_limit,
        resume_used=membership.get("resume_used", 0),
        resume_limit=plan.resume_analysis_limit,
        interview_used=membership.get("interview_used", 0),
        interview_limit=plan.mock_interview_limit,
        expert_discount=plan.expert_discount,
        usage_reset_at=membership.get("usage_reset_at"),
    )

MEMBERSHIP_USAGE_LIMITS = {
    "ai_chat_used": "ai_chat_limit",
    "resume_used": "resume_analysis_limit",
    "interview_used": "mock_interview_limit",
}

def rollover_membership_usage(membership: Dict[str, Any]) -> bool:
    """Reset paid-plan monthly allowances only when their server-side window ends."""
    if membership.get("plan_id", "free") == "free":
        return False
    now = datetime.utcnow()
    reset_at_text = membership.get("usage_reset_at")
    try:
        reset_at = datetime.fromisoformat(str(reset_at_text).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        reset_at = now + timedelta(days=30)
        membership["usage_reset_at"] = reset_at.replace(microsecond=0).isoformat() + "Z"
        return True
    if reset_at > now:
        return False
    while reset_at <= now:
        reset_at += timedelta(days=30)
    membership.update({
        "ai_chat_used": 0,
        "resume_used": 0,
        "interview_used": 0,
        "usage_reset_at": reset_at.replace(microsecond=0).isoformat() + "Z",
    })
    return True

def enforce_membership_quota(state: Dict[str, Any], user_id: Optional[str], usage_key: str) -> None:
    if not user_id or usage_key not in MEMBERSHIP_USAGE_LIMITS:
        return
    membership = _get_user_membership(state, user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    rollover_membership_usage(membership)
    plan = _get_plan_by_id(membership.get("plan_id", "free")) or MEMBERSHIP_PLANS[0]
    limit = int(getattr(plan, MEMBERSHIP_USAGE_LIMITS[usage_key]))
    used = int(membership.get(usage_key, 0))
    if limit >= 0 and used >= limit:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "MEMBERSHIP_LIMIT_REACHED",
                "message": "本月该项会员用量已用完，可在会员页查看权益和下次重置时间。",
                "usage_key": usage_key,
                "used": used,
                "limit": limit,
                "usage_reset_at": membership.get("usage_reset_at"),
            },
        )

def record_membership_usage(state: Dict[str, Any], user_id: Optional[str], key: str) -> None:
    if not user_id or key not in {"ai_chat_used", "resume_used", "interview_used"}:
        return
    membership = _get_user_membership(state, user_id)
    if membership is not None:
        rollover_membership_usage(membership)
        membership[key] = int(membership.get(key, 0)) + 1


def _membership_price(plan: MembershipPlan, billing_cycle: str) -> float:
    if billing_cycle == "yearly":
        if plan.price_yearly is None:
            raise HTTPException(status_code=422, detail="该方案暂不支持年付")
        return plan.price_yearly
    return plan.price


def _find_payment_order(state: Dict[str, Any], order_id: str) -> Optional[Dict[str, Any]]:
    return next((item for item in state.get("orders", []) if item.get("id") == order_id), None)


def _payment_status_payload(order: Dict[str, Any]) -> Dict[str, Any]:
    status = order.get("status", "unknown")
    messages = {
        "creating": "订单正在创建",
        "unpaid": "尚未收到服务端支付确认",
        "paid": "支付已由微信支付服务端确认",
        "failed": "微信支付下单失败，未扣款",
        "closed": "订单已关闭",
        "refund_processing": "退款处理中",
        "refunded": "退款已由微信支付服务端确认",
        "refund_failed": "退款未成功，请联系平台核对",
    }
    return PaymentOrderStatus(
        order_id=order["id"],
        status=status,
        product_type=order.get("product_type", "unknown"),
        amount_total=int(order.get("amount_total", 0)),
        currency=order.get("currency", "CNY"),
        fulfilled=bool(order.get("fulfilled")),
        message=messages.get(status, "订单状态待核对"),
    ).model_dump()


def _create_wechat_payment_order(
    user_id: str,
    product_type: str,
    description: str,
    amount_total: int,
    metadata: Dict[str, Any],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not can_user_initiate_payment(user_id, product_type):
        raise HTTPException(status_code=503, detail=_payment_unavailable_detail(product_type, user_id))
    if amount_total <= 0:
        raise HTTPException(status_code=422, detail="支付金额必须大于 0")

    with _state_lock:
        state = load_beta_state()
        user = state.get("users", {}).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        openid = user.get("profile", {}).get("wechat_openid", "")
        if not openid:
            raise HTTPException(
                status_code=409,
                detail={"code": "WECHAT_LOGIN_REQUIRED", "message": "支付前需要使用真实微信身份重新进入小程序"},
            )
        if request_id:
            existing = next(
                (
                    item for item in state.get("orders", [])
                    if item.get("user_id") == user_id
                    and item.get("product_type") == product_type
                    and item.get("client_request_id") == request_id
                ),
                None,
            )
            if existing:
                if existing.get("status") == "unpaid" and existing.get("prepay_id"):
                    return {"order": existing, "payment_params": _build_miniprogram_payment_params(existing["prepay_id"])}
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "PAYMENT_REQUEST_ALREADY_EXISTS",
                        "message": "这次支付请求已处理，请刷新订单状态，不要重复支付",
                        "order_id": existing["id"],
                    },
                )
        active_order = next(
            (
                item for item in state.get("orders", [])
                if item.get("user_id") == user_id
                and item.get("product_type") == product_type
                and item.get("metadata") == metadata
                and item.get("status") in {"creating", "unpaid"}
            ),
            None,
        )
        if active_order:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACTIVE_PAYMENT_ORDER_EXISTS",
                    "message": "已有一笔相同待确认订单，请先核对或关闭原订单，避免重复支付",
                    "order_id": active_order["id"],
                },
            )
        order_id = f"PC{datetime.utcnow().strftime('%y%m%d%H%M%S')}{secrets.token_hex(7)}"[:32]
        order = {
            "id": order_id,
            "user_id": user_id,
            "product_type": product_type,
            "description": description[:127],
            "amount_total": amount_total,
            "currency": "CNY",
            "status": "creating",
            "fulfilled": False,
            "metadata": metadata,
            "client_request_id": request_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        state.setdefault("orders", []).insert(0, order)
        save_beta_state(state)

    try:
        result = get_wechat_pay_client().pay(
            description=order["description"],
            out_trade_no=order_id,
            amount={"total": amount_total, "currency": "CNY"},
            payer={"openid": openid},
            time_expire=(datetime.utcnow() + timedelta(minutes=15)).replace(microsecond=0).isoformat() + "Z",
            attach=order_id,
        )
        payload = _parse_wechat_pay_response(result, "下单", {200})
        prepay_id = str(payload.get("prepay_id", ""))
        payment_params = _build_miniprogram_payment_params(prepay_id)
    except Exception as error:
        print(f"[WeChatPay] create order failed: {type(error).__name__}: {error}")
        with _state_lock:
            state = load_beta_state()
            stored = _find_payment_order(state, order_id)
            if stored and stored.get("status") == "creating":
                stored.update({"status": "failed", "failure_code": type(error).__name__, "updated_at": now_iso()})
                save_beta_state(state)
        raise HTTPException(
            status_code=502,
            detail={"code": "WECHAT_PAY_CREATE_FAILED", "message": "微信支付下单未成功，当前不会扣款，请稍后重试"},
        )

    with _state_lock:
        state = load_beta_state()
        stored = _find_payment_order(state, order_id)
        if not stored:
            raise HTTPException(status_code=500, detail="支付订单持久化异常")
        if stored.get("status") == "creating":
            stored["status"] = "unpaid"
        stored.update({"prepay_id": prepay_id, "updated_at": now_iso()})
        save_beta_state(state)
    return {"order": stored, "payment_params": payment_params}


def _activate_membership_from_order(state: Dict[str, Any], order: Dict[str, Any]) -> None:
    metadata = order.get("metadata", {})
    plan = _get_plan_by_id(metadata.get("plan_id", ""))
    user = state.get("users", {}).get(order.get("user_id"))
    if not plan or plan.id == "free" or not user:
        raise ValueError("会员订单关联的用户或方案不存在")
    cycle = metadata.get("billing_cycle", "monthly")
    duration_days = 365 if cycle == "yearly" else 30
    membership = _get_user_membership(state, order["user_id"])
    now = datetime.utcnow()
    start_at = now
    preserve_current_usage = False
    current_expire = membership.get("expire_at") if membership else None
    if membership and membership.get("plan_id") == plan.id and current_expire:
        try:
            parsed = datetime.fromisoformat(str(current_expire).replace("Z", "+00:00")).replace(tzinfo=None)
            if parsed > start_at:
                start_at = parsed
                preserve_current_usage = True
        except ValueError:
            pass
    user["membership"] = {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "expire_at": (start_at + timedelta(days=duration_days)).replace(microsecond=0).isoformat() + "Z",
        "ai_chat_used": int(membership.get("ai_chat_used", 0)) if preserve_current_usage else 0,
        "resume_used": int(membership.get("resume_used", 0)) if preserve_current_usage else 0,
        "interview_used": int(membership.get("interview_used", 0)) if preserve_current_usage else 0,
        "usage_reset_at": (
            membership.get("usage_reset_at")
            if preserve_current_usage and membership.get("usage_reset_at")
            else (now + timedelta(days=30)).replace(microsecond=0).isoformat() + "Z"
        ),
        "activated_by_order_id": order["id"],
    }


def _apply_successful_payment(state: Dict[str, Any], transaction: Dict[str, Any]) -> Dict[str, Any]:
    order_id = str(transaction.get("out_trade_no", ""))
    order = _find_payment_order(state, order_id)
    if not order:
        raise ValueError("未知的商户订单号")
    if transaction.get("trade_state") != "SUCCESS":
        raise ValueError("交易状态不是 SUCCESS")
    amount = transaction.get("amount") or {}
    if int(amount.get("total", -1)) != int(order.get("amount_total", -2)) or amount.get("currency", "CNY") != order.get("currency", "CNY"):
        raise ValueError("回调金额或币种与服务端订单不一致")
    if str(transaction.get("appid", "")) != str(WECHAT_APP_ID) or str(transaction.get("mchid", "")) != str(WECHAT_PAY_MCH_ID):
        raise ValueError("回调 AppID 或商户号不匹配")
    if order.get("status") in {"refund_processing", "refunded"}:
        return order
    if order.get("status") == "paid" and order.get("fulfilled"):
        return order

    order.update({
        "status": "paid",
        "transaction_id": transaction.get("transaction_id"),
        "paid_at": transaction.get("success_time") or now_iso(),
        "updated_at": now_iso(),
    })
    if order.get("product_type") == "membership":
        _activate_membership_from_order(state, order)
    elif order.get("product_type") == "expert":
        booking_id = order.get("metadata", {}).get("booking_id")
        booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
        if not booking or booking.get("user_id") != order.get("user_id"):
            raise ValueError("专家订单关联的预约不存在")
        booking.update({
            "payment_status": "paid",
            "payment_order_id": order["id"],
            "status": "待服务",
            "updated_at": now_iso(),
        })
        update_user_booking_copy(state, booking)
    else:
        raise ValueError("未知的支付商品类型")
    order["fulfilled"] = True
    append_product_event_to_state(
        state,
        "payment.fulfilled",
        order.get("user_id"),
        {"product_type": order.get("product_type"), "order_id": order["id"]},
    )
    return order


def _apply_successful_refund(state: Dict[str, Any], refund: Dict[str, Any]) -> Dict[str, Any]:
    order = _find_payment_order(state, str(refund.get("out_trade_no", "")))
    if not order:
        raise ValueError("退款关联的商户订单不存在")
    if refund.get("refund_status") != "SUCCESS":
        raise ValueError("退款状态不是 SUCCESS")
    if order.get("refund_idempotency_no") != refund.get("out_refund_no"):
        raise ValueError("商户退款单号不匹配")
    amount = refund.get("amount") or {}
    if int(amount.get("refund", -1)) != int(order.get("amount_total", -2)):
        raise ValueError("退款金额与服务端订单不一致")
    if order.get("status") == "refunded":
        return order
    order.update({
        "status": "refunded",
        "refund_id": refund.get("refund_id"),
        "refunded_at": refund.get("success_time") or now_iso(),
        "updated_at": now_iso(),
    })
    if order.get("product_type") == "expert":
        booking_id = order.get("metadata", {}).get("booking_id")
        booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
        if booking:
            booking.update({
                "status_code": "cancelled",
                "status": "已取消并退款",
                "payment_status": "refunded",
                "refund_status": "success",
                "cancelled_at": booking.get("cancelled_at") or now_iso(),
                "updated_at": now_iso(),
            })
            expert = next((item for item in state.get("experts", []) if item.get("id") == booking.get("expertId")), None)
            if expert and booking.get("slot") and booking["slot"] not in expert.setdefault("slots", []):
                expert["slots"].append(booking["slot"])
            update_user_booking_copy(state, booking)
    append_product_event_to_state(
        state,
        "payment.refunded",
        order.get("user_id"),
        {"product_type": order.get("product_type"), "order_id": order["id"]},
    )
    return order


@app.get("/api/v1/membership/plans")
def get_membership_plans(user_id: Optional[str] = None):
    available = can_user_initiate_payment(user_id, "membership")
    plans = []
    for plan in MEMBERSHIP_PLANS:
        purchasable = bool(available and plan.id != "free")
        note = plan.billing_note
        features = plan.features
        if purchasable:
            note = "仅以微信支付服务端确认结果开通；支付前请核对价格与权益。"
            features = [item.removeprefix("方案假设：") for item in plan.features]
        plans.append(plan.model_copy(update={"purchasable": purchasable, "billing_note": note, "features": features}).model_dump())
    return {"plans": plans}

@app.get("/api/v1/membership/status")
def get_membership_status(user_id: str):
    with _state_lock:
        state = load_beta_state()
        membership = _get_user_membership(state, user_id)
        if membership is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        save_beta_state(state)
    return _membership_to_response(membership).model_dump()

@app.post("/api/v1/membership/subscribe")
def subscribe_membership(request: MembershipSubscribeRequest):
    plan = _get_plan_by_id(request.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail="无效的会员方案")
    if plan.id == "free":
        raise HTTPException(status_code=400, detail="免费版无需订阅")
    cycle = request.billing_cycle.strip().lower()
    if cycle not in {"monthly", "yearly"}:
        raise HTTPException(status_code=422, detail="billing_cycle 必须是 monthly 或 yearly")
    amount_total = _money_to_fen(_membership_price(plan, cycle))
    created = _create_wechat_payment_order(
        user_id=request.user_id,
        product_type="membership",
        description=f"Pinco {plan.name}{'年付' if cycle == 'yearly' else '月付'}",
        amount_total=amount_total,
        metadata={"plan_id": plan.id, "billing_cycle": cycle},
        request_id=request.request_id,
    )
    return {
        "success": True,
        "order_id": created["order"]["id"],
        "amount_total": amount_total,
        "currency": "CNY",
        "payment_params": created["payment_params"],
        "message": "订单已创建；会员只会在微信支付服务端确认后开通。",
    }


@app.post("/api/v1/payments/wechat/notify")
async def handle_wechat_payment_notification(request: Request):
    """Verify and decrypt the WeChat Pay notification before fulfillment."""
    body = await request.body()
    try:
        notification = get_wechat_pay_client().callback(dict(request.headers), body)
        if not isinstance(notification, dict):
            raise ValueError("回调验签或解密失败")
        if notification.get("event_type") != "TRANSACTION.SUCCESS":
            return {"code": "SUCCESS", "message": "非支付成功事件已忽略"}
        transaction = notification.get("resource")
        if not isinstance(transaction, dict):
            raise ValueError("回调缺少已解密交易数据")
        with _state_lock:
            state = load_beta_state()
            _apply_successful_payment(state, transaction)
            save_beta_state(state)
        return {"code": "SUCCESS", "message": "成功"}
    except Exception as error:
        print(f"[WeChatPay] payment notify rejected: {type(error).__name__}: {error}")
        return JSONResponse(
            status_code=400,
            content={"code": "FAIL", "message": "支付通知校验失败"},
        )


@app.get("/api/v1/payments/orders")
def list_payment_orders(user_id: str, product_type: Optional[str] = None):
    if product_type and product_type not in {"membership", "expert"}:
        raise HTTPException(status_code=422, detail="不支持的支付订单类型")
    state = load_beta_state()
    orders = [
        item for item in state.get("orders", [])
        if item.get("user_id") == user_id and (not product_type or item.get("product_type") == product_type)
    ]
    return {"orders": [_payment_status_payload(item) for item in orders[:20]]}


@app.get("/api/v1/payments/orders/{order_id}")
def get_payment_order_status(order_id: str, user_id: str, refresh: bool = True):
    with _state_lock:
        state = load_beta_state()
        order = _find_payment_order(state, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="支付订单不存在")
        if order.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="只能查询自己的支付订单")
        current_status = order.get("status")
        if not refresh or current_status in {"paid", "refunded", "failed", "closed"}:
            return _payment_status_payload(order)

    if current_status == "refund_processing":
        try:
            refund = _parse_wechat_pay_response(
                get_wechat_pay_client().query_refund(order.get("refund_idempotency_no")),
                "查询退款",
                {200},
            )
        except Exception as error:
            print(f"[WeChatPay] refund query failed: {type(error).__name__}: {error}")
            raise HTTPException(
                status_code=502,
                detail={"code": "WECHAT_PAY_REFUND_QUERY_FAILED", "message": "暂未能确认退款结果，请稍后刷新"},
            )
        with _state_lock:
            state = load_beta_state()
            order = _find_payment_order(state, order_id)
            if not order or order.get("user_id") != user_id:
                raise HTTPException(status_code=404, detail="支付订单不存在")
            refund_status = refund.get("status") or refund.get("refund_status")
            if refund_status == "SUCCESS":
                _apply_successful_refund(state, {
                    **refund,
                    "out_trade_no": order_id,
                    "out_refund_no": order.get("refund_idempotency_no"),
                    "refund_status": "SUCCESS",
                })
            elif refund_status in {"CLOSED", "ABNORMAL"}:
                order.update({"status": "paid", "wechat_refund_status": refund_status, "updated_at": now_iso()})
                booking_id = order.get("metadata", {}).get("booking_id")
                booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
                if booking:
                    booking.update({"payment_status": "paid", "refund_status": "failed", "status": "待服务", "updated_at": now_iso()})
                    update_user_booking_copy(state, booking)
            else:
                order["wechat_refund_status"] = refund_status or "PROCESSING"
            save_beta_state(state)
            return _payment_status_payload(order)

    try:
        transaction = _parse_wechat_pay_response(
            get_wechat_pay_client().query(out_trade_no=order_id),
            "查询订单",
            {200},
        )
    except Exception as error:
        print(f"[WeChatPay] order query failed: {type(error).__name__}: {error}")
        raise HTTPException(
            status_code=502,
            detail={"code": "WECHAT_PAY_QUERY_FAILED", "message": "暂未能从微信支付确认订单状态，请稍后刷新；不要重复支付"},
        )

    with _state_lock:
        state = load_beta_state()
        order = _find_payment_order(state, order_id)
        if not order or order.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="支付订单不存在")
        trade_state = transaction.get("trade_state")
        if trade_state == "SUCCESS":
            try:
                _apply_successful_payment(state, transaction)
            except ValueError as error:
                print(f"[WeChatPay] queried transaction rejected: {error}")
                raise HTTPException(status_code=409, detail="微信交易与本地订单核对不一致，请联系平台处理")
        elif trade_state in {"CLOSED", "REVOKED", "PAYERROR"}:
            order.update({"status": "closed", "wechat_trade_state": trade_state, "updated_at": now_iso()})
        else:
            order.update({"status": "unpaid", "wechat_trade_state": trade_state or "UNKNOWN", "updated_at": now_iso()})
        save_beta_state(state)
        return _payment_status_payload(order)


@app.post("/api/v1/payments/orders/{order_id}/close")
def close_payment_order(order_id: str, request: CommunityActionRequest):
    with _state_lock:
        state = load_beta_state()
        order = _find_payment_order(state, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="支付订单不存在")
        if order.get("user_id") != request.user_id:
            raise HTTPException(status_code=403, detail="只能操作自己的支付订单")
        if order.get("status") in {"paid", "refunded", "refund_processing"}:
            return _payment_status_payload(order)
        if order.get("status") in {"closed", "failed"}:
            return _payment_status_payload(order)

    try:
        transaction = _parse_wechat_pay_response(
            get_wechat_pay_client().query(out_trade_no=order_id), "关闭前查询订单", {200}
        )
        if transaction.get("trade_state") == "SUCCESS":
            with _state_lock:
                state = load_beta_state()
                order = _apply_successful_payment(state, transaction)
                save_beta_state(state)
                return _payment_status_payload(order)
        _parse_wechat_pay_response(
            get_wechat_pay_client().close(out_trade_no=order_id), "关闭订单", {204}
        )
    except Exception as error:
        print(f"[WeChatPay] close order failed: {type(error).__name__}: {error}")
        raise HTTPException(
            status_code=502,
            detail={"code": "WECHAT_PAY_CLOSE_FAILED", "message": "订单暂未关闭，请先核对微信支付记录，不要重复创建订单"},
        )

    with _state_lock:
        state = load_beta_state()
        order = _find_payment_order(state, order_id)
        if not order or order.get("user_id") != request.user_id:
            raise HTTPException(status_code=404, detail="支付订单不存在")
        if order.get("status") not in {"paid", "refunded"}:
            order.update({"status": "closed", "updated_at": now_iso()})
            if order.get("product_type") == "expert":
                booking_id = order.get("metadata", {}).get("booking_id")
                booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
                if booking and booking.get("payment_order_id") == order_id:
                    booking.update({"payment_status": "payment_required", "status": "待付款", "updated_at": now_iso()})
                    booking.pop("payment_order_id", None)
                    update_user_booking_copy(state, booking)
            save_beta_state(state)
        return _payment_status_payload(order)


@app.post("/api/v1/payments/orders/{order_id}/refund")
def refund_payment_order(order_id: str, request: PaymentRefundRequest):
    with _state_lock:
        state = load_beta_state()
        order = _find_payment_order(state, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="支付订单不存在")
        if order.get("user_id") != request.user_id:
            raise HTTPException(status_code=403, detail="只能操作自己的支付订单")
        if order.get("product_type") != "expert":
            raise HTTPException(status_code=422, detail="会员退款需要人工核对剩余权益，暂不支持客户端直接发起")
        if order.get("status") == "refunded":
            return _payment_status_payload(order)
        if order.get("status") != "paid" or not order.get("fulfilled"):
            raise HTTPException(status_code=409, detail="只有已确认支付的订单可以退款")
        booking_id = order.get("metadata", {}).get("booking_id")
        booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
        if not booking or booking.get("status_code") == "completed":
            raise HTTPException(status_code=409, detail="服务已完成或预约不存在，不能由客户端自动退款")
        refund_no = f"RF{datetime.utcnow().strftime('%y%m%d%H%M%S')}{secrets.token_hex(7)}"[:32]
        order.update({
            "status": "refund_processing",
            "refund_idempotency_no": refund_no,
            "refund_reason": request.reason.strip(),
            "updated_at": now_iso(),
        })
        booking.update({"payment_status": "refund_processing", "refund_status": "processing", "status": "退款处理中", "updated_at": now_iso()})
        update_user_booking_copy(state, booking)
        save_beta_state(state)

    try:
        payload = _parse_wechat_pay_response(
            get_wechat_pay_client().refund(
                out_refund_no=refund_no,
                out_trade_no=order_id,
                reason=request.reason.strip() or "用户取消未开始的专家预约",
                amount={"refund": order["amount_total"], "total": order["amount_total"], "currency": order["currency"]},
                notify_url=WECHAT_PAY_REFUND_NOTIFY_URL,
            ),
            "申请退款",
            {200},
        )
    except Exception as error:
        print(f"[WeChatPay] refund request failed: {type(error).__name__}: {error}")
        with _state_lock:
            state = load_beta_state()
            stored = _find_payment_order(state, order_id)
            if stored and stored.get("refund_idempotency_no") == refund_no:
                stored.update({"status": "paid", "refund_failure_code": type(error).__name__, "updated_at": now_iso()})
                booking = next(
                    (item for item in state.get("expert_bookings", []) if item.get("id") == booking_id),
                    None,
                )
                if booking:
                    booking.update({"payment_status": "paid", "refund_status": "failed", "status": "待服务", "updated_at": now_iso()})
                    update_user_booking_copy(state, booking)
                save_beta_state(state)
        raise HTTPException(
            status_code=502,
            detail={"code": "WECHAT_PAY_REFUND_FAILED", "message": "退款申请未成功，预约仍保留，请勿重复操作并联系平台核对"},
        )

    with _state_lock:
        state = load_beta_state()
        order = _find_payment_order(state, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="支付订单不存在")
        if payload.get("status") == "SUCCESS":
            _apply_successful_refund(state, {
                **payload,
                "out_trade_no": order_id,
                "out_refund_no": refund_no,
                "refund_status": "SUCCESS",
            })
        elif payload.get("status") in {"CLOSED", "ABNORMAL"}:
            order.update({"status": "paid", "wechat_refund_status": payload.get("status"), "updated_at": now_iso()})
            booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking_id), None)
            if booking:
                booking.update({"payment_status": "paid", "refund_status": "failed", "status": "待服务", "updated_at": now_iso()})
                update_user_booking_copy(state, booking)
        else:
            order["wechat_refund_status"] = payload.get("status", "PROCESSING")
        save_beta_state(state)
        return _payment_status_payload(order)


@app.post("/api/v1/payments/wechat/refund-notify")
async def handle_wechat_refund_notification(request: Request):
    body = await request.body()
    try:
        notification = get_wechat_pay_client().callback(dict(request.headers), body)
        if not isinstance(notification, dict):
            raise ValueError("退款回调验签或解密失败")
        if notification.get("event_type") != "REFUND.SUCCESS":
            return {"code": "SUCCESS", "message": "非退款成功事件已忽略"}
        refund = notification.get("resource")
        if not isinstance(refund, dict):
            raise ValueError("退款回调缺少已解密数据")
        with _state_lock:
            state = load_beta_state()
            _apply_successful_refund(state, refund)
            save_beta_state(state)
        return {"code": "SUCCESS", "message": "成功"}
    except Exception as error:
        print(f"[WeChatPay] refund notify rejected: {type(error).__name__}: {error}")
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "退款通知校验失败"})


@app.post("/api/v1/membership/interest")
def capture_membership_interest(request: MembershipInterestRequest):
    plan = _get_plan_by_id(request.plan_id)
    if not plan or plan.id == "free":
        raise HTTPException(status_code=400, detail="请选择一个待验证的付费方案")
    cycle = request.billing_cycle.strip().lower()
    if cycle not in {"monthly", "yearly"}:
        raise HTTPException(status_code=422, detail="billing_cycle 必须是 monthly 或 yearly")
    with _state_lock:
        state = load_beta_state()
        community_user(state, request.user_id)
        interests = state.setdefault("membership_interests", [])
        existing = next(
            (item for item in interests if item.get("user_id") == request.user_id and item.get("plan_id") == plan.id),
            None,
        )
        if existing:
            existing.update({"billing_cycle": cycle, "updated_at": now_iso()})
            interest = existing
        else:
            interest = {
                "id": f"membership-interest-{uuid.uuid4().hex[:12]}",
                "user_id": request.user_id,
                "plan_id": plan.id,
                "billing_cycle": cycle,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            interests.append(interest)
        append_product_event_to_state(state, "membership.interest.created", request.user_id, {"plan_id": plan.id, "billing_cycle": cycle})
        save_beta_state(state)
    return {
        "interest": interest,
        "message": "已登记开通意向；当前不会扣款，支付开放前会再次向你确认。",
    }

@app.post("/api/v1/experts/{expert_id}/pay", response_model=ExpertPayResponse)
def pay_expert(expert_id: str, request: ExpertPayRequest):
    if request.coupon_code:
        raise HTTPException(status_code=422, detail="优惠码尚未开放，服务端不会接受客户端自报折扣")
    with _state_lock:
        state = load_beta_state()
        expert = next(
            (item for item in state.get("experts", []) if item.get("id") == expert_id and item.get("status") == "approved"),
            None,
        )
        if not expert:
            raise HTTPException(status_code=404, detail="专家不存在")
        booking = next(
            (item for item in state.get("expert_bookings", []) if item.get("id") == request.booking_id),
            None,
        )
        if not booking or booking.get("user_id") != request.user_id or booking.get("expertId") != expert_id:
            raise HTTPException(status_code=404, detail="预约不存在")
        if booking.get("status_code") != "confirmed":
            raise HTTPException(status_code=409, detail="专家确认接单后才能支付")
        if booking.get("payment_status") == "paid":
            raise HTTPException(status_code=409, detail="该预约已支付，请勿重复支付")
        if booking.get("payment_status") not in {"payment_required", "unpaid"}:
            raise HTTPException(status_code=409, detail="该预约当前不需要支付")
        membership = _get_user_membership(state, request.user_id) or {"plan_id": "free"}
        plan = _get_plan_by_id(membership.get("plan_id", "free")) or MEMBERSHIP_PLANS[0]
        original_price = float(expert.get("reference_price", 0))
        discount = float(plan.expert_discount)
        final_price = float((Decimal(str(original_price)) * Decimal(str(discount))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        amount_total = _money_to_fen(final_price)
        if amount_total <= 0:
            raise HTTPException(status_code=422, detail="该服务参考价为 0，无需调用支付")

    created = _create_wechat_payment_order(
        user_id=request.user_id,
        product_type="expert",
        description=f"Pinco 专家服务-{expert.get('service_name', '求职咨询')}",
        amount_total=amount_total,
        metadata={"booking_id": booking["id"], "expert_id": expert_id},
        request_id=request.request_id,
    )
    with _state_lock:
        state = load_beta_state()
        stored_booking = next((item for item in state.get("expert_bookings", []) if item.get("id") == booking["id"]), None)
        if stored_booking:
            stored_booking.update({
                "payment_status": "unpaid",
                "payment_order_id": created["order"]["id"],
                "updated_at": now_iso(),
            })
            update_user_booking_copy(state, stored_booking)
            save_beta_state(state)
    return ExpertPayResponse(
        success=True,
        order_id=created["order"]["id"],
        expert_id=expert_id,
        expert_name=expert["name"],
        topic=expert.get("service_name", "求职咨询"),
        slot=booking["slot"],
        original_price=original_price,
        discount=discount,
        actual_price=final_price,
        final_price=final_price,
        payment_method="wechat",
        booking_id=booking["id"],
        payment_params=created["payment_params"],
    )


# --- Voice Upload (ASR) ---
_whisper_model = None
_whisper_model_lock = Lock()

def get_whisper_model():
    if not ENABLE_LOCAL_WHISPER:
        raise RuntimeError("Local Whisper is disabled in this deployment.")
    global _whisper_model
    if _whisper_model is None:
        with _whisper_model_lock:
            if _whisper_model is None:
                try:
                    import os
                    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
                    from faster_whisper import WhisperModel
                    print("[ASR] Loading Whisper model...")
                    # tiny + 单线程用于本地开发；云托管生产环境默认禁用，避免小规格
                    # 容器加载模型时 OOM，连带让聊天等所有接口一起下线。
                    _whisper_model = WhisperModel(
                        "tiny",
                        device="cpu",
                        compute_type="int8",
                        cpu_threads=1,
                        num_workers=1,
                    )
                    print("[ASR] Whisper model loaded")
                except Exception as e:
                    print(f"[ASR] Failed to load Whisper model: {e}")
                    raise
    return _whisper_model

def transcribe_with_external_asr(temp_path: str) -> str:
    if ASR_PROVIDER != "openai" or not ASR_API_KEY:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ASR_NOT_CONFIGURED",
                "message": "语音转文字服务尚未配置，请在云托管中设置 ASR_PROVIDER、ASR_API_KEY、ASR_BASE_URL 和 ASR_MODEL。",
            },
        )
    from openai import OpenAI
    client = OpenAI(base_url=ASR_BASE_URL, api_key=ASR_API_KEY, timeout=60.0)
    with open(temp_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(model=ASR_MODEL, file=audio_file)
    return str(getattr(result, "text", "") or "").strip()

def get_aliyun_nls_token() -> str:
    now = int(time.time())
    cached_id = str(_aliyun_nls_token_cache.get("id") or "")
    cached_expiry = int(_aliyun_nls_token_cache.get("expires_at") or 0)
    if cached_id and now < cached_expiry - 300:
        return cached_id
    if not ALIYUN_AK_ID or not ALIYUN_AK_SECRET:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ALIYUN_ASR_CREDENTIALS_MISSING",
                "message": "阿里云语音鉴权尚未完成，请在云托管中配置 ALIYUN_AK_ID 和 ALIYUN_AK_SECRET。",
            },
        )
    with _aliyun_nls_token_lock:
        now = int(time.time())
        cached_id = str(_aliyun_nls_token_cache.get("id") or "")
        cached_expiry = int(_aliyun_nls_token_cache.get("expires_at") or 0)
        if cached_id and now < cached_expiry - 300:
            return cached_id
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest
        client = AcsClient(ALIYUN_AK_ID, ALIYUN_AK_SECRET, "cn-shanghai")
        request = CommonRequest()
        request.set_method("POST")
        request.set_domain("nls-meta.cn-shanghai.aliyuncs.com")
        request.set_version("2019-02-28")
        request.set_action_name("CreateToken")
        response = client.do_action_with_exception(request)
        payload = json.loads(response.decode("utf-8") if isinstance(response, bytes) else response)
        token_info = payload.get("Token") or {}
        token_id = str(token_info.get("Id") or "")
        expires_at = int(token_info.get("ExpireTime") or 0)
        if not token_id or not expires_at:
            raise RuntimeError("Aliyun NLS token response is incomplete.")
        _aliyun_nls_token_cache["id"] = token_id
        _aliyun_nls_token_cache["expires_at"] = expires_at
        return token_id

def prepare_aliyun_audio(temp_path: str) -> tuple[str, str, bool]:
    """Return an Aliyun-compatible audio path, format name, and conversion flag.

    WeChat DevTools can return WebM/Opus bytes even when RecorderManager was
    requested with ``format: mp3`` and the temporary filename ends in ``.mp3``.
    Sending those bytes to NLS as MP3 produces a misleading upstream failure.
    Real devices normally produce MP3, so only the WebM simulator case is
    normalized here.
    """
    with open(temp_path, "rb") as audio_file:
        header = audio_file.read(16)
    is_webm = header.startswith(b"\x1a\x45\xdf\xa3")
    if not is_webm:
        return temp_path, "mp3", False

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ASR_AUDIO_CONVERTER_MISSING",
                "message": "当前录音格式需要转换，但服务端缺少音频转换组件。",
            },
        )
    normalized_path = f"{temp_path}.normalized.mp3"
    try:
        completed = subprocess.run(
            [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                temp_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "48k",
                normalized_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Audio conversion timed out.") from error
    if completed.returncode != 0 or not os.path.exists(normalized_path):
        stderr = (completed.stderr or "").strip()[-500:]
        raise RuntimeError(f"Audio conversion failed: {stderr}")
    print(f"[ASR] Normalized WebM/Opus recording to MP3: {os.path.getsize(normalized_path)} bytes")
    return normalized_path, "mp3", True

def transcribe_with_aliyun_asr(temp_path: str) -> str:
    if not ALIYUN_NLS_APP_KEY:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ALIYUN_ASR_APP_KEY_MISSING",
                "message": "阿里云语音项目 App Key 尚未配置。",
            },
        )
    token = get_aliyun_nls_token()
    prepared_path, audio_format, converted = prepare_aliyun_audio(temp_path)
    try:
        with open(prepared_path, "rb") as audio_file:
            audio_content = audio_file.read()
        query = urlencode({
            "appkey": ALIYUN_NLS_APP_KEY,
            "format": audio_format,
            "sample_rate": 16000,
            "enable_punctuation_prediction": "true",
            "enable_inverse_text_normalization": "true",
            "enable_voice_detection": "true",
        })
        request = UrlRequest(
            f"{ALIYUN_NLS_ENDPOINT}?{query}",
            data=audio_content,
            headers={
                "X-NLS-Token": token,
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(audio_content)),
            },
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        if int(result.get("status") or 0) != 20000000:
            raise RuntimeError(
                f"Aliyun NLS failed: status={result.get('status')}, message={result.get('message')}"
            )
        return str(result.get("result") or "").strip()
    finally:
        if converted and os.path.exists(prepared_path):
            os.remove(prepared_path)

@app.post("/api/v1/voice/upload")
async def voice_upload(request: Request, type: str = "voice"):
    """Upload voice file and return ASR text."""
    try:
        filename, content, _ = await get_uploaded_file(request)
        print(f"[ASR] Received voice upload: {filename}, type={type}")
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        # Save to temp file
        temp_path = f"/tmp/voice_{uuid.uuid4().hex}.mp3"
        with open(temp_path, "wb") as f:
            f.write(content)

        try:
            language = "zh"
            if ASR_PROVIDER == "openai":
                text = transcribe_with_external_asr(temp_path)
            elif ASR_PROVIDER == "aliyun":
                text = transcribe_with_aliyun_asr(temp_path)
            elif ENABLE_LOCAL_WHISPER:
                model = get_whisper_model()
                segments, info = model.transcribe(temp_path, language="zh", beam_size=1, vad_filter=True)
                text = "".join([segment.text for segment in segments]).strip()
                language = info.language
            else:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "ASR_NOT_CONFIGURED",
                        "message": "语音转文字服务尚未配置，录音已安全结束，但暂时不能识别为文字。",
                    },
                )
            print(f"[ASR] Transcribed: {text[:50]}...")
            return {"text": text, "language": language}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ASR] Error: {e}")
        raise HTTPException(
            status_code=502,
            detail={"code": "ASR_UPSTREAM_ERROR", "message": "语音识别服务暂时不可用，请稍后重试。"},
        )

# --- Frontend Static Files ---
# Serve built Next.js static export; must be registered AFTER all API routes
# so that API paths take priority.
@app.get("/")
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"service": "pinco-backend", "status": "online", "health": "/health"}

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    # API routes are checked first, so this only handles non-API paths.
    file_path = os.path.join(FRONTEND_DIR, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    # Fallback to index.html for client-side routing (e.g. /articles, /garden)
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
