"""
Base adapter interface for platform abstraction.

Defines the abstract interface that all platform adapters must implement.
This ensures consistent behavior across Linux, Zephyr, and other platforms.

平台适配器基础接口 - 所有平台适配器必须实现的抽象接口
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class CommandResult:
    """
    Result of a command execution.

    命令执行结果数据结构
    """

    def __init__(
        self,
        return_code: int,
        stdout: str = "",
        stderr: str = "",
        duration: float = 0.0,
    ):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration

    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.return_code == 0

    def __repr__(self) -> str:
        return (
            f"CommandResult(code={self.return_code}, "
            f"stdout_len={len(self.stdout)}, stderr_len={len(self.stderr)})"
        )


class BaseAdapter(ABC):
    """
    Abstract base class for platform adapters.

    平台适配器抽象基类 - 定义所有适配器必须实现的方法

    Platform adapters are responsible for:
    - Executing commands on the target platform
    - Collecting system logs
    - Detecting available devices

    平台适配器的职责：
    - 在目标平台上执行命令
    - 收集系统日志
    - 检测设备可用性
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the adapter.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._initialized = False

    @abstractmethod
    def detect_platform(self) -> str:
        """
        Detect the current platform type.

        Returns:
            Platform identifier string (e.g., "linux", "zephyr")

        检测当前平台类型
        返回值：平台标识字符串
        """
        pass

    @abstractmethod
    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        shell: bool = True,
    ) -> CommandResult:
        """
        Execute a command on the platform.

        Args:
            command: Command to execute
            timeout: Optional timeout in seconds
            shell: Whether to run in shell mode

        Returns:
            CommandResult with return code, stdout, stderr

        在平台上执行命令
        参数：
            command: 要执行的命令
            timeout: 超时时间（秒）
            shell: 是否在 shell 模式下运行
        返回值：
            包含返回码、标准输出、标准错误的 CommandResult
        """
        pass

    @abstractmethod
    def collect_syslog(self) -> str:
        """
        Collect system logs.

        Returns:
            System log content as string

        收集系统日志
        返回值：系统日志内容字符串
        """
        pass

    @abstractmethod
    def detect_devices(self) -> Dict[str, List[str]]:
        """
        Detect available devices on the platform.

        Returns:
            Dictionary mapping device type to list of device paths

        检测平台上的可用设备
        返回值：设备类型到设备路径列表的映射字典
        """
        pass

    def initialize(self) -> bool:
        """
        Initialize the adapter.

        Returns:
            True if initialization successful

        初始化适配器
        """
        self._initialized = True
        return True

    @property
    def is_initialized(self) -> bool:
        """Check if adapter is initialized."""
        return self._initialized
