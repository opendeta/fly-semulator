#!/usr/bin/env python3
"""Find the plastic (Kenyon-cell -> MBON) synapses and the DAN reward/punishment sets.

Biology (modelled, literature-grounded):
  * mushroom body: KCs are the sparse odour/context code, MBONs the output,
    DANs deliver the teaching signal (PAM = appetitive, PPL1 = aversive).
  * dopamine-gated KC->MBON plasticity (Hige 2015, Handler 2019, Aso 2014).
"""
import os, time
import numpy as np, pandas as pd, scipy.sparse as sp

D = os.environ.get("FLY_DATA", "/workspace/fly/data")
t0 = time.time()
W = sp.load_npz(f"{D}/brain_csr.npz").tocsr()
meta = pd.read_parquet(f"{D}/brain_meta.parquet")
N = W.shape[0]
print("neurons", N, "edges", W.nnz, flush=True)

is_kc = meta.is_kc.values.astype(bool)
is_mbon = meta.is_mbon.values.astype(bool)
types = meta["type"].fillna("").values
is_pam = meta.is_dan.values.astype(bool) & np.array([t.upper().startswith("PAM") for t in types])
is_ppl1 = meta.is_dan.values.astype(bool) & np.array([t.upper().startswith("PPL1") for t in types])
is_gust = meta.is_gust.values.astype(bool)

# KC -> MBON edges: positions inside csr.data
kc_ix = np.flatnonzero(is_kc)
mbon_set = set(np.flatnonzero(is_mbon).tolist())
rows, cols, pos = [], [], []
for k in kc_ix:
    a, b = W.indptr[k], W.indptr[k + 1]
    for p in range(a, b):
        if W.indices[p] in mbon_set:
            rows.append(k); cols.append(W.indices[p]); pos.append(p)
pos = np.asarray(pos, dtype=np.int64)
print(f"KC->MBON plastic synapses: {len(pos)}  (KC {is_kc.sum()}, MBON {is_mbon.sum()})", flush=True)
print(f"DAN: PAM(reward) {is_pam.sum()}  PPL1(punish) {is_ppl1.sum()}  gustatory {is_gust.sum()}", flush=True)

# KC -> MBON split by MBON compartment innervation from PAM vs PPL1 (approach/avoid labels)
A = W.tocsr()
pam_in = np.asarray(A[np.flatnonzero(is_pam), :].sum(axis=0)).ravel()
ppl1_in = np.asarray(A[np.flatnonzero(is_ppl1), :].sum(axis=0)).ravel()
compartment = np.where((pam_in - ppl1_in) > 0, 1, np.where((ppl1_in - pam_in) > 0, -1, 0))
print("MBONs labelled  appetitive:", int(((compartment > 0) & is_mbon).sum()),
      " aversive:", int(((compartment < 0) & is_mbon).sum()), flush=True)

np.savez_compressed(f"{D}/plastic.npz",
                    pos=pos,
                    pre_kc=np.asarray(rows, dtype=np.int32),      # presynaptic Kenyon cell
                    post_mbon=np.asarray(cols, dtype=np.int32),   # postsynaptic MBON
                    w0=W.data[pos].astype(np.float32),
                    compartment=compartment.astype(np.int8),
                    kc=kc_ix.astype(np.int32),
                    pam=np.flatnonzero(is_pam).astype(np.int32),
                    ppl1=np.flatnonzero(is_ppl1).astype(np.int32),
                    gust=np.flatnonzero(is_gust).astype(np.int32))
print("saved plastic.npz  (%.1fs)" % (time.time() - t0))
