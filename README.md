# Hardware Test Platform

嵌入式测试通用软件框架 - Embedded Testing Framework for Seeed Hardware Platforms

## Overview

A unified testing framework for Seeed's mainstream hardware platforms (Nordic, ESP, CM4/CM5, RK, Jetson, TI, etc.). Provides standardized commands and status codes for EE/TE to perform hardware testing without deep software knowledge.

统一 Seeed 主流硬件平台（Nordic、ESP、CM4/CM5、RK、Jetson、TI）的测试调用方式，提供标准化命令与状态码，降低 EE/TE 使用门槛。

## Features

- **Three-Layer Architecture**: Functions → Cases → Fixtures for high reusability
- **Standardized Status Codes**: Consistent error handling across all tests
- **Multi-Platform Support**: Linux (SOC) and Zephyr (MCU) adapters
- **Real-Time Dashboard**: CLI-based monitoring with rich library
- **Four-Level Output**: Terminal, logs, tmp results, and reports

## Quick Start

### 1. Setup Environment

```bash
# Clone repository
git clone <repository-url>
cd hardware_test_platform

# Run setup script
./setup_env.sh

# Activate virtual environment
source venv/bin/activate
```

### 2. Run Tests

```bash
# List available fixtures
./bin/run_fixture --list

# Run a fixture
./bin/run_fixture --name quick_functional_test

# Run with serial number (production testing)
./bin/run_fixture --name production_full_test --sn SN12345

# Run a single case
./bin/run_case --config cases/eth_case.json
```

### 3. View Dashboard

```bash
# Start CLI dashboard
python3 -m framework.dashboard --fixture network_test
```

## Architecture

```
┌──────────────────────────────────────────┐
│           Interface Layer                │
│  CLI/API (run_fixture, run_case)         │
├──────────────────────────────────────────┤
│            Orchestration Layer           │
│  Fixture Runner / Case Runner / Scheduler│
├──────────────────────────────────────────┤
│             Test Logic Layer             │
│  Functions + Case orchestration          │
├──────────────────────────────────────────┤
│          Platform Adapter Layer          │
│  LinuxAdapter / ZephyrAdapter            │
├──────────────────────────────────────────┤
│           Output & Observability         │
│  terminal + logs + tmp + reports         │
└──────────────────────────────────────────┘
```

## Directory Structure

```
hardware_test_platform/
├── bin/                    # CLI entry points
│   ├── run_fixture
│   ├── run_case
│   └── setup_env.sh
├── framework/
│   ├── core/               # Core engine
│   │   ├── status_codes.py
│   │   ├── function_runner.py
│   │   ├── case_runner.py
│   │   ├── fixture_runner.py
│   │   ├── scheduler.py
│   │   └── result_store.py
│   ├── platform/           # Platform adapters
│   │   ├── base_adapter.py
│   │   └── linux_adapter.py
│   ├── logging/            # Logging system
│   │   └── logger.py
│   └── dashboard/          # CLI dashboard
│       └── cli_dashboard.py
├── functions/              # Test functions
│   ├── network/
│   │   └── test_eth.py
│   ├── uart/
│   │   └── test_uart.py
│   └── ...
├── cases/                  # Case configurations
│   ├── eth_case.json
│   └── ...
├── fixtures/               # Fixture configurations
│   ├── network_test.json
│   ├── production_full_test.json
│   └── quick_functional_test.json
├── config/                 # Global configurations
│   └── global_config.json
├── logs/                   # Log files (auto-created)
├── tmp/                    # Intermediate results (auto-created)
└── reports/                # Test reports (auto-created)
```

## Status Codes

| Code | Description | Chinese |
|------|-------------|---------|
| 0 | Success | 测试成功 |
| 1 | Timeout | 超时 |
| 2 | Missing parameter | 缺少参数 |
| -1 | Test failed | 测试失败 |
| -2 | Environment/dependency missing | 缺少环境/依赖 |
| -101 | Device not found | 找不到设备 |
| -102 | Device error | 设备异常 |
| -103 | File not found | 未找到文件 |

## Configuration

### Global Config (`config/global_config.json`)

```json
{
  "product": {
    "sku": "CM4",
    "stage": "DVT",
    "default_sn_for_test": "DVT",
    "engineer": "TBD"
  },
  "runtime": {
    "default_retry": 2,
    "default_retry_interval": 5,
    "default_timeout": 60
  }
}
```

### Case Config (`cases/*.json`)

```json
{
  "case_name": "Ethernet Module Test",
  "module": "eth",
  "functions": [
    {
      "name": "test_eth",
      "params": {"ip": "192.168.1.1"},
      "enabled": true
    }
  ],
  "execution": "sequential",
  "timeout": 60
}
```

### Fixture Config (`fixtures/*.json`)

```json
{
  "fixture_name": "quick_functional_test",
  "cases": ["cases/eth_case.json"],
  "execution": "sequential",
  "stop_on_failure": false,
  "retry": 1
}
```

## Development

### Adding a New Test Function

1. Create function in `functions/<module>/test_<name>.py`
2. Implement function with standard signature
3. Return dict with `code`, `message`, `details`

```python
from framework.core.status_codes import StatusCode

def test_my_feature(param1: str) -> dict:
    """Test my feature."""
    # Implementation
    return {
        "code": StatusCode.SUCCESS,
        "message": "Test passed",
        "details": {"param1": param1}
    }
```

### Adding a New Case

1. Create `cases/<module>_case.json`
2. Define functions to run
3. Test with `./bin/run_case --config cases/<module>_case.json`

### Adding a New Fixture

1. Create `fixtures/<scenario>.json`
2. Combine existing cases
3. Run with `./bin/run_fixture --name <scenario>`

## Requirements

- Python 3.8+
- Linux environment (for Linux platform testing)
- Optional: pyserial for UART testing

## License

MIT License

## Contributing

1. Follow Google-style code comments (bilingual EN/CN)
2. Add README for new functions
3. Test with existing fixtures before submitting
