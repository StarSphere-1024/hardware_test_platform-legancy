"""
Report generator for fixture execution results.

Provides production-grade report output with:
- Human-readable text report (*.report)
- Structured JSON sidecar (*.report.json)
- Atomic file writes
- Safe filename sanitization
- Non-blocking failure handling support

报告生成器
提供可读文本报告 + 结构化 JSON 报告，支持原子落盘与安全命名
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.core.status_codes import StatusCode


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects.

    支持 datetime 和 date 对象的 JSON 序列化
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


@dataclass
class ReportArtifact:
    """Generated report artifact paths.

    生成的报告产物路径
    """

    text_report_path: Path
    json_report_path: Path


class ReportGenerator:
    """Generate fixture reports in text + JSON formats.

    生成 fixture 文本与 JSON 报告
    """

    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_filename_part(value: str) -> str:
        """Sanitize filename token for cross-platform safety.

        清理文件名片段，避免非法字符
        """
        value = value.strip() or "UNKNOWN"
        value = re.sub(r"[^a-zA-Z0-9._-]", "_", value)
        return value[:64]

    @staticmethod
    def _atomic_write(path: Path, content: str):
        """Atomically write text content to target path.

        原子写入文本到目标文件
        """
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
        temp_path.replace(path)

    def _build_json_payload(
        self,
        fixture_result: Any,
        fixture_config: Dict[str, Any],
        sku: str,
        report_id: str,
        generated_at: str,
    ) -> Dict[str, Any]:
        """Build structured JSON report payload.

        构建结构化 JSON 报告内容
        """
        pass_rate = 0.0
        total_cases = fixture_result.total_pass + fixture_result.total_fail
        if total_cases > 0:
            pass_rate = fixture_result.total_pass / total_cases

        case_items: List[Dict[str, Any]] = []
        for case in fixture_result.case_results:
            function_items = []
            for func in case.function_results:
                function_items.append(
                    {
                        "name": func.name,
                        "code": int(func.code),
                        "status": "pass" if func.success else "fail",
                        "message": func.message,
                        "duration": round(func.duration, 4),
                        "details": func.details or {},
                    }
                )

            case_items.append(
                {
                    "case_name": case.case_name,
                    "module": case.module,
                    "status": case.status,
                    "duration": round(case.duration, 4),
                    "retry_count": case.retry_count,
                    "error": case.error,
                    "pass_count": case.pass_count,
                    "fail_count": case.fail_count,
                    "functions": function_items,
                }
            )

        return {
            "metadata": {
                "generated_at": generated_at,
                "schema_version": "1.0",
                "report_type": "fixture",
            },
            "fixture": {
                "name": fixture_result.fixture_name,
                "description": fixture_config.get("description", ""),
                "status": fixture_result.status,
                "duration": round(fixture_result.duration, 4),
                "loop_count": fixture_result.loop_count,
                "sn_or_stage": report_id,
                "sku": sku,
            },
            "summary": {
                "total_cases": total_cases,
                "passed_cases": fixture_result.total_pass,
                "failed_cases": fixture_result.total_fail,
                "pass_rate": round(pass_rate, 4),
            },
            "config_snapshot": {
                "execution": fixture_config.get("execution", "sequential"),
                "stop_on_failure": fixture_config.get("stop_on_failure", False),
                "retry": fixture_config.get("retry", 0),
                "retry_interval": fixture_config.get("retry_interval", 5),
                "loop": fixture_config.get("loop", False),
                "loop_count": fixture_config.get("loop_count", 1),
                "loop_interval": fixture_config.get("loop_interval", 0),
            },
            "cases": case_items,
        }

    def _build_text_report(self, payload: Dict[str, Any]) -> str:
        """Build human-readable text report content.

        构建可读文本报告内容
        """
        fixture = payload["fixture"]
        summary = payload["summary"]
        metadata = payload["metadata"]

        lines = [
            "=" * 72,
            "Hardware Test Platform - Fixture Report",
            "=" * 72,
            f"Generated At : {metadata['generated_at']}",
            f"Schema Ver   : {metadata['schema_version']}",
            "",
            "[Fixture]",
            f"Name         : {fixture['name']}",
            f"Description  : {fixture['description']}",
            f"Status       : {fixture['status']}",
            f"Duration(s)  : {fixture['duration']:.2f}",
            f"Loop Count   : {fixture['loop_count']}",
            f"SKU          : {fixture['sku']}",
            f"SN/STAGE     : {fixture['sn_or_stage']}",
            "",
            "[Summary]",
            f"Total Cases  : {summary['total_cases']}",
            f"Passed Cases : {summary['passed_cases']}",
            f"Failed Cases : {summary['failed_cases']}",
            f"Pass Rate    : {summary['pass_rate'] * 100:.2f}%",
            "",
            "[Case Details]",
        ]

        for case in payload["cases"]:
            lines.append(
                f"- {case['case_name']} (module={case['module']}) "
                f"status={case['status']} duration={case['duration']:.2f}s retry={case['retry_count']}"
            )
            if case.get("error"):
                lines.append(f"  error: {case['error']}")

            for func in case["functions"]:
                lines.append(
                    f"    * {func['name']} code={func['code']} status={func['status']} "
                    f"duration={func['duration']:.2f}s message={func['message']}"
                )

        lines.extend(["", "=" * 72, ""])
        return "\n".join(lines)

    def generate(
        self,
        fixture_result: Any,
        fixture_config: Dict[str, Any],
        global_config: Optional[Dict[str, Any]] = None,
        sn: Optional[str] = None,
    ) -> ReportArtifact:
        """Generate and persist text + JSON fixture reports.

        生成并落盘 fixture 文本与 JSON 报告
        """
        global_config = global_config or {}
        product = global_config.get("product", {})

        sku = self._sanitize_filename_part(str(product.get("sku", "UNKNOWN")))
        stage = self._sanitize_filename_part(str(product.get("stage", "UNKNOWN")))
        report_id = self._sanitize_filename_part(str(sn or stage))

        status_for_filename = "pass" if fixture_result.status == "pass" else "fail"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        file_base = f"{sku}_{report_id}_{timestamp}_{status_for_filename}"
        text_report_path = self.reports_dir / f"{file_base}.report"
        json_report_path = self.reports_dir / f"{file_base}.report.json"

        payload = self._build_json_payload(
            fixture_result=fixture_result,
            fixture_config=fixture_config,
            sku=sku,
            report_id=report_id,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        text_content = self._build_text_report(payload)
        json_content = json.dumps(payload, indent=2, ensure_ascii=False, cls=DateTimeEncoder)

        self._atomic_write(text_report_path, text_content)
        self._atomic_write(json_report_path, json_content)

        return ReportArtifact(
            text_report_path=text_report_path,
            json_report_path=json_report_path,
        )


def status_code_descriptions() -> Dict[int, Dict[str, str]]:
    """Return status code description map for external use.

    返回状态码中英文描述映射
    """
    descriptions: Dict[int, Dict[str, str]] = {}
    for code in StatusCode:
        descriptions[int(code)] = {
            "en": code.description,
            "zh": code.description_zh,
        }
    return descriptions
