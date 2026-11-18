from llm import ask_llm


if __name__ == "__main__":
    prompt = "In one sentence, explain what a SQL database is."
    answer = ask_llm(prompt)

    print("\nLLM response:")
    print(answer)
