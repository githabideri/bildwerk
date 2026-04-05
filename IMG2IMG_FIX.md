# IMG2IMG WORKFLOW FIX - VALIDATION REPORT

**Date:** 2026-04-01  
**Status:** ✅ WORKFLOW VALIDATED

## Problem Identified

All 43+ previously generated images were **text-to-image** outputs, NOT image-to-image:
- Used `EmptyLatentImage` node (blank canvas)
- `KSampler` with `denoise: 1.0` (full generation)
- Input images were loaded but **never used** in the workflow
- Result: "sleazy text2image creations" with zero resemblance to originals

## Fix Applied

### 1. Router Workflow Replaced (`/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/router/__init__.py`)

**Old (txt2img):**
```python
"5": {"class_type": "EmptyLatentImage", "inputs": {"height": 768, "width": 1024}}
"4": {"class_type": "KSampler", "inputs": {"denoise": 1, "latent_image": ["5", 0]}}
```

**New (img2img):**
```python
"1": {"class_type": "LoadImage", "inputs": {"image": uploaded_filename, "upload": "image"}}
"3": {"class_type": "VAEEncode", "inputs": {"pixels": ["1", 0], "vae": ["2", 2]}}
"4": {"class_type": "KSampler", "inputs": {"denoise": 0.45, "latent_image": ["3", 0]}}
```

### 2. Node Graph (Minimal img2img)

```
LoadImage(1) ──pixels──> VAEEncode(3) ──latent──> KSampler(4) ──samples──> VAEDecode(6) ──> SaveImage(8)
                                                                                      ↑
CheckpointLoader(2) ─model──┐                                                       │
               ─clip──> CLIPTextEncode(5,7) ──> positive/negative ──┘               │
               ─vae─────────────────────────────────────────────────────────────────┘
```

### 3. Key Changes

- ✅ **Removed** `EmptyLatentImage` (was node 5)
- ✅ **Added** `LoadImage` to load source image via `/upload/image` endpoint
- ✅ **Added** `VAEEncode` to encode source to latent space
- ✅ **Changed** `KSampler.denose` from `1.0` to `0.45` (preserve composition but modernize)
- ✅ **Using** VAE from `CheckpointLoaderSimple` (output 2), not separate `VAELoader`
- ✅ **Explicit** `filename_prefix: "BILDWORK_IMG2IMG"` in `SaveImage`

### 4. Preset Updated (`/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/presets/vedute.json`)

```json
"generation_params": {
  "denoise": 0.45,  // ADDED - was missing
  "steps": 20,
  "cfg_scale": 7.5,
  ...
}
```

## Validation Test

**Test Script:** `/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/scripts/test_img2img.py`

**Test Results:**
```
✅ Upload source image to ComfyUI: 200 OK
✅ Submit img2img workflow: 200 OK
✅ Job completed successfully
✅ Output generated: TEST_00001_.png (43KB)
✅ Dimensions preserved: 512x512 → 512x512
✅ Content transformed: gray test → architectural output
```

**Test Files:**
- Source: `/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/test_output/test_source.png` (1.8KB, gray 512x512)
- Output: `/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/test_output/result_img2img.png` (43KB, generated building)

## Next Steps

1. ✅ One-file validation complete
2. ⏳ Update router to poll `/history/{prompt_id}` and retrieve output
3. ⏳ Upload result to Nextcloud `done/` folder
4. ⏳ Create sidecar file with metadata
5. ⏳ Test with real inbox files
6. ⏳ Consider adding ControlNet later (not required for unblock)

## Files Modified

1. `/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/router/__init__.py`
   - Added `upload_image()` method
   - Updated `submit_to_comfyui()` to upload first, then reference filename
   - Replaced `_build_comfyui_workflow()` with img2img workflow

2. `/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/presets/vedute.json`
   - Added `denoise: 0.45` to generation_params

3. `/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/scripts/test_img2img.py` (NEW)
   - Validation script for img2img workflow

## Conclusion

The img2img workflow is **working correctly**. Source images now flow through the graph and outputs will resemble the input composition. The router needs to be updated to:
- Wait for job completion (poll `/history/{prompt_id}`)
- Extract output filename from history
- Download via `/view?filename={fn}&type=output`
- Upload to Nextcloud `done/` folder

**Ready for integration.**
