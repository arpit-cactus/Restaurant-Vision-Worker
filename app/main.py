import asyncio
from datetime import datetime, timezone
import logging
import os
import random
import signal
import sys
from typing import Any

# Ensure parent directory (cv-worker) is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api_client import BackendAPIClient
from app.config import settings
from app.local_queue import SQLiteEventQueue
from app.state_machine import TableStateMachine

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [cv_worker] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cv_worker")


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm to test whether point (x, y) is inside polygon."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    try:
        p1x, p1y = float(polygon[0][0]), float(polygon[0][1])
        for i in range(1, n + 1):
            p2x, p2y = float(polygon[i % n][0]), float(polygon[i % n][1])
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
    except (IndexError, TypeError, ValueError):
        return False
    return inside


class CVWorkerEngine:
    def __init__(self):
        self.queue = SQLiteEventQueue(settings.SQLITE_PATH)
        self.client = BackendAPIClient()
        self.running = False
        self.flush_trigger = asyncio.Event()

        # Config state
        self.worker_id: str | None = None
        self.restaurant_id: str | None = None
        self.seat_threshold_sec: int = 20
        self.leave_threshold_sec: int = 60
        self.cameras: list[dict[str, Any]] = []

        # Table state machines: table_id -> TableStateMachine
        self.state_machines: dict[str, TableStateMachine] = {}
        # Mapped camera regions: camera_id -> list of {table_id, polygon}
        self.camera_regions: dict[str, list[dict[str, Any]]] = {}

        # Simulation occupant tracking for demo/dev mode
        self.simulated_occupants: dict[str, int] = {}
        self.simulated_cycle_end: dict[str, float] = {}

    async def update_config(self) -> bool:
        """Fetches the latest configuration from the backend."""
        config = await self.client.fetch_config()
        if not config:
            return False

        self.restaurant_id = str(config.get("restaurant_id"))
        if config.get("worker_id"):
            self.worker_id = str(config.get("worker_id"))
        self.seat_threshold_sec = config.get("seat_threshold_sec", 20)
        self.leave_threshold_sec = config.get("leave_threshold_sec", 60)
        self.cameras = config.get("cameras", [])

        # Sync table state machines
        seen_tables: set[str] = set()
        new_camera_regions: dict[str, list[dict[str, Any]]] = {}

        for cam in self.cameras:
            cam_id = str(cam.get("camera_id"))
            regions = cam.get("regions", [])
            new_camera_regions[cam_id] = regions

            for reg in regions:
                t_id = str(reg.get("table_id"))
                seen_tables.add(t_id)
                if t_id not in self.state_machines:
                    self.state_machines[t_id] = TableStateMachine(
                        restaurant_id=self.restaurant_id,
                        table_id=t_id,
                        seat_threshold_sec=self.seat_threshold_sec,
                        leave_threshold_sec=self.leave_threshold_sec,
                    )
                    logger.info(f"Initialized state machine for table {t_id}")
                else:
                    self.state_machines[t_id].seat_threshold_sec = self.seat_threshold_sec
                    self.state_machines[t_id].leave_threshold_sec = self.leave_threshold_sec

        # Clean up state machines for tables that are no longer mapped
        for old_t_id in list(self.state_machines.keys()):
            if old_t_id not in seen_tables:
                del self.state_machines[old_t_id]
                self.simulated_occupants.pop(old_t_id, None)
                self.simulated_cycle_end.pop(old_t_id, None)

        self.camera_regions = new_camera_regions
        logger.info(
            f"Config synced: restaurant={self.restaurant_id}, cameras={len(self.cameras)}, "
            f"active_tables={len(self.state_machines)}"
        )
        return True

    async def heartbeat_loop(self) -> None:
        """Sends periodic heartbeats to maintain worker and camera online status."""
        while self.running:
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                camera_health_list = [
                    {
                        "camera_id": str(cam.get("camera_id")),
                        "status": "online",
                        "last_frame_at": now_iso,
                    }
                    for cam in self.cameras
                    if cam.get("camera_id")
                ]

                success = await self.client.send_heartbeat(
                    worker_id=self.worker_id,
                    cameras=camera_health_list,
                )
                if success:
                    logger.debug("Heartbeat acknowledged by backend")
                else:
                    logger.warning("Heartbeat delivery failed (backend unreachable or token issue)")
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")

            await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SEC)

    async def config_poll_loop(self) -> None:
        """Periodically polls backend for camera and ROI configuration updates."""
        while self.running:
            try:
                await self.update_config()
            except Exception as e:
                logger.error(f"Error in config poll loop: {e}")

            await asyncio.sleep(settings.CONFIG_POLL_INTERVAL_SEC)

    async def queue_flush_loop(self) -> None:
        """Continuously flushes buffered events from SQLite to backend with dead-letter protection."""
        while self.running:
            try:
                pending = self.queue.get_pending(limit=50)
                if pending:
                    success, is_fatal_client_error = await self.client.send_events(pending)
                    event_ids = [e["event_id"] for e in pending]

                    if success:
                        self.queue.remove(event_ids)
                        logger.info(f"Successfully flushed {len(pending)} events to backend")
                    elif is_fatal_client_error:
                        # 400 or 422: Poison-pill events rejected by schema or invalid table reference
                        logger.error(
                            f"Moving {len(event_ids)} permanently unprocessable events to dead-letter queue"
                        )
                        self.queue.mark_failed(event_ids, "Backend 4xx client validation error")
                    else:
                        # 5xx or network disconnect: increment retries and backoff
                        self.queue.increment_retries(event_ids)
                        logger.warning(
                            f"Network retry scheduled for {len(pending)} buffered events"
                        )
                        await asyncio.sleep(3.0)
                        continue
            except Exception as e:
                logger.error(f"Error in queue flush loop: {e}")

            try:
                # Wait for next event trigger or fallback interval
                await asyncio.wait_for(self.flush_trigger.wait(), timeout=1.5)
                self.flush_trigger.clear()
            except asyncio.TimeoutError:
                pass

    async def detection_loop(self) -> None:
        """Continuous computer vision detection / occupancy evaluation loop."""
        loop_interval = max(0.5, 1.0 / settings.SAMPLE_FPS)

        while self.running:
            try:
                now = datetime.now(timezone.utc)
                now_ts = now.timestamp()

                # Process detections for each camera and mapped region
                for cam in self.cameras:
                    cam_id = str(cam.get("camera_id"))
                    regions = self.camera_regions.get(cam_id, [])

                    for reg in regions:
                        table_id = str(reg.get("table_id"))
                        poly = reg.get("polygon", [])
                        sm = self.state_machines.get(table_id)
                        if not sm:
                            continue

                        # Determine person count
                        if settings.SIMULATION_MODE or not cam.get("rtsp_url"):
                            # Simulation engine: cycles tables through realistic seated / free patterns
                            cycle_end = self.simulated_cycle_end.get(table_id, 0)
                            if now_ts >= cycle_end:
                                # Start new state cycle
                                if sm.current_state == "free":
                                    # Sit guests
                                    p_count = random.choice([2, 3, 4])
                                    self.simulated_occupants[table_id] = p_count
                                    # Stay for 25-45 seconds
                                    self.simulated_cycle_end[table_id] = now_ts + random.randint(25, 45)
                                else:
                                    # Vacate table
                                    self.simulated_occupants[table_id] = 0
                                    # Free for 30-60 seconds
                                    self.simulated_cycle_end[table_id] = now_ts + random.randint(30, 60)

                            person_count = self.simulated_occupants.get(table_id, 0)
                        else:
                            # Direct RTSP detection fallback (if opencv available)
                            person_count = 0

                        # Update debounce state machine
                        event = sm.update(person_count=person_count, timestamp=now, camera_id=cam_id)
                        if event:
                            logger.info(
                                f"Detection Transition: Table {table_id} {event['from_state']} -> "
                                f"{event['to_state']} (party: {event['person_count']})"
                            )
                            self.queue.enqueue(event)
                            self.flush_trigger.set()

            except Exception as e:
                logger.error(f"Error in detection loop: {e}")

            await asyncio.sleep(loop_interval)

    async def start(self) -> None:
        """Starts all worker asynchronous loops."""
        logger.info("Initializing TableSense CV Worker Engine...")
        self.running = True

        # Initial config attempt with backoff
        for attempt in range(1, 11):
            logger.info(f"Connecting to backend ({settings.API_URL}) - attempt {attempt}/10...")
            if await self.update_config():
                break
            await asyncio.sleep(min(5.0, 1.0 * attempt))

        logger.info(
            f"Worker started. Pending events in local queue: {self.queue.count()}. "
            f"Simulation Mode: {settings.SIMULATION_MODE}"
        )

        # Launch all concurrent loops
        await asyncio.gather(
            self.heartbeat_loop(),
            self.config_poll_loop(),
            self.queue_flush_loop(),
            self.detection_loop(),
        )

    async def stop(self) -> None:
        logger.info("Stopping CV Worker Engine...")
        self.running = False
        self.flush_trigger.set()
        await self.client.close()


async def main() -> None:
    engine = CVWorkerEngine()

    def handle_signal():
        asyncio.create_task(engine.stop())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    try:
        await engine.start()
    except asyncio.CancelledError:
        pass
    finally:
        await engine.stop()
        logger.info("CV Worker shut down gracefully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
