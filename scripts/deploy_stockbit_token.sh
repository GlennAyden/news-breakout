#!/usr/bin/env bash
# Deploy a fresh Stockbit access token to the VPS and verify the orderbook feature.
#
# Alur harian (±30 detik):
#   1) Ambil access-token fresh dari Chrome (login):
#        F12 -> Network -> klik request 'exodus' -> Headers ->
#        Request Headers -> 'authorization: Bearer <SALIN INI>'
#   2) Tempel ke baris  STOCKBIT_ACCESS_TOKEN=  di ./.env   (atau pass sebagai argumen)
#   3) Jalankan:  bash scripts/deploy_stockbit_token.sh
#
# Mode:
#   bash scripts/deploy_stockbit_token.sh [TOKEN]   -> push token ke VPS, restart, verifikasi
#   bash scripts/deploy_stockbit_token.sh check      -> hanya cek status di VPS (tak ganti token)
#
# Override (opsional, via env var):
#   VPS_HOST=ubuntu@43.156.128.91   VPS_KEY=~/.ssh/glenn.pem   VPS_DIR='~/news-breakout'
set -uo pipefail

VPS_HOST="${VPS_HOST:-ubuntu@43.156.128.91}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/glenn.pem}"
VPS_DIR="${VPS_DIR:-~/news-breakout}"

ssh_vps() { ssh -i "$VPS_KEY" -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 "$VPS_HOST" "$@"; }

verify() {
  echo "--- status VPS ---"
  ssh_vps bash -s <<REMOTE
cd $VPS_DIR
echo "orderbook_enabled=\$(PYTHONPATH=. .venv/bin/python -c 'import news_breakout.config as c; print(c.load_settings().orderbook_enabled)' 2>&1)"
echo "service=\$(systemctl is-active news-breakout.service)"
echo "--- live fetch BBCA ---"
PYTHONPATH=. .venv/bin/python scripts/check_orderbook.py --live BBCA 2>&1 | grep -v 'INFO HTTP Request'
REMOTE
}

# --- status-only mode ---------------------------------------------------------
if [ "${1:-}" = "check" ] || [ "${1:-}" = "status" ]; then verify; exit $?; fi

# --- resolve token: argument(s) > ./.env --------------------------------------
# Use "$*" so a pasted "Bearer <token>" (two cmd args) is joined, not truncated.
TOKEN="$*"
if [ -z "$TOKEN" ] && [ -f .env ]; then
  TOKEN="$(grep '^STOCKBIT_ACCESS_TOKEN=' .env | head -1 | cut -d= -f2- || true)"
fi
TOKEN="${TOKEN#Bearer }"; TOKEN="${TOKEN#bearer }"
TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
if [ -z "$TOKEN" ]; then
  echo "ERROR: token kosong."
  echo "  Jalankan:  bash scripts/deploy_stockbit_token.sh <TOKEN>"
  echo "  atau isi  STOCKBIT_ACCESS_TOKEN=  di ./.env lalu jalankan tanpa argumen."
  exit 1
fi

# --- best-effort: decode JWT exp, tolak kalau sudah mati, tampilkan sisa jam ---
payload="$(printf '%s' "$TOKEN" | cut -d. -f2)"
pad=$(( (4 - ${#payload} % 4) % 4 ))
[ "$pad" -gt 0 ] && payload="${payload}$(head -c "$pad" </dev/zero | tr '\0' '=')"
exp="$(printf '%s' "$payload" | tr '_-' '/+' | base64 -d 2>/dev/null | grep -o '"exp":[0-9]\+' | grep -o '[0-9]\+' || true)"
now="$(date +%s)"
if [ -n "$exp" ]; then
  if [ "$exp" -le "$now" ]; then
    echo "ERROR: token SUDAH KEDALUWARSA (~$(( (now-exp)/60 )) menit lalu). Ambil access-token BARU dari Chrome."
    exit 1
  fi
  echo "Token valid ~$(( (exp-now)/3600 )) jam lagi (exp=$exp)."
else
  echo "WARN: gagal decode exp lokal; lanjut (verifikasi --live yang menentukan)."
fi

# --- push token ke VPS + restart (satu koneksi SSH) ---------------------------
echo "Deploy token ke $VPS_HOST ..."
ssh_vps "sed -i '/^STOCKBIT_ACCESS_TOKEN=/d' $VPS_DIR/.env && printf '\nSTOCKBIT_ACCESS_TOKEN=%s\n' '$TOKEN' >> $VPS_DIR/.env && sudo -n systemctl restart news-breakout.service && sleep 3 && echo restarted" \
  || { echo "ERROR: gagal push/restart ke VPS"; exit 1; }

verify
echo "=== Selesai. Token aktif di VPS. ==="
