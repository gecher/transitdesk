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


def get_llm(temperature: float = 0):
    """The first provider in LLM_ORDER, without fallback (for quick tests)."""
    first = os.getenv("LLM_ORDER", "gemini,groq").split(",")[0].strip()
    return PROVIDERS[first](temperature)


def with_backup(build):
    """build(llm) -> runnable. Tries providers in LLM_ORDER, one after another."""
    names = [n.strip() for n in os.getenv("LLM_ORDER", "gemini,groq").split(",")]
    runnables = [build(PROVIDERS[n]()) for n in names]
    return runnables[0].with_fallbacks(runnables[1:]) if len(runnables) > 1 else runnables[0]
def is_temporary(error: Exception) -> bool:
    text = str(error)
    return any(code in text for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


overload_retry = RetryPolicy(max_attempts=4, initial_interval=2.0, backoff_factor=2.0,
                             retry_on=is_temporary)