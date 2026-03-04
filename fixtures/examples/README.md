# Fixture 示例

本目录包含各种测试 fixture 示例，展示如何使用硬件测试平台。

## Fixture 文件结构

```json
{
  "fixture_name": "测试名称",
  "description": "测试描述",
  "cases": ["case 文件列表"],
  "execution": "sequential|parallel",
  "stop_on_failure": true|false,
  "loop": true|false,
  "loop_count": 循环次数，
  "loop_interval": 循环间隔 (秒),
  "retry": 重试次数，
  "retry_interval": 重试间隔 (秒),
  "report_enabled": true|false,
  "sn_required": true|false,
  "timeout": 超时时间 (秒)
}
```

## 可用示例

### Fixture 示例

| 文件 | 描述 | 适用场景 |
|------|------|----------|
| `smoke_test.json` | 冒烟测试 | 快速验证基本功能 |
| `full_hardware_test.json` | 完整硬件测试 | 全面测试所有硬件模块 |
| `stress_test.json` | 压力测试 | 多次循环验证稳定性 |

### Case 示例

| 文件 | 描述 | 测试模块 |
|------|------|----------|
| `i2c_case.json` | I2C 总线测试 | I2C |
| `usb_case.json` | USB 端口测试 | USB |
| `rtc_case.json` | RTC 时钟测试 | RTC |
| `gpio_case.json` | GPIO 引脚测试 | GPIO |
| `wifi_case.json` | WiFi 连接测试 | WiFi |

## 使用方法

### 1. 运行 Fixture

```bash
# 使用 fixtures 目录中的 fixture
python -m framework.cli.fixture_runner fixtures/examples/smoke_test.json

# 带详细输出
python -m framework.cli.fixture_runner fixtures/examples/full_hardware_test.json --verbose

# 指定 case 和 functions 目录
python -m framework.cli.fixture_runner fixtures/examples/smoke_test.json \
    --cases-dir cases \
    --functions-dir functions

# 覆盖循环次数
python -m framework.cli.fixture_runner fixtures/examples/stress_test.json --loop-count 5
```

### 2. 自定义 Fixture

复制示例并根据需要修改：

```bash
cp fixtures/examples/smoke_test.json fixtures/my_custom_test.json
```

然后编辑 `fixtures/my_custom_test.json` 调整参数。

### 3. 创建自定义 Case

参考 `cases/examples/` 目录中的示例创建新的测试用例。

## 参数说明

### Fixture 参数

- **fixture_name**: Fixture 名称
- **description**: 测试描述
- **cases**: 要执行的测试用例列表
- **execution**: 执行模式 (`sequential` 顺序执行 / `parallel` 并行执行)
- **stop_on_failure**: 失败时是否停止
- **loop**: 是否循环执行
- **loop_count**: 循环次数（loop=true 时有效）
- **loop_interval**: 循环间隔时间（秒）
- **retry**: 失败重试次数
- **retry_interval**: 重试间隔时间（秒）
- **report_enabled**: 是否生成报告
- **sn_required**: 是否需要序列号
- **timeout**: 超时时间（秒）

### Case 参数

- **case_name**: 用例名称
- **description**: 用例描述
- **module**: 测试模块名称
- **functions**: 要执行的测试函数列表
  - **name**: 函数名称
  - **params**: 函数参数
  - **enabled**: 是否启用
- **execution**: 执行模式
- **timeout**: 用例超时时间
- **retry**: 重试次数
- **retry_interval**: 重试间隔

## 示例场景

### 场景 1: 生产线快速测试

使用 `smoke_test.json`，只测试基本 connectivity：

```bash
python -m framework.cli.fixture_runner fixtures/examples/smoke_test.json
```

### 场景 2: 研发全面验证

使用 `full_hardware_test.json`，测试所有模块：

```bash
python -m framework.cli.fixture_runner fixtures/examples/full_hardware_test.json
```

### 场景 3: 稳定性验证

使用 `stress_test.json`，循环运行 10 次：

```bash
python -m framework.cli.fixture_runner fixtures/examples/stress_test.json
```

### 场景 4: 自定义测试

创建自己的 fixture：

```bash
# 1. 复制示例
cp fixtures/examples/smoke_test.json fixtures/my_custom_test.json

# 2. 编辑 fixtures/my_custom_test.json 添加需要的 cases

# 3. 运行
python -m framework.cli.fixture_runner fixtures/my_custom_test.json
```

## 注意事项

1. **路径配置**: case 文件路径相对于 cases 目录
2. **模块依赖**: 确保测试函数模块已实现
3. **超时设置**: 根据实际硬件调整超时时间
4. **重试策略**: 网络相关测试建议设置 retry >= 2
5. **硬件依赖**: GPIO、I2C、RTC 等测试需要真实硬件环境
6. **参数配置**: case 中的参数需要根据实际硬件配置调整（如 GPIO 引脚号、I2C 总线号等）
7. **WiFi 测试**: 需要配置实际的 SSID 和密码，默认禁用

## 预期测试结果

运行 `full_hardware_test.json` 时：
- **在没有真实硬件的环境中**：大部分硬件相关测试会失败（正常现象）
- **在真实硬件环境中**：根据硬件配置，相应测试会通过

示例输出：
```
Fixture: full_hardware_test
Status: PARTIAL
Duration: 37.94s
Passed: 4, Failed: 3
```
