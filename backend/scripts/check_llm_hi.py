import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ai_platform.config import get_platform_settings
from backend.ai_platform.llm import get_llm_platform
from backend.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> None:
    configure_logging()
    settings = get_platform_settings()
    logger.info(
        "Running LLM hi check: provider=%s model=%s fallback_provider=%s fallback_model=%s",
        settings.llm_provider,
        settings.vision_model,
        settings.fallback_llm_provider,
        settings.fallback_vision_model,
    )

    result = await get_llm_platform().get_llm_response(
        prompt='Return JSON only with exactly this shape: {"message":"hi"}',
        context={"purpose": "local connectivity check"},
    )
    logger.info(
        "LLM hi check succeeded: model=%s fallback_used=%s primary_error=%s",
        result.model,
        result.fallback_used,
        result.primary_error,
    )
    print(result.raw_text)


if __name__ == "__main__":
    asyncio.run(main())