set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${GRID_HOST:-127.0.0.1}"
PORT="${GRID_PORT:-8000}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r "apps/server/requirements.txt"

export GRID_DATA_DIR="$ROOT_DIR/data"

echo "WebUI: http://127.0.0.1:${PORT}/"
./.venv/bin/python -m uvicorn app.main:app --app-dir "apps/server" --host "$HOST" --port "$PORT"

