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
from PIL import Image
from flask import Flask, Response, request, jsonify, send_file, redirect
from world_sim import World
from fly_render import render_frame
from brain_panel import render_panel
from train_panel import render_curve
from video_input import extract as extract_video

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
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024
world = World()
world.start_brain_thread()
state = {"frame": None, "frame_small": None, "panel": None, "curve": None, "fps": 0.0}
UPLOADS = os.environ.get("FLY_UPLOADS", "uploads")
os.makedirs(UPLOADS, exist_ok=True)


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
    curve_t = 0.0
    while True:
        t0 = time.time()
        world.step(0.033)
        img = render_frame(world)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82)
        state["frame"] = buf.getvalue()
        if n % 2 == 0:                       # half rate for the lite stream
            sbuf = io.BytesIO()
            img.resize((480, 270), Image.BILINEAR).save(sbuf, "JPEG", quality=72)
            state["frame_small"] = sbuf.getvalue()
        n += 1
        now = time.time()
        if now - fps_t >= 1.0:
            state["fps"] = round(n / (now - fps_t), 1)
            n = 0
            fps_t = now
        if now - panel_t > 2.0:
            panel_t = now
            state["panel"] = render_panel(world)
        if now - curve_t > 3.0:
            curve_t = now
            state["curve"] = render_curve(world)
        sl = 0.033 - (time.time() - t0)
        if sl > 0:
            time.sleep(sl)


threading.Thread(target=sim_loop, daemon=True).start()


@app.route("/")
def index():
    return HTML


@app.route("/video.mjpg")
def video():
    fps = max(2, min(30, int(request.args.get("fps", 25) or 25)))
    small = request.args.get("small") == "1"
    def gen():
        delay = 1.0 / fps
        while True:
            f = state["frame_small" if small else "frame"]
            if f:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(f)).encode() + b"\r\n\r\n" + f + b"\r\n")
            time.sleep(delay)
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


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("video")
    if f is None or not f.filename:
        return jsonify(ok=False, error="no file"), 400
    name = "".join(c for c in f.filename if c.isalnum() or c in "._-")[:80] or "clip.mp4"
    path = os.path.join(UPLOADS, name)
    f.save(path)
    try:
        meta = extract_video(path, UPLOADS)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    import numpy as np
    z = np.load(os.path.join(UPLOADS, "video_drive.npz"))
    world.video = dict(left=z["left"], right=z["right"], motion=z["motion"],
                       fps=float(z["fps"]), name=name)
    world.cue_side = int(z["cue"])
    world.mode = "video"
    world.auto_light = False
    return jsonify(ok=True, meta=meta)


@app.route("/api/train", methods=["POST"])
def api_train():
    j = request.get_json(force=True, silent=True) or {}
    a = str(j.get("action", "start"))
    if a == "start":
        world.cue_side = int(j.get("cue_side") or world.cue_side or 1)
        world.start_training(n_trials=int(j.get("trials") or 12),
                             cue_secs=float(j.get("cue_secs") or 6.0),
                             test_secs=float(j.get("test_secs") or 6.0))
    elif a == "stop":
        world.stop_training()
    elif a == "reset":
        world.cmd("reset_learning")
    return jsonify(ok=True, state=world.stats.get("train", {}))


