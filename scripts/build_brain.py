#!/usr/bin/env python3
"""Build compact signed MaleCNS brain graph (CSR npz) + neuron metadata parquet."""
import os
import time
import numpy as np
import pandas as pd
import pyarrow.feather as feather
import scipy.sparse as sp

DATA = os.environ.get("FLY_DATA", "./data")
t0 = time.time()

ann = feather.read_table(f"{DATA}/body-annotations.feather",
    columns=["bodyId", "superclass", "class", "type", "instance", "somaSide"]).to_pandas()
print("ann rows:", len(ann), flush=True)

nt = feather.read_table(f"{DATA}/neurotransmitters.feather",
    columns=["body", "consensus_nt", "celltype_predicted_nt"]).to_pandas()
nt["nt"] = nt["consensus_nt"].fillna(nt["celltype_predicted_nt"]).fillna("acetylcholine")
nt = nt.drop_duplicates("body")[["body", "nt"]]
INHIB = {"gaba", "glutamate"}
nt["sign"] = np.where(nt["nt"].str.lower().isin(INHIB), -1.0, 1.0)
print("nt rows:", len(nt), flush=True)

w = feather.read_table(f"{DATA}/weights.feather",
    columns=["body_pre", "body_post", "weight"]).to_pandas()
print("edge rows:", len(w), flush=True)

bodies = np.unique(np.concatenate([w["body_pre"].values, w["body_post"].values]))
N = len(bodies)
print("graph neurons:", N, flush=True)

pre = np.searchsorted(bodies, w["body_pre"].values)
post = np.searchsorted(bodies, w["body_post"].values)
sign_s = pd.Series(nt["sign"].values, index=nt["body"].values).reindex(bodies).fillna(1.0)
sign_arr = sign_s.values.astype(np.float32)
data = w["weight"].values.astype(np.float32) * sign_arr[pre]
del w

csr = sp.csr_matrix((data, (pre, post)), shape=(N, N), dtype=np.float32)
csr.sum_duplicates()
del pre, post, data

in_abs = np.asarray(np.abs(csr).sum(axis=0)).ravel()
in_abs[in_abs == 0] = 1.0
csr.data /= in_abs[csr.indices]
print("edges after merge:", csr.nnz, flush=True)

sp.save_npz(f"{DATA}/brain_csr.npz", csr, compressed=True)

meta = pd.DataFrame({"bodyId": bodies})
ann2 = ann.drop_duplicates("bodyId").set_index("bodyId")
meta = meta.merge(ann2, left_on="bodyId", right_index=True, how="left")
for c in ["superclass", "class", "type", "instance", "somaSide"]:
    meta[c] = meta[c].fillna("")
sc, cl = meta["superclass"], meta["class"]
meta["is_vis"]    = sc.eq("ol_sensory")
meta["is_dn"]     = sc.eq("descending_neuron")
meta["is_asc"]    = sc.eq("ascending_neuron")
meta["is_motor"]  = sc.isin(["vnc_motor", "cb_motor"])
meta["is_olf"]    = cl.eq("olfactory")
meta["is_gust"]   = cl.eq("gustatory")
meta["is_kc"]     = cl.eq("Kenyon_Cell")
meta["is_dan"]    = cl.eq("DAN")
meta["is_mbon"]   = cl.eq("MBON")
meta["is_mecha"]  = cl.isin(["mechanosensory_tactile", "mechanosensory", "mechanosensory_proprioceptive"])
meta["inh"] = sign_s.reindex(bodies).fillna(1.0).values < 0
meta.to_parquet(f"{DATA}/brain_meta.parquet", index=False)

print("\n--- group counts ---")
for k in ["is_vis", "is_dn", "is_asc", "is_motor", "is_olf", "is_gust", "is_kc", "is_dan", "is_mbon", "is_mecha", "inh"]:
    print(f"{k:9s}", int(meta[k].sum()))
print("somaSide:", meta["somaSide"].value_counts().to_dict())

print("\n--- scipy matvec benchmark (full graph) ---")
W = csr.tocsr()
rng = np.random.default_rng(0)
x = (rng.random(N) < 0.02).astype(np.float32)
t = time.time()
for _ in range(50):
    y = W @ x
dt = (time.time() - t) / 50
print(f"matvec: {dt*1000:.2f} ms/step -> {1/dt:.0f} steps/s (scipy, dense spike vector)")
print("build time %.1fs" % (time.time() - t0))
