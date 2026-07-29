# No-code-lite ML Training Orchestration — CLAUDE.md

## 專案簡介

在現有的圖像預處理 GUI（Flask + YOLO dataset preprocessing）基礎上，擴充成一個完整的
**No-code ML Training Orchestration 平台**，讓使用者無需寫程式碼即可：

1. 上傳並預處理資料集（已完成）
2. 設定 training 參數並提交 ML 訓練任務
3. 透過 priority queue 非同步管理多個任務
4. 自動分配 GPU 資源、隔離各 training container
5. 在 Dashboard 即時監控任務狀態與 GPU 使用率

---

## 系統架構

```
┌─────────────────────────────────────────────────────────┐
│                    Web UI (Flask + JS)                   │
│   Page 1: Image Preprocessing  (index.html) ← 已有      │
│   Page 2: Training Job Submit  (train.html)  ← 新增     │
│   Page 3: Job Dashboard        (dashboard.html) ← 新增  │
└────────────────────┬────────────────────────────────────┘
                     │ REST API (Flask)
┌────────────────────▼────────────────────────────────────┐
│                  Flask API Server (app.py)               │
│   /api/jobs        - 提交、查詢、取消任務               │
│   /api/resources   - GPU 資源狀態                        │
│   /api/queue       - 佇列狀態                            │
└──────┬───────────────────────────┬──────────────────────┘
       │                           │
┌──────▼──────┐         ┌──────────▼──────────────────────┐
│   Redis     │         │   Job Scheduler (scheduler.py)   │
│  - Priority │◄────────│   - 讀取 queue、分配 GPU         │
│    Queue    │         │   - 啟動 Docker container        │
│  - Job      │         │   - 監控 job 狀態回寫 Redis      │
│    Status   │         └──────────┬──────────────────────┘
└─────────────┘                    │ docker-py SDK
                         ┌──────────▼──────────────────────┐
                         │   Docker Engine                  │
                         │   - training containers (YOLOv8) │
                         │   - GPU device assignment        │
                         │   - resource limits (mem/cpu)    │
                         └─────────────────────────────────┘
```

---

## 技術選型

| 元件 | 選擇 | 原因 |
|------|------|------|
| Web Framework | Flask (現有) | 維持一致性 |
| 任務佇列 | Redis + `rq` (Redis Queue) | 輕量、支援 priority、易於整合 |
| 容器管理 | `docker` Python SDK | 直接控制 Docker daemon |
| GPU 監控 | `pynvml` / `nvidia-smi` subprocess | 取得 GPU 使用率與記憶體 |
| ML Training | YOLOv8 (Ultralytics) | 與現有 YOLO dataset 格式一致 |
| 前端 | 現有 Bootstrap 4 + Vanilla JS | 維持一致性 |
| 資料儲存 | Redis (job metadata) + 本地檔案系統 | Demo 用途，無需資料庫 |

---

## 目錄結構（目標）

```
preprocessing_gui/
├── app.py                        # 已有：圖像預處理 API + 新增 job API 路由
├── config.py                     # 新增：設定檔（Redis URL、GPU 數量等）
├── requirements.txt              # 新增：所有依賴
│
├── job_manager/                  # 新增：核心 orchestration 模組
│   ├── __init__.py
│   ├── queue_manager.py          # Priority queue 操作（enqueue/dequeue/status）
│   ├── gpu_manager.py            # GPU 資源分配與監控
│   ├── docker_manager.py         # Docker container 生命週期管理
│   └── scheduler.py              # 主排程迴圈（背景 thread/process）
│
├── worker/
│   └── training_worker.py        # RQ worker 入口（被 scheduler 啟動）
│
├── docker/
│   ├── training/
│   │   ├── Dockerfile            # YOLOv8 training image
│   │   └── train.py              # container 內的 training 腳本
│   └── docker-compose.yml        # 一鍵啟動完整服務（Flask + Redis）
│
├── templates/
│   ├── index.html                # 已有：預處理頁面
│   ├── train.html                # 新增：提交 training job 頁面
│   └── dashboard.html            # 新增：job 監控 dashboard
│
├── static/
│   ├── index.css                 # 已有
│   ├── index.js                  # 已有
│   ├── train.js                  # 新增
│   └── dashboard.js              # 新增
│
└── CLAUDE.md                     # 本文件
```

---

## 完整 TODO List 與執行步驟

### Phase 0：環境準備

- [ ] **0.1** 確認 Docker daemon 已啟動，且有 `docker` CLI 可用
- [ ] **0.2** 確認是否有 NVIDIA GPU + Docker NVIDIA runtime（無 GPU 則 mock）
- [ ] **0.3** 建立 `requirements.txt`，包含所有新依賴：
  ```
  flask, flask-cors,          # 已有
  opencv-python, pillow,      # 已有
  numpy,                      # 已有
  redis, rq,                  # 任務佇列
  docker,                     # Docker SDK
  pynvml,                     # GPU 監控
  ultralytics,                # YOLOv8（可選，只在 container 內）
  ```
