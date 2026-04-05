# bildwerk Architecture

## System Overview

bildwerk is a batch processing pipeline for historical image modernization. It uses ComfyUI with SDXL and ControlNet to transform old engravings and photographs into modern photorealistic views while preserving composition.

## Architecture

```
┌─────────────┐     WebDAV     ┌──────────────┐
│  Nextcloud  │◄──────────────►│   Router     │
│  (inbox)    │                │  (orchestr.) │
└─────────────┘                └──────┬───────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              ┌───────────┐     ┌───────────┐     ┌───────────┐
              │ GPU Worker│     │ GPU Worker│     │  CPU Fallback│
              │   (3060)  │     │   (3060)  │     │   (router)  │
              └───────────┘     └───────────┘     └───────────┘
                    │                 │                 │
                    ▼                 ▼                 ▼
              ┌───────────┐     ┌───────────┐     ┌───────────┐
              │  ComfyUI  │     │  ComfyUI  │     │  Diffusers│
              │  SDXL+CN  │     │  SDXL+CN  │     │  OpenVINO │
              └───────────┘     └───────────┘     └───────────┘
```

## Infrastructure (Generic)

### Hardware Requirements

| Component | GPU | RAM | Storage | Notes |
|-----------|-----|-----|---------|-------|
| Router | None | 4-8 GB | 8-16 GB | Job orchestration, Nextcloud integration |
| GPU Worker | RTX 3060 12GB+ | 8-16 GB | 16-32 GB | ComfyUI with SDXL + ControlNet |
| CPU Fallback | None | 32-64 GB | 16-32 GB | OpenVINO (experimental) |

### Proxmox LXC Design

Each component runs in its own LXC container for isolation:

| LXC Name | GPU | Role |
|----------|-----|------|
| bildwerk-router | None | Job orchestration, Nextcloud integration |
| bildwerk-cpu | None | CPU fallback (OpenVINO) |
| bildwerk-gpu-a | GPU #1 | GPU worker (ComfyUI) |
| bildwerk-gpu-b | GPU #2 | GPU worker (ComfyUI) |

**Note:** Actual VMIDs and host assignments are environment-specific (see private repo).

### Network Design

#### IP Allocation Pattern

Components follow a consistent IP-to-VMID mapping:
- IP `192.168.0.X` → VMID `3X` (e.g., `.49` → `349`)

#### Port Allocation

| Component | Port | Service |
|-----------|------|---------|
| Router | 8080 | Job API |
| CPU Worker | 8081 | ComfyUI API |
| GPU Worker A | 8188 | ComfyUI |
| GPU Worker B | 8189 | ComfyUI |

#### Connectivity

- All LXCs on same internal network
- Direct LAN access (no Tailscale needed for internal comms)
- Router has external access to Nextcloud

### GPU Passthrough

LXC GPU assignment requires:

```
lxc.cgroup2.devices.allow: c 234:* rwm  # NVIDIA character devices
lxc.cgroup2.devices.allow: c 243:* rwm  # NVIDIA UVM
lxc.cgroup2.devices.allow: c 244:* rwm  # NVIDIA video devices
```

## Component Design

### Router

The router is the central orchestrator:

- **Role:** Job lifecycle management, Nextcloud integration
- **Technology:** Python, systemd service
- **Database:** SQLite (local job state)
- **API:** REST (worker communication)

**Responsibilities:**
- Poll Nextcloud inbox for new files
- Download files to local staging
- Submit jobs to available workers
- Track job state and retries
- Upload results to Nextcloud
- Handle errors and notifications

### GPU Workers

Each GPU worker runs ComfyUI in headless mode:

- **Technology:** ComfyUI with API
- **Model:** SDXL base + refiner
- **ControlNet:** softedge, canny, mlsd, depth, lineart
- **Deployment:** systemd service in LXC

**Responsibilities:**
- Listen for job requests via API
- Execute ComfyUI workflows
- Return results and metrics
- Report health status

### CPU Fallback

Experimental CPU-based processing:

