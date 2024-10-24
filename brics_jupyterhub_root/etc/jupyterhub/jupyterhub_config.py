"""
JupyterHub configuration for deployment of containerised JupyterHub with BricsAuthenticator
"""

c = get_config()  #noqa

from pathlib import Path
import sys

# TODO Remove workaround of editing module search path after bricsspawner has been migrated to bricsauthenticator 
#   repository
sys.path.append(str(Path(__file__).parent))

from tornado import web
from typing import Callable
from traitlets import default
import batchspawner  # Even though not used, needed to register batchspawner interface

from bricsspawner import BricsSlurmSpawner

c.JupyterHub.cleanup_servers = False
c.JupyterHub.spawner_class = BricsSlurmSpawner

c.Spawner.env_keep = []
c.Spawner.notebook_dir = '~/'
c.Spawner.start_timeout = 420


def get_ssh_key_file() -> Path:
    """
    Return a path to an SSH key under JUPYTERHUB_SRV_DIR

    Gets JUPYTERHUB_SRV_DIR from environment or raises RuntimeError.
    Also raises RuntimeError if $JUPYTERHUB_SRV_DIR/ssh_key does not exist.
    """
    from os import environ
    try:
        srv_dir = environ["JUPYTERHUB_SRV_DIR"]
    except KeyError as e:
        raise RuntimeError("Environment variable JUPYTERHUB_SRV_DIR must be set") from e

    try:
        return (Path(srv_dir) / "ssh_key").resolve(strict=True)
    except FileNotFoundError as e:
        raise RuntimeError(f"SSH private key not found at expected location") from e

SSH_CMD=["ssh",
    "-i", str(get_ssh_key_file()),
    "-oStrictHostKeyChecking=no",
    "-oUserKnownHostsFile=/dev/null",
    "jupyterspawner@localhost sudo -u {username}",
]
SLURMSPAWNER_WRAPPERS_BIN="/tools/brics/admin/jupyterspawner/venvs/slurmspawner_wrappers/bin"

c.BricsSlurmSpawner.req_srun = "srun --export=ALL"
c.BricsSlurmSpawner.exec_prefix = " ".join(SSH_CMD)
c.BricsSlurmSpawner.batch_submit_cmd = " ".join(
    [
        "{% for var in keepvars.split(',') %}{{var}}=\"'${{'{'}}{{var}}{{'}'}}'\" {% endfor %}",
        f"{SLURMSPAWNER_WRAPPERS_BIN}/slurmspawner_sbatch",
]
)
c.BricsSlurmSpawner.batch_query_cmd = "SLURMSPAWNER_JOB_ID={{job_id}} " + f"{SLURMSPAWNER_WRAPPERS_BIN}/slurmspawner_squeue"
c.BricsSlurmSpawner.batch_cancel_cmd = "SLURMSPAWNER_JOB_ID={{job_id}} " + f"{SLURMSPAWNER_WRAPPERS_BIN}/slurmspawner_scancel"
c.BricsSlurmSpawner.batch_script = """#!/bin/bash
{% if partition  %}#SBATCH --partition={{partition}}
{% endif %}{% if runtime    %}#SBATCH --time={{runtime}}
{% endif %}{% if memory     %}#SBATCH --mem={{memory}}
{% endif %}{% if gres       %}#SBATCH --gres={{gres}}
{% endif %}{% if ngpus      %}#SBATCH --gpus={{ngpus}}
{% endif %}{% if nprocs     %}#SBATCH --cpus-per-task={{nprocs}}
{% endif %}{% if reservation%}#SBATCH --reservation={{reservation}}
{% endif %}{% if options    %}#SBATCH {{options}}{% endif %}

set -euo pipefail

source /tools/brics/jupyter/miniforge3/bin/activate jupyter-user-env

export JUPYTER_PATH=/tools/brics/jupyter/jupyter_data${JUPYTER_PATH:+:}${JUPYTER_PATH:-}

trap 'echo SIGTERM received' TERM
{{prologue}}
{% if srun %}{{srun}} {% endif %}{{cmd}}
echo "jupyterhub-singleuser ended gracefully"
{{epilogue}}
"""

c.Authenticator.enable_auth_state = True
