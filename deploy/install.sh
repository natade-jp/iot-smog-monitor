#!/usr/bin/env bash
set -euo pipefail

APP_NAME="iot-smog-monitor"
DEST_DIR="/opt/${APP_NAME}"
SERVICE_NAME="smog-monitor.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "${DEST_DIR}"
rsync -av --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "logs" \
  --exclude "data" \
  "${PROJECT_ROOT}/" "${DEST_DIR}/"

mkdir -p "${DEST_DIR}/data"
chmod 755 "${DEST_DIR}/data"

python3 -m pip install --upgrade pip
python3 -m pip install -r "${DEST_DIR}/requirements.txt"

install -m 644 "${DEST_DIR}/deploy/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "Installed and started ${SERVICE_NAME}"
echo "Check logs: journalctl -u ${SERVICE_NAME} -f"
