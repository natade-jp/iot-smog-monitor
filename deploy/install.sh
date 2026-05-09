#!/usr/bin/env bash
set -euo pipefail

# 配置先アプリ名・サービス名
APP_NAME="iot-smog-monitor"
DEST_DIR="/opt/${APP_NAME}"
SERVICE_NAME="smog-monitor.service"

# root 実行必須（/opt, /etc/systemd/system への書き込みが必要）
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install.sh"
  exit 1
fi

# このスクリプトの場所を基準に、プロジェクトルートを解決
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# プロジェクトを /opt 配下へ同期コピー（不要ファイルは除外）
mkdir -p "${DEST_DIR}"
rsync -av --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "logs" \
  --exclude "data" \
  "${PROJECT_ROOT}/" "${DEST_DIR}/"

# ログ保存ディレクトリを作成
mkdir -p "${DEST_DIR}/data"
chmod 755 "${DEST_DIR}/data"

# Python依存を apt で導入（PEP 668 環境でも安全）
apt update
apt install -y \
  python3-rpi.gpio \
  python3-smbus

# systemd サービスを登録して起動
install -m 644 "${DEST_DIR}/deploy/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "Installed and started ${SERVICE_NAME}"
echo "Check logs: journalctl -u ${SERVICE_NAME} -f"
