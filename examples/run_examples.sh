#!/usr/bin/env bash
#
# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent.  All rights reserved.
#
# tRPC-A2A-Python is licensed under the Apache-2.0.
#
# Start the example server for one agent, run the matching client, then stop the server.
#
# Usage:
#   ./run_examples.sh                       # same as "basic" with trpc_python.yaml
#   ./run_examples.sh basic [conf]          # basic agent, both basic clients, GET /hello
#   ./run_examples.sh streaming             # streaming agent and streaming_client.py
#   ./run_examples.sh multiturn             # multiturn agent and multiturn_client.py
#   ./run_examples.sh error                 # error agent and error_client.py
#   ./run_examples.sh push                  # push agent and push_notify_client.py
#   ./run_examples.sh task_push             # task push agent and task_push_notify_client.py
#   ./run_examples.sh modes                 # basic against each config
#   ./run_examples.sh all                   # the feature scenarios, then modes
#   ./run_examples.sh list                  # list example names and config files
#
# A conf path is a file name under this directory, or an absolute path.
# Only "basic" takes a conf. The other feature scenarios use trpc_python.yaml,
# because cancel and multi-turn state stay in the process that handled the task.
# The A2A service listens on 18080. Push clients also bind 19080 and 19081.
# Clients load examples/clients/trpc_python.yaml relative to the package root,
# so they are started with that directory as the working directory.
#
# Environment:
#   PYTHON   interpreter to use (default: ../.venv/bin/python, then ../venv/bin/python, then python3)
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Package root first. A sibling checkout of the SDK (../trpc_sdk) is inserted
# ahead of site-packages so this example uses that source.
PYTHONPATH="${PKG_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
SDK_PARENT="$(cd "${PKG_DIR}/.." && pwd)"
if [[ -f "${SDK_PARENT}/trpc_sdk/http/__init__.py" ]]; then
  PYTHONPATH="${SDK_PARENT}:${PYTHONPATH}"
fi
export PYTHONPATH

# Forked workers on macOS abort if httpx reads the system proxy settings.
export NO_PROXY="${NO_PROXY:+${NO_PROXY},}localhost,127.0.0.1"
export no_proxy="${no_proxy:+${no_proxy},}localhost,127.0.0.1"

if [[ -n "${PYTHON:-}" ]]; then
  PY="${PYTHON}"
elif [[ -x "${PKG_DIR}/.venv/bin/python" ]]; then
  PY="${PKG_DIR}/.venv/bin/python"
elif [[ -x "${PKG_DIR}/venv/bin/python" ]]; then
  PY="${PKG_DIR}/venv/bin/python"
else
  PY="$(command -v python3)"
fi

SERVER_LOG="${SCRIPT_DIR}/.server_run.log"
SERVER_PID=""
HOST="127.0.0.1"
PORT=18080
PUSH_PORT=19080
TASK_PUSH_PORT=19081

CONFIGS=(
  trpc_python.yaml
  trpc_python_single_process_merge.yaml
  trpc_python_single_process_separate.yaml
  trpc_python_multi_process_separate.yaml
  trpc_python_multi_process_merge.yaml
)

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*" >&2; }
ok()  { printf '\033[1;32m[PASS]\033[0m %s\n' "$*" >&2; }
bad() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; }

port_open() {
  local port="${1:-${PORT}}"
  "${PY}" -c "import socket; s=socket.create_connection(('${HOST}', ${port}), 0.2); s.close()" >/dev/null 2>&1
}

wait_ready() {
  local tries=60
  while (( tries-- > 0 )); do
    port_open && return 0
    if [[ -n "${SERVER_PID}" ]] && ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      return 1
    fi
    sleep 0.5
  done
  return 1
}

wait_port_free() {
  local tries=20
  while (( tries-- > 0 )); do
    port_open || return 0
    sleep 0.5
  done
  return 1
}

