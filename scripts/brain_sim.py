"""Event-driven LIF on the real MaleCNS connectome (numba, nogil)."""
import os
import numpy as np
import pandas as pd
import scipy.sparse as sp
from numba import njit

@njit(nogil=True, cache=True)
def _lif_step(indptr, indices, data, v, thr, spk, I, ext, noise, gain, decay):
    N = v.shape[0]
    for i in range(N):
        I[i] = 0.0
    for j in range(N):
        if spk[j]:
            for k in range(indptr[j], indptr[j + 1]):
                I[indices[k]] += data[k]
    ns = 0
    for i in range(N):
        vv = v[i] * decay + gain * I[i] + ext[i] + noise[i]
        if vv > thr[i]:
            v[i] = 0.0
            spk[i] = 1
            ns += 1
        else:
            if vv < -thr[i]:
                vv = -thr[i]
            v[i] = vv
            spk[i] = 0
    return ns

class Brain:
    def __init__(self, data_dir=None, dt=0.004, seed=7):
        data_dir = data_dir or os.environ.get("FLY_DATA", "./data")
        self.W = sp.load_npz(f"{data_dir}/brain_csr.npz").tocsr()
        self.meta = pd.read_parquet(f"{data_dir}/brain_meta.parquet")
        N = self.W.shape[0]
        self.N = N
        self.dt = dt
        self.indptr = self.W.indptr.astype(np.int64)
        self.indices = self.W.indices.astype(np.int64)
        self.data = self.W.data.astype(np.float32)
        self.v = (np.random.default_rng(seed).random(N) * 0.2).astype(np.float32)
        self.thr = np.ones(N, np.float32)
        self.spk = np.zeros(N, np.uint8)
        self.I = np.zeros(N, np.float32)
        self.ext = np.zeros(N, np.float32)
        self.rate = np.zeros(N, np.float32)
        self.gain = np.float32(5.0)
        self.noise_amp = 0.05
        self.decay = np.float32(np.exp(-dt / 0.020))
        self.target_rate = 0.012
        self.steps = 0
        self.rng = np.random.default_rng(seed + 1)
        self.noise_pool = (self.rng.standard_normal((32, N), dtype=np.float32) * self.noise_amp)
        self._ni = 0
        m = self.meta
        side = m["somaSide"].values
        self.idx = {}
        def add(name, mask):
            self.idx[name] = np.flatnonzero(mask).astype(np.int64)
        add("vis_L", m.is_vis.values & (side == "L"))
        add("vis_R", m.is_vis.values & (side == "R"))
        add("vis",   m.is_vis.values)
        add("dn_L",  m.is_dn.values & (side == "L"))
        add("dn_R",  m.is_dn.values & (side == "R"))
        add("dn",    m.is_dn.values)
        add("motor", m.is_motor.values)
        add("asc",   m.is_asc.values)
        add("olf_L", m.is_olf.values & (side == "L"))
        add("olf_R", m.is_olf.values & (side == "R"))
        add("gust",  m.is_gust.values)
        add("kc",    m.is_kc.values)
        add("dan",   m.is_dan.values)
        add("mbon",  m.is_mbon.values)
        add("mecha", m.is_mecha.values)
        self.last_ns = 0

    def set_drive(self, drives):
        self.ext[:] = 0.0
        for g, cur in drives.items():
            ix = self.idx.get(g)
            if ix is not None and cur != 0.0:
                self.ext[ix] = np.float32(cur)

    def step(self, n=1):
        for _ in range(n):
            noise = self.noise_pool[self._ni & 31]
            self._ni += 1
            ns = _lif_step(self.indptr, self.indices, self.data, self.v,
                           self.thr, self.spk, self.I, self.ext, noise,
                           self.gain, self.decay)
            self.last_ns = ns
            self.steps += 1
            if self.steps % 4 == 0:
                self.rate *= np.float32(0.996)
                self.rate += np.float32(0.004) * self.spk
            if self.steps % 100 == 0:
                r = self.rate / self.target_rate
                f = 1.0 + 0.05 * np.clip(r - 1.0, -1.0, 1.0)
                self.thr = np.clip(self.thr * f, 0.35, 2.5).astype(np.float32)

    def hz(self, group):
        ix = self.idx[group]
        return float(self.rate[ix].mean() / self.dt) if len(ix) else 0.0

    def pop_hz(self):
        return {g: self.hz(g) for g in ["vis_L", "vis_R", "dn_L", "dn_R", "motor",
                                        "olf_L", "olf_R", "gust", "kc", "dan", "mbon", "mecha", "asc"]}
