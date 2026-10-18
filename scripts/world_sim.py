"""Fly body + light world + phototaxis, coupled to the real brain (brain runs in its own thread)."""
import threading
import time
import numpy as np
from collections import deque
from brain_sim import Brain

class World:
    def __init__(self, dt=0.004):
        self.brain = Brain(dt=dt)
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
        self._drive = {}
        self._pending_cmd = None
        self._last_cmd = "-"
        self._t0 = time.time()
        self._steps0 = 0
        self._thread = None
        self.warmup(6.0)

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

    def cmd(self, c, val=None):
        L = self.light
        self._pending_cmd = c + (("=" + str(val)) if val is not None else "")
        if c in ("light_left", "light_right", "light_up", "light_down"):
            self.auto_light = False          # manual control takes over
        if c == "light_left":   L["x"] -= 6
        elif c == "light_right":L["x"] += 6
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

    def step(self, wall_dt):
        if self.paused:
            self.stats["paused"] = True
            return
        f, L = self.fly, self.light
        dx, dy = L["x"] - f["x"], L["y"] - f["y"]
        dist = float(np.hypot(dx, dy)) + 1e-6
        bearing = (np.arctan2(dy, dx) - f["yaw"] + np.pi) % (2 * np.pi) - np.pi
        inten = (1.0 if L["on"] else 0.0) * 60.0 / (60.0 + dist * dist / 12.0)
        self.brain.set_drive({
            "vis_L": inten * max(0.0, np.cos(bearing + 0.7)) * 0.9,
            "vis_R": inten * max(0.0, np.cos(bearing - 0.7)) * 0.9})

        dnL, dnR = self.brain.hz("dn_L"), self.brain.hz("dn_R")
        mot = self.brain.hz("motor")
        turn = self.innate * np.sin(bearing) + self.brain_gain * np.tanh((dnR - dnL) / 15.0)
        f["yaw"] = (f["yaw"] + turn * wall_dt * 1.6) % (2 * np.pi)
        spd = (6.0 + 3.0 * np.tanh(mot / 12.0)) * self.speed_scale
        f["speed"] = spd
        f["x"] += spd * np.cos(f["yaw"]) * wall_dt
        f["y"] += spd * np.sin(f["yaw"]) * wall_dt
        f["z"] = 3.5 + 0.6 * np.sin(self.t * 2.1)
        f["flap"] += wall_dt * 22.0
        f["phase"] += wall_dt * (7.0 + 2.0 * np.tanh(mot / 12.0))
        self.t += wall_dt

        if self.auto_light and L["on"]:
            L["x"] = 32.0 * np.cos(self.t * 0.12)
            L["y"] = 32.0 * np.sin(self.t * 0.12)
            L["z"] = 22.0 + 8.0 * np.sin(self.t * 0.07)
        if dist < 7.0 and L["on"] and self.t - self.catch_t > 4.0:
            self.catch_t = self.t
            self.caught += 1
            a = self.rng.uniform(0, 2 * np.pi)
            L["x"], L["y"] = 34 * np.cos(a), 34 * np.sin(a)

        el = max(time.time() - self._t0, 1e-6)
        factor = ((self.brain.steps - self._steps0) * self.dt) / el
        p = self.brain.pop_hz()
        if self._pending_cmd:
            self._last_cmd = self._pending_cmd
            self._pending_cmd = None
        self.stats = dict(
            auto=self.auto_light, last_cmd=self._last_cmd, t=round(self.t, 1), dist=round(dist, 1), bearing=round(float(bearing), 2),
            speed=round(float(spd), 2), turn=round(float(turn), 2), brain_x=round(factor, 2),
            caught=self.caught, paused=False,
            light=dict(x=round(L["x"], 1), y=round(L["y"], 1), z=round(L["z"], 1), on=L["on"]),
            fly={k: (round(v, 2) if isinstance(v, float) else v) for k, v in f.items()},
            hz={k: round(v, 2) for k, v in p.items()},
            innate=self.innate, brain_gain=self.brain_gain,
        )
        if self.t - self.last_hist > 0.1:
            self.last_hist = self.t
            self.hist.append((self.t, p["vis_L"] + p["vis_R"], p["dn_L"] + p["dn_R"],
                              p["motor"], p["kc"], p["dan"], p["mbon"]))
