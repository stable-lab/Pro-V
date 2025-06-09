# Pro-V: An Efficient Program Generation Multi-Agent System for Automatic RTL Verification

![DAC-overview](fig/iccad_pro_v.png)

## Overview

Pro-V is an advanced multi-agent system designed for automated RTL (Register Transfer Level) verification through intelligent program generation. The system leverages large language models (LLMs) to automatically generate testbenches, analyze circuit behavior, and verify RTL designs against specifications.

### Key Features
- **Automated Testbench Generation**: Generates comprehensive testbenches for both combinational and sequential circuits
- **Multi-Agent Architecture**: Integrates multiple specialized agents for different verification tasks
- **LLM Integration**: Supports multiple LLM providers (OpenAI, Anthropic, Google Vertex AI)
- **Circuit Type Classification**: Automatically classifies circuits as combinational (CMB) or sequential (SEQ)
- **Consistency Checking**: Validates consistency between RTL and Python reference models
- **Intelligent Refinement**: Iteratively improves generated code through feedback loops

## Core Components

### Main Generator (`src/generate.py`) 
The **primary entry point** and orchestrator of the entire verification flow:
- Configures the multi-agent system
- Manages the verification pipeline
- Coordinates between different specialized agents
- Handles circuit type classification and routing

### Key Modules

1. **TB_Generator** (`src/gen_tb.py`): Generates testbench stimulus for RTL designs
2. **JudgeForRTL** (`src/judge_for_RTL.py`): Analyzes and validates RTL implementations against specifications
3. **PyChecker/PyChecker_SEQ** (`src/pychecker.py`, `src/pychecker_seq.py`): Generates Python reference models for verification
4. **ConsistencyChecker** (`src/check_consistency.py`): Validates consistency between different implementations
5. **CircuitTypeClassifier** (`src/classify_circuit_type.py`): Automatically determines circuit type (CMB/SEQ)
6. **RefinePythonAgent** (`src/refine_python_agent.py`): Iteratively refines generated Python models

## Environment Setup

### 1. Repository Installation
```bash
git clone https://github.com/stable-lab/Pro-V.git
cd src

# Initialize submodules for benchmarks
git submodule update --init --recursive

# Create and activate conda environment
conda create -n pro-v python=3.11
conda activate pro-v

# Install Python dependencies
pip install -r requirements.txt
```

### 2. API Configuration
Create a `key.cfg` file in the project root with your API keys:

```ini
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
VERTEX_SERVICE_ACCOUNT_PATH=/path/to/your/service-account.json
VERTEX_REGION=your_vertex_region
```

Alternatively, set environment variables:
```bash
export OPENAI_API_KEY="your_key_here"
export ANTHROPIC_API_KEY="your_key_here"
```

### 3. Verilog Simulation Tools

#### Install Icarus Verilog (iverilog)

**Ubuntu/Debian:**
```bash
# Install dependencies
sudo apt install -y autoconf gperf make gcc g++ bison flex

# Install iverilog v12
git clone https://github.com/steveicarus/iverilog.git
cd iverilog
git checkout v12-branch
sh ./autoconf.sh
./configure
make -j4
sudo make install
```

**macOS:**
```bash
brew install icarus-verilog
```

**Verify Installation:**
```bash
iverilog -v
# Expected output: Icarus Verilog version 12.0 (stable) (v12_0)
```

#### Install Verilator

**Ubuntu/Debian:**
```bash
sudo apt install verilator
```

**macOS:**
```bash
brew install verilator
```

**From Source:**
```bash
git clone https://github.com/verilator/verilator
cd verilator
autoconf
export VERILATOR_ROOT=`pwd`
./configure
make -j4
sudo make install
```


### 4. Benchmark Setup
```bash
# The verilog-eval benchmark should be available as a submodule
# If not already initialized:
git submodule update --init --recursive

# Verify benchmark location
ls verilog-eval/
```



## Usage Guide

### Basic Usage
The main entry point is `src/generate.py`. Configure the parameters in the script:

