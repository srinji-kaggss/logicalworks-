#!/usr/bin/env bash
# install.sh — one-command production installer for lgwks
# Usage: ./install.sh
# Idempotent: running twice is safe.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
BIN_DIR="$REPO_ROOT/bin"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

# ── Step 1: Python ───────────────────────────────────────────────────────────
step "Checking Python..."

if ! command -v python3 >/dev/null 2>&1; then
    error "python3 not found."
    echo ""
    echo "Install Python 3.10+ :"
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt-get install python3.12 python3.12-venv"
    echo "  Or download from https://www.python.org/downloads/"
    exit 1
fi

PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'; then
    error "Python ${PY_MAJOR}.${PY_MINOR} found, but 3.10+ is required."
    exit 1
fi

info "Python ${PY_MAJOR}.${PY_MINOR} ✓"

# ── Step 2: venv ───────────────────────────────────────────────────────────
step "Setting up virtual environment..."

if [ -d "$VENV_DIR" ]; then
    info "Virtual environment exists at $VENV_DIR"
else
    python3 -m venv "$VENV_DIR"
    info "Created virtual environment"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python"

# Upgrade pip / setuptools (pin <82 for torch 2.12 compat)
$PIP install --quiet --upgrade pip "setuptools<82" wheel

# ── Step 3: Runtime dependencies ─────────────────────────────────────────────
step "Installing runtime dependencies..."
$PIP install --quiet -r "$REPO_ROOT/requirements.txt"
info "Runtime deps ✓"

# ── Step 4: Dev dependencies (for model setup) ────────────────────────────────
step "Installing developer dependencies (ML setup)..."
$PIP install --quiet -r "$REPO_ROOT/requirements-dev.txt"
info "Dev deps ✓"

# ── Step 5: Playwright browsers ──────────────────────────────────────────────
step "Installing Playwright browsers..."

if $VENV_DIR/bin/playwright install chromium webkit >/dev/null 2>&1; then
    info "Playwright browsers ✓"
else
    warn "Playwright browser install had issues."
    warn "Run manually if needed: $VENV_DIR/bin/playwright install"
fi

# ── Step 6: Download models ──────────────────────────────────────────────────
step "Downloading models (one-time)..."

if [ -d "$REPO_ROOT/models/tiny-bert" ] && [ -f "$REPO_ROOT/models/tiny-bert/config.json" ]; then
    info "PyTorch model already present ✓"
    if [ -d "$REPO_ROOT/models/tiny-bert.mlpackage" ]; then
        info "CoreML model already present ✓"
    else
        warn "CoreML model missing (optional; may require Python ≤3.12)"
    fi
else
    if $PYTHON "$REPO_ROOT/scripts/setup_models.py" all tiny-bert; then
        info "Models downloaded and converted ✓"
    else
        # If the torch model exists but conversion failed, continue
        if [ -d "$REPO_ROOT/models/tiny-bert" ] && [ -f "$REPO_ROOT/models/tiny-bert/config.json" ]; then
            warn "Model download succeeded but CoreML conversion failed (optional)."
            warn "Framework will use CPU (torch) inference."
        else
            error "Model download failed."
            echo ""
            echo "Common causes:"
            echo "  - No internet connection"
            echo "  - HuggingFace Hub is down"
            echo "  - Disk space exhausted (need ~500MB for torch + models)"
            echo ""
            echo "To retry: $PYTHON $REPO_ROOT/scripts/setup_models.py all tiny-bert"
            exit 1
        fi
    fi
fi

# ── Step 7: CLI wrapper ──────────────────────────────────────────────────────
step "Creating CLI wrapper..."

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/lgwks" << 'EOF'
#!/usr/bin/env bash
# lgwks — auto-activates the repo virtual environment
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/lgwks" "$@"
EOF

chmod +x "$BIN_DIR/lgwks"
info "CLI wrapper at $BIN_DIR/lgwks"

# ── Step 8: Smoke test ─────────────────────────────────────────────────────
step "Running smoke test (lgwks doctor)..."

if "$BIN_DIR/lgwks" doctor; then
    info "Smoke test passed ✓"
else
    error "Smoke test failed."
    echo ""
    echo "Run diagnostics manually:"
    echo "  $BIN_DIR/lgwks doctor"
    exit 1
fi

# ── Step 9: Next steps ─────────────────────────────────────────────────────
echo ""
info "Installation complete."
echo ""
echo "Add to your PATH (pick one):"
echo ""
echo "  Temporary (this shell only):"
echo "    export PATH=\"$BIN_DIR:\$PATH\""
echo ""
echo "  Permanent (add to ~/.zshrc or ~/.bash_profile):"
echo "    echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc"
echo ""
echo "Then run:"
echo "  lgwks doctor        # verify health"
echo "  lgwks login <url>   # authenticate with a site"
echo "  lgwks --help        # see all commands"
echo ""
