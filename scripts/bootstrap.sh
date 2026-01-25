set -euo pipefail

REPO_URL="https://github.com/githubbzxs/grid"
TARGET_DIR="${GRID_DIR:-grid}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    SUDO=""
  fi
fi

ensure_python_deps() {
  if command -v apt-get >/dev/null 2>&1; then
    if [ -z "$SUDO" ] && [ "$(id -u)" -ne 0 ]; then
      echo "缺少 python3-venv，请以 root 或使用 sudo 运行。"
      exit 1
    fi
    need_install=0
    if command -v dpkg >/dev/null 2>&1; then
      dpkg -s python3-venv >/dev/null 2>&1 || need_install=1
      dpkg -s python3-pip >/dev/null 2>&1 || need_install=1
    else
      python3 -c "import ensurepip" >/dev/null 2>&1 || need_install=1
    fi
    if [ "$need_install" -eq 1 ]; then
      echo "安装 python3-venv 与 python3-pip..."
      $SUDO apt-get update
      $SUDO apt-get install -y python3-venv python3-pip
    fi
    return 0
  fi
  if python3 -c "import ensurepip" >/dev/null 2>&1; then
    return 0
  fi
  echo "缺少 python3-venv，请先安装 Python 3.11+ 及 python3-venv。"
  exit 1
}

if ! command -v git >/dev/null 2>&1; then
  echo "缺少 git，请先安装 git。"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "缺少 python3，请先安装 Python 3.11+。"
  exit 1
fi

ensure_python_deps

if [ -d "$TARGET_DIR/.git" ]; then
  echo "检测到已有仓库，正在更新..."
  git -C "$TARGET_DIR" pull --rebase
else
  echo "开始拉取仓库..."
  git clone "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

if [ -d ".venv" ]; then
  if ! ./.venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo "检测到损坏的虚拟环境，准备重建..."
    rm -rf .venv
  fi
fi

bash scripts/start.sh
