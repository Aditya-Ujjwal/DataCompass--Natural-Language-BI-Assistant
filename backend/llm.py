try:
    from google import genai
except ImportError:
    from types import SimpleNamespace
    genai = SimpleNamespace(Client=None)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from config import GEMINI_API_KEY, GEMINI_MODEL, LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL


def _ask_gemini(prompt: str, model: str | None = None) -> str:
    if not GEMINI_API_KEY or genai is None or genai.Client is None:
        raise ValueError("GEMINI_API_KEY / Google GenAI SDK is not configured.")
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.chats.create(model=model or GEMINI_MODEL).send_message(prompt)
    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    return response.text.strip()


def _ask_openai(prompt: str, model: str | None = None) -> str:
    if not OPENAI_API_KEY or OpenAI is None:
        raise ValueError("OPENAI_API_KEY / OpenAI SDK is not configured.")
    response = OpenAI(api_key=OPENAI_API_KEY).responses.create(model=model or OPENAI_MODEL, input=prompt)
    if not response.output_text:
        raise RuntimeError("OpenAI returned an empty response.")
    return response.output_text.strip()


def ask_llm(prompt: str, model: str | None = None, provider: str | None = None) -> str:
    selected = (provider or LLM_PROVIDER).lower().strip()
    if selected == "gemini":
        return _ask_gemini(prompt, model)
    if selected == "openai":
        return _ask_openai(prompt, model)
    raise ValueError(f"Unsupported LLM provider: {selected}. Use 'gemini' or 'openai'.")
