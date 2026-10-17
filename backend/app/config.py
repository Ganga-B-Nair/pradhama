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
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))

    asr_model_size: str = os.getenv("ASR_MODEL_SIZE", "small")
    asr_device: str = os.getenv("ASR_DEVICE", "cpu")
    asr_timeout_seconds: int = int(os.getenv("ASR_TIMEOUT_SECONDS", "900"))

    bns_mode: str = os.getenv("BNS_MODE", "fixture")  # "fixture" | "live"
    insightlaw_base_url: str = os.getenv("INSIGHTLAW_BASE_URL", "https://insightlaw.in")
    insightlaw_timeout_seconds: float = float(os.getenv("INSIGHTLAW_TIMEOUT_SECONDS", "5"))

    cache_dir: str = os.getenv("CACHE_DIR", "../cache")
    # PUBLIC_BASE_URL: the frontend's LAN-reachable origin, encoded in the QR
    # code. A phone can't reach `localhost`, so set it to http://<LAN IP>:3000
    # before the demo (docs/HACKATHON_PLAN.md §6.6).
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000")
    # Golden-run cache (§9): when a model stage fails, reuse its last good output.
    demo_cache: bool = os.getenv("DEMO_CACHE", "0") == "1"
    code_version: str = os.getenv("CODE_VERSION", "dev")

    # Jurisdiction Lookup (Google Places + Kerala Police nearby-stations service).
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    kerala_police_base_url: str = os.getenv("KERALA_POLICE_BASE_URL", "https://ps.keralapolice.gov.in")
    jurisdiction_online: bool = os.getenv("JURISDICTION_ONLINE", "1") == "1"

    station_code: str = os.getenv("STATION_CODE", "KCPS")
    station_name: str = os.getenv("STATION_NAME", "Cyber Police Station, Kochi City")


settings = Settings()
