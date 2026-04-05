#!/bin/bash
# bildwerk - Initial setup script
# This script prepares the basic directory structure and checks prerequisites

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "🏛️ bildwerk Setup Script"
echo "========================"
echo ""

# Check prerequisites
echo "📋 Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3.10 or newer."
    exit 1
fi
echo "✅ Python3: $(python3 --version)"

# Check Git
if ! command -v git &> /dev/null; then
    echo "❌ Git not found. Please install Git."
    exit 1
fi
echo "✅ Git: $(git --version)"

# Check for private submodule
if [ ! -d ".git/modules/private" ] && [ ! -d "private" ]; then
    echo "⚠️  Private submodule not found. Run:"
    echo "   git submodule add <private-repo-url> private"
    echo ""
fi

# Create directory structure
echo ""
echo "📁 Creating directory structure..."

mkdir -p "${ROOT_DIR}/logs"
mkdir -p "${ROOT_DIR}/temp"
mkdir -p "${ROOT_DIR}/output"
mkdir -p "${ROOT_DIR}/private/config"
mkdir -p "${ROOT_DIR}/private/secrets"

echo "✅ Directory structure created"

# Create config templates
echo ""
echo "📝 Creating config templates..."

cat > "${ROOT_DIR}/private/config/router.yaml.example" << 'EOF'
# bildwerk Router Configuration

router:
  name: bildwerk-router
  listen_host: "0.0.0.0"
  listen_port: 8080
  poll_interval_seconds: 30
  max_concurrent_jobs: 2

nextcloud:
  base_url: "https://nextcloud.example.com"
  username: "bildwerk-service"
  # password should be in secrets/nextcloud.yaml
  folders:
    base: "bildwerk"
    inbox: "inbox"
    processing: "processing"
    done: "done"
    error: "error"
    review: "review"

workers:
  - name: "gpu-a"
    url: "http://192.168.0.XXX:8188"
    type: "gpu"
    capacity: 1
  - name: "gpu-b"
    url: "http://192.168.0.XXX:8189"
    type: "gpu"
    capacity: 1
  - name: "cpu"
    url: "http://192.168.0.XXX:8081"
    type: "cpu"
    capacity: 1
    experimental: true

logging:
  level: "INFO"
  graylog:
    enabled: false
    host: "graylog.example.com"
    port: 12201
EOF

cat > "${ROOT_DIR}/private/config/worker.yaml.example" << 'EOF'
# bildwerk GPU Worker Configuration

worker:
  name: bildwerk-gpu-a
  listen_host: "0.0.0.0"
  listen_port: 8188
  type: "gpu"

comfyui:
  path: "/opt/bildwerk/worker/ComfyUI"
  api_port: 8188
  args:
    - --listen
    - 0.0.0.0
    - --port
    - "8188"
    - --disable-safety-checker

models:
  base_path: "/opt/bildwerk/worker/ComfyUI/models"
  checkpoint: "sd_xl_base_1.0.safetensors"
  refiner: "sd_xl_refiner_1.0.safetensors"
  controlnets:
    - "controlnet-sdxl-softedge.safetensors"
    - "controlnet-sdxl-canny.safetensors"
    - "controlnet-sdxl-mlsd.safetensors"
    - "controlnet-sdxl-depth.safetensors"
    - "controlnet-sdxl-lineart.safetensors"

presets:
  path: "/opt/bildwerk/bildwerk/presets"

temp_path: "/tmp/bildwerk/worker"
output_path: "/tmp/bildwerk/output"

logging:
  level: "INFO"
  graylog:
    enabled: false
    host: "graylog.example.com"
    port: 12201
EOF

echo "✅ Config templates created"

# Create .gitignore for private data
cat > "${ROOT_DIR}/private/.gitignore" << 'EOF'
# Secrets
secrets/*.yaml
secrets/*.json

# Logs
logs/*
!.gitkeep

# Temporary files
temp/*
!.gitkeep

# Output files
output/*
!.gitkeep

# Environment
.env
*.pyc
__pycache__/
*.egg-info/
EOF

echo "✅ .gitignore created"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Configure Nextcloud service account"
echo "2. Edit private/config/router.yaml with your settings"
echo "3. Set up GPU worker LXCs on wgpx15"
echo "4. Download required models (SDXL, ControlNet)"
echo "5. Start services"
echo ""
echo "See docs/deployment.md for detailed instructions."