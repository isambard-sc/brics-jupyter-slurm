#!/bin/bash
set -euo pipefail

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

USAGE='./jh_slurm_pod.sh {up|down}'

function bring_pod_up {
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
  
  # Bring up podman pod
  podman kube play jh_slurm_pod.yaml
}

function tear_pod_down {
  # Tear down podman pod
  podman kube down jh_slurm_pod.yaml 

  # Delete podman named volume containing JupyterHub data
  podman volume rm jupyterhub_root
}

# Validate number of arguments
if (( $# != 1 )); then
  echo "Error: incorrect number of arguments"
  echo
  echo "Usage: ${USAGE}"
  exit 1
fi 

# Bring up or tear down podman pod using K8s manifest
if [[ $1 == "up" ]]; then

  echo "Bringing up pod"
  set -x
  bring_pod_up

elif [[ $1 == "down" ]]; then
  echo "Tearing pod down"
  set -x
  tear_pod_down
else
  echo "Error: incorrect argument values"
  echo
  echo "Usage: ${USAGE}"
  exit 1
fi