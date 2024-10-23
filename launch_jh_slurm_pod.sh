#!/bin/bash
set -euo pipefail

set -x

# Build local container images
podman build -t brics_jupyterhub ./brics_jupyterhub
podman build -t brics_slurm ./brics_slurm

# Create podman named volume
podman volume create jupyterhub_root_vol
if [[ $(uname) == "Darwin" ]]; then
  # podman volume import not available using remote client, so run podman inside VM
  tar --cd brics_jupyterhub_root/ --create --file - . | podman machine ssh podman volume import jupyterhub_root_vol -
else
  tar --cd brics_jupyterhub_root/ --create --file - . | podman volume import jupyterhub_root_vol -
fi

podman kube play --replace jh_slurm_pod.yaml

# To tear down pod
# podman kube down jh_slurm_pod.yaml 

# To remove volme
# podman volume rm jupyterhub_root_vol

set +x
