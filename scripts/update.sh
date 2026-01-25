set -euo pipefail

TARGET_DIR="${GRID_DIR:-grid}"

if [ ! -d "$TARGET_DIR/.git" ]; then
  echo "未找到仓库目录：$TARGET_DIR"
  echo "请先执行一键部署脚本。"
  exit 1
fi

git -C "$TARGET_DIR" pull --rebase
cd "$TARGET_DIR"
bash scripts/start.sh