- [ ] **0.4** 在本機啟動 Redis：
  ```bash
  docker run -d -p 6379:6379 --name redis redis:alpine
  ```
- [ ] **0.5** 建立 `config.py`，統一管理設定

---

### Phase 1：Priority Queue 系統

**目標**：能把 training job 放進 priority queue，並查詢佇列狀態。

- [ ] **1.1** 實作 `job_manager/queue_manager.py`
  - `submit_job(job_config, priority)` → 放入 Redis 佇列，回傳 `job_id`
  - `get_job_status(job_id)` → 查詢 job 狀態（pending / running / done / failed）
  - `list_jobs()` → 列出所有 job 及其狀態
  - `cancel_job(job_id)` → 取消排隊中的 job
  - Priority levels: `high(1)`, `medium(2)`, `low(3)`

- [ ] **1.2** Job metadata 結構（儲存在 Redis hash）：
  ```json
  {
    "job_id": "uuid",
    "user": "demo_user",
    "status": "pending|running|completed|failed",
    "priority": 1,
    "dataset": "processed_dataset.zip",
    "model": "yolov8n",
    "epochs": 10,
    "gpu_id": null,
    "submitted_at": "2026-02-28T10:00:00",
    "started_at": null,
    "finished_at": null,
    "logs": "",
    "container_id": null
  }
  ```

---

### Phase 2：GPU 資源管理

**目標**：知道哪些 GPU 可用，並分配給 job。

- [ ] **2.1** 實作 `job_manager/gpu_manager.py`
  - `get_gpu_count()` → 回傳可用 GPU 數量（無 GPU 返回 1 作為 mock）
  - `get_gpu_status()` → 回傳每張 GPU 的使用率、記憶體、溫度
  - `allocate_gpu()` → 找到空閒 GPU，標記為 occupied，回傳 `gpu_id`
  - `release_gpu(gpu_id)` → 釋放 GPU
  - GPU 狀態存於 Redis，key: `gpu:{gpu_id}:status`

- [ ] **2.2** Mock 模式（無 NVIDIA GPU）：
  - 以 CPU 模擬 1 張「GPU」
  - `pynvml` 不可用時自動 fallback 到 mock

---

### Phase 3：Docker Container 管理

**目標**：為每個 training job 啟動獨立 container，完成後自動清理。

- [ ] **3.1** 建立 `docker/training/Dockerfile`
  ```dockerfile
  FROM ultralytics/ultralytics:latest
  WORKDIR /workspace
  COPY train.py .
  ENTRYPOINT ["python", "train.py"]
  ```

- [ ] **3.2** 建立 `docker/training/train.py`（container 內部腳本）
  - 接收環境變數：`MODEL`, `EPOCHS`, `DATASET_PATH`, `JOB_ID`
  - 執行 YOLOv8 training
  - 完成後寫入結果到 `/workspace/results/`

- [ ] **3.3** 實作 `job_manager/docker_manager.py`
  - `start_training_container(job_id, gpu_id, config)` → 啟動 container
    - Mount dataset 目錄
    - 設定環境變數傳入 training 參數
    - 指定 GPU device（`device_requests`）
    - 設定 memory limit（resource isolation）
  - `get_container_logs(container_id)` → 取得即時 log
  - `stop_container(container_id)` → 停止並移除 container
  - `cleanup_finished_containers()` → 清理已完成的 container

- [ ] **3.4** Build training image：
  ```bash
  docker build -t ml-training:latest ./docker/training/
  ```

---

### Phase 4：Job Scheduler（排程迴圈）

**目標**：背景持續運行，從 queue 取出 job 並分配資源啟動 container。

- [ ] **4.1** 實作 `job_manager/scheduler.py`
  - 以 threading.Thread 在 Flask 啟動時背景運行
  - 主迴圈（每 5 秒）：
    1. 從 priority queue 取出最高優先 pending job
    2. 呼叫 `gpu_manager.allocate_gpu()` 嘗試分配 GPU
    3. 若有可用 GPU → 呼叫 `docker_manager.start_training_container()`
    4. 更新 job status 為 `running`
    5. 監控 running containers，完成後更新 status 為 `completed/failed`，釋放 GPU

- [ ] **4.2** 錯誤處理：
  - Container 啟動失敗 → status 設為 `failed`，GPU 釋放
  - Job timeout 機制（超過 N 分鐘自動停止）

---

### Phase 5：REST API 擴充

**目標**：在 `app.py` 新增 job 管理相關 API endpoint。

- [ ] **5.1** 新增以下路由：

  | Method | Endpoint | 功能 |
  |--------|----------|------|
  | POST | `/api/jobs` | 提交新 training job |
  | GET | `/api/jobs` | 列出所有 jobs |
  | GET | `/api/jobs/<job_id>` | 查詢單一 job 狀態 |
  | DELETE | `/api/jobs/<job_id>` | 取消 job |
  | GET | `/api/jobs/<job_id>/logs` | 取得 container logs |
  | GET | `/api/resources` | GPU 資源狀態 |
  | GET | `/api/queue` | 佇列狀態（各 priority 的等待數） |

