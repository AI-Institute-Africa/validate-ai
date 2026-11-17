from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-change-me-dev-only-change-me"  # noqa: S105
DEV_WEBHOOK_SECRET = "dev-webhook-secret"  # noqa: S105


class Settings(BaseSettings):
    """Runtime configuration. Business limits live in payment_policies, not here.

    Defaults are production-safe: dev conveniences (dev login, fake readers, skipped malware
    scan) only switch on when POPS_ENV is explicitly dev or test.
    """

    model_config = SettingsConfigDict(env_prefix="POPS_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "prod"
    # the organisation POST /auth/dev-login uses when the caller names none (dev and test only), so
    # the console and the seed scripts land in the same organisation
    dev_org_name: str = "Cognify"
    # standalone demo (`python -m app.demo`): mounts /demo (scenarios, samples, reset) and
    # simulated readers. Never for production: startup refuses it.
    demo: bool = False
    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:5432/pops"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # inline: run the pipeline in the request (dev/tests); celery: enqueue
    pipeline_mode: Literal["inline", "celery"] = "celery"
    pipeline_max_attempts: int = 3
    stuck_after_seconds: int = 300

    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_seconds: int = 8 * 3600
    evidence_url_ttl_seconds: int = 300

    # OIDC (Cognify identity). When set, RS256 tokens from this issuer are accepted.
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_role_claim: str = "pops_role"
    oidc_org_claim: str = "pops_org"
    oidc_require_mfa_for_finance: bool = True

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: str = "./var/evidence"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "pops-evidence"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    max_upload_bytes: int = 10 * 1024 * 1024
    # camera RAW files are large by nature (20-80 MB); only they may exceed max_upload_bytes
    max_raw_upload_bytes: int = 80 * 1024 * 1024
    # everything one request may carry, so a few big files cannot exhaust memory
    max_claim_upload_bytes: int = 120 * 1024 * 1024

    # malware scanning via clamd (INSTREAM). Required in prod.
    clamav_host: str | None = None
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 30.0

    # upload rate limits (per authenticated caller, and per claimant across callers)
    rate_limit_uploads_per_minute: int = 30
    rate_limit_claims_per_claimant_per_day: int = 20
    # legibility previews run the readers (the vision model costs money) before any
    # claim exists
    rate_limit_previews_per_minute: int = 20
    # the standalone image-to-text converter runs a reader too
    rate_limit_text_conversions_per_minute: int = 20

    # global kill switch for rules-based auto-approval; overrides every organisation's policy
    auto_approve_disabled: bool = False
    # global kill switch for AI temporary approval; overrides every organisation's policy
    ai_temp_approve_disabled: bool = False

    # global kill switch for KYC auto-verification (app/kyc/auto.py); overrides every policy
    kyc_auto_disabled: bool = False
    # face matching for KYC: onnx (needs POPS_KYC_FACE_MODEL_PATH) | insightface (the same ArcFace
    # model, with the face aligned first: needs YuNet too) | fake (tests) | demo | none.
    # With none, or a missing model, nothing is auto-verified: a person decides (fail closed).
    kyc_face_backend: Literal["onnx", "insightface", "fake", "demo", "none"] = "onnx"
    kyc_face_model_path: str = "./var/models/face-embedding.onnx"
    # face detector: a YuNet ONNX model (OpenCV Zoo); on OpenCV 4 the bundled Haar cascade is
    # used when this file is absent
    kyc_face_detector_path: str = "./var/models/face-detection-yunet.onnx"
    rate_limit_kyc_per_subject_per_day: int = 5

    # read-only provider lookups (app/lookups): evidence for a person, never a decision.
    # off | shadow (record the result in the audit trail); both are advisory.
    lookup_mode: Literal["off", "shadow"] = "off"
    lookup_disabled: bool = False  # global kill switch
    lookup_backend: Literal["fake", "browser"] = "fake"
    # the browser backend's own language model is chosen by the browser-use library; set this
    # only after confirming it runs on a host we control
    lookup_browser_allowed: bool = False
    lookup_allowed_domains: list[str] = []
    lookup_timeout_seconds: int = 60

    # languages (besides English) whose outbound messages (WhatsApp, approve/reject texts) a
    # fluent reviewer has signed off and that may be sent; see app/claims/messages.py
    payer_message_languages_live: list[str] = []
    allow_draft_payer_messages: bool = False  # staging only: send unreviewed drafts

    # extraction readers: ollama | donut | fake ; ocr: tesseract | none
    vlm_backend: Literal["ollama", "donut", "fake"] = "ollama"
    # Shadow mode (blueprint phase 4): advisory AI proposals recorded beside claims and scored
    # against human decisions. Proposals never touch claim state, so this is safe to flip on;
    # flip it off to stop recording. The AI proposer additionally obeys the guardrail kill switch.
    shadow_mode_enabled: bool = False
    # Self-hosted by default: no outside AI service is called. In production the host must be
    # private or listed in ai_allowed_hosts (see app/core/ai_http.py).
    ollama_url: str = "http://ollama:11434"
    ollama_api_key: str | None = None
    ollama_model: str = "qwen3-vl:235b"
    ollama_timeout_seconds: float = 120.0
    # hosts (exact or parent domain) a model call may reach in production, besides private ones
    ai_allowed_hosts: list[str] = []
    donut_model_path: str = "./var/models/donut-pops"
    ocr_backend: Literal["tesseract", "none"] = "tesseract"
    ocr_languages: str = "eng"
    # Phase 0 calibration without code changes: JSON files that extend or override the built-in
    # provider layouts and statement CSV profiles (see docs/configuration.md)
    provider_templates_file: str | None = None
    statement_profiles_file: str | None = None
    alert_templates_file: str | None = None
    # extra payment-status words, e.g. in Shona or isiNdebele: {"word": "success|pending|..."}
    status_synonyms_file: str | None = None

    # recipient-side alerts: optional IMAP mailbox polled for bank/mobile-money credit emails
    alert_imap_host: str | None = None
    alert_imap_user: str | None = None
    alert_imap_password: str | None = None
    alert_imap_folder: str = "INBOX"
    alert_imap_source_id: str | None = None  # the registered email alert source it feeds
    alert_source_stale_minutes: int = 30  # forwarder heartbeat expected at least this often
    rate_limit_alerts_per_minute: int = 120
    # refuse alert requests that are not signed (X-POPs-Timestamp / X-POPs-Signature); a
    # signature that is present is always verified. See docs/alerts.md.
    alert_require_signature: bool = False

    # WhatsApp Business (Cloud API): payers send their POP to the business number
    whatsapp_verify_token: str | None = None  # the webhook "verify token" set in Meta's console
    whatsapp_app_secret: str | None = None  # signs every webhook (X-Hub-Signature-256)
    whatsapp_access_token: str | None = None  # downloads media and sends replies
    whatsapp_phone_number_id: str | None = None
    whatsapp_org_id: str | None = None  # optional: only accept payment codes of this org
    whatsapp_graph_url: str = "https://graph.facebook.com/v21.0"

    cognify_webhook_url: str | None = None
    cognify_webhook_secret: str = DEV_WEBHOOK_SECRET

    # Host-system provisioning (POST /internal/orgs). The endpoint does not exist unless a key
    # is set; it can only find or create an organisation by name.
    provisioning_key: str | None = None

    # where suspected-fake alerts go (any or both): a Slack/Teams-style webhook, and email
    admin_alert_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "pops-engine@localhost"
    admin_alert_emails: list[str] = []

    # official ZiG/USD rate from the Reserve Bank of Zimbabwe (see app/fx and docs/fx-rates.md)
    fx_enabled: bool = False
    # hours (UTC, cron syntax) on weekdays when the daily fetch tries until the file is found
    fx_fetch_hours: str = "5-16"
    fx_max_daily_move_pct: float = 25.0

    # trained authenticity detectors (docs/authenticity-detectors.md). off: nothing runs. shadow:
    # scores are recorded and change nothing. escalate: a high score can send a claim to a person
    # (never approve or reject). The model files and manifest.json are read from detect_model_dir.
    detect_mode: Literal["off", "shadow", "escalate"] = "off"
    detect_model_dir: str = "./var/models/detect"

    # where this deployment's data lives, for audit packets and the compliance screen (for example
    # "ZA-af-south-1" or "ZW-onprem"). Required in production: hosting is a deliberate choice.
    data_region: str | None = None
    # interactive API docs (/docs); default on in dev and off in production
    docs_enabled: bool | None = None

    cors_origins: list[str] = ["http://localhost:5173"]

    # observability
    log_json: bool = True
    sentry_dsn: str | None = None
    otel_endpoint: str | None = None

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "test")

    @property
    def docs_on(self) -> bool:
        return self.is_dev if self.docs_enabled is None else self.docs_enabled


