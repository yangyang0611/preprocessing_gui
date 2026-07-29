# NoCode ML Orchestrator

A no-code object-detection platform built on Flask. Upload raw images, build a
preprocessing pipeline, train a detector on a GPU-scheduled Docker container, watch
the loss curve live, then run inference — all from the browser, without writing code.

```
Upload images  →  Preprocess  →  Submit training job  →  Dashboard (live)  →  Inference
   /               /                  /train                /dashboard          /inference
```

---

## Features

### 1. Image Preprocessing (`/`)
Upload a folder of images (with optional YOLO-format `.txt` labels) and chain
preprocessing steps into a pipeline. Steps are drag-and-drop reorderable, and the
order matters — the pipeline is applied top to bottom.

| Operation | Options |
|-----------|---------|
| Resize | Custom width × height |
| Rotate | 90 / 180 / 270 degrees |
| Mirror | Horizontal flip |
| Add Noise | Gaussian / Brightness / Saturation |

The result is packaged as `processed/processed_dataset.zip`, which becomes a
selectable dataset on the training page.

### 2. Training Job Submission (`/train`)
Pick a model, tune hyperparameters, choose a priority, submit. The job goes into a
Redis priority queue and is dispatched when a GPU frees up.

**Model catalog** — two families, 9 architectures, 25 checkpoints:

| Family | Architectures |
|--------|---------------|
| YOLO | YOLOv5 (n/s/m/l/x) · YOLOv8 (n/s/m/l/x) · YOLOv9 (c/e) · YOLOv10 (n/s/m/b/l/x) · YOLO11 (n/s/m/l/x) |
| Transformer | RT-DETR (l/x) · YOLO-World v2 (s/m/l/x) |

**Tunable hyperparameters:** `epochs`, `batch_size`, `imgsz`, `lr0`, `optimizer`,
`patience`. **Priority:** High (1) / Medium (2) / Low (3).

### 3. Live Dashboard (`/dashboard`)
Polls every 3 seconds:

- **GPU panel** — per-device utilization, VRAM used/total, temperature, and which
  user currently holds the device
- **Queue panel** — pending job counts split by priority
- **Job table** — status badge, model, epochs, priority, owner, assigned GPU,
  submitted time; expandable rows for live container logs
- **Training progress** — per-epoch loss/mAP chart streamed from the running job's
  `results.csv`
- **Controls** — cancel a pending/running job, delete a finished job (removes its
  Redis record and `results/<job_id>/` artifacts)

### 4. Inference (`/inference`)
Run a trained or uploaded model against a single image and view the annotated
result with per-detection confidences.

Model sources:
- **Trained** — any completed job's `results/<job_id>/weights/best.pt`
- **Uploaded** — your own `.pt` file, uploaded and managed through the UI

Inference runs in a one-shot container built from the same training image, with an
adjustable confidence threshold.

### 5. Users
Demo-grade, username-only login (no password). A user record is created on first
login. Every job records its owner, so the dashboard can filter to "my jobs" and
the GPU panel can show who is occupying each device.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Web UI (Flask + Vanilla JS)              │
│  /           Preprocessing      /dashboard   Monitoring      │
│  /train      Job submission     /inference   Prediction      │
│  /login      Username login                                  │
└───────────────────────┬──────────────────────────────────────┘
                        │ REST API
