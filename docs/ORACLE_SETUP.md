# Running Fly Brain Lab forever, free — Oracle Cloud Always Free

Oracle's Always Free tier gives a **4-core ARM (Ampere A1) VM with 24 GB RAM, free forever**
(no time limit, unlike a trial). That is more than this project needs, and it never sleeps.

Only **one inbound port (SSH 22)** is required: the app reaches the internet through an
*outbound* Cloudflare tunnel, exactly like the current setup, so no web ports need opening.

## 1. Create the account

* https://signup.cloud.oracle.com — pick a **home region close to you** (latency matters).
* A card is required for identity verification; Always Free resources are not charged.

## 2. Create the instance

Oracle Console → **Compute → Instances → Create instance**

| field | value |
|---|---|
| Name | `fly-lab` |
| Image | **Ubuntu 24.04** (Canonical) |
| Shape | **VM.Standard.A1.Flex** → **4 OCPU**, **24 GB** memory (Always Free limits) |
| Boot volume | 100 GB (free allowance is 200 GB) |
| Networking | create/keep the default VCN, **assign a public IPv4** |
| SSH keys | **Paste public key** → paste the key below |

SSH public key (paste this in the "Paste public key" box):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEy7mw9/8+V/xJzV3qyP16V2/KQjl0QmjaZ1ZVtHS6KW fly-semulator-watchdog
```

> ⚠️ Ampere capacity is often exhausted ("Out of host capacity"). Try other
> **availability domains** in the shape selector, or retry a few minutes later.

## 3. Tell the agent the public IP

Copy the instance's **Public IP address** and send it over. From there the agent will:

1. SSH in (the key above is already installed),
2. run `scripts/provision_oracle.sh` (installs python/ffmpeg/cloudflared, clones the repo,
   downloads the CC-BY connectome, builds the graph + plasticity substrate),
3. start `scripts/watchdog.py` under `tmux`, which keeps the dashboard and the tunnel alive
   and **auto-updates `docs/backend.json`** so the GitHub Pages front-end follows it.

The public link never changes: **https://opendeta.github.io/fly-semulator/?k=...**

## 4. Optional — a nicer URL

With a Cloudflare account + any domain you own, a *named* tunnel gives a permanent
`https://fly.yourdomain.com`. Ask the agent to set it up once the VM is running.
