#!/usr/bin/env bash
# Shared helpers for hardware-workspace path / serial overrides.
# Source from other scripts:  source "$(dirname "$0")/lib_hw_root.sh"
#
# After resolve_hw_root_args "$@":
#   - LEROBOT_HW_ROOT is exported
#   - HW mirrors that path
#   - REMAINING holds argv with --hw-root consumed
#
# Optional (set before calling resolve_record_args for recording scripts):
#   PORT_FOLLOWER / PORT_LEADER / DATASET_ROOT env fallbacks

: "${LEROBOT_HW_ROOT:=${HOME}/work/lerobot-hw}"

resolve_hw_root_args() {
  HW="${LEROBOT_HW_ROOT}"
  REMAINING=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --hw-root)
        [[ $# -ge 2 ]] || {
          echo "ERROR: --hw-root requires a path" >&2
          exit 1
        }
        HW="$2"
        shift 2
        ;;
      --hw-root=*)
        HW="${1#*=}"
        shift
        ;;
      *)
        REMAINING+=("$1")
        shift
        ;;
    esac
  done
  export LEROBOT_HW_ROOT="$HW"
}