```python
args_dict = {
    "model": "claude-3-5-sonnet-v2@20241022",
    "provider": "vertexanthropic",
    "temperature": 0,
    "top_p": 0.1,
    "max_token": 8192,
    "task_numbers": [150, 155, 156],  # Specific benchmark tasks
    "folder_path": "../verilog-eval/HDLBits/HDLBits_data_backup0304.jsonl",
    "run_identifier": "gen_tb",
    "key_cfg_path": "../key.cfg",
    "sampling_size": 5,
    "max_trials": 6,
    "stage": 0,  # 0: full pipeline, 1: skip some stages, 2: skip more stages
}
```

### Running the System
```bash
cd src
python generate.py
```

### Configuration Parameters

| Parameter | Description | Options |
|-----------|-------------|---------|
| `model` | LLM model to use | `gpt-4o-2024-08-06`, `claude-3-5-sonnet-v2@20241022`, etc. |
| `provider` | API provider | `openai`, `anthropic`, `vertexanthropic`, `sglang` |
| `task_numbers` | Specific benchmark tasks to run | List of integers |
| `circuit_type` | Circuit type (if not auto-detected) | `"CMB"`, `"SEQ"`, or `None` for auto-detection |
| `sampling_size` | Number of Python reference models to generate | Integer (default: 5) |
| `max_trials` | Maximum refinement iterations | Integer (default: 6) |
| `temperature` | LLM generation randomness | Float [0, 1] |
| `top_p` | LLM nucleus sampling parameter | Float [0, 1] |

### Output Structure
```
output_tb_gen_tb_<timestamp>/
├── <task_id>/
│   ├── spec.txt              # Problem specification
│   ├── module_header.txt     # RTL module header
│   ├── top.v                 # RTL implementation
│   ├── pychecker_*.py        # Generated Python reference models
│   ├── stimulus_*.json       # Generated test stimuli
│   └── logs/                 # Detailed execution logs
```

## Advanced Features

### Multi-Stage Pipeline
The system supports a multi-stage verification pipeline:
- **Stage 0**: Full pipeline including spec refinement, circuit classification, stimulus and python checker generation
- **Stage 1**: Skip spec refinement and circuit classification
- **Stage 2**: Skip spec refinement, circuit classification and stimuli generation.


### Circuit Type Support
- **Combinational Circuits (CMB)**: Logic gates, multiplexers, encoders, etc.
- **Sequential Circuits (SEQ)**: State machines, counters, memory elements, etc.

### LLM Provider Support
- **OpenAI**: GPT-4, GPT-4o models
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Haiku
- **Google Vertex AI**: Gemini models
- **SGLang**: Local model serving

## Development Guide

### Code Style
The project uses Python 3.11+ with type hints and follows PEP 8 standards.

### Adding New Agents
1. Create a new agent class in the `src/` directory
2. Implement the required interface methods
3. Add appropriate prompt templates in `utils/prompts.py`
4. Register the agent in the main `generate.py` orchestrator

### Testing
```bash
cd tests
python test_llm_chat.py      # Test LLM integration
python test_rtl_generator.py # Test RTL generation
python test_single_agent.py  # Test individual agents
```

### Logging
The system provides comprehensive logging through `utils/log_utils.py`:
- Execution traces
- Token usage statistics
- Error diagnostics
- Performance metrics

## Troubleshooting

### Common Issues

1. **iverilog version mismatch**: Ensure you have iverilog v12 installed
2. **API key errors**: Verify your `key.cfg` file format and permissions
3. **Memory issues**: Reduce `sampling_size` for large circuits
4. **Timeout errors**: Increase `max_token` or reduce problem complexity

### Performance Optimization
- Use local models with SGLang for faster iteration
- Implement caching for repeated operations
- Optimize prompt templates for specific circuit types

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with appropriate tests
4. Submit a pull request with detailed description

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Citation

If you use Pro-V in your research, please cite:

```bibtex
@article{pro-v-2024,
  title={Pro-V: An Efficient Program Generation Multi-Agent System for Automatic RTL Verification},
  author={[Authors]},
  journal={[Conference/Journal]},
  year={2024}
}
```