- **Technology:** Diffusers + OpenVINO
- **Model:** SDXL (OpenVINO optimized)
- **Use Case:** Validation, fallback, off-hours batch

**Note:** CPU performance is 5-10x slower than GPU. Use only when appropriate.

### Nextcloud Integration

#### Service Account

- **Username:** `bildwerk-service`
- **Access:** WebDAV only
- **Scope:** Single folder tree (`bildwerk/`)

#### Folder Structure

```
bildwerk/
├── inbox/         # User uploads here
├── processing/    # Files being processed
├── done/          # Completed outputs
├── error/         # Failed jobs
└── review/        # Optional: manual review queue
```

#### Lifecycle

1. User uploads file to `inbox/`
2. Router polls `inbox/` (every 30s)
3. Router downloads file → local staging
4. Router moves NC file to `processing/`
5. Router submits job to GPU worker (via HTTP API)
6. Worker processes → outputs to local path
7. Router downloads result → uploads to `done/`
8. Router moves NC file from `processing/` to `done/` or `error/`

### Job Schema

#### Job Request (Router → Worker)

```json
{
  "job_id": "uuid-v4",
  "created_at": "2026-03-23T10:00:00Z",
  "input_path": "/tmp/bildwerk/staging/file.png",
  "preset": "vedute",
  "params": {
    "steps": 20,
    "cfg_scale": 7.5,
    "seed": -1,
    "width": 1024,
    "height": 768
  },
  "output_path": "/tmp/bildwerk/output/",
  "callback_url": "http://router:8080/api/v1/jobs/{job_id}/complete"
}
```

#### Job Response (Worker → Router)

```json
{
  "job_id": "uuid-v4",
  "status": "completed",
  "output_path": "/tmp/bildwerk/output/file_processed.png",
  "started_at": "2026-03-23T10:00:05Z",
  "completed_at": "2026-03-23T10:02:30Z",
  "metrics": {
    "steps": 20,
    "time_per_step_ms": 7500,
    "gpu_memory_peak_mb": 8192
  }
}
```

#### State Machine

```
inbox → processing → (completed → done) | (failed → error)
```

### ComfyUI Workflows

#### Preset Design

Each preset defines:
- **ControlNet models** (primary + secondary)
- **Generation parameters** (steps, CFG, sampler)
- **Model configuration** (base, refiner)
- **Preprocessing** (edge detection, depth estimation)
- **Prompt templates** (positive/negative)

#### Available Presets

| Preset | Use Case | ControlNet | Notes |
|--------|----------|------------|-------|
| vedute | Historical city views | softedge + depth | Preserves spatial relationships |
| facades | Building facades | canny/mlsd + depth | Sharp architectural lines |
| portraits | Portrait engravings | lineart + depth | Facial structure preservation |

### Logging & Monitoring

#### Centralized Logging

- **Backend:** Graylog (configured in private repo)
- **Format:** JSON structured logging
- **Retention:** 30 days

#### Metrics

- **Backend:** Prometheus + OpenTelemetry
- **Metrics:**
  - Job queue length
  - Processing time per job
  - GPU utilization
  - Error rates

#### Future Controller

Planned integration with central controller for:
- Dynamic GPU assignment across applications
- Load balancing
- Priority scheduling

## Security

### Network

- Workers only expose API ports to internal network
- Router is the only component with external access
- No direct worker-to-Nextcloud communication

### Authentication

- Router-Worker: API tokens (stored in private repo)
- Nextcloud: Service account with limited scope
- No user-facing auth (internal tool)

### Data

- Temporary files cleaned after job completion
- No persistent storage of intermediate results
- All outputs go through Nextcloud (audit trail)


- [ComfyUI Documentation](https://docs.comfy.org/)
- [ComfyUI Server API](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [Nextcloud WebDAV API](https://docs.nextcloud.com/server/32/developer_manual/client_apis/WebDAV/index.html)
- [SDXL + ControlNet](https://huggingface.co/docs/diffusers/en/api/pipelines/controlnet_sdxl)