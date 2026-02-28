#!/bin/bash
#
# Setup Environment Script for Hardware Test Platform
#
# This script sets up the Python environment and installs dependencies.
# Run this script once to prepare the test environment.
#
# Usage:
#     ./setup_env.sh
#
# 硬件测试平台环境部署脚本
# 一次性运行此脚本来准备测试环境

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "Hardware Test Platform - Setup Environment"
echo "硬件测试平台 - 环境部署"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check Python version
print_info "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    print_info "Python version: $PYTHON_VERSION"

    # Check if Python >= 3.8
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
        print_error "Python 3.8+ required, found $PYTHON_VERSION"
        exit 1
    fi
else
    print_error "Python 3 not found. Please install Python 3.8+"
    exit 1
fi

# Check for pip
print_info "Checking pip..."
if ! command -v pip3 &> /dev/null; then
    print_error "pip3 not found. Please install pip."
    exit 1
fi

# Create virtual environment
print_info "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_info "Virtual environment created at ./venv"
else
    print_info "Virtual environment already exists at ./venv"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
print_info "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
print_info "Installing dependencies from requirements.txt..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    print_info "Dependencies installed successfully"
else
    print_warning "requirements.txt not found"
fi

# Create required directories
print_info "Creating required directories..."
mkdir -p logs tmp reports config

# Set permissions
print_info "Setting permissions..."
chmod +x bin/run_fixture bin/run_case 2>/dev/null || true

# Verify installation
print_info "Verifying installation..."
python3 -c "import rich; import psutil; print('  - rich: OK')" 2>/dev/null || print_warning "  - rich: not installed"
python3 -c "import psutil; print('  - psutil: OK')" 2>/dev/null || print_warning "  - psutil: not installed"

# Print summary
echo ""
echo "========================================"
echo "Setup Complete!"
echo "环境部署完成!"
echo "========================================"
echo ""
echo "Usage:"
echo "  1. Activate virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Run fixtures:"
echo "     ./bin/run_fixture --name 功能快速验证"
echo ""
echo "  3. List available fixtures:"
echo "     ./bin/run_fixture --list"
echo ""
echo "========================================"
