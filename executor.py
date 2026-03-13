from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any


@dataclass
class TestCaseResult:
    input_data: Any
    expected_output: Any
    actual_output: Any
    passed: bool
    stderr: str
    error_tag: str | None


def _build_runner_script(user_code: str) -> str:
    """Wrap user code with a stable entrypoint that executes solve(*args)."""
    return (
        "import json\n"
        "import inspect\n"
        "import traceback\n"
        "\n"
        f"{user_code}\n"
        "\n"
        "if 'solve' not in globals():\n"
        "    raise NameError(\"Define a function named solve(...)\")\n"
        "\n"
        "def _coerce_args(raw):\n"
        "    sig = inspect.signature(solve)\n"
        "    positional = [\n"
        "        p for p in sig.parameters.values()\n"
        "        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)\n"
        "    ]\n"
        "    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())\n"
        "    if has_varargs:\n"
        "        return raw if isinstance(raw, list) else [raw]\n"
        "    if len(positional) <= 1:\n"
        "        return [raw]\n"
        "    return raw if isinstance(raw, list) else [raw]\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    raw = json.loads(input())\n"
        "    try:\n"
        "        args = _coerce_args(raw)\n"
        "        result = solve(*args)\n"
        "        print(json.dumps({'ok': True, 'result': result}))\n"
        "    except Exception as exc:\n"
        "        print(json.dumps({'ok': False, 'error': str(exc), 'trace': traceback.format_exc()}))\n"
        "        raise\n"
    )


def _parse_process_output(stdout: str) -> tuple[Any, str | None]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None, "no_output"

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return lines[-1].strip(), None

    if not isinstance(payload, dict):
        return payload, None

    if payload.get("ok"):
        return payload.get("result"), None
    return None, "runtime_error"


def run_single_test(user_code: str, test_input: Any, timeout_seconds: int = 3) -> tuple[Any, str, str | None]:
    """
    Execute one test in a subprocess.

    Returns:
      (actual_output, stderr, error_tag)
    """
    script = _build_runner_script(user_code)
    tmp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp_file:
            tmp_file.write(script)
            tmp_path = tmp_file.name

        process = subprocess.Popen(
            [sys.executable, tmp_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        input_payload = json.dumps(test_input)
        stdout, stderr = process.communicate(input=input_payload + "\n", timeout=timeout_seconds)

        actual_output, parse_error = _parse_process_output(stdout)

        if process.returncode != 0:
            if parse_error is None:
                parse_error = "runtime_error"
            return actual_output, stderr.strip(), parse_error

        return actual_output, stderr.strip(), parse_error

    except subprocess.TimeoutExpired:
        process.kill()
        return None, "Time Limit Exceeded", "timeout"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc), "executor_error"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def evaluate_submission(problem: dict[str, Any], user_code: str, timeout_seconds: int = 3) -> tuple[bool, str | None, list[TestCaseResult]]:
    results: list[TestCaseResult] = []

    for case in problem["test_cases"]:
        actual, stderr, error_tag = run_single_test(user_code, case["input"], timeout_seconds=timeout_seconds)
        passed = error_tag is None and actual == case["output"]

        if not passed and error_tag is None:
            error_tag = "wrong_answer"

        results.append(
            TestCaseResult(
                input_data=case["input"],
                expected_output=case["output"],
                actual_output=actual,
                passed=passed,
                stderr=stderr,
                error_tag=error_tag,
            )
        )

    is_correct = all(result.passed for result in results)
    if is_correct:
        return True, None, results

    first_failure = next((result for result in results if not result.passed), None)
    return False, (first_failure.error_tag if first_failure else "unknown_error"), results
