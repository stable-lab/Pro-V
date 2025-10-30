#!/bin/bash

# Pro-V Environment Setup Script
# This script sets up a Python virtual environment and installs all dependencies

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

# Check Python version
print_info "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    print_error "Python3 not found, please install Python 3.11 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | grep -oP '\d+\.\d+')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    print_warning "Recommended Python 3.11 or higher, current version: $PYTHON_VERSION"
    print_warning "Note: Python 3.13+ may have compatibility issues with some packages"
else
    print_success "Python version check passed: $PYTHON_VERSION"
fi

# Create virtual environment
VENV_DIR="pro_v_venv"
print_info "Creating virtual environment: $VENV_DIR"

if [ -d "$VENV_DIR" ]; then
    print_warning "Virtual environment already exists, delete and recreate? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
        print_info "Removed old virtual environment"
    else
        print_info "Using existing virtual environment"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    print_success "Virtual environment created successfully"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Check for build tools
print_info "Checking for build tools..."
BUILD_TOOLS_OK=true

# Check for pkg-config
if ! command -v pkg-config &> /dev/null; then
    print_warning "pkg-config not found (needed for finding system libraries)"
    BUILD_TOOLS_OK=false
else
    print_success "pkg-config found"
fi

# Check for gcc/compiler
if ! command -v gcc &> /dev/null && ! command -v clang &> /dev/null; then
    print_warning "C compiler (gcc/clang) not found"
    BUILD_TOOLS_OK=false
else
    print_success "C compiler found"
fi

# Check for Rust compiler (needed for some packages like outlines-core)
if command -v rustc &> /dev/null; then
    RUST_VERSION=$(rustc --version)
    print_success "Rust compiler found: $RUST_VERSION"
else
    print_warning "Rust compiler not found (needed for building outlines-core)"
    BUILD_TOOLS_OK=false
fi

if [ "$BUILD_TOOLS_OK" = false ]; then
    print_warning "Some build tools are missing!"
    print_info "To install all required build tools:"
    echo ""
    echo "  Ubuntu/Debian:"
    echo "    sudo apt-get update"
    echo "    sudo apt-get install -y build-essential pkg-config libssl-dev"
    echo ""
    echo "  Fedora/RHEL:"
    echo "    sudo yum groupinstall -y 'Development Tools'"
    echo "    sudo yum install -y pkg-config openssl-devel"
    echo ""
    echo "  For Rust compiler:"
    echo "    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
    echo "    source \$HOME/.cargo/env"
    echo ""
    print_warning "Continue anyway? Installation may fail for some packages. (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for OpenSSL and set up environment
print_info "Checking for OpenSSL..."
OPENSSL_FOUND=false

# Method 1: Check for system OpenSSL development libraries
if pkg-config --exists openssl 2>/dev/null; then
    print_success "System OpenSSL found via pkg-config"
    export PKG_CONFIG_PATH="$(pkg-config --variable pc_path pkg-config)"
    OPENSSL_FOUND=true
elif [ -f "/usr/include/openssl/ssl.h" ]; then
    print_success "System OpenSSL headers found"
    OPENSSL_FOUND=true
fi

# Method 2: Check for conda OpenSSL
if command -v conda &> /dev/null; then
    print_info "Conda found, setting up OpenSSL environment..."
    
    # Try to install OpenSSL via conda
    if conda install -c conda-forge openssl -y 2>/dev/null; then
        print_success "OpenSSL installed via conda"
        
        # Set environment variables for conda OpenSSL
        CONDA_PREFIX=$(conda info --base)
        if [ -d "$CONDA_PREFIX/include/openssl" ]; then
            export OPENSSL_DIR="$CONDA_PREFIX"
            export OPENSSL_INCLUDE_DIR="$CONDA_PREFIX/include"
            export OPENSSL_LIB_DIR="$CONDA_PREFIX/lib"
            export PKG_CONFIG_PATH="$CONDA_PREFIX/lib/pkgconfig:$PKG_CONFIG_PATH"
            export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
            print_success "OpenSSL environment variables set"
            OPENSSL_FOUND=true
        fi
    else
        print_warning "OpenSSL installation via conda failed"
    fi
fi

# Warn if OpenSSL not found
if [ "$OPENSSL_FOUND" = false ]; then
    print_warning "OpenSSL development libraries not found!"
    print_info "Some packages may fail to install. To fix this:"
    echo ""
    echo "  Ubuntu/Debian:"
    echo "    sudo apt-get update"
    echo "    sudo apt-get install -y libssl-dev pkg-config"
    echo ""
    echo "  Fedora/RHEL:"
    echo "    sudo yum install -y openssl-devel pkg-config"
    echo ""
    echo "  Or use conda:"
    echo "    conda install -c conda-forge openssl pkg-config"
    echo ""
    print_warning "Press Enter to continue anyway, or Ctrl+C to abort and install OpenSSL..."
    read -r
fi

# Upgrade pip
print_info "Upgrading pip..."
pip install --upgrade pip wheel

# Install Python dependencies in stages with better error handling
print_info "Installing core dependencies..."
if ! pip install anthropic openai tiktoken pydantic configparser jinja2 ply python-dateutil rich; then
    print_error "Core dependencies installation failed"
    exit 1
fi

