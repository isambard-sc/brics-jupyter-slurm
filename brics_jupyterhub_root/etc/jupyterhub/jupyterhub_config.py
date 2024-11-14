"""
JupyterHub configuration for deployment of containerised JupyterHub with BricsAuthenticator
"""

c = get_config()  #noqa

from pathlib import Path
import sys

# TODO Remove workaround of editing module search path after bricsspawner has 
#   been migrated to bricsauthenticator repository. This is required so that 
#   Spawner code can be stored in a separate file (for testing), but still be
#   imported by the JupyterHub config file when used by JupyterHub.
sys.path.append(str(Path(__file__).parent))

import batchspawner  # Even though not used, needed to register batchspawner interface
from bricsauthenticator import BricsAuthenticator
from bricsspawner import BricsSlurmSpawner
from jupyterhub.handlers import BaseHandler

# The JupyterHub public proxy should listen on all interfaces, with a base URL
# of /jupyter
c.JupyterHub.bind_url = "http://:8000/jupyter"

# The Hub API should listen on an IP address that can be reached by spawned
# single-user servers
c.JupyterHub.hub_bind_url = "http://127.0.0.1:8081"

# BricsAuthenticator decodes claims from the JWT received in HTTP headers,
# uses the short_name claim from the received JWT as the username of the
# authenticated user, and passes the projects claim from the received JWT
# to BricsSpawner via auth_state. See
#
# * https://jupyterhub.readthedocs.io/en/latest/reference/authenticators.html#authentication-state
# * https://github.com/isambard-sc/bricsauthenticator/blob/main/src/bricsauthenticator/bricsauthenticator.py

# DUMMY_USERNAME is a fixed username which looks like a decoded short_name claim
# that can be passed to the Spawner class as auth_state to mock the behaviour of
# BricsAuthenticator without receiving a JWT. This is obtained from the
# environment variable DEV_USER_CONFIG_DEFAULT_SHORT_NAME in the environment of the
# JupyterHub process. The value of DEV_USER_CONFIG_DEFAULT_SHORT_NAME must
# correspond to the <USER> component of one of the Unix usernames in
# the DEV_USER_CONFIG_UNIX_USERNAMES environment variable.
def get_short_name_claim_list() -> list[str]:
    """
    Return a list of strings that look like decoded short_name claims

    Gets a whitespace-separated list of Unix usernames in the form
    <USER>.<PROJECT> from DEV_USER_CONFIG_UNIX_USERNAMES in the environment or
    raises RuntimeError.

    Constructs the list of short_name claims as by extracting unique <USER>
    values from the list of Unix usernames.
    """
    from os import environ
    try:
        unix_usernames = environ["DEV_USER_CONFIG_UNIX_USERNAMES"]
    except KeyError as e:
        raise RuntimeError("Environment variable DEV_USER_CONFIG_UNIX_USERNAMES must be set") from e

    return list(set(unix_username.split(".")[0] for unix_username in unix_usernames.split()))

def get_default_short_name_claim() -> str:
    """
    Return a string that looks like a decoded short_name claim

    Gets a string from DEV_USER_CONFIG_DEFAULT_SHORT_NAME in the environment or
    raises RuntimeError.

    This value can be used as the fixed short_name claim to pass to
    DummyBricsAuthenticator.
    """
    from os import environ
    try:
        return environ["DEV_USER_CONFIG_DEFAULT_SHORT_NAME"]
    except KeyError as e:
        raise RuntimeError("Environment variable DEV_USER_CONFIG_DEFAULT_SHORT_NAME must be set") from e

DUMMY_USERNAME = get_default_short_name_claim()

short_name_claims = get_short_name_claim_list()
if DUMMY_USERNAME not in short_name_claims:
    raise RuntimeError(f"The default short_name '{DUMMY_USERNAME}' is not present in the list of short_name values extracted from the environment: {short_name_claims}")

