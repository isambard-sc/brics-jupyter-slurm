#!/bin/bash
set -euo pipefail

# Authorized keys for jupyterspawner user
chown -R jupyterspawner:jupyterspawner /home/jupyterspawner/.ssh
chmod u=rw,g=,o= /home/jupyterspawner/.ssh/authorized_keys