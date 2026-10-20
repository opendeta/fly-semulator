---
title: Fly Brain Lab
emoji: 🪰
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# 🪰 FLY BRAIN LAB — live male fruit fly connectome

A live, embodied simulation of the **male *Drosophila* central nervous system**: the real
**MaleCNS v1.0** connectome (164,740 neurons, 25.6M synaptic edges) running as an
event-driven LIF spiking network that steers a body toward light — plus **associative
learning** on the connectome's own **61,210 KC→MBON synapses** (dopamine-gated plasticity,
PAM = reward / PPL1 = punishment).

* live video + live brain activity panel
* remote control (move the light, pause, knobs)
* **upload a video** → it becomes what the fly's compound eyes see
* **train**: a visual cue is paired with sugar; the KC→MBON weights change and the fly
  learns to orient to the cue (measured learning curve in the console)

Honest limits: LIF is a strong simplification; the plasticity rule is a literature-grounded
model (Hige 2015 / Handler 2019 / Aso 2014), not a measurement; the body is stylized, not
NeuroMechFly. On the free 2-vCPU Space the brain clock is slower than on a big machine.

Code: https://github.com/opendeta/fly-semulator (MIT). Connectome data: CC-BY 4.0 —
Berg et al. 2025 (MaleCNS v1.0, Janelia / Cambridge / MRC LMB / Google Research);
Dorkenwald et al. 2024. Data is downloaded at build time, not redistributed in git.
