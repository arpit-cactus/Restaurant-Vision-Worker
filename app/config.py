import os
from pydantic import BaseModel


class WorkerSettings(BaseModel):
    API_URL: str = os.getenv("TS_API_URL", "http://127.0.0.1:8000")
    WORKER_TOKEN: str = os.getenv("TS_WORKER_TOKEN", "dev_worker_token_secret_12345")
    AGENT_VERSION: str = "1.0.0"
    HEARTBEAT_INTERVAL_SEC: int = int(os.getenv("TS_HEARTBEAT_INTERVAL_SEC", "15"))
    CONFIG_POLL_INTERVAL_SEC: int = int(os.getenv("TS_CONFIG_POLL_INTERVAL_SEC", "30"))
    SQLITE_PATH: str = os.getenv("TS_SQLITE_PATH", "/tmp/tablesense_worker_queue.db")
    SAMPLE_FPS: float = float(os.getenv("TS_SAMPLE_FPS", "10.0"))
    SIMULATION_MODE: bool = os.getenv("TS_SIMULATION_MODE", "true").lower() in ("true", "1", "yes")


settings = WorkerSettings()
