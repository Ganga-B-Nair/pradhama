import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "trace_demo")

    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "trace-local-dev")

    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")

    asr_model_size: str = os.getenv("ASR_MODEL_SIZE", "small")
    asr_device: str = os.getenv("ASR_DEVICE", "cpu")

    bns_mode: str = os.getenv("BNS_MODE", "fixture")  # "fixture" | "live"
    insightlaw_base_url: str = os.getenv("INSIGHTLAW_BASE_URL", "https://insightlaw.in")
    insightlaw_timeout_seconds: float = float(os.getenv("INSIGHTLAW_TIMEOUT_SECONDS", "5"))

    evidence_dir: str = os.getenv("EVIDENCE_DIR", "../evidence")
    # PUBLIC_BASE_URL: the frontend's LAN-reachable origin. Used only for the QR
    # verification link, since /verify is a frontend page (frontend/app/verify).
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000")
    # API_PUBLIC_BASE_URL: this backend's own LAN-reachable origin. Used for the
    # export HTML/JSON/certificate links, which are served directly by FastAPI
    # (Jinja2 + qrcode) so printing works with no frontend export page required.
    api_public_base_url: str = os.getenv("API_PUBLIC_BASE_URL", "http://localhost:8000")
    demo_cache: bool = os.getenv("DEMO_CACHE", "0") == "1"


settings = Settings()
