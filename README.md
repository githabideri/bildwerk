# BILDWERK 🏛️⚙️

Automated conversion of architectural sketches and historical drawings into photorealistic modern photographs using AI.

**Version:** 0.1.0 (Working Prototype)  
**Last Updated:** 2026-04-01

---

## OVERVIEW

**bildwerk** transforms historical images (Veduten, engravings, facades, portraits) into modern photorealistic photographs while preserving composition and key structural elements.

### Core Philosophy

- **File-based state machine** - No databases, simple folder lifecycle
- **Archetype-specific presets** - Different workflows for different image types
- **Two-pass refinement** - Structure preservation + material polish
- **Review routing** - Auto-QC routes uncertain outputs to human review
- **Sidecar metadata** - Every output has traceable provenance

---

## QUICK START

```bash
# Clone repository
git clone <repo-url> bildwerk
cd bildwerk

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install aiohttp aiofiles pyyaml prometheus-client

# Configure (see DEPLOYMENT_NOTES.md in bildwerk-private)
cp router/config.example.yaml router/config.yaml
# Edit config.yaml and secrets/nextcloud.yaml

# Test connection
python3 scripts/test_e2e.py list

# Run router
python3 -m router.main
```

---

## ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        BILDWERK SYSTEM                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────┐│
│  │  Nextcloud   │────────▶│   Router     │────────▶│ Worker   ││
│  │  (WebDAV)    │◀────────│  (Python)    │◀────────│ (GPU)    ││
│  └──────────────┘         └──────────────┘         └──────────┘│
│        │                       │                          │     │
│        ▼                       ▼                          ▼     │
│   Folder lifecycle      Job orchestration          ComfyUI    │
│   State tracking        Preset routing             SDXL       │
│   Sidecar storage       Retry logic                ControlNet │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### File Lifecycle

```
inbox/ → processing/ → [ComfyUI img2img] → done/
                                              │
                                    ┌─────────┴─────────┐
                                    │                   │
                               Auto-QC pass         Auto-QC fail
                                    │                   │
                                    ▼                   ▼
                                 done/              review/
```

---

## DOCUMENTATION

| Document | Location | Description |
|----------|----------|-------------|
| **Architecture** | `ARCHITECTURE.md` | System design, workflows, sidecar schema |
| **Classification Contract** | `docs/CLASSIFICATION_MANIFEST_CONTRACT.md` | How to integrate image classification |
| **Auto-QC & Review** | `docs/AUTO_QC_AND_REVIEW.md` | Quality metrics and review routing |
| **Deployment Notes** | `bildwerk-private/DEPLOYMENT_NOTES.md` | Production deployment, runbook |
| **Current Status** | `bildwerk-private/CURRENT_STATUS_SNAPSHOT.md` | What works, what's missing |

---

## PRESETS

Archetype-specific configurations with two-pass support:

| Preset | Pass | Purpose | Status |
|--------|------|---------|--------|
| `interior_passage_v2_p1` | 1 | Interior vaults, corridors, cloisters | ✅ Tested |
| `interior_passage_v2_p2` | 2 | Refinement (material polish) | 📋 Scaffolding |
| `veduta_city_v1_p1` | 1 | City views, panoramas | ✅ Tested |
| `facade_v1_p1` | 1 | Building exteriors | 📋 Scaffolding |
| `portrait_engraving_v1_p1` | 1 | Historical portraits | 📋 Scaffolding |

**Preset Files:** `<installation-path>/bildwerk/presets/`

---

## FEATURES

### Implemented ✅

- File-based state machine (no database)
- Nextcloud WebDAV integration (authenticated, retry logic)
- ComfyUI worker orchestration (upload, prompt, poll, download)
- Archetype-specific presets (interior, veduta, facade, portrait)
- Two-stage pipeline (generation + upscale)
- Sidecar metadata generation (JSON with provenance)
- Duplicate prevention (completed_jobs marker)
- Retry logic for transient network failures
- FLUX.2 Klein 4B distilled (local, no API)

### Scaffolding 📋

- Auto-QC metrics (saturation, clipping, contrast)
- Review folder routing
- Classification manifest consumer (contract defined)
- Two-pass pipeline orchestration

### Planned 🔮

- Auto-QC metrics (saturation, clipping, contrast)
- Batch processing mode
- Web UI for review workflow
- Prometheus metrics + Grafana dashboard
- Multi-worker load balancing
- Alternative model backends (SDXL, SD3)

---

## COMPONENTS

### Router (Python)

Core orchestration component:
- Polls `inbox/` for new files (every 30s)
- Routes files to appropriate preset based on archetype
- Manages worker communication (upload, prompt, poll, download)
- Generates sidecar metadata for every output
- Tracks completed jobs (prevents reprocessing)
- Routes low-confidence outputs to `review/`

**Location:** `<installation-path>/bildwerk/router/`

### Worker (GPU)

Image generation backend:
- ComfyUI with FLUX.2 Klein 4B (distilled)
- Two-stage pipeline: Generation + Upscale
- RealESRGAN_x4plus for 4x upscaling
- Local models (no external API dependencies)

**Endpoint:** `http://192.168.0.49:8188` (locmox)

### Nextcloud Storage

File-based state machine using WebDAV:

| Folder | Purpose | Contains |
|--------|---------|----------|
| `inbox/` | New jobs | Source images waiting |
| `processing/` | Active jobs | Temporary (should be empty most of time) |
| `done/` | Completed | Source + output + sidecar |
| `error/` | Technical failures | Source images that failed |
| `review/` | Low confidence | Outputs needing human review |

---

## SIDECAR METADATA

Every output has a JSON sidecar with full provenance:

```json
{
  "job_id": "uuid-v4",
  "source_filename": "original.jpg",
  "output_filename": "OUTPUT_00001_.png",
  "preset": "interior_passage_v2_p1",
  "parameters": {
    "denoise": 0.33,
    "cfg_scale": 5.2,
    "steps": 30
  },
  "started_at": "2026-04-01T17:33:01Z",
  "finished_at": "2026-04-01T17:33:24Z",
  "source_sha256": "...",
  "output_sha256": "..."
}
```

See `ARCHITECTURE.md` for full schema.

---

## PRIVATE DEPLOYMENT NOTES

Deployment-specific configuration, credentials, and operational procedures are in the separate `bildwerk-private` repository:

- Host topology and endpoints
- Step-by-step deployment guide
- Runbook and troubleshooting
- Current status snapshot (anti-compaction checkpoint)
- Secrets management

---

## TESTING

### Single File Test

```bash
cd <installation-path>/bildwerk
python3 scripts/test_e2e.py <filename>
```

### List Inbox

```bash
python3 scripts/test_e2e.py list
```

### Interior Passage Test

```bash
python3 scripts/test_interior.py <filename>
```

---

## LICENSE

GPL-3.0. See `LICENSE` file.

---

*Built for historical image modernization.*
