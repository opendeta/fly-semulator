"""Headless associative-learning run (real time, full CPU)."""
import time, numpy as np
from world_sim import World
w = World(use_learner=True)
w.start_brain_thread()
w.cue_side = 1
w.start_training(n_trials=12, cue_secs=6.0, test_secs=6.0)
last = time.time(); t0 = last
while w.train["active"] and time.time() - t0 < 260:
    now = time.time(); dt = min(now - last, 0.25); last = now
    w.step(dt)
c = w.train["curve"]
print(f"wall {time.time()-t0:.0f}s | sim t={w.stats['t']}s | brain {w.stats['brain_x']}x")
print("KC->MBON weight drift  app/ave:", [round(x,3) for x in w.learner.drift_split()])
print(f"reward pulses {w.train['reward_events']} | plastic updates {w.learner.updates}")
print(f"{'trial':>5} {'oriented%':>10} {'mean_turn':>10} {'approach':>9} {'w_drift':>8}")
for r in c:
    print(f"{r['trial']:>5} {r['oriented']:>10} {r['mean_turn']:>10} {r['approach']:>9} {r['w_drift']:>8}")
if len(c) >= 6:
    a = np.mean([r["oriented"] for r in c[:3]]); b = np.mean([r["oriented"] for r in c[-3:]])
    ta = np.mean([r["mean_turn"] for r in c[:3]]); tb = np.mean([r["mean_turn"] for r in c[-3:]])
    print(f"\nfirst 3 trials: oriented {a:.1f}%  mean_turn {ta:.3f}")
    print(f"last  3 trials: oriented {b:.1f}%  mean_turn {tb:.3f}")
    print(f"CHANGE: oriented {b-a:+.1f} pp | mean_turn {tb-ta:+.3f}")
