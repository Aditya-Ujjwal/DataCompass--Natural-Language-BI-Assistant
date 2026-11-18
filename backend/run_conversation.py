from conversation import Conversation, rewrite_follow_up


if __name__ == "__main__":
    conversation = Conversation()

    first_question = "What was revenue in Delhi last quarter?"
    first_answer = "Delhi generated revenue of ₹190,000 last quarter."

    conversation.add_user_message(first_question)
    conversation.add_assistant_message(first_answer)

    follow_up = "What about Mumbai?"

    result = rewrite_follow_up(
        follow_up,
        conversation.get_history(),
    )

    print("\nPrevious question:")
    print(first_question)

    print("\nPrevious answer:")
    print(first_answer)

    print("\nFollow-up:")
    print(follow_up)

    print("\nRewritten standalone question:")
    print(result.rewritten_question)

    conversation.add_user_message(follow_up)

    print("\nConversation messages:")
    for message in conversation.get_history():
        print(f"{message.role}: {message.content}")
