"""Train the fly on several internet videos, one after another.
The video frames are the fly's visual input; sugar reward teaches it
which side of the video is 'good'. Weights are reset between videos."""
import sys, time
sys.path.insert(0, "/workspace/fly/scripts")
import numpy as np
from world_sim import World

VIDS = ["moon.webm", "bee.webm", "bumblebees.webm", "moonrise.webm", "morningglory.webm"]
w = World(use_learner=True)
w.start_brain_thread()
print("brain ready\n")
rows = []
for v in VIDS:
    z = np.load(f"/workspace/fly/videos/drives/{v}.npz")
    w.video = dict(left=z["left"], right=z["right"], motion=z["motion"],
                   fps=float(z["fps"]), name=v)
    w.cue_side = int(z["cue"])
    w.cmd("reset_learning")                     # fresh synapses for each video
    w.start_training(n_trials=5, cue_secs=5.0, test_secs=5.0)
    t0 = last = time.time()
    while w.train["active"] and time.time() - t0 < 95:
        now = time.time(); dt = min(now - last, 0.25); last = now
        w.step(dt)
    c = w.train["curve"]
    ori = [r["oriented"] for r in c]
    app = w.learner.drift_split()
    rows.append((v, "right" if w.cue_side > 0 else "left", ori, round(w.learner.weight_drift(), 3)))
    print(f"{v:18s} cue={rows[-1][1]:5s} trials={ori}  drift={rows[-1][3]}  app/ave={app[0]:.2f}/{app[1]:.2f}", flush=True)

print("\n=== summary ===")
for v, cue, ori, drift in rows:
    if len(ori) >= 3:
        first, last3 = sum(ori[:2]) / 2, sum(ori[-2:]) / 2
        print(f"{v:18s} cue={cue:5s} {first:5.1f}% -> {last3:5.1f}%  ({last3-first:+.1f} pp)  drift={drift}")
