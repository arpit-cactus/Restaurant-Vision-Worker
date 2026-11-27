import os
from pathlib import Path
from pydantic import BaseModel


def load_dotenv_file(dotenv_path: Path | None = None) -> None:
    """Lightweight standard-library .env loader that populates os.environ

    if the key is not already defined in the environment.
    """
    if dotenv_path is None:
        # Search current working directory, then script directory, then parent directory
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent / ".env",
            Path(__file__).resolve().parent / ".env",
        ]
        for candidate in candidates:
            if candidate.is_file():
                dotenv_path = candidate
                break

    if dotenv_path and dotenv_path.is_file():
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
        except Exception:
            pass


# Automatically load .env before settings class initialization
load_dotenv_file()


class WorkerSettings(BaseModel):
    API_URL: str = os.getenv("TS_API_URL", "http://127.0.0.1:8000")
    WORKER_TOKEN: str = os.getenv("TS_WORKER_TOKEN", "dev_worker_token_secret_12345")
    AGENT_VERSION: str = "1.0.0"
    HEARTBEAT_INTERVAL_SEC: int = int(os.getenv("TS_HEARTBEAT_INTERVAL_SEC", "15"))
    CONFIG_POLL_INTERVAL_SEC: int = int(os.getenv("TS_CONFIG_POLL_INTERVAL_SEC", "30"))
    SQLITE_PATH: str = os.getenv("TS_SQLITE_PATH", "/tmp/tablesense_worker_queue.db")
    SAMPLE_FPS: float = float(os.getenv("TS_SAMPLE_FPS", "10.0"))
    SIMULATION_MODE: bool = os.getenv("TS_SIMULATION_MODE", "true").lower() in ("true", "1", "yes")

    def reload_from_env(self) -> None:
        """Allows re-reading settings if .env or environment variables changed."""
        load_dotenv_file()
        self.API_URL = os.getenv("TS_API_URL", self.API_URL)
        self.WORKER_TOKEN = os.getenv("TS_WORKER_TOKEN", self.WORKER_TOKEN)
        self.HEARTBEAT_INTERVAL_SEC = int(os.getenv("TS_HEARTBEAT_INTERVAL_SEC", str(self.HEARTBEAT_INTERVAL_SEC)))
        self.CONFIG_POLL_INTERVAL_SEC = int(os.getenv("TS_CONFIG_POLL_INTERVAL_SEC", str(self.CONFIG_POLL_INTERVAL_SEC)))
        self.SQLITE_PATH = os.getenv("TS_SQLITE_PATH", self.SQLITE_PATH)
        self.SAMPLE_FPS = float(os.getenv("TS_SAMPLE_FPS", str(self.SAMPLE_FPS)))
        self.SIMULATION_MODE = os.getenv("TS_SIMULATION_MODE", str(self.SIMULATION_MODE)).lower() in ("true", "1", "yes")


settings = WorkerSettings()
