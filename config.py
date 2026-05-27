import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
    YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
    YANDEX_PROMPT_ID = os.getenv("YANDEX_PROMPT_ID")
    YANDEX_PROMPT_ID_VERIFIER = os.getenv("YANDEX_PROMPT_ID_VERIFIER")

    USE_PROXY = os.getenv("USE_PROXY", "False").lower() == "true"
    PROXY_URL = os.getenv("PROXY_URL", None)
    VERIFIER_ENABLED = os.getenv("VERIFIER_ENABLED", "true").lower() == "true"
    DATABASE_URL = os.getenv("DATABASE_URL")

    RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "2"))
    RATE_LIMIT_RPM   = int(os.getenv("RATE_LIMIT_RPM",   "5"))
    RATE_LIMIT_RPH   = int(os.getenv("RATE_LIMIT_RPH",   "30"))

    ADMIN_IDS: set[int] = set(
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    )
    RAG_DATA_PATH = os.getenv(
        "RAG_DATA_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm", "data", "ingredients.json")
    )
    INCI_DB_PATH = os.getenv(
        "INCI_DB_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm", "data", "inci_ingredients.json")
    )


config = Config()