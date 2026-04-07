import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SONNET_MODEL = "anthropic/claude-sonnet-4-20250514"
HAIKU_MODEL = "anthropic/claude-haiku-4-5-20251001"

DEPTH_CONFIG = {
    "shallow": {"questions_per_agent": 3, "total_rounds": 2},
    "medium": {"questions_per_agent": 5, "total_rounds": 4},
    "deep": {"questions_per_agent": 10, "total_rounds": 6},
    "abyss": {"questions_per_agent": -1, "total_rounds": -1},  # unlimited
}

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")


def get_llm(model: str, **kwargs) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base=OPENROUTER_BASE_URL,
        **kwargs,
    )
