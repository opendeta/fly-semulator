"""Live brain activity panel (matplotlib Agg)."""
import io
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"figure.facecolor": "#10141f", "axes.facecolor": "#171d2b",
                     "text.color": "#dfe6f2", "axes.labelcolor": "#dfe6f2",
                     "xtick.color": "#9fb0c8", "ytick.color": "#9fb0c8"})

FIG = plt.figure(figsize=(6.4, 3.6))
AX1 = FIG.add_subplot(2, 1, 1)
AX2 = FIG.add_subplot(2, 1, 2)

GROUPS = ["vis_L", "vis_R", "dn_L", "dn_R", "motor", "olf_L", "olf_R",
          "gust", "kc", "dan", "mbon", "mecha", "asc"]

def render_panel(world):
    st = world.stats or {}
    hz = st.get("hz", {})
    AX1.clear(); AX2.clear()
    vals = [hz.get(g, 0.0) for g in GROUPS]
    cols = ["#ffb347"] * 2 + ["#7fdc8a"] * 2 + ["#66c2ff"] + ["#c792ea"] * 2 + \
           ["#f78c6c"] + ["#ff79c6"] * 3 + ["#8be9fd"] * 2
    AX1.barh(GROUPS[::-1], vals[::-1], color=cols[::-1])
    AX1.set_xlim(0, max(60, max(vals) * 1.15))
    AX1.set_title("population firing rates (Hz)", fontsize=10)
    AX1.tick_params(labelsize=7)
    AX1.grid(alpha=0.15)

    h = list(world.hist)
    if len(h) > 2:
        t = [e[0] for e in h]
        for i, (name, col) in enumerate([("visual", "#ffb347"), ("descending", "#7fdc8a"),
                                          ("motor", "#66c2ff"), ("KC", "#ff79c6")]):
            AX2.plot(t, [e[1 + i] for e in h], color=col, lw=1.2, label=name)
        AX2.set_xlim(max(0, t[0]), t[-1])
        AX2.legend(fontsize=9, loc="upper right", ncol=4)
    AX2.set_title("last 90 s", fontsize=10)
    AX2.set_xlabel("sim time (s)", fontsize=8)
    AX2.tick_params(labelsize=7)
    AX2.grid(alpha=0.15)
    FIG.tight_layout()
    buf = io.BytesIO()
    FIG.savefig(buf, format="png", dpi=95)
    buf.seek(0)
    return buf.getvalue()
