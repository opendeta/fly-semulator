"""Dopamine-gated associative plasticity on the real mushroom-body synapses.

Model (literature-grounded, NOT measured):
  * Kenyon cells carry the sparse context code -> MBONs are the output.
  * PAM dopaminergic neurons signal reward, PPL1 signal punishment
    (Aso et al. 2014); KC->MBON synapses are depressed/strengthened by
    dopamine gated by a KC eligibility trace (Hige 2015, Handler 2019).
  * Appetitive / aversive MBON compartments are labelled from the
    connectome's own PAM vs PPL1 innervation, not hand-assigned.
"""
import numpy as np
import pandas as pd


class Learner:
    def __init__(self, brain, data_dir="/workspace/fly/data", eta=8e-7, learn_gain=1.0):
        self.brain = brain
        z = np.load(f"{data_dir}/plastic.npz")
        self.pos, self.pre, self.post = z["pos"], z["pre_kc"], z["post_mbon"]
        self.w0 = z["w0"].astype(np.float32)
        comp = z["compartment"]
        self.post_comp = comp[self.post].astype(np.float32)
        self.pam, self.ppl1, self.gust = z["pam"], z["ppl1"], z["gust"]
        self.kc = z["kc"]

        meta = pd.read_parquet(f"{data_dir}/brain_meta.parquet")
        is_mbon = meta.is_mbon.values.astype(bool)
        app = np.flatnonzero(is_mbon & (comp > 0))
        ave = np.flatnonzero(is_mbon & (comp < 0))
        self.mbon_app, self.mbon_ave = app, ave

        # compact KC index for each plastic synapse
        lut = -np.ones(brain.N, np.int32)
        lut[self.kc] = np.arange(len(self.kc), dtype=np.int32)
        self.syn_kc = lut[self.pre]

        self.eta = eta
        self.learn_gain = learn_gain
        self.w_now = brain.data[self.pos].copy()
        self.da_r = 0.0          # reward dopamine (EMA)
        self.da_p = 0.0          # punishment dopamine (EMA)
        self.approach = 0.0      # MBON readout: appetitive - aversive
        self.approach0 = None    # innate baseline (set when training starts)
        self.updates = 0

    # ---- teaching signals -------------------------------------------------
    def reward(self, amp=1.0):
        self.da_r = min(1.0, self.da_r + amp)
        self.brain.ext[self.pam] = 1.2 * amp

    def punish(self, amp=1.0):
        self.da_p = min(1.0, self.da_p + amp)
        self.brain.ext[self.ppl1] = 1.2 * amp

    def sugar(self, amp=1.0):
        self.brain.ext[self.gust] = 1.0 * amp

    def clear_drives(self):
        self.brain.ext[self.pam] = 0.0
        self.brain.ext[self.ppl1] = 0.0
        self.brain.ext[self.gust] = 0.0

    # ---- learning step (call every ~50 ms of sim time) --------------------
    def update(self, dt):
        b = self.brain
        # dopamine decays
        self.da_r *= np.exp(-dt / 1.5)
        self.da_p *= np.exp(-dt / 1.5)
        da = float(self.da_r - self.da_p)
        kc_act = b.rate[self.kc]
        act = kc_act[self.syn_kc]
        if abs(da) > 1e-3:
            dw = self.eta * act * da * self.post_comp
            new = np.clip(b.data[self.pos] + dw, 0.5 * self.w0, 1.5 * self.w0)
            b.data[self.pos] = new
            self.w_now = new
            self.updates += 1
        # behavioural readout from the real MBON population
        r = b.rate
        a = float(r[self.mbon_app].mean()) if len(self.mbon_app) else 0.0
        v = float(r[self.mbon_ave].mean()) if len(self.mbon_ave) else 0.0
        self.approach = a - v

    # ---- diagnostics ------------------------------------------------------
    def learned_approach(self):
        """MBON appetitive-aversive readout ABOVE the innate baseline."""
        if self.approach0 is None:
            return 0.0
        return self.approach - self.approach0

    def weight_drift(self):
        return float((self.w_now / self.w0).mean())

    def drift_split(self):
        r = self.w_now / self.w0
        app = r[self.post_comp > 0]; ave = r[self.post_comp < 0]
        return (float(app.mean()) if len(app) else 1.0,
                float(ave.mean()) if len(ave) else 1.0)
