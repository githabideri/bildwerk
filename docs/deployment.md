# bildwerk Deployment Guide

## Prerequisites

- Linux server (Ubuntu 22.04 or Debian 12 recommended)
- Python 3.10+
- Nextcloud instance with WebDAV access
- GPU worker with ComfyUI running (separate machine or container)
- NVIDIA GPU with CUDA support (for generation)

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/githubder/bildwerk.git
cd bildwerk
```

### 2. Set Up Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your configuration
nano .env
```

### 3. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure Nextcloud

1. Create a service account in Nextcloud (e.g., `bildwerk-service`)
2. Create folder structure: `bildwerk/inbox/`, `bildwerk/done/`, etc.
3. Update `.env` with your Nextcloud credentials

### 5. Start the Router

```bash
# Using Python directly
BILDWORK_CONFIG=router/config.yaml python -m router

# Or as a systemd service (see below)
```

## Configuration

### Environment Variables

See `.env.example` for all available options. Key variables:

- `BILDWORK_NEXTCLOUD_URL` - Nextcloud base URL
- `BILDWORK_NEXTCLOUD_USERNAME` - Service account username
- `BILDWORK_NEXTCLOUD_PASSWORD` - Service account password
- `BILDWORK_WORKER_URL` - ComfyUI worker URL (e.g., `http://192.168.1.100:8188`)
- `BILDWORK_CLASSIFICATION_DIR` - Path to classification manifest files

### Router Config

Copy `router/config.yaml.example` to `router/config.yaml` and customize:

```yaml
router:
  name: bildwerk-router
  poll_interval_seconds: 30

nextcloud:
  base_url: "https://your-nextcloud.com"
  username: "bildwerk-service"
  folders:
    base: "bildwerk"
    inbox: "inbox"
    done: "done"
    # ...

workers:
  - name: "gpu-worker"
    url: "http://your-worker:8188"
    type: "gpu"

backends:
  flux_klein_local:
    model: "flux-2-klein-4b-fp8.safetensors"
    workflow_file: "flux_klein_generation_api.json"
    upscale_workflow_file: "flux_klein_upscale_api.json"
    two_stage: true
```

## Systemd Service (Optional)

For production deployment, use the systemd service:

```bash
# Copy service file
sudo cp private/infra/systemd/bildwerk-router.service /etc/systemd/system/

# Enable and start
sudo systemctl enable bildwerk-router
sudo systemctl start bildwerk-router

# Check status
sudo systemctl status bildwerk-router
```

## Worker Setup

The GPU worker runs ComfyUI with the required models. See:

- `private/infra/systemd/bildwerk-gpu-a.service` - systemd unit
- `private/requirements-worker.txt` - dependencies
- Model download scripts in `scripts/`

## Testing

### 1. Test Nextcloud Connection

```bash
# Test WebDAV connectivity
curl -u bildwerk-service:password \
  https://your-nextcloud.com/remote.php/dav/files/bildwerk-service/bildwerk/
```

### 2. Test Worker Connection

```bash
# Check ComfyUI is running
curl http://your-worker:8188/api/status
```

### 3. Run a Test Job

1. Upload a test image to `bildwerk/inbox/` in Nextcloud
2. Watch router logs: `journalctl -u bildwerk-router -f`
3. Check output in `bildwerk/done/`

## Troubleshooting

### Common Issues

**Router won't start:**
- Check `.env` file exists and has no syntax errors
- Verify Nextcloud credentials in `router/config.yaml`
- Check systemd service: `journalctl -u bildwerk-router`

**Jobs stuck in processing:**
- Worker may be down - check ComfyUI service
- Timeout too short - increase in config
- Check worker logs: `journalctl -u bildwerk-gpu-a`

**WebDAV errors:**
- Verify service account password
- Check Nextcloud folder permissions
- Ensure WebDAV is enabled for the account

**No output generated:**
- Check workflow files exist in `workflows/`
- Verify models are loaded on worker
- Check worker has sufficient GPU memory

## Architecture Overview

```
┌─────────────┐     WebDAV     ┌──────────┐     HTTP/JSON     ┌─────────┐
│ Nextcloud   │ ◄─────────────► │  Router  │ ◄───────────────► │ Worker  │
│ (Storage)   │                 │ (Python) │                   │ (GPU)   │
└─────────────┘                 └──────────┘                   └─────────┘
     │                                │                              │
     ▼                                ▼                              ▼
  Files                       Job orchestration              ComfyUI
  inbox/                       Preset routing                FLUX.2
  done/                        State management              Upscale
  error/                       Metadata generation
```

## Security

- Never commit `.env` files with real credentials
- Use separate service accounts for Nextcloud
- Keep `private/` submodule separate from public repo
- Rotate passwords regularly

## Next Steps

- Review `ARCHITECTURE.md` for system design
- Check `docs/` for additional documentation
- See `presets/` for available generation presets
