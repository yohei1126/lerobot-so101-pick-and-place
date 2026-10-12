#!/bin/bash
set -eo pipefail
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
exec "$@"
