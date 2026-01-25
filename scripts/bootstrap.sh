set -euo pipefail

REPO_URL="https://github.com/githubbzxs/grid"
TARGET_DIR="${GRID_DIR:-grid}"

if ! command -v git >/dev/null 2>&1; then
  echo "缺少 git，请先安装 git。"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "缺少 python3，请先安装 Python 3.11+。"
  exit 1
fi

if [ -d "$TARGET_DIR/.git" ]; then
  echo "检测到已有仓库，正在更新..."
  git -C "$TARGET_DIR" pull --rebase
else
  echo "开始拉取仓库..."
  git clone "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"
bash scripts/start.sh