┌───────────────────────▼──────────────────────────────────────┐
│                    Flask API Server (app.py)                  │
│  /api/auth/*     login / logout / me / users                 │
│  /api/jobs*      submit · list · status · cancel · logs      │
│  /api/models*    list · upload · delete                      │
│  /api/inference  run prediction on one image                 │
│  /api/resources  GPU status      /api/queue  queue depth     │
└──────┬────────────────────────────────┬──────────────────────┘
       │                                │
┌──────▼───────┐          ┌─────────────▼──────────────────────┐
│    Redis     │          │  Job Scheduler (daemon thread)      │
│ · priority   │◄────────►│  · polls queue every 5s             │
│   queues     │          │  · allocates GPU (optimistic lock)  │
│ · job hashes │          │  · launches training container      │
│ · gpu locks  │          │  · monitors exit → releases GPU     │
│ · users      │          │  · enforces job timeout             │
└──────────────┘          └─────────────┬──────────────────────┘
                                        │ docker-py SDK
                          ┌─────────────▼──────────────────────┐
                          │        Docker Engine                │
                          │  · ml-training:latest containers    │
                          │  · GPU device assignment            │
                          │  · memory / shm limits              │
                          └────────────────────────────────────┘
```

**Why this shape:** the Flask process never trains. It only enqueues. A background
scheduler thread owns the GPU→job mapping in Redis (via optimistic locking, so two
dispatch attempts can't grab the same device), and each job runs in its own
container with a hard memory cap. A crashed training run cannot take down the web
app, and killing a job is a `container.stop()` away.

---

## Prerequisites

- Python 3.10+
- Docker (with the daemon reachable at `/var/run/docker.sock`)
- NVIDIA GPU + driver — optional; falls back to CPU and a mocked single device
- [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for GPU access inside containers

```bash
# nvidia-container-toolkit (Ubuntu/Debian)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
```

---

## Quick Start

### Option A — Local

```bash
# 1. Dependencies
pip install -r requirements.txt

# 2. Redis
docker run -d -p 6379:6379 --name redis --restart unless-stopped redis:alpine

# 3. Training image (required — jobs and inference both run in it)
docker build -t ml-training:latest ./docker/training/

# 4. Flask
python app.py
```

### Option B — Docker Compose

```bash
docker build -t ml-training:latest ./docker/training/

# HOST_BASE_DIR must be the HOST path, so sibling training containers
# launched by the app can mount the same volumes correctly.
HOST_BASE_DIR=$(pwd) docker compose -f docker/docker-compose.yml up --build
```

Then open `http://localhost:5000`. Log in with any username
(lowercase letters/digits/`_`/`-`, 2–32 chars) — the account is created on the spot.

| URL | Page | Auth |
|-----|------|------|
| `/` | Image preprocessing | public |
| `/login` | Username login | public |
| `/train` | Submit a training job | required |
| `/dashboard` | Monitor jobs & GPU | required |
| `/inference` | Run predictions | required |

### Try it without your own data

```bash
python scripts/make_demo_dataset.py    # generates a small synthetic YOLO dataset
```

Then upload it on `/`, run any preprocessing step, submit a `yolov8n.pt` job with
`epochs=1`. On CPU that finishes in a few minutes.

---

## Configuration

All settings live in `config.py`, overridable by environment variable where noted.

| Setting | Default | Meaning |
|---------|---------|---------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection (env) |
| `GPU_COUNT` | `1` | Devices to assume when NVML is unavailable |
| `GPU_MEMORY_LIMIT` | `6g` | Per-container memory cap |
| `JOB_TIMEOUT_MINUTES` | `120` | Auto-kill a job past this runtime |
| `SCHEDULER_INTERVAL_SECONDS` | `5` | Dispatch loop period |
| `TRAINING_IMAGE` | `ml-training:latest` | Image used for training *and* inference |
| `HOST_BASE_DIR` | repo root | Host path for volume mounts (env) — **must** be set when Flask itself runs in a container |

---

## Project Structure

```
preprocessing_gui/
├── app.py                       # Flask app: preprocessing + all APIs + scheduler boot
├── config.py                    # Centralized settings
├── requirements.txt
├── Dockerfile                   # Flask app image
│
├── job_manager/
│   ├── queue_manager.py         # Redis priority queue: submit/dequeue/cancel/delete
│   ├── gpu_manager.py           # NVML polling + GPU allocation with optimistic locking
│   ├── docker_manager.py        # Training container lifecycle & log streaming
│   ├── scheduler.py             # Background thread: dispatch, monitor, timeout, cleanup
│   ├── inference_manager.py     # Model discovery, upload, one-shot inference containers
│   └── user_manager.py          # Username registry in Redis
│
├── docker/
│   ├── training/
│   │   ├── Dockerfile           # ultralytics base + train.py
│   │   └── train.py             # Runs inside the container; reports progress to Redis
│   └── docker-compose.yml       # Redis + Flask
│
├── templates/                   # index / login / train / dashboard / inference
├── static/                      # matching JS + shared CSS
│
└── scripts/
    ├── make_demo_dataset.py     # Synthetic YOLO dataset generator
    └── predict.py               # Inference entrypoint executed inside the container
```

### Runtime directories (gitignored, created on demand)

| Path | Contents |
|------|----------|
| `uploads/` | Raw uploaded images, cleared per session |
| `processed/` | Preprocessed output + `processed_dataset.zip` |
| `models/` | Pretrained `.pt` checkpoints, auto-downloaded by Ultralytics |
| `results/<job_id>/` | Per-job training output: `weights/best.pt`, `results.csv` |
| `user_models/<id>/` | User-uploaded `.pt` weights + `meta.json` |
| `inference_runs/<req_id>/` | Annotated prediction images |

---

## API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/login` | Log in / create user — `{"username": "..."}` |
| `POST` | `/api/auth/logout` | Clear session |
| `GET` | `/api/auth/me` | Current user |
| `GET` | `/api/auth/users` | All known users |

### Datasets & Jobs
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/datasets` | Available dataset zips |
| `POST` | `/api/jobs` | Submit a training job *(auth)* |
| `GET` | `/api/jobs` | List jobs — `?owner=me` to filter to your own |
| `GET` | `/api/jobs/<id>` | Single job status |
| `DELETE` | `/api/jobs/<id>` | Cancel a running job / delete a finished one |
| `GET` | `/api/jobs/<id>/logs` | Container logs |
| `GET` | `/api/jobs/<id>/metrics` | Per-epoch metrics parsed from `results.csv` |

### Models & Inference
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/models` | Trained + uploaded models |
| `POST` | `/api/models/upload` | Upload a `.pt` (multipart: `model`, `name`) |
| `DELETE` | `/api/models/<id>` | Delete an uploaded model |
| `POST` | `/api/inference` | Predict (multipart: `model_id`, `image`, `conf`) |

### Resources
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/resources` | Per-GPU utilization, memory, temperature, holder |
| `GET` | `/api/queue` | Pending counts per priority |

**Submit a job:**
```bash
curl -X POST http://localhost:5000/api/jobs \
  -H "Content-Type: application/json" -b cookies.txt \
  -d '{"model":"yolov8n.pt","epochs":10,"batch_size":16,"imgsz":640,
       "dataset":"processed_dataset.zip","priority":"high"}'
# → {"job_id": "…", "status": "pending"}
```

**Run inference:**
```bash
curl -X POST http://localhost:5000/api/inference \
  -F "model_id=<job_id or uploaded model id>" \
  -F "image=@test.jpg" -F "conf=0.25"
```

---

## Job Lifecycle

```
pending ──dispatch──► running ──exit 0───► completed
   │                     │
   │                     └──exit ≠ 0 ────► failed
   │                     └──timeout ─────► failed
   └──cancel──► cancelled
```

Redis keys: `job:<job_id>` (hash), the three priority queues, `gpu:<id>:status` /
`:job` / `:owner`, `users` (set) and `user:<name>` (hash).

---

## No GPU?

Everything still runs:

- `gpu_manager` catches the missing NVML and reports a single mocked device
- Training containers launch without `device_requests`, so Ultralytics uses CPU
- Use `yolov8n.pt` with `epochs=1` for a demo that finishes in minutes

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Web framework | Flask 3 |
| Queue & state | Redis |
| Container orchestration | docker-py SDK |
| GPU monitoring | nvidia-ml-py (pynvml) |
| Training / inference | Ultralytics (YOLOv5–YOLO11, RT-DETR, YOLO-World) |
| Frontend | Bootstrap 4 + Vanilla JS |

---

## Notes & Limitations

This is a demo, not a production system:

- Login is username-only, with no password or authorization checks — any logged-in
  user can see and cancel any job
- Job state lives entirely in Redis; there is no database and no backup
- The app needs access to the Docker socket, which is equivalent to host root
- The scheduler is a single in-process thread — running multiple Flask workers
  would dispatch each job more than once