# DUMMY_AUTH_STATE is a fixed dictionary which looks like a decoded project claim
# that can be passed to the Spawner class as auth_state to mock the behaviour of
# BricsAuthenticator without receiving a JWT. This is generated using the list of
# Unix usernames in the environment variable DEV_USER_CONFIG_UNIX_USERNAMES in
# the environment of the JupyterHub process
def get_projects_claim(username: str, infrastructures: list[str] = None) -> dict[str, list[str]]:
    """
    Return a dict that looks like a decoded projects claim for `username`

    Gets a whitespace-separated list of Unix usernames in the form
    <USER>.<PROJECT> from DEV_USER_CONFIG_UNIX_USERNAMES in the environment or
    raises RuntimeError.

    Constructs the projects claim as a dictionary mapping all <PROJECT> values
    with corresponding <USER> == `username` to a default list of infrastructures.
    """
    from os import environ
    if infrastructures is None:
        infrastructures = ["slurm.aip1.isambard", "jupyter.aip1.isambard", "slurm.3.isambard"]

    try:
        unix_usernames = environ["DEV_USER_CONFIG_UNIX_USERNAMES"]
    except KeyError as e:
        raise RuntimeError("Environment variable DEV_USER_CONFIG_UNIX_USERNAMES must be set") from e

    projects = [unix_username.split(".")[1] for unix_username in unix_usernames.split() if unix_username.split(".")[0] == username]

    return {project: infrastructures for project in projects}

DUMMY_AUTH_STATE = get_projects_claim(DUMMY_USERNAME)

class DummyBricsLoginHandler(BaseHandler):
    """
    Handler with dummy get() that authenticates with a fixed username and auth_state
    """
    async def get(self):
        user = await self.auth_to_user({"name": DUMMY_USERNAME, "auth_state": DUMMY_AUTH_STATE})
        self.set_login_cookie(user)
        next_url = self.get_next_url(user)
        self.redirect(next_url)

class DummyBricsAuthenticator(BricsAuthenticator):
    """
    Replaces login page handler for BricsAuthenticator with a handler with dummy get method
    
    This can be used in place of BricsAuthenticator when testing BricsSlurmSpawner
    (which expects auth_state) in a context where HTTP requests do not contain
    valid JWTs
    """
    def get_handlers(self, app):
        return [(r"/login", DummyBricsLoginHandler)]

# Use BriCS-customised Authenticator class (registered as entry point by
# bricsauthenticator package)
#c.JupyterHub.authenticator_class = "brics"

# Use DummyAuthenticator extended to provide mock auth_state to BricsSlurmSpawner
c.JupyterHub.authenticator_class = DummyBricsAuthenticator

# TODO Restrict allowed usernames to a list of dummy users, e.g. using 
#   allowed_users configuration attribute. Then the product of the allowed users
#   and projects in DUMMY_AUTH_STATE can be used to create project-specific test
#   accounts in the Slurm container

# Don't shut down single-user servers when Hub is shut down. This allows the hub
# to restart and reconnect to running user servers
c.JupyterHub.cleanup_servers = False

# Use BriCS-customised SlurmSpawner class
c.JupyterHub.spawner_class = BricsSlurmSpawner

# The default env_keep contains a number of variables which do not need to be
# passed from JupyterHub to the single-user server when starting the server as
# a batch job.
# 
# Set env_keep to empty list to avoid these environment variables from becoming
# part of SlurmSpawner's keepvars template variable and their values in the
# environment for JupyterHub being passed through to the spawned single-user
# server.
c.Spawner.env_keep = []

# Set environment variables to pass information through to the job submission
# script environment/spawned Jupyter user server. The variables are prefixed
# with JUPYTERHUB_* to ensure that they are passed through the `sudo` command
# used to invoke `sbatch` (according to the sudoers policy)
c.Spawner.environment = {
    "JUPYTERHUB_BRICS_MINIFORGE_PREFIX_DIR": "/opt/jupyter/miniforge3",
    "JUPYTERHUB_BRICS_OPT_JUPYTER_DIR": "/opt/jupyter"
}

