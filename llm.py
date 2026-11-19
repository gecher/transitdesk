import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import RetryPolicy

load_dotenv()


def gemini(temperature: float = 0):
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        temperature=temperature,
        thinking_level=os.getenv("THINKING_LEVEL", "low"),
        max_retries=1,
        timeout=30,
    )


def groq(temperature: float = 0):
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        temperature=temperature,
        reasoning_effort=os.getenv("GROQ_REASONING_EFFORT", "low"),  # low = fast
        max_retries=1,
        timeout=30,
    )


PROVIDERS = {"gemini": gemini, "groq": groq}
KEYS = {"gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"), "groq": ("GROQ_API_KEY",)}


def available_providers() -> list[str]:
    """Providers from LLM_ORDER whose API key is set (a missing key would crash at start-up)."""
    names = [n.strip() for n in os.getenv("LLM_ORDER", "gemini,groq").split(",") if n.strip()]
    return [n for n in names if n in PROVIDERS and any(os.getenv(k) for k in KEYS[n])]


class MissingLLM:
    """Stands in when no API key is set: the app still starts, and the chat explains the problem."""

    def with_structured_output(self, *args, **kwargs):
        return self

    def bind_tools(self, *args, **kwargs):
        return self

    def invoke(self, *args, **kwargs):
        raise RuntimeError("No LLM API key is set. Add GROQ_API_KEY (or GOOGLE_API_KEY) "
                           "to the environment and restart.")


def get_llm(temperature: float = 0):
    """The first available provider, without fallback (for quick tests)."""
    names = available_providers()
    return PROVIDERS[names[0]](temperature) if names else MissingLLM()


def with_backup(build):
    """build(llm) -> runnable. Tries the available providers in LLM_ORDER, one after another."""
    names = available_providers()
    if not names:
        return MissingLLM()
    runnables = [build(PROVIDERS[n]()) for n in names]
    return runnables[0].with_fallbacks(runnables[1:]) if len(runnables) > 1 else runnables[0]


def is_temporary(error: Exception) -> bool:
    text = str(error)
    return any(code in text for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


overload_retry = RetryPolicy(max_attempts=4, initial_interval=2.0, backoff_factor=2.0,
                             retry_on=is_temporary)