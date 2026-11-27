from datetime import datetime, timezone
import logging
from typing import Any
import httpx
from app.config import settings

logger = logging.getLogger("cv_worker.api")


class BackendAPIClient:
    def __init__(self, base_url: str = settings.API_URL, token: str = settings.WORKER_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client: httpx.AsyncClient | None = None

    def _get_headers(self) -> dict[str, str]:
        # Always use latest token from settings
        return {
            "X-Worker-Token": settings.WORKER_TOKEN or self.token,
            "User-Agent": f"TableSense-CVWorker/{settings.AGENT_VERSION}",
        }

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(12.0, connect=6.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def send_events(self, events: list[dict[str, Any]]) -> tuple[bool, bool]:
        """Posts occupancy events to backend.

        Returns:
            (success: bool, is_fatal_client_error: bool)
        """
        if not events:
            return True, False

        url = f"{self.base_url}/api/v1/ingest/events"
        payload = {"events": events}

        try:
            client = await self.get_client()
            res = await client.post(url, json=payload, headers=self._get_headers())

            if res.status_code == 200:
                return True, False

            # Check if client error (validation failure / bad UUID / 400 / 422)
            if res.status_code in (400, 422):
                logger.error(
                    f"Fatal validation error posting events ({res.status_code}): {res.text}"
                )
                return False, True

            if res.status_code in (401, 403):
                logger.error(
                    f"Unauthorized ({res.status_code}) - invalid worker token. Please verify TS_WORKER_TOKEN."
                )
                return False, True

            logger.error(f"Backend returned HTTP {res.status_code}: {res.text}")
            return False, False

        except httpx.RequestError as e:
            logger.warning(f"Network error posting events to backend ({url}): {e}")
            return False, False
        except Exception as e:
            logger.error(f"Unexpected error in send_events: {e}")
            return False, False

    async def send_heartbeat(self, worker_id: str | None, cameras: list[dict[str, Any]]) -> bool:
        url = f"{self.base_url}/api/v1/ingest/heartbeat"
        payload: dict[str, Any] = {
            "worker_id": str(worker_id) if worker_id else None,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "agent_version": settings.AGENT_VERSION,
            "fps": settings.SAMPLE_FPS,
            "cpu_pct": 15.0,
            "gpu_pct": 20.0,
            "cameras": cameras,
        }

        try:
            client = await self.get_client()
            res = await client.post(url, json=payload, headers=self._get_headers())
            return res.status_code == 200
        except httpx.RequestError as e:
            logger.warning(f"Connection error sending heartbeat: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in send_heartbeat: {e}")
            return False

    async def fetch_config(self) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/v1/ingest/config"
        try:
            client = await self.get_client()
            res = await client.get(url, headers=self._get_headers())
            if res.status_code == 200:
                return res.json().get("data")
            if res.status_code in (401, 403):
                logger.error(
                    f"Worker authentication failed ({res.status_code}). Check TS_WORKER_TOKEN."
                )
            else:
                logger.warning(f"Failed to fetch config ({res.status_code}): {res.text}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Network error fetching config from backend: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in fetch_config: {e}")
            return None
