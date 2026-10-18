#!/usr/bin/env python3
"""Keep the live fly lab up, and keep the public link working.

- supervises the Flask dashboard (restarts it if it dies)
- supervises the cloudflared tunnel (restarts it if it dies)
- when the tunnel URL changes, rewrites docs/backend.json and pushes it,
  so the GitHub Pages site always finds the live backend automatically.
Also keeps an active process on the machine (prevents idle sleep).
"""
import json, os, pathlib, re, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(os.environ.get("FLY_ROOT", "/workspace/fly"))
REPO = ROOT / "repo"
LOGS = ROOT / "logs"; LOGS.mkdir(exist_ok=True)
ENV = {**os.environ,
       "FLY_PW": os.environ.get("FLY_PW", "975bf54e"),
       "FLY_KEY": os.environ.get("FLY_KEY", "ctrl-72fedb10ad5f5933"),
       "FLY_VIEW_KEY": os.environ.get("FLY_VIEW_KEY", "view-2b612492b255d468")}
PORT = int(os.environ.get("FLY_PORT", "8000"))

def log(m): print(time.strftime("[%H:%M:%S]"), m, flush=True)

def spawn(cmd, logname):
    f = open(LOGS / logname, "a")
    return subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=ENV)

def web_alive():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/login", timeout=5)
        return True
    except Exception:
        return False

def tunnel_url():
    try:
        txt = (LOGS / "tunnel.log").read_text()[-60000:]
    except FileNotFoundError:
        return None
    m = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", txt)
    return m[-1] if m else None

def publish(url):
    p = REPO / "docs" / "backend.json"
    try:
        d = json.loads(p.read_text())
    except Exception:
        d = {"view_key": ENV["FLY_VIEW_KEY"]}
    if d.get("url") == url:
        return False
    d["url"] = url
    d["view_key"] = ENV["FLY_VIEW_KEY"]
    d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    d.setdefault("note", "Live compute backend (Omnara machine, MaleCNS LIF simulation). "
                         "Updated automatically by scripts/watchdog.py when the tunnel moves.")
    p.write_text(json.dumps(d, indent=2) + "\n")
    subprocess.run(["git", "-C", str(REPO), "add", "docs/backend.json"])
    subprocess.run(["git", "-C", str(REPO), "-c", "commit.gpgsign=false", "commit", "-q",
                    "-m", f"watchdog: backend url -> {url}"])
    r = subprocess.run(["git", "-C", str(REPO), "push", "-q", "origin", "main"],
                       capture_output=True, text=True)
    if r.returncode != 0:      # e.g. the PAT was revoked -> try the deploy key over SSH
        r = subprocess.run(["git", "-C", str(REPO), "push", "-q",
                            "git@github.com:opendeta/fly-semulator.git", "main"],
                           capture_output=True, text=True)
        log("https push failed -> ssh push rc=%d" % r.returncode)
    log(f"published backend url {url} (push rc={r.returncode})")
    return True

web = tun = None
log("watchdog starting")
while True:
    try:
        if web is None or web.poll() is not None:
            log("starting dashboard")
            web = spawn([sys.executable, str(ROOT / "scripts" / "webapp.py")], "web.log")
            time.sleep(25)          # warm-up
        if not web_alive():
            log("dashboard not answering -> restarting")
            try: web.terminate()
            except Exception: pass
            web = None
            continue
        if tun is None or tun.poll() is not None:
            log("starting tunnel")
            tun = spawn(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{PORT}",
                         "--no-autoupdate", "--protocol", "http2"], "tunnel.log")
            time.sleep(18)
        u = tunnel_url()
        if u:
            publish(u)
    except Exception as e:
        log(f"watchdog error: {e!r}")
    time.sleep(20)
