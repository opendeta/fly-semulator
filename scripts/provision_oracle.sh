#!/usr/bin/env bash
# Provision Fly Brain Lab on a fresh Ubuntu 22.04/24.04 VM (x86 or ARM).
# Usage:  bash provision_oracle.sh [install-dir]
set -euo pipefail
DIR="${1:-$HOME/fly-semulator}"

echo "== packages =="
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip ffmpeg git curl tmux ca-certificates

echo "== cloudflared =="
if ! command -v cloudflared >/dev/null; then
  ARCH=$(uname -m)
  case "$ARCH" in
    aarch64|arm64) PKG=cloudflared-linux-arm64.deb ;;
    x86_64)        PKG=cloudflared-linux-amd64.deb ;;
    *) echo "unsupported arch $ARCH"; exit 1 ;;
  esac
  curl -sL -o /tmp/cf.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/$PKG"
  sudo dpkg -i /tmp/cf.deb >/dev/null || sudo apt-get install -f -y -qq
fi
cloudflared --version

echo "== repo =="
[ -d "$DIR/.git" ] || git clone --depth 1 https://github.com/opendeta/fly-semulator "$DIR"
cd "$DIR"

echo "== python env =="
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "== connectome data (CC-BY, ~535 MB) + plasticity substrate =="
export FLY_DATA="$DIR/data"
bash scripts/fetch_data.sh
python3 scripts/build_plasticity.py

echo "== start under tmux =="
cat > "$DIR/run.sh" <<RUN
#!/usr/bin/env bash
cd "$DIR" && . .venv/bin/activate
export FLY_DATA="$DIR/data"
export FLY_UPLOADS="$DIR/uploads"
export FLY_PW="\${FLY_PW:-975bf54e}"
export FLY_KEY="\${FLY_KEY:-ctrl-72fedb10ad5f5933}"
export FLY_VIEW_KEY="\${FLY_VIEW_KEY:-view-2b612492b255d468}"
mkdir -p "\$FLY_UPLOADS" logs
exec python3 scripts/watchdog.py
RUN
chmod +x "$DIR/run.sh"
tmux kill-session -t fly 2>/dev/null || true
tmux new-session -d -s fly "bash $DIR/run.sh 2>&1 | tee -a $DIR/logs/run.log"
sleep 5
tmux ls
echo
echo "done. the watchdog is running in tmux session 'fly'."
echo "log: tail -f $DIR/logs/run.log   (it prints the tunnel URL and pushes it to GitHub)"
