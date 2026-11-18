from config import GEMINI_API_KEY, GEMINI_MODEL, OPENAI_API_KEY, OPENAI_MODEL
from llm import ask_llm


if __name__ == "__main__":
    prompt = "In one sentence, explain what a SQL database is."

    print("\nGemini:")
    if GEMINI_API_KEY:
        print(ask_llm(prompt, provider="gemini", model=GEMINI_MODEL))
    else:
        print("Skipped because GEMINI_API_KEY is not configured.")

    print("\nOpenAI:")
    if OPENAI_API_KEY:
        print(ask_llm(prompt, provider="openai", model=OPENAI_MODEL))
    else:
        print("Skipped because OPENAI_API_KEY is not configured.")