print_info "Installing LlamaIndex dependencies..."
if ! pip install llama-index-core llama-index-llms-anthropic llama-index-llms-openai llama-index-llms-vertex llama-index; then
    print_warning "LlamaIndex installation had issues, but continuing..."
fi

print_info "Installing Google Cloud dependencies..."
if ! pip install google-auth google-auth-oauthlib google-cloud-aiplatform; then
    print_warning "Google Cloud dependencies had issues, but continuing..."
fi

print_info "Installing cocotb..."
if ! pip install cocotb; then
    print_warning "Cocotb installation failed, but continuing..."
fi

print_info "Installing Ray..."
if ! pip install 'ray[default]'; then
    print_error "Ray installation failed"
    exit 1
fi

print_info "Installing vLLM and related dependencies (this may take several minutes)..."
print_info "This step requires Rust compiler and OpenSSL development libraries..."

# Try to install outlines-core first (the package that was failing)
if pip install outlines-core --no-build-isolation 2>/dev/null; then
    print_success "outlines-core installed successfully"
elif pip install outlines-core 2>/dev/null; then
    print_success "outlines-core installed successfully"
else
    print_warning "outlines-core installation failed, trying alternative approach..."
fi

# Now try vLLM
VLLM_INSTALLED=false
if pip install vllm; then
    print_success "vLLM installed successfully"
    VLLM_INSTALLED=true
elif pip install vllm --no-build-isolation 2>/dev/null; then
    print_success "vLLM installed with --no-build-isolation"
    VLLM_INSTALLED=true
else
    print_error "vLLM installation failed!"
    print_info "This usually happens due to missing dependencies. To fix:"
    echo ""
    echo "  1. Install OpenSSL development libraries:"
    echo "     Ubuntu/Debian: sudo apt-get install -y libssl-dev pkg-config build-essential"
    echo "     Fedora/RHEL:   sudo yum install -y openssl-devel pkg-config gcc gcc-c++"
    echo ""
    echo "  2. Install Rust compiler if not present:"
    echo "     curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo ""
    echo "  3. Then re-run this script"
    echo ""
    print_warning "Continue without vLLM? (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

if [ "$VLLM_INSTALLED" = true ]; then
    print_success "All Python dependencies installed successfully"
else
    print_warning "Installation completed but vLLM is not available"
fi

# Install Pro-V package in editable mode
print_info "Installing Pro-V package in editable mode..."
if [ -f "setup.py" ]; then
    pip install -e .
    print_success "Pro-V package installed successfully (editable mode)"
else
    print_warning "setup.py not found, skipping installation"
fi

# Add PRO-V directory to PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
print_info "Added $PROJECT_ROOT to PYTHONPATH"

# Check if Pyverilog is installed, if not, provide instructions
if ! python -c "import pyverilog" &> /dev/null; then
    print_warning "Pyverilog not installed (optional for some features)"
    print_info "To install Pyverilog manually:"
    echo "    git clone https://github.com/PyHDI/Pyverilog.git"
    echo "    cd Pyverilog && python setup.py install --user && cd .."
fi

# Check for verilator (required for simulation)
print_info "Checking Verilator..."
if command -v verilator &> /dev/null; then
    VERILATOR_VERSION=$(verilator --version | head -n1)
    print_success "Verilator installed: $VERILATOR_VERSION"
else
    print_warning "Verilator not installed (required for simulation)"
    print_info "To install Verilator without sudo:"
    echo "    git clone https://github.com/verilator/verilator"
    echo "    cd verilator && git checkout stable"
    echo "    autoconf && ./configure --prefix=\$HOME/.local"
    echo "    make -j\$(nproc) && make install"
    echo "    export PATH=\$HOME/.local/bin:\$PATH  # Add to ~/.bashrc"
    echo ""
    print_info "Or use package manager if available:"
    echo "    Ubuntu/Debian: apt install verilator"
    echo "    macOS: brew install verilator"
fi

# Check for key.cfg
print_info "Checking configuration file..."
if [ ! -f "key.cfg" ]; then
    print_warning "key.cfg file not found"
    print_info "Please create key.cfg file and add API keys:"
    echo ""
    echo "    OPENAI_API_KEY='your_openai_key'"
    echo "    ANTHROPIC_API_KEY='your_anthropic_key'"
    echo "    VERTEX_SERVICE_ACCOUNT_PATH='path_to_service_account.json'"
    echo "    VERTEX_REGION='us-central1'"
    echo ""
else
    print_success "Found configuration file key.cfg"
fi

# Print summary
echo ""
print_success "========================================="
print_success "Pro-V setup completed!"
print_success "========================================="
echo ""
print_info "To activate the environment (recommended):"
echo "    source ./activate.sh"
echo ""
print_info "Or activate manually:"
echo "    source $PROJECT_ROOT/pro_v_venv/bin/activate"
echo "    export PYTHONPATH=\"$PROJECT_ROOT:\$PYTHONPATH\""
echo ""
print_info "To run Pro-V:"
echo "    cd $PROJECT_ROOT"
echo "    source ./activate.sh  # If not already activated"
echo "    python PRO-V/prompting_top_agent_ray.py"
echo ""
print_info "To deactivate:"
echo "    deactivate"
echo ""

# Update activation helper script
cat > "$PROJECT_ROOT/activate.sh" << 'EOF'
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
EOF
chmod +x "$PROJECT_ROOT/activate.sh"
print_success "Created: source pro_v_venv/bin/activate"

