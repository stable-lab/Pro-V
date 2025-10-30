#!/usr/bin/env bash
set -Eeuo pipefail

########################################
# >>> Config (edit these) <<<
########################################
# Visible GPUs in the order you want to consume them (comma-separated, no spaces)
# Example for 8 GPUs: "0,1,2,3,4,5,6,7"
GPU_IDS="2,3"

# Model weights path (local dir or HF repo ID)
MODEL_PATH="/home/lah003/models/Qwen3-8B"

# Served model name for the OpenAI-compatible server (defaults to basename of MODEL_PATH if empty)
SERVED_MODEL_NAME="Qwen/Qwen3-8B"
EXPERIMENT_NAME="fine_thinking_8B"
# vLLM max context length
MAX_LEN=36000

# Base server port (replicas use PORT+i)
PORT=8020

# Parallelism knobs
TP_SIZE=2          # tensor-parallel per replica
DP_SIZE=1          # number of replicas (data-parallel); total GPUs used = TP_SIZE * DP_SIZE

# Optional: extra vLLM flags, e.g. '--gpu-memory-utilization 0.95 --dtype auto'
VLLM_EXTRA=""

# Optional: extra args passed to prompting_top_agent_ray.py
# Use --max_concurrency to control concurrent tasks (default: 50 in ray script)
# Use --num_cpus to set Ray CPU resources (default: system_cpus/100)
EXTRA_ARGS="--max_concurrency 50"

# Task numbers to process (comma-separated or range, e.g., '1,2,3' or '1-10' or '1,5-10,15')
# Leave empty to process all tasks (1-156)
TASK_NUMBERS=""

# ---- Sampling/runtime knobs (exported) ----
TEMPERATURE=0
TOP_P=0.1
TEMPERATURE_SAMPLE=0.6
TOP_P_SAMPLE=0.95
MAX_TOKEN=20000
ENABLE_THINKING=true

# Optional filters (empty means no filter)
FILTER_INSTANCE=""

FOLDER_PATH="./verilog-eval/HDLBits/test_benchmark_new.json"
RUN_IDENTIFIER="gen_tb"
KEY_CFG_PATH="../key.cfg"
USE_GOLDEN_REF=true
SAMPLING_SIZE=5
STIMULI_SAMPLING_SIZE=3
MAX_TRIALS=5
STAGE=0
DAY="20250408"
DUT=false
########################################

# ------------------------------
# Derived and exported settings
# ------------------------------
export TEMPERATURE TOP_P TEMPERATURE_SAMPLE TOP_P_SAMPLE MAX_TOKEN \
       ENABLE_THINKING FOLDER_PATH RUN_IDENTIFIER KEY_CFG_PATH USE_GOLDEN_REF \
       SAMPLING_SIZE STIMULI_SAMPLING_SIZE MAX_TRIALS STAGE DAY DUT \
       FILTER_INSTANCE

# Resolve served model name if not explicitly set
if [[ -z "${SERVED_MODEL_NAME}" ]]; then
  SERVED_MODEL_NAME="$(basename "${MODEL_PATH}")"
fi

# Find Python
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[ERROR] Python not found. Please install python3 or adjust PATH." >&2
  exit 1
fi

# Tool checks
command -v curl >/dev/null 2>&1 || { echo "[ERROR] 'curl' is required." >&2; exit 1; }
command -v lsof >/dev/null 2>&1 || { echo "[ERROR] 'lsof' is required for port checks." >&2; exit 1; }

# ------------------------------
# GPU parsing and validation
# ------------------------------
IFS=',' read -r -a GPU_ARR <<< "${GPU_IDS}"
TOTAL_GPUS_AVAILABLE="${#GPU_ARR[@]}"
TOTAL_GPUS_NEEDED=$(( TP_SIZE * DP_SIZE ))

if (( TOTAL_GPUS_NEEDED < 1 )); then
  echo "[ERROR] Invalid TOTAL_GPUS_NEEDED=${TOTAL_GPUS_NEEDED}. Check TP_SIZE and DP_SIZE." >&2
  exit 1
fi

if (( TOTAL_GPUS_AVAILABLE < TOTAL_GPUS_NEEDED )); then
  echo "[ERROR] Not enough GPUs. Available=${TOTAL_GPUS_AVAILABLE} from GPU_IDS='${GPU_IDS}', needed=${TOTAL_GPUS_NEEDED} (TP_SIZE*DP_SIZE)." >&2
  exit 1
fi