- [ ] **5.2** 在 Flask 啟動時初始化 scheduler thread

---

### Phase 6：Web UI — Training Job 提交頁面

**目標**：`train.html` — 讓使用者填寫 training 參數並提交任務。

- [ ] **6.1** UI 元件：
  - 選擇 dataset（從已上傳/處理的 zip 中選擇）
  - 選擇 model（YOLOv8n / YOLOv8s / YOLOv8m）
  - 設定 epochs（數字輸入）
  - 設定 batch size
  - 選擇 priority（High / Medium / Low）
  - 提交按鈕
  - 提交成功後顯示 `job_id`，並提供連結到 Dashboard

- [ ] **6.2** 實作 `static/train.js`
  - `submitJob()` → POST `/api/jobs`
  - 顯示提交結果與 job_id

- [ ] **6.3** 在 `index.html` 與 `train.html` 加入 navbar 導覽

---

### Phase 7：Web UI — Dashboard 監控頁面

**目標**：`dashboard.html` — 即時顯示所有 jobs 與 GPU 資源狀態。

- [ ] **7.1** GPU Resource Panel：
  - 每張 GPU 的卡片，顯示：GPU 編號、使用率（%）、記憶體（已用/總量）、溫度
  - 顏色指示（綠/黃/紅）

- [ ] **7.2** Job Queue Panel：
  - 分三欄：High / Medium / Low priority 等待中的任務數

- [ ] **7.3** Job List Table：
  - 欄位：Job ID、狀態、模型、Epochs、Priority、提交時間、GPU
  - 狀態 badge（pending=灰、running=藍、completed=綠、failed=紅）
  - 每列可展開看 logs
  - Cancel 按鈕（pending/running 狀態可用）

- [ ] **7.4** 實作 `static/dashboard.js`
  - 每 3 秒 polling `/api/jobs` 與 `/api/resources`
  - 動態更新表格與 GPU 卡片
  - `cancelJob(job_id)` → DELETE `/api/jobs/<job_id>`
  - `fetchLogs(job_id)` → GET `/api/jobs/<job_id>/logs`

---

### Phase 8：Docker Compose 整合

**目標**：一個指令啟動完整服務。

- [ ] **8.1** 建立 `docker/docker-compose.yml`：
  ```yaml
  services:
    redis:
      image: redis:alpine
      ports: ["6379:6379"]

    flask-app:
      build: ..
      ports: ["5000:5000"]
      depends_on: [redis]
      volumes:
        - ../processed:/app/processed
      environment:
        - REDIS_URL=redis://redis:6379
  ```

- [ ] **8.2** 建立主 `Dockerfile`（Flask app）

---

### Phase 9：Demo 腳本與測試

- [ ] **9.1** 準備 demo 用小型資料集（COCO128 或自製小資料）
- [ ] **9.2** 手動 end-to-end 測試：
  - 上傳資料集 → 預處理 → 提交 training job（High priority）→ 再提交 2 個 Low priority → Dashboard 觀察排程
- [ ] **9.3** GPU 隔離測試：同時啟動 2 個 job，確認分配到不同 GPU
- [ ] **9.4** 更新 README.md，加入架構圖與啟動說明

---

## 實作順序建議

```
Phase 0（環境）→ Phase 1（Queue）→ Phase 2（GPU）→ Phase 3（Docker）
→ Phase 4（Scheduler）→ Phase 5（API）→ Phase 6（Train UI）
→ Phase 7（Dashboard）→ Phase 8（Compose）→ Phase 9（Demo）
```

每個 Phase 完成後可獨立測試。Phase 5 完成後即可用 curl 測試全流程，再做 UI。

---

## 無 GPU 環境的處理

若機器沒有 NVIDIA GPU：
- `gpu_manager.py` 自動進入 mock 模式，模擬 1 張 GPU
- Docker container 不傳入 `device_requests`，以 CPU 執行訓練
- Demo 時使用 `yolov8n`（最小模型）+ `epochs=1`，約 2-5 分鐘完成

---

## 關鍵依賴版本（參考）

```
flask==3.0.0
redis==5.0.1
rq==1.16.1
docker==7.0.0
pynvml==11.5.0
ultralytics==8.1.0
```

---

## 注意事項

1. **現有功能不動**：`app.py` 原有的 `/upload`, `/process`, `/download` 路由保持不變
2. **Scheduler 為背景 Thread**：Flask 主 thread 不受影響
3. **WSL2 環境**：Docker Desktop for Windows 需啟動，`/var/run/docker.sock` 需可存取
4. **Redis 需先啟動**：所有 job 操作依賴 Redis
5. **Demo 優先**：Phase 9 以前，先求功能完整，不追求 production-grade 安全性