resolve_conf() {
  local conf="${1:-${SCRIPT_DIR}/trpc_python.yaml}"
  if [[ "${conf}" != /* ]]; then
    if [[ -f "${SCRIPT_DIR}/${conf}" ]]; then
      conf="${SCRIPT_DIR}/${conf}"
    fi
  fi
  if [[ ! -f "${conf}" ]]; then
    bad "config not found: ${conf}"
    return 1
  fi
  printf '%s\n' "${conf}"
}

require_port_free() {
  local port="$1"
  if port_open "${port}"; then
    bad "port ${port} is already in use; stop that process first"
    return 1
  fi
}

start_server() {
  local conf="$1"
  local agent="${2:-basic}"
  if port_open; then
    bad "port ${PORT} is already in use; stop that process first"
    return 1
  fi
  log "starting server: ${conf} (agent ${agent})"
  : > "${SERVER_LOG}"
  # `exec` makes the subshell become the python process, so $! is its pid.
  ( cd "${SCRIPT_DIR}" && exec "${PY}" trpc_main.py --conf "${conf}" --agent "${agent}" ) >>"${SERVER_LOG}" 2>&1 &
  SERVER_PID=$!
  if ! wait_ready; then
    bad "server did not start listening on ${PORT}; last log lines:"
    tail -n 40 "${SERVER_LOG}" || true
    stop_server
    return 1
  fi
}

stop_server() {
  # EXIT also calls this when no server was started (for example `list`).
  [[ -z "${SERVER_PID}" ]] && return 0
  pkill -TERM -P "${SERVER_PID}" 2>/dev/null || true
  kill -TERM "${SERVER_PID}" 2>/dev/null || true
  local _
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    kill -0 "${SERVER_PID}" 2>/dev/null || break
    sleep 0.5
  done
  pkill -KILL -P "${SERVER_PID}" 2>/dev/null || true
  kill -KILL "${SERVER_PID}" 2>/dev/null || true
  wait "${SERVER_PID}" 2>/dev/null || true
  SERVER_PID=""
  if ! wait_port_free; then
    bad "port ${PORT} still in use after stopping the server"
    return 1
  fi
}

run_python_client() {
  local label="$1"
  local script="$2"
  local rc=0
  log "running ${label}"
  # Clients load examples/clients/trpc_python.yaml relative to the package root.
  ( cd "${PKG_DIR}" && "${PY}" "${script}" ) || rc=$?
  if [[ ${rc} -eq 0 ]]; then
    ok "${label}"
  else
    bad "${label} (exit ${rc})"
  fi
  return ${rc}
}

check_hello() {
  local body rc=0
  body="$(curl -fsS --max-time 10 "http://${HOST}:${PORT}/hello")" || rc=$?
  if [[ ${rc} -ne 0 ]]; then
    bad "GET /hello (curl ${rc})"
    return 1
  fi
  if [[ "${body}" != *"hello world"* ]]; then
    bad "GET /hello missing 'hello world'"
    printf '%s\n' "${body}" >&2
    return 1
  fi
  ok "GET /hello"
}

run_clients() {
  local rc=0
  run_python_client "basic_client" "examples/clients/basic_client.py" || rc=1
  run_python_client "basic_client_without_yaml" "examples/clients/basic_client_without_yaml.py" || rc=1
  check_hello || rc=1
  return ${rc}
}

run_basic() {
  local conf
  conf="$(resolve_conf "${1:-}")" || return 1
  start_server "${conf}" basic || return 1
  log "running clients against ${HOST}:${PORT}"
  local rc=0
  run_clients || rc=$?
  stop_server || rc=1
  if [[ ${rc} -eq 0 ]]; then
    ok "basic $(basename "${conf}")"
  else
    bad "basic $(basename "${conf}") (see ${SERVER_LOG})"
  fi
  return ${rc}
}

run_feature() {
  local example="$1"
  local agent="$2"
  local script="$3"
  local webhook_port="${4:-}"
  local conf rc=0
  conf="$(resolve_conf "")" || return 1
  if [[ -n "${webhook_port}" ]]; then
    require_port_free "${webhook_port}" || return 1
  fi
  start_server "${conf}" "${agent}" || return 1
  log "running ${example} against ${HOST}:${PORT}"
  run_python_client "$(basename "${script}" .py)" "${script}" || rc=$?
  stop_server || rc=1
  if [[ ${rc} -eq 0 ]]; then
    ok "${example}"
  else
    bad "${example} (see ${SERVER_LOG})"
  fi
  return ${rc}
}

run_streaming() {
  run_feature "streaming" "streaming" "examples/clients/streaming_client.py"
}

run_multiturn() {
  run_feature "multiturn" "multiturn" "examples/clients/multiturn_client.py"
}

run_error() {
  run_feature "error" "error" "examples/clients/error_client.py"
}

run_push() {
  run_feature "push" "push_notify" "examples/clients/push_notify_client.py" "${PUSH_PORT}"
}

run_task_push() {
  run_feature "task_push" "task_push_notify" "examples/clients/task_push_notify_client.py" "${TASK_PUSH_PORT}"
}

run_features() {
  local rc=0
  run_basic || rc=1
  run_streaming || rc=1
  run_multiturn || rc=1
  run_error || rc=1
  run_push || rc=1
  run_task_push || rc=1
  return ${rc}
}

run_modes() {
  local rc=0 conf
  for conf in "${CONFIGS[@]}"; do
    run_basic "${conf}" || rc=1
  done
  return ${rc}
}

run_all() {
  local rc=0
  run_features || rc=1
  run_modes || rc=1
  return ${rc}
}

no_extra_args() {
  local name="$1"
  local extra="${2:-}"
  local hint="$3"
  if [[ -n "${extra}" ]]; then
    bad "${name} only accepts the example name (${hint})"
    return 2
  fi
}

trap 'stop_server' EXIT INT TERM

main() {
  case "${1:-basic}" in
    list)
      echo "Available examples: basic streaming multiturn error push task_push modes all"
      echo "Configs:"
      printf '  %s\n' "${CONFIGS[@]}"
      ;;
    basic)
      run_basic "${2:-}"
      ;;
    streaming)
      no_extra_args streaming "${2:-}" "uses trpc_python.yaml" || return 2
      run_streaming
      ;;
    multiturn)
      no_extra_args multiturn "${2:-}" "uses trpc_python.yaml" || return 2
      run_multiturn
      ;;
    error)
      no_extra_args error "${2:-}" "uses trpc_python.yaml" || return 2
      run_error
      ;;
    push)
      no_extra_args push "${2:-}" "uses trpc_python.yaml" || return 2
      run_push
      ;;
    task_push)
      no_extra_args task_push "${2:-}" "uses trpc_python.yaml" || return 2
      run_task_push
      ;;
    modes)
      no_extra_args modes "${2:-}" "runs basic against every config" || return 2
      run_modes
      ;;
    all)
      no_extra_args all "${2:-}" "runs the feature scenarios, then modes" || return 2
      run_all
      ;;
    *)
      bad "unknown example: $1 (try: ./run_examples.sh list)"
      return 2
      ;;
  esac
}

main "$@"
