from datetime import datetime, timezone
import logging
from typing import Any
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class BackendAPIClient:
    def __init__(self, base_url: str = settings.API_URL, token: str = settings.WORKER_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"X-Worker-Token": self.token}

    async def send_events(self, events: list[dict[str, Any]]) -> bool:
        if not events:
            return True

        url = f"{self.base_url}/api/v1/ingest/events"
        payload = {"events": events}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=self.headers)
                if res.status_code == 200:
                    return True
                logger.error(f"Failed to post events: {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.warning(f"Connection error posting events to backend: {e}")
            return False

    async def send_heartbeat(self, worker_id: str | None, cameras: list[dict[str, Any]]) -> bool:
        url = f"{self.base_url}/api/v1/ingest/heartbeat"
        payload: dict[str, Any] = {
            "worker_id": str(worker_id) if worker_id else "00000000-0000-0000-0000-000000000000",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "agent_version": settings.AGENT_VERSION,
            "fps": settings.SAMPLE_FPS,
            "cpu_pct": 15.0,
            "gpu_pct": 20.0,
            "cameras": cameras,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(url, json=payload, headers=self.headers)
                return res.status_code == 200
        except Exception as e:
            logger.warning(f"Error sending heartbeat: {e}")
            return False

    async def fetch_config(self) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/v1/ingest/config"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self.headers)
                if res.status_code == 200:
                    return res.json().get("data")
                return None
        except Exception as e:
            logger.warning(f"Error fetching config: {e}")
            return None
