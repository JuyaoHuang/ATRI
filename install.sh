#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/JuyaoHuang/atri.git}"
TARGET_DIR="${TARGET_DIR:-atri}"
PYPI_INDEX="${PYPI_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"
SKIP_CLONE=0

usage() {
  cat <<'EOF'
Usage:
  bash install.sh [options]

Options:
  --repo-url URL       Git repository URL to clone when not already in atri.
  --target-dir DIR     Clone target directory. Default: atri
  --pypi-index URL     PyPI mirror for uv sync.
                       Default: https://pypi.tuna.tsinghua.edu.cn/simple
                       Aliyun alternative: https://mirrors.aliyun.com/pypi/simple/
  --npm-registry URL   npm registry mirror.
                       Default: https://registry.npmmirror.com
  --skip-clone         Do not clone. Require current directory to be atri.
  -h, --help           Show this help.

Environment overrides:
  REPO_URL, TARGET_DIR, PYPI_INDEX, NPM_REGISTRY
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url)
      REPO_URL="${2:?missing value for --repo-url}"
      shift 2
      ;;
    --target-dir)
      TARGET_DIR="${2:?missing value for --target-dir}"
      shift 2
      ;;
    --pypi-index)
      PYPI_INDEX="${2:?missing value for --pypi-index}"
      shift 2
      ;;
    --npm-registry)
      NPM_REGISTRY="${2:?missing value for --npm-registry}"
      shift 2
      ;;
    --skip-clone)
      SKIP_CLONE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

is_atri_repo() {
  [[ -f "pyproject.toml" && -f "config.yaml" && -f ".gitmodules" ]]
}

need_cmd git
need_cmd uv
need_cmd npm

if is_atri_repo; then
  REPO_DIR="$(pwd)"
elif [[ "$SKIP_CLONE" -eq 1 ]]; then
  echo "--skip-clone was set, but current directory is not an atri repository." >&2
  exit 1
elif [[ -d "$TARGET_DIR/.git" ]]; then
  REPO_DIR="$(cd "$TARGET_DIR" && pwd)"
else
  echo "Cloning atri from: $REPO_URL"
  git clone --recurse-submodules "$REPO_URL" "$TARGET_DIR"
  REPO_DIR="$(cd "$TARGET_DIR" && pwd)"
fi

cd "$REPO_DIR"

echo "Repository: $REPO_DIR"
echo "Syncing submodules..."
git submodule sync --recursive
git submodule update --init --recursive

if [[ ! -f ".env" && -f ".env.example" ]]; then
  echo "Creating .env from .env.example"
  cp ".env.example" ".env"
fi

echo "Installing backend dependencies with uv"
echo "PyPI index: $PYPI_INDEX"
UV_DEFAULT_INDEX="$PYPI_INDEX" uv sync

if [[ -f "frontend/package.json" ]]; then
  echo "Installing frontend dependencies with npm"
  echo "npm registry: $NPM_REGISTRY"
  (
    cd frontend
    npm install --registry "$NPM_REGISTRY"
  )
else
  echo "frontend/package.json was not found. Check submodule status." >&2
  exit 1
fi

cat <<'EOF'

Install finished.

Next steps:
  1. Edit .env and fill OPENAI_API_KEY / COMPRESS_API_KEY.
  2. Start backend:
       uv run python -m src.main
  3. Start frontend in another terminal:
       cd frontend
       npm run dev

URLs:
  Frontend: http://localhost:5200
  Backend:  http://localhost:8430
  Swagger:  http://localhost:8430/docs
EOF
