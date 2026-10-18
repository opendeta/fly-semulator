#!/usr/bin/env bash
# Download the MaleCNS v1.0 flat connectome (CC-BY 4.0, Janelia/Google Research).
# No login required. ~535 MB total.
set -euo pipefail
OUT="${FLY_DATA:-./data}"
mkdir -p "$OUT"
BASE="https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"

get () {  # get <remote-name> <local-name>
  [ -f "$OUT/$2" ] && { echo "have $2"; return; }
  echo "downloading $2 ..."
  curl -L --fail --retry 3 -o "$OUT/$2" "$BASE/$1"
}

get body-annotations-male-cns-v1.0-minconf-0.5.feather                  body-annotations.feather
get body-neurotransmitters-male-cns-v1.0.feather                        neurotransmitters.feather
get connectome-weights-male-cns-v1.0-minconf-0.5-significant-only.feather weights.feather

echo "building compact brain graph ..."
FLY_DATA="$OUT" python3 scripts/build_brain.py
echo "done."
