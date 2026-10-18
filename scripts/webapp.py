#!/usr/bin/env python3
"""FLY BRAIN LAB web dashboard: live MJPEG + brain panel + remote control."""
import io
import os
import secrets
import threading
import time
from flask import Flask, Response, request, jsonify, send_file
from world_sim import World
from fly_render import render_frame
from brain_panel import render_panel

USER = "fly"
PW = os.environ.get("FLY_PW") or secrets.token_hex(4)
print(f"[webapp] login: {USER} / {PW}", flush=True)
open(os.environ.get("FLY_LOGIN_FILE", "fly_login.txt"), "w").write(f"{USER} {PW}\n")

app = Flask(__name__)
world = World()
world.start_brain_thread()
state = {"frame": None, "panel": None, "fps": 0.0}

def sim_loop():
    fps_t = time.time()
    n = 0
    panel_t = 0.0
    while True:
        t0 = time.time()
        world.step(0.033)                      # fixed step, no catch-up spiral
        img = render_frame(world)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82)
        state["frame"] = buf.getvalue()
        n += 1
        now = time.time()
        if now - fps_t >= 1.0:
            state["fps"] = round(n / (now - fps_t), 1)
            n = 0
            fps_t = now
        if now - panel_t > 1.2:
            panel_t = now
            state["panel"] = render_panel(world)
        sl = 0.033 - (time.time() - t0)
        if sl > 0:
            time.sleep(sl)

threading.Thread(target=sim_loop, daemon=True).start()

@app.before_request
def auth():
    a = request.authorization
    if not (a and a.username == USER and a.password == PW):
        return Response("401 Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="fly"'})

@app.route("/")
def index():
    return HTML

@app.route("/video.mjpg")
def video():
    def gen():
        while True:
            f = state["frame"]
            if f:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(f)).encode() + b"\r\n\r\n" + f + b"\r\n")
            time.sleep(0.05)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/brain.png")
def brain_png():
    p = state["panel"]
    return send_file(io.BytesIO(p), mimetype="image/png") if p else ("", 204)

@app.route("/api/state")
def api_state():
    s = dict(world.stats or {})
    s["fps"] = state["fps"]
    return jsonify(s)

@app.route("/api/cmd", methods=["POST"])
def api_cmd():
    j = request.get_json(force=True, silent=True) or {}
    world.cmd(str(j.get("cmd", "")), j.get("val"))
    return jsonify(ok=True)

HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🦟 FLY BRAIN LAB</title><style>
body{background:#0b0e17;color:#dfe6f2;font-family:system-ui,sans-serif;margin:0;padding:14px}
h1{font-size:20px;margin:0 0 10px} .wrap{display:flex;gap:14px;flex-wrap:wrap}
.card{background:#141a28;border:1px solid #232c42;border-radius:10px;padding:10px}
button{background:#22304d;color:#dfe6f2;border:1px solid #35476e;border-radius:8px;
padding:8px 13px;margin:3px;cursor:pointer;font-size:14px} button:hover{background:#2c3d61}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:4px}
table{font-size:13px;border-collapse:collapse}td{padding:2px 8px}
.lab{color:#8fa3c2;font-size:12px;margin:8px 0 3px}
input[type=range]{width:220px}
</style></head><body>
<h1>🦟 FLY BRAIN LAB <span style="font-size:12px;color:#8fa3c2">
— MaleCNS connectome (164,740 neurons) live on Omnara</span></h1>
<div class="wrap">
 <div class="card"><img src="/video.mjpg" width="854" height="480" style="border-radius:8px">
  <div class="lab">REMOTE CONTROL</div>
  <div class="grid">
   <button onclick="cmd('light_left')">◀ light</button>
   <button onclick="cmd('light_right')">light ▶</button>
   <button onclick="cmd('light_up')">▲ light</button>
   <button onclick="cmd('light_down')">light ▼</button>
   <button onclick="cmd('light_on')">💡 ON</button>
   <button onclick="cmd('light_off')">⚫ OFF</button>
   <button onclick="cmd('auto')">🔄 auto-drift</button>
   <button onclick="cmd('pause')">⏯ pause</button>
   <button onclick="cmd('reset')">↺ reset fly</button>
  </div>
  <div class="lab">INNATE phototaxis <input type="range" min="0" max="3" step="0.1" value="1"
    onchange="cmd('innate',this.value)"> ·
   BRAIN steering <input type="range" min="0" max="3" step="0.1" value="0.6"
    onchange="cmd('brain_gain',this.value)"> ·
   speed <input type="range" min="0.2" max="2" step="0.1" value="1"
    onchange="cmd('speed',this.value)"></div>
 </div>
 <div class="card">
  <img src="/brain.png" id="panel" width="360">
  <div class="lab">LIVE STATE</div>
  <table id="st"></table>
 </div>
</div>
<script>
function cmd(c,v){fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({cmd:c,val:v===undefined?null:parseFloat(v)})})}
function tick(){fetch('/api/state').then(r=>r.json()).then(s=>{
 document.getElementById('st').innerHTML=
 `<tr><td>sim time</td><td>${s.t}s</td></tr>
  <tr><td>video</td><td>${s.fps} fps</td></tr>
  <tr><td>brain speed</td><td>${s.brain_x}x real-time</td></tr>
  <tr><td>dist to light</td><td>${s.dist} mm</td></tr>
  <tr><td>fly speed</td><td>${s.speed} mm/s</td></tr>
  <tr><td>turn rate</td><td>${s.turn} rad/s</td></tr>
  <tr><td>lights caught</td><td>${s.caught}</td></tr>
  <tr><td>VIS L/R</td><td>${s.hz.vis_L} / ${s.hz.vis_R} Hz</td></tr>
  <tr><td>DN L/R</td><td>${s.hz.dn_L} / ${s.hz.dn_R} Hz</td></tr>
  <tr><td>MOTOR</td><td>${s.hz.motor} Hz</td></tr>
  <tr><td>KC / DAN / MBON</td><td>${s.hz.kc} / ${s.hz.dan} / ${s.hz.mbon} Hz</td></tr>`});
 setTimeout(()=>{document.getElementById('panel').src='/brain.png?t='+Date.now()},0)}
tick();setInterval(tick,1500);setInterval(()=>tick(),1500);
</script></body></html>"""

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, threaded=True)
