# Hardware Test Platform - Development Guide

## Project Overview

This is an embedded testing framework for Seeed's hardware platforms. It provides a three-layer architecture (Functions → Cases → Fixtures) for reusable and maintainable hardware tests.

## Quick Commands

```bash
# Setup environment
./setup_env.sh

# Activate virtual environment
source venv/bin/activate

# Run tests
./bin/run_fixture --name 功能快速验证
./bin/run_case --config cases/eth_case.json

# List available fixtures
./bin/run_fixture --list
```

## Architecture

### Core Layers

1. **Interface Layer** (`bin/`)
   - `run_fixture` - Execute test fixtures
   - `run_case` - Execute test cases

2. **Orchestration Layer** (`framework/core/`)
   - `FunctionRunner` - Execute individual test functions
   - `CaseRunner` - Execute case configurations
   - `FixtureRunner` - Execute fixture scenarios
   - `Scheduler` - Handle parallel/sequential execution

3. **Platform Layer** (`framework/platform/`)
   - `LinuxAdapter` - Linux platform commands
   - `BaseAdapter` - Abstract interface

4. **Output Layer** (`framework/logging/`, `framework/dashboard/`)
   - `Logger` - 3-level debug logging
   - `CLIDashboard` - Real-time terminal display

### Key Data Flow

```
Fixture Config (JSON)
    ↓
FixtureRunner → Scheduler → CaseRunner
    ↓                      ↓
Functions (Python)    ResultStore (tmp/)
    ↓                      ↓
Status Codes          Dashboard reads JSON
```

## Adding New Components

### New Test Function

1. Create file in `functions/<module>/test_<name>.py`
2. Implement function returning `Dict[str, Any]`:

```python
from framework.core.status_codes import StatusCode

def test_my_feature(param1: str) -> dict:
    """Test my feature with description."""
    try:
        # Implementation
        return {
            "code": StatusCode.SUCCESS,
            "message": "Test passed",
            "duration": 1.5,
            "details": {"param1": param1}
        }
    except Exception as e:
        return {
            "code": StatusCode.FAILED,
            "message": str(e),
        }
```

3. Add to module `__init__.py`
4. Create case config in `cases/`

### New Case Configuration

```json
{
  "case_name": "My Module Test",
  "description": "Test my module",
  "module": "mymodule",
  "functions": [
    {
      "name": "test_my_feature",
      "params": {"param1": "value"},
      "enabled": true
    }
  ],
  "execution": "sequential",
  "timeout": 60,
  "retry": 2,
  "retry_interval": 5
}
```

### New Fixture Configuration

```json
{
  "fixture_name": "My Scenario",
  "description": "Description here",
  "cases": ["cases/my_module_case.json"],
  "execution": "sequential",
  "stop_on_failure": false,
  "loop": false,
  "retry": 1
}
```

## Status Codes Reference

| Code | Use Case |
|------|----------|
| 0 | Success |
| 1 | Timeout |
| 2 | Missing parameter |
| -1 | General failure |
| -2 | Missing dependency |
| -101 | Device not found |
| -102 | Device error |
| -103 | File not found |

## Development Patterns

### Logging

```python
from framework.logging.logger import Logger

logger = Logger("my_module", level=Logger.LEVEL_BASIC)

logger.info("Starting test")
logger.debug("Debug info", level=2, value=42)
logger.error("Error occurred")
```

### Result Storage

```python
from framework.core.result_store import ResultStore, TestResult

store = ResultStore()

# Write running status
store.write_running_status("eth", "Ethernet Test")

# Write success
store.write_success(
    module="eth",
    case_name="Ethernet Test",
    duration=2.5,
    details={"latency_ms": 10}
)

# Write failure
store.write_failure(
    module="eth",
    case_name="Ethernet Test",
    duration=2.5,
    error="Connection timeout",
    retry_count=1
)
```

### Platform Adapter

```python
from framework.platform.linux_adapter import LinuxAdapter

adapter = LinuxAdapter()
adapter.detect_platform()  # Returns "linux"

result = adapter.execute("ping -c 4 8.8.8.8")
if result.success:
    print(result.stdout)

syslog = adapter.collect_syslog()
devices = adapter.detect_devices()
```

## Testing Checklist

Before committing changes:

- [ ] Function returns proper status codes
- [ ] Error handling covers edge cases
- [ ] Logging at appropriate levels
- [ ] Result written to tmp/ for dashboard
- [ ] Configuration files are valid JSON
- [ ] Bilingual comments (EN/CN) for public APIs

## Common Issues

### pyserial not installed

```bash
source venv/bin/activate
pip install pyserial
```

### Permission denied for serial port

```bash
sudo usermod -a -G dialout $USER
# Log out and back in
```

### Dashboard not updating

Check that tmp/ directory exists and result files are being written:

```bash
ls -la tmp/
cat tmp/*_result.json
```

## Project Structure

```
hardware_test_platform/
├── bin/                      # CLI entry points
├── framework/
│   ├── core/                 # Execution engine
│   ├── platform/             # Hardware adapters
│   ├── logging/              # Logging system
│   └── dashboard/            # CLI dashboard
├── functions/                # Test implementations
├── cases/                    # Case JSON configs
├── fixtures/                 # Fixture JSON configs
├── config/                   # Global configs
├── tools/                    # Utility scripts
├── logs/                     # Log output
├── tmp/                      # Intermediate results
└── reports/                  # Test reports
```

## Design Principles

1. **Configuration-Driven**: Behavior controlled by JSON configs
2. **State-Driven**: Results written to tmp/ for dashboard
3. **Single Responsibility**: Each module has one purpose
4. **Extensible**: New tests require no core changes
5. **Bilingual**: Comments and docs in EN/CN
