"""
Status codes for test results.

Standardized status codes for all test functions to ensure consistent
error handling and reporting across the framework.

状态码定义 - 所有测试函数的统一返回值标准
"""

from enum import IntEnum


class StatusCode(IntEnum):
    """
    Standard status codes for test results.

    测试状态码枚举类 - 用于统一标识测试结果的各类状态

    Status Code Reference:
    - 0: Success - 测试成功
    - 1: Timeout - 超时
    - 2: Missing parameter - 缺少参数
    - -1: Test failed - 测试失败
    - -101: Device not found - 找不到设备
    - -102: Device error - 设备异常
    - -103: File not found - 未找到指定路径文件
    - -2: Environment missing - 缺少环境/依赖包
    """

    # Success codes
    SUCCESS = 0               # 测试成功 - Test completed successfully

    # Error codes (positive - user errors)
    TIMEOUT = 1               # 超时 - Operation timed out
    MISSING_PARAM = 2         # 缺少参数 - Missing required parameter

    # Error codes (negative - system errors)
    FAILED = -1               # 测试失败 - Test failed, conditions not met
    ENV_MISSING = -2          # 缺少环境/依赖包 - Missing environment or dependency

    # Device specific errors
    DEVICE_NOT_FOUND = -101   # 找不到设备 - Device not found
    DEVICE_ERROR = -102       # 设备异常 - Device error or exception
    FILE_NOT_FOUND = -103     # 未找到指定路径文件 - Specified file not found

    @classmethod
    def is_success(cls, code: int) -> bool:
        """Check if status code indicates success."""
        return code == cls.SUCCESS

    @classmethod
    def is_error(cls, code: int) -> bool:
        """Check if status code indicates any error."""
        return code != cls.SUCCESS

    @classmethod
    def is_retryable(cls, code: int) -> bool:
        """
        Check if the error is retryable.

        Retryable errors: timeout, device error
        Non-retryable errors: missing param, device not found
        """
        retryable_codes = {
            cls.TIMEOUT,
            cls.DEVICE_ERROR,
        }
        return code in retryable_codes

    @property
    def description(self) -> str:
        """Get human-readable description of status code."""
        descriptions = {
            self.SUCCESS: "Success",
            self.TIMEOUT: "Timeout",
            self.MISSING_PARAM: "Missing parameter",
            self.FAILED: "Test failed",
            self.ENV_MISSING: "Environment/dependency missing",
            self.DEVICE_NOT_FOUND: "Device not found",
            self.DEVICE_ERROR: "Device error",
            self.FILE_NOT_FOUND: "File not found",
        }
        return descriptions.get(self, f"Unknown status code: {self}")

    @property
    def description_zh(self) -> str:
        """Get Chinese description of status code."""
        descriptions = {
            self.SUCCESS: "测试成功",
            self.TIMEOUT: "超时",
            self.MISSING_PARAM: "缺少参数",
            self.FAILED: "测试失败",
            self.ENV_MISSING: "缺少环境/依赖",
            self.DEVICE_NOT_FOUND: "找不到设备",
            self.DEVICE_ERROR: "设备异常",
            self.FILE_NOT_FOUND: "未找到文件",
        }
        return descriptions.get(self, f"未知状态码：{self}")


# Convenience constants
SUCCESS = StatusCode.SUCCESS
TIMEOUT = StatusCode.TIMEOUT
MISSING_PARAM = StatusCode.MISSING_PARAM
FAILED = StatusCode.FAILED
ENV_MISSING = StatusCode.ENV_MISSING
DEVICE_NOT_FOUND = StatusCode.DEVICE_NOT_FOUND
DEVICE_ERROR = StatusCode.DEVICE_ERROR
FILE_NOT_FOUND = StatusCode.FILE_NOT_FOUND
