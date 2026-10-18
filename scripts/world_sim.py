"""Fly body + light/video world + associative learning, coupled to the real brain.

modes
  light : innate phototaxis toward a drifting light
  video : the fly's eyes are driven by an uploaded video (left/right luminance)
  train : associative learning - a visual cue is paired with sugar; the
          connectome's own KC->MBON synapses change (learner.py)
"""
import os
import threading
import time
from collections import deque

import numpy as np

from brain_sim import Brain
from learner import Learner


class World:
    def __init__(self, dt=0.004, data_dir=None, use_learner=True):
        self.data_dir = data_dir or os.environ.get("FLY_DATA", "/workspace/fly/data")
        self.brain = Brain(data_dir=self.data_dir, dt=dt)
        self.dt = dt
        self.t = 0.0
        self.fly = dict(x=0.0, y=0.0, z=3.5, yaw=0.0, speed=0.0, flap=0.0, phase=0.0)
        self.light = dict(x=30.0, y=12.0, z=25.0, on=True)
        self.auto_light = True
        self.paused = False
        self.innate = 1.0
        self.brain_gain = 0.6
        self.speed_scale = 1.0
        self.hist = deque(maxlen=900)
        self.stats = {}
        self.caught = 0
        self.catch_t = -100.0
        self.last_hist = 0.0
        self.rng = np.random.default_rng(11)
        self._pending_cmd = None
        self._last_cmd = "-"
        self._t0 = time.time()
        self._steps0 = 0
        self._thread = None

        self.baseline = 0.55          # ambient light: keeps the circuit alive
        self.mode = "light"
        self.video = None
        self.cue_side = 1                     # +1 cue on the right, -1 on the left
        self.learner = Learner(self.brain, self.data_dir) if use_learner else None
        self.learn_gain = 1.6
        self.train = dict(active=False, done=False, trial=0, n_trials=15,
                          phase="idle", t_phase=0.0, cue_secs=5.0, test_secs=4.0,
                          curve=[], reward_events=0, punish_events=0,
                          oriented=0.0, bearing=0.0, w_drift=1.0, approach=0.0)
        self._learn_t = 0.0
        self.warmup(6.0)

    # ---------------------------------------------------------------- setup
    def warmup(self, seconds):
        n = int(seconds / self.dt)
        self.brain.set_drive({"vis_L": 0.5, "vis_R": 0.5})
        self.brain.step(n)
        self.brain.set_drive({})

    def start_brain_thread(self):
        def loop():
            while True:
                self.brain.step(1)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------- commands
    def cmd(self, c, val=None):
        L = self.light
        self._pending_cmd = c + (("=" + str(val)) if val is not None else "")
        if c in ("light_left", "light_right", "light_up", "light_down"):
            self.auto_light = False
            self.mode = "light"
            self.stop_training()
        if c == "light_left":   L["x"] -= 6
        elif c == "light_right": L["x"] += 6
        elif c == "light_up":   L["z"] = min(60, L["z"] + 6)
        elif c == "light_down": L["z"] = max(6, L["z"] - 6)
        elif c == "light_on":   L["on"] = True
        elif c == "light_off":  L["on"] = False
        elif c == "auto":
            self.auto_light = not self.auto_light
            if self.auto_light:
                self.catch_t = -100.0
        elif c == "pause":      self.paused = not self.paused
        elif c == "reset":
            self.fly.update(x=0.0, y=0.0, z=3.5, yaw=0.0)
            self.caught = 0
        elif c == "innate" and val is not None:     self.innate = float(val)
        elif c == "brain_gain" and val is not None: self.brain_gain = float(val)
        elif c == "speed" and val is not None:      self.speed_scale = float(val)
        elif c == "mode_light":
            self.mode = "light"; self.stop_training()
        elif c == "mode_video" and self.video is not None:
            self.mode = "video"; self.stop_training()
            self.auto_light = False
            L.update(on=True, z=20.0, y=0.0)
            L["x"] = 35.0 * self.cue_side
        elif c == "start_training":
            self.start_training(val)
        elif c == "stop_training":
            self.stop_training()
        elif c == "reset_learning" and self.learner is not None:
            self.learner.brain.data[self.learner.pos] = self.learner.w0
            self.learner.w_now = self.learner.w0.copy()
            self.train["curve"] = []
            self.train["reward_events"] = 0

    # ------------------------------------------------------------- training
    def start_training(self, n_trials=None, cue_secs=5.0, test_secs=4.0):
        tr = self.train
        tr.update(active=True, done=False, trial=0, phase="cue", t_phase=0.0,
                  curve=[], reward_events=0, punish_events=0, oriented=0.0)
        if n_trials:
            tr["n_trials"] = int(n_trials)
        tr["cue_secs"], tr["test_secs"] = float(cue_secs), float(test_secs)
        if self.learner is not None:
            self.learner.approach0 = self.learner.approach     # innate baseline
        self.mode = "train"
        self.auto_light = False
        self._innate_user = self.innate
        self._brain_gain_user = self.brain_gain
        self.brain_gain = 0.10
        self.light.update(on=True, z=20.0, x=0.0)
        self.light["y"] = -35.0 * self.cue_side     # cue 90 deg to the side
        self.fly["yaw"] = 0.0
        self.fly.update(x=0.0, y=0.0)
        self.train["phase"] = "cue"

    def stop_training(self):
        self.train["active"] = False
        self.train["phase"] = "idle"
        if self.learner:
            self.learner.clear_drives()

    # ----------------------------------------------------------------- step
    def step(self, wall_dt):
        if self.paused:
            self.stats["paused"] = True
            return
        f, L = self.fly, self.light
        # --- where is the cue / light, in the fly's frame ---
        dx, dy = L["x"] - f["x"], L["y"] - f["y"]
        dist = float(np.hypot(dx, dy)) + 1e-6
        bearing = (np.arctan2(dy, dx) - f["yaw"] + np.pi) % (2 * np.pi) - np.pi
        inten = (1.0 if L["on"] else 0.0) * 60.0 / (60.0 + dist * dist / 12.0)

        if self.mode == "video" and self.video is not None:
            v = self.video
            i = int(self.t * v["fps"]) % len(v["left"])
            dl, dr = float(v["left"][i]), float(v["right"][i])
            self.brain.set_drive({"vis_L": self.baseline + 1.1 * dl,
                                  "vis_R": self.baseline + 1.1 * dr})
        else:
            dl = inten * max(0.0, np.cos(bearing + 0.7))
            dr = inten * max(0.0, np.cos(bearing - 0.7))
            self.brain.set_drive({"vis_L": self.baseline + 1.1 * dl,
                                  "vis_R": self.baseline + 1.1 * dr})

        # --- readout: descending + motor (+ learned MBON bias) ---
        dnL, dnR = self.brain.hz("dn_L"), self.brain.hz("dn_R")
        mot = self.brain.hz("motor")
        bias = 0.0
        if self.learner is not None:
            self._learn_t += wall_dt
            if self._learn_t >= 0.05:
                self._learn_t = 0.0
                self.learner.update(0.05)
            bias = float(np.tanh((self.learner.learned_approach() / self.dt) / 40.0))
        turn = (self.innate * np.sin(bearing)
                + self.brain_gain * np.tanh((dnR - dnL) / 15.0)
                + self.learn_gain * bias * np.sin(bearing))
        f["yaw"] = (f["yaw"] + turn * wall_dt * 1.6) % (2 * np.pi)
        spd = (6.0 + 3.0 * np.tanh(mot / 12.0)) * self.speed_scale
        f["speed"] = spd
        if self.mode == "train":
            f["x"] = f["y"] = 0.0        # tethered: measure orientation only
        else:
            f["x"] += spd * np.cos(f["yaw"]) * wall_dt
            f["y"] += spd * np.sin(f["yaw"]) * wall_dt
        f["z"] = 3.5 + 0.6 * np.sin(self.t * 2.1)
        f["flap"] += wall_dt * 22.0
        f["phase"] += wall_dt * (7.0 + 2.0 * np.tanh(mot / 12.0))
        self.t += wall_dt

        # --- training protocol ---
        tr = self.train
        if tr["active"]:
            tr["t_phase"] += wall_dt
            tr["bearing"] = float(bearing)
            oriented = abs(bearing) < 1.0
            if tr["phase"] == "cue":
                self.innate = 0.5 * getattr(self, "_innate_user", 1.0)   # scaffold
                if oriented:
                    if not tr.get("_was_oriented"):
                        tr["reward_events"] += 1
                    tr["_was_oriented"] = True
                    self.learner.reward(0.9 * max(0.25, float(np.cos(bearing))))
                    self.learner.sugar(0.6)
                else:
                    tr["_was_oriented"] = False
                    self.learner.clear_drives()
                if tr["t_phase"] >= tr["cue_secs"]:
                    tr["phase"], tr["t_phase"] = "test", 0.0
                    tr["oriented"] = 0.0
                    tr["n_test"] = 0
                    tr["turn_sum"] = 0.0
                    self.fly["yaw"] = 0.0        # identical starting condition
            else:                                   # test: cue only, no reward
                self.innate = 0.0          # ONLY the learned bias can steer now
                self.learner.clear_drives()
                tr["n_test"] = tr.get("n_test", 0) + 1
                tr["oriented"] += 1.0 if oriented else 0.0
                tr["turn_sum"] = tr.get("turn_sum", 0.0) + float(turn)
                if tr["t_phase"] >= tr["test_secs"]:
                    frac = tr["oriented"] / max(tr["n_test"], 1)
                    tr["curve"].append(dict(
                        trial=tr["trial"] + 1,
                        oriented=round(100 * frac, 1),
                        mean_turn=round(tr.get("turn_sum", 0.0) / max(tr["n_test"], 1), 3),
                        approach=round(float(self.learner.learned_approach()), 3),
                        w_drift=round(self.learner.weight_drift(), 3)))
                    tr["trial"] += 1
                    tr["phase"], tr["t_phase"] = "cue", 0.0
                    self.fly["yaw"] = 0.0
                    if tr["trial"] >= tr["n_trials"]:
                        tr["active"], tr["done"], tr["phase"] = False, True, "done"
                        self.learner.clear_drives()
                        self.innate = getattr(self, "_innate_user", 1.0)
                        self.brain_gain = getattr(self, "_brain_gain_user", 0.6)
        # --- auto light drift only in light mode ---
        if self.mode == "light" and self.auto_light and L["on"]:
            L["x"] = 32.0 * np.cos(self.t * 0.12)
            L["y"] = 32.0 * np.sin(self.t * 0.12)
            L["z"] = 22.0 + 8.0 * np.sin(self.t * 0.07)
        if dist < 7.0 and L["on"] and self.t - self.catch_t > 4.0:
            self.catch_t = self.t
            self.caught += 1
            if self.mode == "light":
                a = self.rng.uniform(0, 2 * np.pi)
                L["x"], L["y"] = 34 * np.cos(a), 34 * np.sin(a)

        if self._pending_cmd:
            self._last_cmd = self._pending_cmd
            self._pending_cmd = None
        el = max(time.time() - self._t0, 1e-6)
        factor = ((self.brain.steps - self._steps0) * self.dt) / el
        p = self.brain.pop_hz()
        self.stats = dict(
            auto=self.auto_light, last_cmd=self._last_cmd, t=round(self.t, 1),
            mode=self.mode, dist=round(dist, 1), bearing=round(float(bearing), 2),
            speed=round(float(spd), 2), turn=round(float(turn), 2),
            brain_x=round(factor, 2), caught=self.caught, paused=False,
            light=dict(x=round(L["x"], 1), y=round(L["y"], 1), z=round(L["z"], 1), on=L["on"]),
            fly={k: (round(v, 2) if isinstance(v, float) else v) for k, v in f.items()},
            hz={k: round(v, 2) for k, v in p.items()},
            innate=self.innate, brain_gain=self.brain_gain,
            cue_side=self.cue_side,
            approach=round(bias, 3), approach_hz=round(float(self.learner.learned_approach() / self.dt), 1) if self.learner else 0.0,
            video=(self.video["name"] if self.video else None),
            train=dict(active=tr["active"], done=tr["done"], trial=tr["trial"],
                       n_trials=tr["n_trials"], phase=tr["phase"],
                       reward_events=tr["reward_events"], curve=tr["curve"][-40:],
                       w_drift=round(self.learner.weight_drift(), 3) if self.learner else 1.0),
        )
        if self.t - self.last_hist > 0.1:
            self.last_hist = self.t
            self.hist.append((self.t, p["vis_L"] + p["vis_R"], p["dn_L"] + p["dn_R"],
                              p["motor"], p["kc"], p["dan"], p["mbon"]))
