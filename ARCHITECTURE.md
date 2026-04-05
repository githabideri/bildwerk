# BILDWERK ARCHITECTURE

**Version:** 0.1.0  
**Last Updated:** 2026-04-01

---

## SYSTEM OVERVIEW

Bildwerk is an automated image processing pipeline that converts architectural sketches, engravings, and historical drawings into photorealistic modern photographs using AI image generation.

### Core Philosophy

- **File-based state machine** - No databases, simple folder lifecycle
- **Archetype-specific presets** - Different workflows for different image types
- **Two-pass refinement** - Structure preservation + material polish
- **Review routing** - Auto-QC routes uncertain outputs to human review
- **Sidecar metadata** - Every output has traceable provenance

---

## COMPONENTS

```
┌─────────────────────────────────────────────────────────────────┐
│                        BILDWERK SYSTEM                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────┐│
│  │  Nextcloud   │────────▶│   Router     │────────▶│ Worker   ││
│  │  Storage     │◀────────│  (Python)    │◀────────│ (GPU)    ││
│  └──────────────┘         └──────────────┘         └──────────┘│
│        │                       │                          │     │
│        ▼                       ▼                          ▼     │
│   Folder lifecycle      Job orchestration          ComfyUI    │
│   State tracking        Preset routing             SDXL       │
│   Sidecar storage       Retry logic                ControlNet │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Nextcloud Storage

File-based state machine using WebDAV:

| Folder | Purpose | Lifecycle |
|--------|---------|-----------|
| `inbox/` | New jobs | Source imagesawaiting processing |
| `processing/` | Active jobs | Temporary (should be empty most of time) |
| `done/` | Completed | Source + output + sidecar |
| `error/` | Technical failures | Source images that failed |
| `review/` | Low confidence | Outputs needing human review |

### Router (Python)

Core orchestration component:

- **Polls** `inbox/` for new files
- **Routes** files to appropriate preset based on archetype
- **Manages** worker communication (upload, prompt, poll, download)
- **Generates** sidecar metadata for every output
- **Tracks** completed jobs (prevents reprocessing)
- **Routes** low-confidence outputs to `review/`

### Worker (GPU)

Image generation backend:

- **ComfyUI** with FLUX.2 Klein 4B (distilled)
- **Two-stage pipeline:** Generation + Upscale
- **Img2img** workflow using ReferenceNet architecture
- **Upscale** with RealESRGAN_x4plus (4x)
- **Local models:** No external API dependencies

---

## FILE-BASED LIFECYCLE

```
1. User drops source image in inbox/
                │
                ▼
2. Router polls inbox/ (every 30s)
                │
                ▼
3. Move file: inbox/ → processing/
                │
                ▼
4. Download source locally
                │
                ▼
5. Classify archetype (or use manual assignment)
                │
                ▼
6. Select preset by archetype
                │
                ▼
7. Upload source to ComfyUI
                │
                ▼
8. Submit img2img workflow
                │
                ▼
9. Poll for completion (up to 300s)
                │
                ▼
10. Download output + generate sidecar
                │
                ▼
11. Run auto-QC metrics
    │
    ├───[PASS]──▶ Upload to done/
    │             Mark completed
    │
    └───[UNCERTAIN]──▶ Upload to review/
                       Flag for human review
                │
                ▼
