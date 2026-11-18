from pprint import pprint

from assistant import run_assistant


if __name__ == "__main__":
    question = "Which city generated the highest revenue?"

    result = run_assistant(question)

    print("\nIntegrated assistant result:")
    pprint(result, sort_dicts=False)
