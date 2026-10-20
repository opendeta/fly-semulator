import sys, time
sys.path.insert(0, "/workspace/fly/scripts")
import numpy as np
from world_sim import World
w = World(use_learner=True); w.start_brain_thread()
for v in ["bumblebees.webm", "moon.webm"]:
    z = np.load(f"/workspace/fly/videos/drives/{v}.npz")
    w.video = dict(left=z["left"], right=z["right"], motion=z["motion"], fps=float(z["fps"]), name=v)
    w.cue_side = int(z["cue"]); w.cmd("reset_learning")
    w.start_training(n_trials=5, cue_secs=5.0, test_secs=5.0)
    t0 = last = time.time()
    while w.train["active"] and time.time() - t0 < 80:
        now = time.time(); dt = min(now - last, 0.25); last = now; w.step(dt)
    c = [r["oriented"] for r in w.train["curve"]]
    a, b = w.learner.drift_split()
    print(f"{v:16s} trials={c}  drift={w.learner.weight_drift():.3f} app/ave={a:.2f}/{b:.2f}", flush=True)
