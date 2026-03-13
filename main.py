from __future__ import annotations

import json
import time
from typing import Any

from analytics import build_cli_report, extract_structural_features
from database import fetch_attempts_with_problem_meta, init_db, log_attempt, upsert_problems
from executor import evaluate_submission
from problem_engine import get_problem_by_id, load_problems


def _read_float(prompt: str, minimum: float = 0.0) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
            if value < minimum:
                raise ValueError
            return value
        except ValueError:
            print(f"Enter a number >= {minimum}.")


def _read_int(prompt: str, minimum: int = 0, maximum: int = 100) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
            if value < minimum or value > maximum:
                raise ValueError
            return value
        except ValueError:
            print(f"Enter an integer between {minimum} and {maximum}.")


def _collect_code_block() -> str:
    print("Paste Python code. Define solve(...). Type END on a new line to finish.")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def _display_problems(problems: list[dict[str, Any]]) -> None:
    print("\nAvailable Problems")
    print("------------------")
    for problem in problems:
        print(
            f"{problem['id']}. {problem['title']} | {problem['topic']} | "
            f"{problem['difficulty']} | expected={problem['expected_time']} min"
        )


def _display_problem(problem: dict[str, Any]) -> None:
    print("\nSelected Problem")
    print("----------------")
    print(f"Title      : {problem['title']}")
    print(f"Topic      : {problem['topic']}")
    print(f"Difficulty : {problem['difficulty']}")
    print(f"Expected   : {problem['expected_time']} minutes")
    print(f"Tags       : {', '.join(problem['concept_tags'])}")
    print("Description:")
    print(problem["description"])


def main() -> None:
    init_db()

    problems = load_problems()
    upsert_problems(problems)
    _display_problems(problems)

    selected_id = _read_int("\nSelect problem id: ", minimum=1, maximum=10**9)
    problem = get_problem_by_id(selected_id)

    if not problem:
        print("Problem not found. Exiting.")
        return

    _display_problem(problem)

    started_at = time.perf_counter()
    predicted_time = _read_float("Predicted solve time (minutes): ", minimum=0.1)
    confidence = _read_int("Confidence (0-100): ", minimum=0, maximum=100)
    user_code = _collect_code_block()

    is_correct, error_tag, results = evaluate_submission(problem, user_code, timeout_seconds=3)
    elapsed_minutes = max((time.perf_counter() - started_at) / 60.0, 0.1)

    print("\nExecution Results")
    print("-----------------")
    for idx, result in enumerate(results, start=1):
        status = "PASS" if result.passed else "FAIL"
        print(f"Case {idx}: {status}")
        if not result.passed:
            print(f"  expected={result.expected_output}")
            print(f"  actual={result.actual_output}")
            if result.stderr:
                print(f"  stderr={result.stderr}")
            if result.error_tag:
                print(f"  error_tag={result.error_tag}")

    structural = extract_structural_features(user_code)

    attempt_payload = {
        "problem_id": problem["id"],
        "topic": problem["topic"],
        "difficulty": problem["difficulty"],
        "time_taken": round(elapsed_minutes, 4),
        "predicted_time": predicted_time,
        "confidence": confidence,
        "correct": is_correct,
        "error_tag": error_tag,
        "structural_features": json.dumps(structural.as_dict()),
    }
    log_attempt(attempt_payload)

    print("\nSubmission Summary")
    print("------------------")
    print(f"Correct        : {is_correct}")
    print(f"Time Taken     : {elapsed_minutes:.2f} minutes")
    print(f"Logged Error   : {error_tag}")

    print("\n[Phase 2] Structural Code Signals")
    for key, value in structural.as_dict().items():
        print(f"- {key}: {value}")

    attempts = fetch_attempts_with_problem_meta()
    print()
    print(build_cli_report(attempts))


if __name__ == "__main__":
    main()