# Slice GPUs for each replica
replica_cuda_devices=()
for (( i=0; i<DP_SIZE; i++ )); do
  start=$(( i * TP_SIZE ))
  end=$(( start + TP_SIZE - 1 ))
  slice=""
  for (( j=start; j<=end; j++ )); do
    slice+="${GPU_ARR[j]},"
  done
  slice="${slice%,}"
  replica_cuda_devices+=("${slice}")
done

# ------------------------------
# Helpers
# ------------------------------
wait_for_ready() {
  # Poll an OpenAI-compatible /v1/models endpoint
  local port="$1"
  local seconds="${2:-120}"
  for _ in $(seq 1 "${seconds}"); do
    if curl -fsS "http://127.0.0.1:${port}/v1/models" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

get_remote_model_name() {
  curl -fsS "http://127.0.0.1:${1}/v1/models" \
    | ${PY} - <<'PY' || true
import sys, json
try:
    data = json.load(sys.stdin)
    models = data.get("data", [])
    if models:
        print(models[0].get("id",""))
except Exception:
    pass
PY
}

launch_replica() {
  local idx="$1"
  local port="$2"
  local cuda="$3"
  local log_file="vllm_${port}.log"

  echo "[INFO] Launching vLLM replica #${idx}: CUDA=${cuda}, port=${port}, model='${MODEL_PATH}', served-name='${SERVED_MODEL_NAME}', TP=${TP_SIZE}, MAX_LEN=${MAX_LEN}"
  (
    set -x
    CUDA_VISIBLE_DEVICES="${cuda}" \
    ${PY} -m vllm.entrypoints.openai.api_server \
      --model "${MODEL_PATH}" \
      --served-model-name "${SERVED_MODEL_NAME}" \
      --tensor-parallel-size "${TP_SIZE}" \
      --max-model-len "${MAX_LEN}" \
      --port "${port}" \
      ${VLLM_EXTRA} \
      >"${log_file}" 2>&1
  ) &
  local pid=$!
  echo "[INFO] vLLM replica #${idx} started (PID=${pid}); logs: ${log_file}"
  STARTED_PIDS+=("${pid}")
  STARTED_LOGS+=("${log_file}")
  STARTED_PORTS+=("${port}")
  STARTED_FLAGS+=("launched")
}

try_link_or_launch() {
  # Enforce: try to link within 10s; if not available and port free => launch and wait 120s
  # If port occupied by non-vLLM, error and exit.
  local idx="$1"
  local port="$2"
  local cuda="$3"

  echo "[INFO] Probing port :${port} for an existing vLLM/OpenAI server (10s)..."
  if wait_for_ready "${port}" 10; then
    local name
    name="$(get_remote_model_name "${port}" || true)"
    if [[ -n "${name}" ]]; then
      echo "[INFO] Reusing running server on :${port} serving '${name}'."
      SERVED_MODEL_NAME="${name}"
    else
      echo "[WARN] Server on :${port} responded but model list was empty/unparseable; reusing anyway."
    fi
    STARTED_PIDS+=("")
    STARTED_LOGS+=("<external>")
    STARTED_PORTS+=("${port}")
    STARTED_FLAGS+=("existing")
    return 0
  fi

  # Not ready within 10s; check if port is free to launch our own
  if lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[ERROR] Port ${port} is occupied by a non-responsive or non-vLLM service. Stop it or change PORT." >&2
    exit 1
  fi

  echo "[INFO] No server detected on :${port} within 10s. Launching our vLLM and waiting up to 120s..."
  launch_replica "${idx}" "${port}" "${cuda}"
  if ! wait_for_ready "${port}" 120; then
    echo "[ERROR] vLLM on port ${port} did not become ready in 120s. Check logs: ${STARTED_LOGS[-1]}." >&2
    exit 1
  fi
  echo "[INFO] vLLM is ready on :${port}."
}

# ------------------------------
# Launch orchestration
# ------------------------------
STARTED_PIDS=()
STARTED_LOGS=()
STARTED_PORTS=()
STARTED_FLAGS=()  # "existing" or "launched"

# Cleanup all launched replicas on exit
cleanup() {
  local code=$?
  echo "[INFO] Cleaning up (exit code ${code})."
  for i in "${!STARTED_PIDS[@]}"; do
    local pid="${STARTED_PIDS[$i]}"
    local flag="${STARTED_FLAGS[$i]}"
    if [[ -n "${pid}" && "${flag}" == "launched" ]]; then
      if ps -p "${pid}" >/dev/null 2>&1; then
        echo "[INFO] Terminating vLLM process (PID=${pid})"
        kill "${pid}" >/dev/null 2>&1 || true
        sleep 1
        pkill -P "${pid}" >/dev/null 2>&1 || true
        if ps -p "${pid}" >/dev/null 2>&1; then
          kill -9 "${pid}" >/dev/null 2>&1 || true
        fi
      fi
    fi
  done
}
trap cleanup EXIT INT TERM ERR

# DP orchestration: apply "link in 10s else launch & wait 120s" to each replica port
if (( DP_SIZE == 1 )); then
  try_link_or_launch 0 "${PORT}" "${replica_cuda_devices[0]}"
else
  # First pass: probe existing servers or launch new ones (in parallel)
  echo "[INFO] Launching ${DP_SIZE} vLLM replicas in parallel..."
  for (( i=0; i<DP_SIZE; i++ )); do
    rport=$(( PORT + i ))
    cuda="${replica_cuda_devices[$i]}"
    
    echo "[INFO] Probing port :${rport} for an existing vLLM/OpenAI server (10s)..."
    if wait_for_ready "${rport}" 10; then
      name="$(get_remote_model_name "${rport}" || true)"
      if [[ -n "${name}" ]]; then
        echo "[INFO] Reusing running server on :${rport} serving '${name}'."
        SERVED_MODEL_NAME="${name}"
      else
        echo "[WARN] Server on :${rport} responded but model list was empty/unparseable; reusing anyway."
      fi
      STARTED_PIDS+=("")
      STARTED_LOGS+=("<external>")
      STARTED_PORTS+=("${rport}")
      STARTED_FLAGS+=("existing")
    else
      # Not ready within 10s; check if port is free to launch our own
      if lsof -iTCP:"${rport}" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "[ERROR] Port ${rport} is occupied by a non-responsive or non-vLLM service. Stop it or change PORT." >&2
        exit 1
      fi
      
      echo "[INFO] No server detected on :${rport}. Launching vLLM replica #${i} in background..."
      launch_replica "${i}" "${rport}" "${cuda}"
    fi
  done
  
  # Second pass: wait for all newly launched servers to become ready
  echo "[INFO] Waiting for all newly launched vLLM replicas to become ready (120s timeout each)..."
  for i in "${!STARTED_PORTS[@]}"; do
    prt="${STARTED_PORTS[$i]}"
    flag="${STARTED_FLAGS[$i]}"
    if [[ "${flag}" == "launched" ]]; then
      if ! wait_for_ready "${prt}" 120; then
        echo "[ERROR] vLLM on port ${prt} did not become ready in 120s. Check logs: ${STARTED_LOGS[$i]}." >&2
        exit 1
      fi
      echo "[INFO] vLLM is ready on :${prt}."
    fi
  done
fi

# ---------------------------------
# Build endpoint list and sharding
# ---------------------------------
ENDPOINTS=()
for prt in "${STARTED_PORTS[@]}"; do
  ENDPOINTS+=("http://127.0.0.1:${prt}")
done

# Export all endpoints for Ray script to handle load balancing
export VLLM_ENDPOINTS_CSV
VLLM_ENDPOINTS_CSV="$(IFS=','; echo "${ENDPOINTS[*]}")"

echo "[INFO] Active endpoints: ${VLLM_ENDPOINTS_CSV}"
echo "[INFO] Model served as: ${SERVED_MODEL_NAME}"
echo "[INFO] TP_SIZE=${TP_SIZE}, DP_SIZE=${DP_SIZE}, Total GPUs used=${TOTAL_GPUS_NEEDED}"

# ---------------------------------
# Run prompting_top_agent_ray.py
# ---------------------------------
echo "[INFO] Running prompting_top_agent_ray.py (testing all tasks)..."
echo "[INFO] Load balancing across ${DP_SIZE} vLLM replica(s) will be handled by Ray"

# Build thinking mode flag
THINKING_FLAG=""
if [[ "${ENABLE_THINKING}" == "true" ]]; then
  THINKING_FLAG="--enable_thinking"
  echo "[INFO] Thinking mode is enabled"
fi

# Build task numbers flag
TASK_NUMBERS_FLAG=""
if [[ -n "${TASK_NUMBERS}" ]]; then
  TASK_NUMBERS_FLAG="--task_numbers ${TASK_NUMBERS}"
  echo "[INFO] Processing specified tasks: ${TASK_NUMBERS}"
else
  echo "[INFO] Processing all tasks (1-156)"
fi

set -x
${PY} pro_v/prompting_top_agent_ray.py \
  --model "${SERVED_MODEL_NAME}" \
  --vllm_endpoints "${VLLM_ENDPOINTS_CSV}" \
  --provider vllm \
  --experiment_name "${EXPERIMENT_NAME}" \
  ${THINKING_FLAG} \
  ${TASK_NUMBERS_FLAG} \
  ${EXTRA_ARGS}
set +x

echo "[INFO] Evaluation finished."
