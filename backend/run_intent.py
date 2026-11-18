from intent import understand_question


if __name__ == "__main__":
    question = "Which city generated the highest revenue last quarter?"
    result = understand_question(question)

    print("\nStructured intent:")
    print(result.model_dump_json(indent=2))
