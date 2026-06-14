import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class PlatformSettings:
    llm_provider: str
    fallback_llm_provider: str | None
    gemini_api_key: str | None
    openai_api_key: str | None
    openai_base_url: str | None
    vision_model: str
    fallback_vision_model: str | None
    fast_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    circuit_failure_threshold: int
    circuit_cooldown_seconds: float
    use_stub_llm: bool


@lru_cache(maxsize=1)
def get_platform_settings() -> PlatformSettings:
    load_env_files()
    provider = os.getenv("LLM_PROVIDER", "stub").strip().lower()
    use_stub = os.getenv("USE_STUB_LLM", "true").strip().lower() in {"1", "true", "yes"}
    return PlatformSettings(
        llm_provider=provider,
        fallback_llm_provider=os.getenv("FALLBACK_LLM_PROVIDER"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        vision_model=os.getenv("VISION_MODEL", "gemini-2.5-flash"),
        fallback_vision_model=os.getenv("FALLBACK_VISION_MODEL", "gpt-4o-mini"),
        fast_model=os.getenv("FAST_MODEL", "gemini-2.5-flash"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "1")),
        circuit_failure_threshold=int(os.getenv("LLM_CIRCUIT_FAILURE_THRESHOLD", "3")),
        circuit_cooldown_seconds=float(os.getenv("LLM_CIRCUIT_COOLDOWN_SECONDS", "60")),
        use_stub_llm=use_stub or provider == "stub",
    )


def load_env_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for env_path in (repo_root / ".env", repo_root / "backend" / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
