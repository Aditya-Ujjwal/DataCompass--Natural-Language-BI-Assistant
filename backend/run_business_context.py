from business_context import context_to_prompt_text, load_business_context


if __name__ == "__main__":
    context = load_business_context()

    print("\nBusiness / Database Context")
    print("=" * 50)
    print(context_to_prompt_text(context))
