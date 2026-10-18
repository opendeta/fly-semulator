import io, time
from world_sim import World
from fly_render import render_frame
from brain_panel import render_panel
w = World()
w.start_brain_thread()
t0 = time.time(); n = 0; pt = 0
while time.time() - t0 < 12:
    a = time.time()
    w.step(0.033)
    img = render_frame(w)
    b = io.BytesIO(); img.save(b, "JPEG", quality=82)
    n += 1
    if time.time() - pt > 1.2:
        pt = time.time(); render_panel(w)
    sl = 0.033 - (time.time() - a)
    if sl > 0: time.sleep(sl)
print(f"loop fps: {n/(time.time()-t0):.1f}  brain_x: {w.stats['brain_x']}  hz: {w.stats['hz']}")
