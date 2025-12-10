#!/usr/bin/env bash
set -Eeo pipefail

########################################
# Config
########################################
GPU_IDS="2,3"
#MODEL_PATH="/home/nvidia/user/yujie/pychecker_rl/qwen_sft_output_pychecker/checkpoint-855"
#SERVED_MODEL_NAME="/home/nvidia/user/yujie/pychecker_rl/qwen_sft_output_pychecker/checkpoint-361"
MODEL_PATH="your model path"
SERVED_MODEL_NAME=${MODEL_PATH}
EXPERIMENT_NAME="qwen3_8b_non_think"
MAX_LEN=36000
PORT=8020
TP_SIZE=2
DP_SIZE=1
MAX_CONCURRENCY=50
TASK_NUMBERS=""
VLLM_EXTRA=""

# Sampling settings
TEMPERATURE=0
TOP_P=0.95
TEMPERATURE_SAMPLE=0
TOP_P_SAMPLE=0.95
MAX_TOKEN=20000
ENABLE_THINKING=true
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

export TEMPERATURE TOP_P TEMPERATURE_SAMPLE TOP_P_SAMPLE MAX_TOKEN \
       ENABLE_THINKING FOLDER_PATH RUN_IDENTIFIER KEY_CFG_PATH USE_GOLDEN_REF \
       SAMPLING_SIZE STIMULI_SAMPLING_SIZE MAX_TRIALS STAGE DAY DUT FILTER_INSTANCE

########################################
# Setup
########################################
PY=$(command -v python3 || command -v python)
[[ -z "$PY" ]] && { echo "[ERROR] Python not found"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CHAT_TEMPLATE="${REPO_ROOT}/qwen3_nonthinking.jinja"
LOG_FILE="${REPO_ROOT}/vllm_${PORT}.log"

IFS=',' read -r -a GPU_ARR <<< "${GPU_IDS}"
TOTAL_GPUS_NEEDED=$((TP_SIZE * DP_SIZE))
[[ ${#GPU_ARR[@]} -lt $TOTAL_GPUS_NEEDED ]] && { echo "[ERROR] Not enough GPUs"; exit 1; }
SELECTED_GPUS=("${GPU_ARR[@]:0:TOTAL_GPUS_NEEDED}")
CUDA_DEVICES=$(IFS=','; echo "${SELECTED_GPUS[*]}")

########################################
# Global variables
########################################
VLLM_PID=""
PYTHON_PID=""
CLEANUP_DONE=false

########################################
# Cleanup handler
########################################
cleanup() {
  $CLEANUP_DONE && return
  CLEANUP_DONE=true
  
  echo ""
  echo "[INFO] Cleaning up..."
  
  [[ -n "$PYTHON_PID" ]] && kill -9 $PYTHON_PID 2>/dev/null || true
  [[ -n "$VLLM_PID" ]] && {
    echo "[INFO] Stopping vLLM (PID=$VLLM_PID)"
    pkill -9 -P $VLLM_PID 2>/dev/null || true
    kill -9 $VLLM_PID 2>/dev/null || true
  }
  
  echo "[INFO] Cleanup done"
}

trap 'echo "[INFO] Interrupted"; cleanup; exit 130' INT
trap 'cleanup' EXIT

########################################
# Check for existing vLLM (3s timeout)
########################################
echo "[INFO] Checking for vLLM on port $PORT (3s)..."
VLLM_EXISTS=false

for i in {1..3}; do
  if curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
    echo "[INFO] Found existing vLLM on port $PORT"
    VLLM_EXISTS=true
    break
  fi
  sleep 1
done

########################################
# Launch vLLM if not found
########################################
if ! $VLLM_EXISTS; then
  echo "[INFO] No vLLM found. Starting vLLM..."
  echo "[INFO] Model: $MODEL_PATH"
  echo "[INFO] GPUs: $GPU_IDS (TP=$TP_SIZE)"
  echo "[INFO] Max length: $MAX_LEN"
  echo "[INFO] Port: $PORT"
  echo "-----------------------------------"
  
  (
    set -x
    CUDA_VISIBLE_DEVICES="${CUDA_DEVICES}" \
    ${PY} -m vllm.entrypoints.openai.api_server \
      --model "${MODEL_PATH}" \
      --served-model-name "${SERVED_MODEL_NAME}" \
      --tensor-parallel-size "${TP_SIZE}" \
      --max-model-len "${MAX_LEN}" \
      --port "${PORT}" \
      --chat-template "${CHAT_TEMPLATE}" \
      ${VLLM_EXTRA} \
      >"${LOG_FILE}" 2>&1
  ) &
  VLLM_PID=$!
  echo ""
  echo "[INFO] vLLM started (PID=$VLLM_PID)"
  
  # Wait for vLLM to be ready (120s timeout)
  echo "[INFO] Waiting for vLLM to be ready..."
  for i in {1..120}; do
    if curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
      echo "[INFO] vLLM is ready!"
      break
    fi
    [[ $i -eq 120 ]] && { echo "[ERROR] vLLM timeout. Check vllm_$PORT.log"; exit 1; }
    sleep 1
  done
fi

########################################
# Run evaluation
########################################
echo "-----------------------------------"
echo "[INFO] Starting evaluation..."
echo "[INFO] Experiment: $EXPERIMENT_NAME"
echo "[INFO] Concurrency: $MAX_CONCURRENCY"
[[ -n "$TASK_NUMBERS" ]] && echo "[INFO] Tasks: $TASK_NUMBERS" || echo "[INFO] Tasks: ALL"
echo "-----------------------------------"

VLLM_ENDPOINTS_CSV="http://127.0.0.1:${PORT}"
export VLLM_ENDPOINTS_CSV
$PY pro_v/prompting_top_agent_simple.py \
  --model "$SERVED_MODEL_NAME" \
  --vllm_endpoints "$VLLM_ENDPOINTS_CSV" \
  --experiment_name "$EXPERIMENT_NAME" \
  --max_concurrency $MAX_CONCURRENCY \
  ${TASK_NUMBERS:+--task_numbers $TASK_NUMBERS} &

PYTHON_PID=$!
wait $PYTHON_PID 2>/dev/null || true


echo ""
echo "[INFO] Main evaluation finished"

########################################
# Run evaluate2 - Mutant Detection
########################################


echo ""
echo "[INFO] Mutant detection evaluation completed. Report saved to: ${EVAL2_REPORT_FILE}"
echo "[INFO] All evaluations finished"
