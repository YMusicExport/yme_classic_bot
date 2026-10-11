#!/usr/bin/env bash
# Run on the server by GitHub Actions (.github/workflows/deploy.yml) — the
# deploy SSH key is restricted to this script in authorized_keys. Updates
# the bot to origin/main and restarts it.
set -euo pipefail

cd /opt/yme_bot
git fetch -q origin main
git reset -q --hard origin/main
.venv/bin/pip install -q -r requirements.txt
systemctl restart yme_bot.service
sleep 5
systemctl is-active yme_bot.service
git log --oneline -1