class ConfigError(RuntimeError):
    pass


def ai_http_host_ok(url: str, allowed: list[str]) -> bool:
    from app.core.ai_http import host_allowed  # local import: ai_http imports this module

    return host_allowed(url, allowed)


def validate_for_startup(s: Settings) -> None:
    """Refuse to boot a production process with dev-only settings."""
    if s.is_dev:
        return
    problems = []
    if s.jwt_secret == DEV_JWT_SECRET or len(s.jwt_secret) < 32:
        problems.append("POPS_JWT_SECRET must be set to a random value of 32+ characters")
    if s.cognify_webhook_url and s.cognify_webhook_secret == DEV_WEBHOOK_SECRET:
        problems.append("POPS_COGNIFY_WEBHOOK_SECRET must be set")
    if s.provisioning_key is not None and len(s.provisioning_key) < 32:
        problems.append("POPS_PROVISIONING_KEY must be 32+ characters when set")
    if s.vlm_backend == "fake":
        problems.append("POPS_VLM_BACKEND=fake is for tests and demos only")
    if s.demo:
        problems.append("POPS_DEMO=true is for the standalone demo only")
    if s.allow_draft_payer_messages:
        problems.append("POPS_ALLOW_DRAFT_PAYER_MESSAGES sends unreviewed translations to payers")
    if s.lookup_mode != "off" and s.lookup_backend == "fake":
        problems.append("POPS_LOOKUP_BACKEND=fake is for tests and demos only")
    if s.lookup_mode != "off" and not s.lookup_allowed_domains:
        problems.append("POPS_LOOKUP_ALLOWED_DOMAINS must list the provider domains")
    if s.lookup_mode != "off" and s.lookup_backend == "browser" and not s.lookup_browser_allowed:
        problems.append(
            "POPS_LOOKUP_BACKEND=browser may call an outside AI service; confirm the model it "
            "uses is on a host we control, then set POPS_LOOKUP_BROWSER_ALLOWED=true"
        )
    if not ai_http_host_ok(s.ollama_url, s.ai_allowed_hosts):
        problems.append(
            "POPS_OLLAMA_URL points to an outside AI service; use a private host or list it in "
            "POPS_AI_ALLOWED_HOSTS"
        )
    if s.ollama_api_key:
        problems.append("POPS_OLLAMA_API_KEY must be empty: no hosted AI keys in production")
    if "://" in s.detect_model_dir:
        problems.append("POPS_DETECT_MODEL_DIR must be a local folder, never a URL")
    if not (s.data_region or "").strip():
        problems.append("POPS_DATA_REGION must say where the data is hosted (e.g. ZA-af-south-1)")
    if s.kyc_face_backend in ("fake", "demo"):
        problems.append(f"POPS_KYC_FACE_BACKEND={s.kyc_face_backend} is for tests and demos only")
    if not s.clamav_host:
        problems.append("POPS_CLAMAV_HOST is required: uploads must be malware-scanned")
    if s.pipeline_mode == "inline":
        problems.append("POPS_PIPELINE_MODE=inline is for development only")
    wa = [s.whatsapp_verify_token, s.whatsapp_app_secret, s.whatsapp_access_token]
    if any(wa) and not all([*wa, s.whatsapp_phone_number_id]):
        problems.append(
            "WhatsApp intake needs POPS_WHATSAPP_VERIFY_TOKEN, _APP_SECRET, _ACCESS_TOKEN "
            "and _PHONE_NUMBER_ID together"
        )
    if problems:
        raise ConfigError("unsafe production configuration:\n- " + "\n- ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