@app.route("/api/curve.png")
def curve_png():
    p = state["curve"]
    return send_file(io.BytesIO(p), mimetype="image/png") if p else ("", 204)


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
  <div id="toast" style="position:fixed;left:50%;transform:translateX(-50%);bottom:18px;
   z-index:99;padding:10px 16px;border-radius:10px;font-size:14px;opacity:0;
   transition:opacity .25s;background:#1d5c33;color:#fff;max-width:92vw;text-align:center"></div>
  <img id="vid" class="stream" alt="live fly stream">
  <button id="lite" onclick="toggleLite()" style="width:100%">⚡ Lite mode</button>
  <div class="lab">Remote control</div>
  <div class="btns">
   <button onclick="cmd('light_left',null,this)">◀ light</button>
   <button onclick="cmd('light_right',null,this)">light ▶</button>
   <button onclick="cmd('light_up',null,this)">▲ light</button>
   <button onclick="cmd('light_down',null,this)">light ▼</button>
   <button onclick="cmd('light_on',null,this)">💡 ON</button>
   <button onclick="cmd('light_off',null,this)">⚫ OFF</button>
   <button onclick="cmd('auto',null,this)">🔄 auto</button>
   <button onclick="cmd('pause',null,this)">⏯ pause</button>
   <button onclick="cmd('reset',null,this)">↺ reset</button>
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
 <div class="card">
  <div class="lab" style="margin-top:0">🎥 Video input → train the fly</div>
  <div class="knob"><input type="file" id="vidfile" accept="video/*" style="width:100%;font-size:13px">
   <button style="width:100%;margin-top:8px" onclick="doUpload()">⬆ Upload video</button></div>
  <div id="vinfo" style="font-size:12.5px;color:#8fa3c2;margin:4px 0"></div>
  <div class="lab">Training session</div>
  <div class="btns" style="grid-template-columns:repeat(2,minmax(0,1fr))">
   <button onclick="train('start')">▶ TRAIN</button>
   <button onclick="train('stop')">⏹ stop</button>
   <button onclick="train('reset')">↺ reset weights</button>
   <button onclick="cmd('mode_light',null,this)">💡 back to light</button>
  </div>
  <div class="knob"><label>trials <span id="vt">12</span> · cue <span id="vc">6</span>s · test <span id="vx">6</span>s</label>
   <input type="range" min="4" max="40" step="1" value="12"
    oninput="document.getElementById('vt').textContent=this.value" id="ntrials">
   <input type="range" min="3" max="12" step="1" value="6"
    oninput="document.getElementById('vc').textContent=this.value" id="cuesecs">
   <input type="range" min="3" max="12" step="1" value="6"
    oninput="document.getElementById('vx').textContent=this.value" id="testsecs">
  </div>
  <div id="tstate" style="font-size:13px;color:#8fa3c2;margin:6px 0"></div>
  <img id="curve" class="stream" style="aspect-ratio:auto" alt="learning curve">
  <div id="ttable" style="font-size:12.5px;margin-top:6px"></div>
 </div>
</div>
<script>
const KEY = new URLSearchParams(location.search).get('k') || '';
let LITE = window.innerWidth < 820 ||
           (navigator.connection && navigator.connection.saveData) ||
           (navigator.deviceMemory && navigator.deviceMemory <= 4);