# Default notebook directory is the user's home directory (`~` is expanded)
c.Spawner.notebook_dir = '~/'

# Allow up to 7 mins (420s) for user session to queue and start
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



# srun command used to run single-user server inside batch script
# Modified to propagate all environment variables from batch script environment.
# This is necessary because by default `srun` will only use environment variables
# specified via the `sbatch` `--export` flag (via SLURM_EXPORT_ENV environment
# variable). We use `--export` to only specify environment variables in
# the keepvars template variable, which has been configured to exclude some
# host-specific variables which are usually included by default, such as PATH.
# This is because the values of these variables comes from the environment
# JupyterHub is running, where PATH etc. is likely to differ to the PATH in a
# batch script executing on a compute node. Using --export=ALL ensures that all
# variables passed through from JupyterHub's environment via keepvars and any
# other environment variables set by Slurm in the batch script environment are
# propagated through `srun`.
c.BricsSlurmSpawner.req_srun = "srun --export=ALL"

# Prefix for commands used to interact with workload scheduler. Default is
# "sudo -E -u {username}" from BatchSpawnerBase, which runs the command as the
# user logged into JupyterHub. For single user testing we do not have `sudo`
# and want to submit the job as the user who started JupyterHub.
# When running JupyterHub in a context where we want to execute workload scheduler
# commands on a different machine (e.g. from within a container), we can run scheduler
# commands on the remote host over SSH by adding `ssh <hostname>` to the exec_prefix.
SSH_CMD=["ssh",
    "-i", str(get_ssh_key_file()),
    "jupyterspawner@localhost sudo -u {username}",
]
c.BricsSlurmSpawner.exec_prefix = " ".join(SSH_CMD)

# Batch submission command which explicitly sets environment for sbatch, passing 
# as options to `sudo` from `exec_prefix`
#
# Explicitly setting the environment for the `batch_submit_cmd` is needed
# because `ssh` does not by default allow passing of arbitrary environment
# variables through to the remote process. OpenSSH client/server can be
# configured allow specific whitelisted variables to be passed from `ssh`'s
# environment into the environment of the remote process, but does not
# do this by default.
#
# The exec_prefix and batch_submit_cmd attributes undergo template expansion
# in BatchSpawner, so we can use Jinja2 templating features to insert
# all environment variables. After template rendering, the full command
# exec_prefix + batch_submit_cmd is run in a shell with environment specified
# by the result of the Spawner class's get_env() function.
#
# `batch_submit_cmd` needs to submit the job using `sbatch`, passing the
# environment variables in template variable keepvars through from the
# environment of the `batch_submit_cmd` to the single-user
# Jupyter server running in the Slurm job. As `sbatch` is being run via `ssh`,
# it does not share the same environment as the `ssh` process (specified by
# get_env()). In this case we expand the environment variables in `keepvars`
# in the environment of the `ssh` process and then explicitly set their values
# as arguments for an `env`/`sudo` command to setup the appropriate environment
# for `sbatch` to pass through to the Slurm job.
#
# NOTE: Care must be taken with quoting! The exec_prefix + batch_submit_cmd is
# run in a shell. Since the command run by the shell is `ssh ... <cmd>`, parameter
# expansion and quote removal occur in the context the `ssh` command is run, not
# in the context where the `<cmd>` is run. This is particularly important as
# some of the `JUPYTERHUB_*` environment variables in keepvars contain quotes
# themselves! In general, any portion of the command run by SSH that should be
# considered a single argument but might be split by the shell should be
# double-quoted, so that only the outer quotes are removed when the
# `ssh ... <cmd>` is processed by the shell.
SLURMSPAWNER_WRAPPERS_BIN="/opt/jupyter/slurmspawner_wrappers/bin"
c.BricsSlurmSpawner.batch_submit_cmd = " ".join(
    [
        "{% for var in keepvars.split(',') %}{{var}}=\"'${{'{'}}{{var}}{{'}'}}'\" {% endfor %}",
        f"{SLURMSPAWNER_WRAPPERS_BIN}/slurmspawner_sbatch",
]
)

