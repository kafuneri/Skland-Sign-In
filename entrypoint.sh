#!/bin/bash
set -e

CRON_EXPR=$(python3 -c "
import yaml
try:
    with open('config.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    print(cfg.get('cron', '0 1 * * *'))
except:
    print('0 1 * * *')
")

echo "定时任务: ${CRON_EXPR}"
echo "首次执行签到..."
python3 main.py || true

echo "${CRON_EXPR} cd /app && python3 main.py >> /proc/1/fd/1 2>&1" > /etc/crontabs/root

echo "启动定时任务调度..."
exec crond -f -l 2
