#!/bin/bash
set -euo pipefail

set -x

# Build local container images
podman build -t brics_jupyterhub ./brics_jupyterhub
podman build -t brics_slurm ./brics_slurm

# Create podman named volume containing JupyterHub data
podman volume create jupyterhub_root
if [[ $(uname) == "Darwin" ]]; then
  # podman volume import not available using remote client, so run podman inside VM
  tar --cd brics_jupyterhub_root/ --create --file - . | podman machine ssh podman volume import jupyterhub_root -
else
  tar --cd brics_jupyterhub_root/ --create --file - . | podman volume import jupyterhub_root -
fi

podman kube play jh_slurm_pod.yaml

# To inspect contents of volume (extract into current directory)
# macOS
#   podman machine ssh podman volume export jupyterhub_root | tar --extract --verbose
# Linux
#   podman volume export jupyterhub_root | tar --extract --verbose

# To tear down pod
#   podman kube down jh_slurm_pod.yaml 
# or
#   podman pod stop jupyterhub-slurm
#   podman pod rm jupyterhub-slurm

# To remove volume
#   podman volume rm jupyterhub_root_vol

set +x
