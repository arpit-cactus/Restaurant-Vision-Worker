# TableSense - Computer Vision Worker

> Autonomous edge computer vision worker for the **TableSense / Camsense** platform.  
> Processes RTSP camera feeds, evaluates table region occupancy with ray-casting polygons, applies debounce state machines, and buffers events in local SQLite for 100% offline resilience.

---

## ⚡ 1-Click Setup & Start (Recommended)

Just run the setup script:
```bash
./setup.sh
# or
./start.sh
```

This single command automatically:
1. Detects Python 3
2. Creates and activates an isolated virtual environment (`.venv`)
3. Installs and verifies dependencies from `requirements.txt`
4. Generates `.env` from `.env.example` if not present
5. Runs the unit test suite
6. Launches the worker engine

---

## 🛠 Manual Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 3. Run Worker
```bash
python app/main.py
```

### 4. Run Unit Tests
```bash
pytest -v
```

### 5. Docker Deployment
```bash
docker build -t tablesense-worker .
docker run -d --net=host --env-file .env tablesense-worker
```

---

## 🔒 Configuration & Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `TS_API_URL` | `http://127.0.0.1:8000` | Backend API base URL |
| `TS_WORKER_TOKEN` | `dev_worker_token_secret_12345` | Authentication token assigned to this worker node |
| `TS_HEARTBEAT_INTERVAL_SEC` | `15` | Telemetry & online health ping interval |
| `TS_CONFIG_POLL_INTERVAL_SEC` | `30` | Interval to pull updated table polygons and thresholds |
| `TS_SQLITE_PATH` | `/tmp/tablesense_worker_queue.db` | Persistent local buffer for offline queueing |
| `TS_SAMPLE_FPS` | `10.0` | Frame evaluation rate |
| `TS_SIMULATION_MODE` | `true` | Runs realistic guest dwell cycles without live RTSP feeds |
