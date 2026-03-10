#!/bin/bash
# Auto-pull latest code and clear .pyc cache before starting bot
# Called by ExecStartPre in bojkofx.service
# NOTE: do NOT write to bojkofx.log here — owned by service user, may cause Permission denied

APP_DIR="/home/macie/bojkofx/app"

cd "${APP_DIR}" && git pull origin master 2>&1 || true
find "${APP_DIR}/src" -name "*.pyc" -delete 2>/dev/null
exit 0