12. Clean up local temp files
```

---

## TWO-STAGE PIPELINE

Each job goes through two stages:

### Stage A: Generation (FLUX.2 Klein)

**Goal:** Convert sketch to photorealistic image while preserving composition

- **Model:** FLUX.2 Klein 4B distilled
- **Architecture:** ReferenceNet-based img2img
- **Steps:** 4 (optimized for speed)
- **CFG:** 1.0 (guidance scale)
- **Input:** Original sketch image
- **Output:** Intermediate generated image (~same resolution as input)

### Stage B: Upscale (RealESRGAN)

**Goal:** Increase resolution while preserving details

- **Model:** RealESRGAN_x4plus
- **Scale:** 4x
- **Input:** Stage A output
- **Output:** Final upscaled image

**Pipeline behavior:**
- Stage B starts only if Stage A succeeds
- If Stage A fails: job marked failed, error logged, processing stops
- If Stage A succeeds but Stage B fails: intermediate output preserved, job marked for review/error
- Both stages logged with separate prompt_ids for traceability

**When single-stage (generation only) is sufficient:**
- Quick previews
- Lower priority archives
- When final resolution is not critical
- Lower priority archives

---

## SIDECAR SCHEMA

Every output has a JSON sidecar file:

```json
{
  "job_id": "uuid-v4",
  "source_filename": "original.jpg",
  "source_remote_path": "Shared/bildwerk/done/original.jpg",
  "output_filename": "FLUX_KLEIN_UPSCALED_00001_.png",
  "intermediate_image": "FLUX_KLEIN_00001_.png",
  "final_image": "FLUX_KLEIN_UPSCALED_00001_.png",
  "preset": "plausible",
  "backend": "flux_klein_local",
  "backend_config": "flux_klein_local",
  "worker": "locmox-gpu",
  "model": "flux-2-klein-4b-fp8.safetensors",
  "stages": {
    "generation": {
      "success": true,
      "prompt_id": "stage-a-prompt-uuid",
      "workflow": "flux_klein_generation_api.json"
    },
    "upscale": {
      "success": true,
      "prompt_id": "stage-b-prompt-uuid",
      "workflow": "flux_klein_upscale_api.json"
    }
  },
  "parameters": {
    "steps": 4,
    "cfg_scale": 1.0,
    "sampler": "euler",
    "scheduler": "normal",
    "upscale_model": "RealESRGAN_x4plus.pth"
  },
  "prompt": "photorealistic modern color photograph, high quality, detailed architecture...",
  "started_at": "2026-04-05T12:00:00.000000",
  "finished_at": "2026-04-05T12:02:30.000000",
  "status": "completed",
  "source_sha256": "...",
  "output_sha256": "...",
  "qc_metrics": {
    "mean_saturation": 0.45,
    "highlight_clipping": 0.02,
    "shadow_clipping": 0.01,
    "local_contrast": 0.67
  },
  "review_required": false,
  "review_reason": null
}
```

---

## NDJSON LOG FORMAT

Router logs in NDJSON for easy parsing:

```json
{"ts":"2026-04-01T17:33:01.766Z","level":"INFO","job_id":"xxx","event":"job_started","filename":"331.jpg"}
{"ts":"2026-04-01T17:33:02.254Z","level":"INFO","job_id":"xxx","event":"worker_submit","prompt_id":"yyy"}
{"ts":"2026-04-01T17:33:24.293Z","level":"INFO","job_id":"xxx","event":"job_completed","duration_sec":22.5}
```

---

## REVIEW FOLDER CONCEPT

### Auto-QC Metrics

Outputs are routed to `review/` if:

| Metric | Threshold | Reason |
|--------|-----------|--------|
| Mean saturation | < 0.15 | Output still too monochrome |
| Highlight clipping | > 0.10 | Overexposed, detail loss |
| Shadow clipping | > 0.15 | Crushed blacks, detail loss |
| Local contrast | < 0.30 | Flat, washed out |
| Geometry drift | > TBD | Composition changed too much (future) |

### Manual Review Workflow

1. Auto-QC flags output → `review/`
2. Human reviews in Nextcloud
3. Three options:
   - **Approve** → Move to `done/`
   - **Reject** → Move to `error/`, log reason
   - **Reprocess** → Move back to `inbox/` with new preset parameters

---

## AUTO-QC CONCEPT

### Saturation Check

```python
def check_saturation(image: np.ndarray) -> float:
    """Return mean saturation (0-1). Flag if < 0.15"""
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    return np.mean(hsv[:,:,1]) / 255.0
```

### Clipping Check

```python
def check_clipping(image: np.ndarray) -> tuple[float, float]:
    """Return (highlight_clipping, shadow_clipping) ratios"""
    flat = image.flatten()
    highlight = np.mean((flat > 240).astype(float))
    shadow = np.mean((flat < 15).astype(float))
    return highlight, shadow
