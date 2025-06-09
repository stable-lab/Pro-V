lsof -i :30000
nohup python -m sglang.launch_server \
    --model-path deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
    --port 30000 \
    --host 0.0.0.0 \
    --mem-fraction-static 0.95 \
    --max-running-requests 8 \
    --max-prefill-tokens 4096 \
    --cuda-graph-max-bs 16 \
    --schedule-conservativeness 1.5 \
    --enable-mixed-chunk \
    --stream-interval 4 \
    > sglang.log 2>&1 &
nohup python generate.py > output.log 2>&1 &