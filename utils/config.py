import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass
class GroqConfig:
    api_key: str | None = os.getenv("GROQ_API_KEY")
    model: str = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    temperature: float = float(os.getenv("GROQ_TEMPERATURE", "0.2"))


@dataclass
class NewsConfig:
    api_key: str | None = os.getenv("NEWS_API_KEY")
    provider: str = os.getenv("NEWS_PROVIDER", "newsapi")  # or rss


@dataclass
class AppConfig:
    groq: GroqConfig = GroqConfig()
    news: NewsConfig = NewsConfig()


def get_app_config() -> AppConfig:
    return AppConfig()

