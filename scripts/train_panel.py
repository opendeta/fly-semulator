"""Learning-curve chart for the training console (matplotlib Agg)."""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"figure.facecolor": "#10141f", "axes.facecolor": "#171d2b",
                     "text.color": "#dfe6f2", "axes.labelcolor": "#dfe6f2",
                     "xtick.color": "#9fb0c8", "ytick.color": "#9fb0c8"})
FIG = plt.figure(figsize=(6.4, 3.4))
AX1 = FIG.add_subplot(1, 1, 1)


def render_curve(world):
    tr = (world.stats or {}).get("train", {}) or {}
    curve = tr.get("curve", [])
    AX1.clear()
    if curve:
        x = [c["trial"] for c in curve]
        y = [c["oriented"] for c in curve]
        AX1.plot(x, y, "o-", color="#ffb347", lw=1.8, ms=4, label="oriented to cue (%)")
        if len(y) >= 4:
            k = max(2, len(y) // 4)
            sm = [sum(y[max(0, i - k + 1):i + 1]) / len(y[max(0, i - k + 1):i + 1]) for i in range(len(y))]
            AX1.plot(x, sm, "--", color="#7fdc8a", lw=1.6, label=f"rolling mean (k={k})")
        AX1.axhline(50, color="#8fa3c2", lw=0.8, ls=":", label="chance")
        AX1.set_ylim(0, 105)
        AX1.set_xlabel("trial", fontsize=9)
        AX1.set_ylabel("oriented to cue (%)", fontsize=9)
        AX1.legend(fontsize=8, loc="lower right", ncol=3)
    else:
        AX1.text(0.5, 0.5, "no training data yet\nupload a video and press TRAIN",
                 ha="center", va="center", color="#8fa3c2", fontsize=11, transform=AX1.transAxes)
        AX1.set_xticks([]); AX1.set_yticks([])
    AX1.set_title("associative learning: cue -> sugar (real KC->MBON plasticity)", fontsize=9)
    AX1.tick_params(labelsize=8)
    AX1.grid(alpha=0.15)
    FIG.tight_layout()
    buf = io.BytesIO()
    FIG.savefig(buf, format="png", dpi=95)
    buf.seek(0)
    return buf.getvalue()
