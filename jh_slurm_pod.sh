#!/bin/bash
set -euo pipefail

USAGE='./jh_slurm_pod.sh {up|down}'

# Get user and group for JupyterHub container volume from environment, or set defaults
: ${JUPYTERUSER:=root}
: ${JUPYTERUSER_UID:=0}
: ${JUPYTERGROUP:=root}
: ${JUPYTERGROUP_GID:=0}

# Get user and group for Slurm container volume from environment, or set defaults
: ${SLURMUSER:=slurm}
: ${SLURMUSER_UID:=64030}
: ${SLURMGROUP=slurm}
: ${SLURMGROUP_GID:=64030}

# Creates an SSH key in the directory provided as an argument, then writes a 
# K8s manifest for a Secret containing the key data to stdout
function make_ssh_key_secret {
  if [[ ! -d ${1} ]]; then
    echo "Error: ${1} is not a directory"
    exit 1
  fi
  ssh-keygen -t ed25519 -f ${1}/ssh_key -N "" -C "JupyterHub-Slurm dev environment" >/dev/null 2>&1
  cat <<EOF
apiVersion: core/v1
kind: Secret
metadata:
  name: jupyterhub-slurm-ssh-key
stringData:
  ssh_key: |
$(cat ${BUILD_TMPDIR}/ssh_key | sed -E -e 's/^/    /')
  ssh_key.pub: |
$(cat ${BUILD_TMPDIR}/ssh_key.pub | sed -E -e 's/^/    /')
immutable: true
EOF
}

function bring_pod_up {
  # Make a temporary directory under ./_build_tmp to store ephemeral build data
  mkdir -p -v _build_tmp/
  BUILD_TMPDIR=$(mktemp -d _build_tmp/jh_slurm_pod.XXXXXXXXXX)
  echo "Temporary build data directory: ${BUILD_TMPDIR}"

  # Build local container images
  podman build -t brics_jupyterhub ./brics_jupyterhub
  podman build -t brics_slurm ./brics_slurm

  # Create podman named volume containing JupyterHub data
  podman volume create jupyterhub_root
  if [[ $(uname) == "Darwin" ]]; then
    # podman volume import not available using remote client, so run podman inside VM
    tar --cd brics_jupyterhub_root/ --create \
      --exclude .gitkeep \
      --uname ${JUPYTERUSER} --uid ${JUPYTERUSER_UID} \
      --gname ${JUPYTERGROUP} --gid ${JUPYTERGROUP_GID} \
      --file - . | podman machine ssh podman volume import jupyterhub_root -
  else
    # TODO update GNU tar command to exclude .gitkeep and set UID/GID for files in archive
    tar --cd brics_jupyterhub_root/ --create --file - . | podman volume import jupyterhub_root -
  fi

  # Create podman named volume containing Slurm data
  podman volume create slurm_root
  if [[ $(uname) == "Darwin" ]]; then
    # podman volume import not available using remote client, so run podman inside VM
    tar --cd brics_slurm_root/ --create \
      --exclude .gitkeep \
      --uname ${SLURMUSER} --uid ${SLURMUSER_UID} \
      --gname ${SLURMGROUP} --gid ${SLURMGROUP_GID} \
      --file - . | podman machine ssh podman volume import slurm_root -
  else
    tar --cd brics_slurm_root/ --create --file - . | podman volume import slurm_root -
  fi
  
  # Create combined manifest file with Secret and Pod
  cat > ${BUILD_TMPDIR}/combined.yaml <<EOF
$(make_ssh_key_secret ${BUILD_TMPDIR})
---
$(cat jh_slurm_pod.yaml)
EOF

  # Bring up pod using combined file
  podman kube play ${BUILD_TMPDIR}/combined.yaml
  
  # Preserve temporary build data directory for debugging (can be manually deleted)
  echo "To delete temporary build data directory:"
  echo "  rm -r -v ${BUILD_TMPDIR}"
}

function tear_pod_down {
  # Tear down podman pod
  podman pod stop jupyterhub-slurm
  podman pod rm jupyterhub-slurm

  # Delete podman named volume containing JupyterHub data
  podman volume rm jupyterhub_root

  # Delete podman named volume containing Slurm data
  podman volume rm slurm_root

  # Delete podman secret containing SSH key
  podman secret rm jupyterhub-slurm-ssh-key

  # Delete podman volume derived from Secret
  podman volume rm jupyterhub-slurm-ssh-key
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
  bring_pod_up

elif [[ $1 == "down" ]]; then
  echo "Tearing pod down"
  tear_pod_down

else
  echo "Error: incorrect argument values"
  echo
  echo "Usage: ${USAGE}"
  exit 1
fi