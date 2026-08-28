from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()


def pick_llm(level: str) -> ChatGoogleGenerativeAI:
    """
    Select the Gemini model according to the required reasoning level.

    Args:
        level: "low", "medium", or "high".

    Returns:
        Configured ChatGoogleGenerativeAI instance.
    """
    level = level.lower()

    if level == "low":
        return ChatGoogleGenerativeAI(
            model="gemini-3.5-flash-lite"
        )
    
    elif level == "medium":
            return ChatGoogleGenerativeAI(
                model="gemini-3.5-flash"
            )

    elif level == "high":
        return ChatGoogleGenerativeAI(
            model="gemini-3.7-flash"
        )

    raise ValueError(
        f"Unsupported level: {level}. Expected 'low', 'medium', or 'high'."
    )