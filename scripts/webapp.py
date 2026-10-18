#!/usr/bin/env python3
"""FLY BRAIN LAB dashboard: live MJPEG + brain panel + remote control.

Auth: cookie login page (default) or `?k=<key>` one-click links.
Two keys:
  FLY_KEY      -> control (commands + view)
  FLY_VIEW_KEY -> view only (streams/panel/state) - safe to embed in a public page
CORS is open so a static front-end (e.g. GitHub Pages) can drive this backend.
"""
import io
import os
import secrets
import threading
import time
from flask import Flask, Response, request, jsonify, send_file, redirect
from world_sim import World
from fly_render import render_frame
from brain_panel import render_panel

USER = os.environ.get("FLY_USER", "fly")
PW = os.environ.get("FLY_PW") or secrets.token_hex(4)
CTRL = os.environ.get("FLY_KEY") or secrets.token_hex(16)
VIEW = os.environ.get("FLY_VIEW_KEY") or secrets.token_hex(16)
print(f"[webapp] login: {USER} / {PW}", flush=True)
print(f"[webapp] control key: {CTRL}", flush=True)
print(f"[webapp] view key:    {VIEW}", flush=True)
print(f"[webapp] one-click:   /?k={CTRL}", flush=True)
open(os.environ.get("FLY_LOGIN_FILE", "fly_login.txt"), "w").write(f"{USER} {PW}\n{CTRL}\n{VIEW}\n")

app = Flask(__name__)
world = World()
world.start_brain_thread()
state = {"frame": None, "panel": None, "fps": 0.0}


def _keys():
    k = request.args.get("k") or request.cookies.get("fly_session")
    if not k:
        a = request.authorization
        if a and a.username == USER and a.password == PW:
            return CTRL
    return k


def _authed(control=False):
    k = _keys()
    if control:
        return k in (CTRL, PW)
    return k in (CTRL, VIEW, PW)


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if (request.form.get("pw") or "") == PW:
            r = redirect("/")
            r.set_cookie("fly_session", CTRL, max_age=86400, httponly=True, samesite="Lax")
            return r
        return Response(LOGIN_HTML.replace("<!--ERR-->",
                        "<p class=err>wrong password / ভুল পাসওয়ার্ড</p>"), 200)
    return Response(LOGIN_HTML, 200)


@app.before_request
def auth():
    if request.path in ("/login", "/favicon.ico"):
        return None
    if request.method == "OPTIONS":
        return Response("", 200)
    if _authed(control=request.path.startswith("/api/cmd")):
        return None
    if request.path.startswith("/api/") or request.path.endswith((".mjpg", ".png")):
        return Response("unauthorized", 401)
    return redirect("/login")


def sim_loop():
    fps_t = time.time()
    n = 0
    panel_t = 0.0
    while True:
        t0 = time.time()
        world.step(0.033)
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


LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0e17"><title>Login · FLY BRAIN LAB</title>
<style>*,*::before,*::after{box-sizing:border-box}
html,body{max-width:100%;overflow-x:hidden}
body{background:#0b0e17;color:#dfe6f2;font-family:system-ui,-apple-system,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:16px}
.card{background:#141a28;border:1px solid #232c42;border-radius:14px;padding:26px 22px;
text-align:center;width:100%;max-width:330px}
h1{font-size:clamp(18px,5.4vw,20px);margin:0 0 6px}
p{color:#8fa3c2;font-size:clamp(12.5px,3.6vw,13.5px);margin:6px 0 16px}
input{width:100%;padding:12px;border-radius:9px;border:1px solid #35476e;background:#0f1524;
color:#dfe6f2;font-size:16px}
button{margin-top:12px;width:100%;padding:12px;border-radius:9px;border:0;background:#2c3d61;
color:#fff;font-size:16px;cursor:pointer;min-height:46px}
.err{color:#ff8080}</style></head><body><div class="card">
<h1>🪰 FLY BRAIN LAB</h1><p>MaleCNS connectome · live simulation</p>
<!--ERR--><form method="post" action="/login">
<input type="password" name="pw" placeholder="password" autofocus autocomplete="current-password">
<button type="submit">Enter →</button></form></div></body></html>"""

HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0e17"><title>🪰 FLY BRAIN LAB</title><style>
*,*::before,*::after{box-sizing:border-box;min-width:0}
html,body{max-width:100%;overflow-x:hidden}
body{background:#0b0e17;color:#dfe6f2;font-family:system-ui,-apple-system,sans-serif;
margin:0;font-size:15px;-webkit-text-size-adjust:100%;
padding:12px 12px calc(26px + env(safe-area-inset-bottom))}
img{max-width:100%;display:block}
h1{font-size:clamp(17px,5.2vw,21px);margin:0 0 10px;line-height:1.25}
h1 small{display:block;font-size:clamp(11px,3.2vw,12.5px);color:#8fa3c2;font-weight:400;margin-top:3px}
.wrap{max-width:1100px;margin:0 auto;display:flex;flex-direction:column;gap:12px}
.card{background:#141a28;border:1px solid #232c42;border-radius:12px;padding:12px;width:100%}
img.stream{width:100%;height:auto;border-radius:9px;background:#05070d;aspect-ratio:854/480;object-fit:contain}
.lab{color:#8fa3c2;font-size:clamp(10.5px,3vw,12px);margin:12px 0 6px;
text-transform:uppercase;letter-spacing:.06em}
.btns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
button{background:#22304d;color:#dfe6f2;border:1px solid #35476e;border-radius:9px;
padding:11px 6px;font-size:clamp(12px,3.5vw,14px);cursor:pointer;min-height:44px;
line-height:1.15;overflow-wrap:anywhere;-webkit-tap-highlight-color:transparent}
button:active{background:#33477a}
.knob{margin:8px 0}.knob label{display:block;font-size:clamp(12px,3.4vw,13.5px);color:#8fa3c2}
input[type=range]{width:100%;height:30px;margin:0}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:8px;padding:6px 2px;
border-bottom:1px solid #1c2434;font-size:clamp(12.5px,3.5vw,13.5px)}
.row span{color:#8fa3c2}.row b{color:#fff;font-weight:600;text-align:right;overflow-wrap:anywhere}
@media (min-width:760px){
 body{padding:22px 18px 46px}
 .wrap{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:16px;align-items:start}
 .card{padding:14px}
}
</style></head><body>
<h1>🦟 FLY BRAIN LAB<small>MaleCNS connectome · 164,740 neurons · live</small></h1>
<div class="wrap">
 <div class="card">
  <img id="vid" class="stream" alt="live fly stream">
  <div class="lab">Remote control</div>
  <div class="btns">
   <button onclick="cmd('light_left')">◀ light</button>
   <button onclick="cmd('light_right')">light ▶</button>
   <button onclick="cmd('light_up')">▲ light</button>
   <button onclick="cmd('light_down')">light ▼</button>
   <button onclick="cmd('light_on')">💡 ON</button>
   <button onclick="cmd('light_off')">⚫ OFF</button>
   <button onclick="cmd('auto')">🔄 auto</button>
   <button onclick="cmd('pause')">⏯ pause</button>
   <button onclick="cmd('reset')">↺ reset</button>
  </div>
  <div class="lab">Knobs</div>
  <div class="knob"><label>innate phototaxis <span id="v1">1.0</span></label>
   <input type="range" min="0" max="3" step="0.1" value="1"
    oninput="document.getElementById('v1').textContent=(+this.value).toFixed(1)"
    onchange="cmd('innate',this.value)"></div>
  <div class="knob"><label>brain steering <span id="v2">0.6</span></label>
   <input type="range" min="0" max="3" step="0.1" value="0.6"
    oninput="document.getElementById('v2').textContent=(+this.value).toFixed(1)"
    onchange="cmd('brain_gain',this.value)"></div>
  <div class="knob"><label>speed <span id="v3">1.0</span></label>
   <input type="range" min="0.2" max="2" step="0.1" value="1"
    oninput="document.getElementById('v3').textContent=(+this.value).toFixed(1)"
    onchange="cmd('speed',this.value)"></div>
 </div>
 <div class="card">
  <img id="panel" class="stream" alt="brain panel" style="aspect-ratio:auto">
  <div class="lab">Live state</div>
  <div id="st"></div>
 </div>
</div>
<script>
const KEY = new URLSearchParams(location.search).get('k') || '';
const Q = KEY ? ('?k=' + encodeURIComponent(KEY)) : '';
document.getElementById('vid').src = '/video.mjpg' + Q;
function cmd(c,v){fetch('/api/cmd'+Q,{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({cmd:c,val:v===undefined?null:parseFloat(v)})})}
function tick(){fetch('/api/state'+Q).then(r=>r.json()).then(s=>{
 const rows=[['sim time',s.t+' s'],['video',s.fps+' fps'],
  ['brain clock',s.brain_x+'× real-time'],['dist to light',s.dist+' mm'],
  ['fly speed',s.speed+' mm/s'],['turn rate',s.turn+' rad/s'],['lights caught',s.caught],
  ['visual L/R',s.hz.vis_L+' / '+s.hz.vis_R+' Hz'],
  ['descending L/R',s.hz.dn_L+' / '+s.hz.dn_R+' Hz'],['motor',s.hz.motor+' Hz'],
  ['KC / DAN / MBON',s.hz.kc+' / '+s.hz.dan+' / '+s.hz.mbon+' Hz']];
 document.getElementById('st').innerHTML=rows.map(r=>
  '<div class="row"><span>'+r[0]+'</span><b>'+r[1]+'</b></div>').join('');
 document.getElementById('panel').src='/brain.png'+Q+'&t='+Date.now()})}
tick();setInterval(tick,1500);
</script></body></html>"""

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, threaded=True)