function u(path, extra){
  const p = new URLSearchParams();
  if(KEY) p.set('k', KEY);
  if(extra) for(const k in extra) p.set(k, extra[k]);
  const q = p.toString();
  return path + (q ? '?' + q : '');
}
function busy(){                       // never fight the user for CPU while typing
  const a = document.activeElement;
  return document.hidden || (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA'));
}
function setStream(){
  document.getElementById('vid').src = u('/video.mjpg', LITE ? {fps: 8, small: 1} : {fps: 25});
  const b = document.getElementById('lite');
  if(b) b.textContent = LITE ? '⚡ Lite mode (tap for full)' : '🎬 Full mode (tap for lite)';
}
function toggleLite(){ LITE = !LITE; setStream(); tick(true); }
function toast(m, ok){
  const t = document.getElementById('toast'); if(!t) return;
  t.textContent = m; t.style.background = ok ? '#1d5c33' : '#5c1d1d'; t.style.opacity = 1;
  clearTimeout(window._tt); window._tt = setTimeout(() => t.style.opacity = 0, 1800);
}
function cmd(c, v, btn){
  if(btn){ btn.style.background = '#3a5285'; setTimeout(() => btn.style.background = '', 260); }
  fetch(u('/api/cmd'), {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({cmd:c, val: v===undefined?null:parseFloat(v)})})
   .then(r => toast(r.ok ? ('✓ ' + c) : ('✗ ' + c + ' (rejected)'), r.ok))
   .catch(e => toast('✗ backend unreachable', false));
}
let tickN = 0;
function tick(force){
  if(!force && busy()) return;
  fetch(u('/api/state')).then(r => r.json()).then(s => {
    tickN++;
    const rows=[['sim time',Math.round(s.t)+' s'],['video',s.fps+' fps'],
      ['brain clock',s.brain_x+'× real-time'],['dist to light',s.dist+' mm'],
      ['fly speed',s.speed+' mm/s'],['turn rate',s.turn+' rad/s'],['lights caught',s.caught],
      ['visual L/R',s.hz.vis_L.toFixed(1)+' / '+s.hz.vis_R.toFixed(1)+' Hz'],
      ['descending L/R',s.hz.dn_L.toFixed(1)+' / '+s.hz.dn_R.toFixed(1)+' Hz'],
      ['motor',s.hz.motor.toFixed(1)+' Hz'],
      ['KC / DAN / MBON',Math.round(s.hz.kc)+' / '+Math.round(s.hz.dan)+' / '+Math.round(s.hz.mbon)+' Hz'],
      ['light',(s.light.on?'ON':'OFF')+' · auto-drift '+(s.auto?'ON':'OFF')],
      ['light pos','x '+s.light.x+'  y '+s.light.y+'  z '+s.light.z],
      ['last command',s.last_cmd]];
    document.getElementById('st').innerHTML=rows.map(r=>
      '<div class="row"><span>'+r[0]+'</span><b>'+r[1]+'</b></div>').join('');
    if(!LITE || tickN % 3 === 0)
      document.getElementById('panel').src = u('/brain.png', {t: Date.now()});
  }).catch(e => {});
}
function doUpload(){
 const f=document.getElementById('vidfile').files[0];
 if(!f){alert('choose a video file first');return}
 const fd=new FormData(); fd.append('video',f);
 document.getElementById('vinfo').textContent='uploading '+f.name+' …';
 fetch(u('/upload'),{method:'POST',body:fd}).then(r=>r.json()).then(j=>{
   if(!j.ok){document.getElementById('vinfo').textContent='✗ '+j.error;return}
   const m=j.meta;
   document.getElementById('vinfo').textContent=
     '✓ '+m.file+' · '+m.seconds+'s · '+m.frames+' frames · cue on the '+m.cue+
     ' — the fly now sees this video';
 }).catch(e=>document.getElementById('vinfo').textContent='✗ upload failed')}
function train(a){
 const body={action:a};
 if(a==='start'){body.trials=+document.getElementById('ntrials').value;
  body.cue_secs=+document.getElementById('cuesecs').value;
  body.test_secs=+document.getElementById('testsecs').value}
 fetch(u('/api/train'),{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(body)}).then(r=>r.json()).then(j=>refreshTrain()).catch(e=>{})}
function refreshTrain(){
 if(busy()) return;
 fetch(u('/api/state')).then(r=>r.json()).then(s=>{
  const t=s.train||{}; const c=t.curve||[];
  document.getElementById('tstate').innerHTML=
   'mode <b>'+(s.mode||'light')+'</b> · trial <b>'+(t.trial||0)+'/'+(t.n_trials||0)+
   '</b> · phase <b>'+(t.phase||'-')+'</b> · reward pulses <b>'+(t.reward_events||0)+
   '</b> · KC→MBON drift <b>'+(t.w_drift||1).toFixed(3)+'×</b>'+(s.video?(' · video: '+s.video):'');
  document.getElementById('ttable').innerHTML = c.length? c.map(r=>
   '<div class="row"><span>trial '+r.trial+'</span><b>'+r.oriented+'% oriented</b></div>').join('') : '';
  document.getElementById('curve').src=u('/api/curve.png',{t:Date.now()})})}
setStream();
tick(); setInterval(tick, LITE ? 6000 : 2500);
setInterval(refreshTrain, LITE ? 9000 : 4000);
refreshTrain();
document.addEventListener('visibilitychange', () => { if(!document.hidden) tick(true); });
</script></body></html>"""

if __name__ == "__main__":
    host = os.environ.get("FLY_HOST", "127.0.0.1")
    port = int(os.environ.get("FLY_PORT", "8000"))
    print(f"[webapp] serving on {host}:{port}", flush=True)
    app.run(host=host, port=port, threaded=True)