# For `batch_query_cmd` and `batch_cancel_cmd`, passing through environment
# variables in `keepvars` is not necessary. However, we must still set the
# environment to pass the required SLURMSPAWNER_JOB_ID environment variable to
# the `slurmspawner_{scancel,squeue}` wrapper scripts, since these receive
# parameters via environment variables (not command line arguments).
c.BricsSlurmSpawner.batch_query_cmd = "SLURMSPAWNER_JOB_ID={{job_id}} " + f"{SLURMSPAWNER_WRAPPERS_BIN}/slurmspawner_squeue"
c.BricsSlurmSpawner.batch_cancel_cmd = "SLURMSPAWNER_JOB_ID={{job_id}} " + f"{SLURMSPAWNER_WRAPPERS_BIN}/slurmspawner_scancel"

# On Isambard-AI, no need to specify memory per node when --gpus is used to
# request a number of GH200s because memory is allocated based on the number of
# GPUs requested
# `--mem=0` requests all memory on each requested compute node in `sbatch`, `srun`
#c.BricsSlurmSpawner.req_memory = "0"
# No need to specify number of nodes required, as Slurm should request the correct number
# of nodes based on the number of GH200s requested
# Request a single node for Jupyter session
#c.BricsSlurmSpawner.req_options = "--nodes=1"
# Based on default for SlurmSpawner
# https://github.com/jupyterhub/batchspawner/blob/fe5a893eaf9eb5e121cbe36bad2e69af798e6140/batchspawner/batchspawner.py#L675
c.BricsSlurmSpawner.batch_script = """#!/bin/bash
#SBATCH --output={{homedir}}/jupyterhub_slurmspawner_%j.log
#SBATCH --job-name=spawner-jupyterhub
#SBATCH --chdir={{homedir}}
#SBATCH --export={{keepvars}}
#SBATCH --get-user-env=L
{% if partition  %}#SBATCH --partition={{partition}}
{% endif %}{% if runtime    %}#SBATCH --time={{runtime}}
{% endif %}{% if memory     %}#SBATCH --mem={{memory}}
{% endif %}{% if gres       %}#SBATCH --gres={{gres}}
{% endif %}{% if ngpus      %}##SBATCH --gpus={{ngpus}}  # NOTE: --gpus disabled in Slurm dev environment
{% endif %}{% if nprocs     %}#SBATCH --cpus-per-task={{nprocs}}
{% endif %}{% if reservation%}#SBATCH --reservation={{reservation}}
{% endif %}{% if options    %}#SBATCH {{options}}{% endif %}

set -euo pipefail

source ${JUPYTERHUB_BRICS_MINIFORGE_PREFIX_DIR}/bin/activate jupyter-user-env

export JUPYTER_PATH=${JUPYTERHUB_BRICS_OPT_JUPYTER_DIR}/jupyter_data${JUPYTER_PATH:+:}${JUPYTER_PATH:-}

trap 'echo SIGTERM received' TERM
{{prologue}}
{% if srun %}{{srun}} {% endif %}{{cmd}}
echo "jupyterhub-singleuser ended gracefully"
{{epilogue}}
"""

# Enable persisting of auth_state, which is used to persist authentication
# information in JupyterHub's database. This is encrypted and the 
# JUPYTERHUB_CRYPT_KEY environment variable must be set. `auth_state` is passed
# from  `Authenticator.authenticate()` to the `Spawner` via 
# `Spawner.auth_state_hook`. This is used to pass the value of the projects 
# claim from the JWT received by Authenticator to the Spawner.
c.Authenticator.enable_auth_state = True
