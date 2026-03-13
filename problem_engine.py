from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "id",
    "title",
    "topic",
    "difficulty",
    "expected_time",
    "concept_tags",
    "description",
    "test_cases",
}
VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}


class ProblemValidationError(ValueError):
    """Raised when the problem bank contains invalid schema entries."""


def _problems_path() -> Path:
    return Path(__file__).resolve().parent / "problems" / "problems.json"


def _validate_problem(problem: dict[str, Any]) -> None:
    missing = REQUIRED_FIELDS - set(problem.keys())
    if missing:
        raise ProblemValidationError(
            f"Problem {problem.get('id', '<unknown>')} missing fields: {sorted(missing)}"
        )

    if problem["difficulty"] not in VALID_DIFFICULTIES:
        raise ProblemValidationError(
            f"Problem {problem['id']} has invalid difficulty: {problem['difficulty']}"
        )

    if not isinstance(problem["concept_tags"], list):
        raise ProblemValidationError(f"Problem {problem['id']} concept_tags must be a list")

    if not isinstance(problem["test_cases"], list) or not problem["test_cases"]:
        raise ProblemValidationError(f"Problem {problem['id']} test_cases must be a non-empty list")

    for idx, case in enumerate(problem["test_cases"]):
        if not isinstance(case, dict) or "input" not in case or "output" not in case:
            raise ProblemValidationError(
                f"Problem {problem['id']} test case #{idx + 1} must contain input/output"
            )


def load_problems() -> list[dict[str, Any]]:
    """Load and validate all problems from JSON storage."""
    path = _problems_path()
    if not path.exists():
        raise FileNotFoundError(f"Problem bank not found at {path}")

    with path.open("r", encoding="utf-8-sig") as file:
        problems = json.load(file)

    if not isinstance(problems, list):
        raise ProblemValidationError("Problem bank root must be a list")

    seen_ids: set[int] = set()
    for problem in problems:
        _validate_problem(problem)
        if problem["id"] in seen_ids:
            raise ProblemValidationError(f"Duplicate problem id detected: {problem['id']}")
        seen_ids.add(problem["id"])

    return problems


def get_problem_by_id(problem_id: int) -> dict[str, Any] | None:
    for problem in load_problems():
        if problem["id"] == problem_id:
            return problem
    return None
