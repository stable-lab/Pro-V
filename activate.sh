#!/bin/bash
# Pro-V Environment Activation Script
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment
source "$PROJECT_ROOT/pro_v_venv/bin/activate"

# Set PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Load Rust environment if available
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
fi

# Set OpenSSL environment for conda if available
if command -v conda &> /dev/null; then
    CONDA_PREFIX=$(conda info --base 2>/dev/null)
    if [ -n "$CONDA_PREFIX" ] && [ -d "$CONDA_PREFIX/include/openssl" ]; then
        export OPENSSL_DIR="$CONDA_PREFIX"
        export OPENSSL_INCLUDE_DIR="$CONDA_PREFIX/include"
        export OPENSSL_LIB_DIR="$CONDA_PREFIX/lib"
        export PKG_CONFIG_PATH="$CONDA_PREFIX/lib/pkgconfig:$PKG_CONFIG_PATH"
        export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
    fi
fi

echo "Pro-V virtual environment activated"
echo "PYTHONPATH: $PROJECT_ROOT"
