"""Turn an uploaded video into what the fly's compound eyes would see.

Each frame is reduced to two luminance channels (left / right half of the
visual field) plus a motion signal; those drive the visual sensory neurons
of the connectome, and the brighter side defines the cue for training.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

W, H, FPS = 64, 36, 10


def extract(path, out_dir="uploads"):
    path = Path(path)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-i", str(path),
           "-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (W * H)
    if n < 5:
        raise ValueError("could not decode the video (or it is too short)")
    f = np.frombuffer(raw[: n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float32) / 255.0
    half = W // 2
    left = f[:, :, :half].mean(axis=(1, 2))
    right = f[:, :, half:].mean(axis=(1, 2))
    # local normalisation so dim and bright clips both drive the eye
    def norm(v):
        lo, hi = float(np.percentile(v, 5)), float(np.percentile(v, 95))
        return np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)
    left, right = norm(left), norm(right)
    motion = np.zeros(n, np.float32)
    if n > 2:
        d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
        motion[1:] = np.clip(d / max(float(np.percentile(d, 95)), 1e-6), 0, 1)
    cue = 1 if right.mean() >= left.mean() else -1
    np.savez_compressed(out_dir / "video_drive.npz",
                        left=left.astype(np.float32), right=right.astype(np.float32),
                        motion=motion, fps=np.float32(FPS), cue=np.int8(cue))
    meta = dict(file=path.name, frames=int(n), seconds=round(n / FPS, 2),
                fps=FPS, size=f"{W}x{H}", cue=("right" if cue > 0 else "left"),
                brightness_left=round(float(left.mean()), 3),
                brightness_right=round(float(right.mean()), 3),
                motion=round(float(motion.mean()), 3))
    (out_dir / "video_meta.json").write_text(json.dumps(meta, indent=2))
    return meta