```

### Local Contrast

```python
def check_local_contrast(image: np.ndarray) -> float:
    """Return local contrast metric (0-1)"""
    # Use Laplacian variance or similar
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()
```

---

## WORKFLOW TEMPLATE STRATEGY

### Preset Structure

```
presets/
├── interior_passage/
│   ├── v1_p1.json  (structure pass, denoise 0.33)
│   ├── v1_p2.json  (refinement pass, denoise 0.15)
│   └── v2_p1.json  (with ControlNet, denoise 0.40)
├── veduta_city/
│   ├── v1_p1.json
│   └── v1_p2.json
├── facade/
│   ├── v1_p1.json
│   └── v1_p2.json
└── portrait_engraving/
    ├── v1_p1.json
    └── v1_p2.json
```

### Preset Schema

```json
{
  "name": "interior_passage_v2_p1",
  "version": "2.0.0",
  "archetype": "interior_passage",
  "pass": 1,
  "description": "Structure-preserving translation with ControlNet",
  "generation_params": {
    "steps": 30,
    "cfg_scale": 5.2,
    "denoise": 0.40,
    "sampler": "euler_ancestral",
    "width": 1024,
    "height": 768
  },
  "model_config": {
    "base": "sd_xl_base_1.0.safetensors"
  },
  "controlnet": [
    {"model": "softedge", "weight": 0.8},
    {"model": "depth", "weight": 0.6}
  ],
  "prompt_templates": {
    "positive": "present-day color architectural photograph...",
    "negative": "black and white, monochrome, sketch..."
  },
  "expected_failures": [
    "May lose fine architectural details if denoise > 0.45",
    "Color may be too warm for cool stone"
  ],
  "review_criteria": [
    "Arches and columns preserved",
    "Color present (not monochrome)",
    "Stone texture visible"
  ]
}
```

---

## ARCHETYPE ROUTING

### Classification → Preset Mapping

```python
ARCHETYPE_TO_PRESET = {
    "interior_passage": "interior_passage_v2_p1",
    "veduta_city": "veduta_city_v1_p1",
    "facade": "facade_v1_p1",
    "portrait_engraving": "portrait_engraving_v1_p1",
    "unclear": None  # Route to review
}
```

### Classification Manifest Contract

Expected input from classification system:

```json
{
  "version": "1.0",
  "generated_at": "2026-04-01T12:00:00Z",
  "files": [
    {
      "filename": "331.jpg",
      "absolute_path": "/path/to/331.jpg",
      "assigned_bucket": "interior_passage",
      "confidence": 0.87,
      "short_reason": "vaulted corridor with arches"
    }
  ]
}
```

**Router behavior:**
- `confidence >= 0.7` → Auto-select preset
- `confidence < 0.7` → Route to `review/` for manual assignment
- `assigned_bucket = "unclear"` → Route to `review/`

---

## SECURITY

- **No secrets in repo** - All credentials in separate `bildwerk-private`
- **No API keys in code** - Use environment variables or config files
- **WebDAV authentication** - Basic auth with app passwords
- **Sidecar provenance** - SHA256 hashes for source/output integrity

---


## SUBMODULES

### bildwerk-private

The `private/` directory is a git submodule pointing to the `bildwerk-private` repository.

**Location:** Local Gitea only (not on GitHub)

**Contains:**
- Secrets (Nextcloud credentials, API keys)
- Production configuration
- Operational status snapshots
- Infrastructure as code

**Cloning:**
```bash
git clone <bildwerk-repo>
cd bildwerk
git submodule init
git submodule update
```

The `private/` submodule will only clone if you have access to the local Gitea instance. External contributors without access will see an empty directory.

---

*Architecture documented for version 0.2.0 (FLUX.2 Klein). See CURRENT_STATUS_SNAPSHOT.md in bildwerk-private for operational details.*
