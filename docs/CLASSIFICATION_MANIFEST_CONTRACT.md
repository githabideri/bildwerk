# Classification Manifest Contract

This document defines the expected format for the classification manifest file used by the bildwerk router to route images to appropriate processing presets.

## Purpose

The classification manifest maps source image filenames to their architectural archetype (e.g., "interior_passage", "facade", "veduta_city"). This allows the router to automatically select the appropriate preset for each image.

## File Location

The manifest file is loaded from a path specified via environment variable:

```bash
BILDWORK_CLASSIFICATION_DIR=classification
BILDWORK_MANIFEST_FILE=manifest.corrected.json
```

Default path: `classification/manifest.corrected.json`

## Manifest Format

The manifest is a JSON file containing an array of file objects:

```json
[
  {
    "filename": "301.jpg",
    "bucket": "interior_passage",
    "confidence": 0.87,
    "reason": "vaulted corridor with arches"
  },
  {
    "filename": "302.jpg",
    "bucket": "facade",
    "confidence": 0.92,
    "reason": "building exterior with columns"
  }
]
```

## Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | Yes | Source image filename (e.g., "301.jpg") |
| `bucket` | string | Yes | Archetype category (see below) |
| `confidence` | number or string | No | Confidence score (0.0-1.0) or "high"/"low" |
| `reason` | string | No | Human-readable explanation |

## Bucket Values

Valid bucket values that map to presets:

| Bucket | Preset | Description |
|--------|--------|-------------|
| `interior_passage` | `interior_passage_v2_p1` | Interior spaces, corridors, vaulted ceilings |
| `veduta_city` | `veduta_city_v1_p1` | City views, street scenes |
| `facade` | `facade_v1_p1` | Building exteriors, architectural facades |
| `portrait_engraving` | `portrait_engraving_v1_p1` | Portrait engravings |
| `unclear` | (none) | Route to review folder |

## Router Behavior

### Confidence Thresholds

- `confidence >= 0.7` (or "high") → Auto-select preset
- `confidence < 0.7` (or "low") → Route to review folder
- Missing confidence → Default to 0.0 (route to review)

### Missing Files

If a filename is not found in the manifest:
- Router routes the file to the `review/` folder
- Manual preset selection required

### Overrides

Manual overrides can be provided via a separate `overrides.json` file:

```json
{
  "301.jpg": {
    "bucket": "facade",
    "reason": "Manual correction - actually a facade"
  }
}
```

Overrides take precedence over the manifest.

## Example Workflow

1. Classification system processes source images
2. Generates `manifest.json` with bucket assignments
3. Human reviewer corrects misclassifications → `manifest.corrected.json`
4. Router loads manifest on startup
5. For each incoming file:
   - Check overrides first
   - Check manifest
   - Route to appropriate preset or review

## Creating a Manifest

### Manual Classification

For small datasets, create the manifest manually:

```json
[
  {"filename": "301.jpg", "bucket": "interior_passage", "confidence": 1.0},
  {"filename": "302.jpg", "bucket": "facade", "confidence": 1.0}
]
```

### Automated Classification

For large datasets, use an image classifier:

1. Extract features from source images
2. Cluster or classify into buckets
3. Output manifest in expected format
4. Human review and correction

## Validation

The router validates the manifest on startup:

- File must exist (unless classification is disabled)
- Must be valid JSON
- Each entry must have `filename` and `bucket`
- Bucket must be a known archetype or "unclear"

Invalid manifests cause router startup failure.
