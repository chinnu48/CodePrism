from __future__ import annotations

import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _speed_index(expected_time: float, actual_time: float) -> float:
    ratio = expected_time / max(actual_time, 0.1)
    return _clamp(ratio, 0.0, 3.0)


def compute_accuracy_per_topic(attempts: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in attempts:
        grouped[row["topic"]].append(int(row["correct"]))
    return {topic: 100.0 * _safe_mean(values) for topic, values in grouped.items()}


def compute_average_time_deviation(attempts: list[dict[str, Any]]) -> float:
    deviations = [float(row["time_taken"]) - float(row["expected_time"]) for row in attempts]
    return _safe_mean(deviations)


def compute_average_speed_index(attempts: list[dict[str, Any]]) -> float:
    values = [_speed_index(float(row["expected_time"]), float(row["time_taken"])) for row in attempts]
    return _safe_mean(values)


def compute_confidence_calibration_score(attempts: list[dict[str, Any]]) -> float:
    """
    Brier-style score mapped to 0-100.
    100 means confidence perfectly matched outcomes.
    """
    if not attempts:
        return 0.0

    squared_errors: list[float] = []
    for row in attempts:
        confidence_prob = float(row["confidence"]) / 100.0
        outcome = float(row["correct"])
        squared_errors.append((confidence_prob - outcome) ** 2)

    brier = _safe_mean(squared_errors)
    return 100.0 * (1.0 - brier)


def compute_weakest_topics(attempts: list[dict[str, Any]], top_n: int = 3) -> list[tuple[str, float]]:
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        by_topic[row["topic"]].append(row)

    weakness_scores: list[tuple[str, float]] = []
    for topic, rows in by_topic.items():
        accuracy = _safe_mean([float(item["correct"]) for item in rows])
        speed = _safe_mean(
            [_speed_index(float(item["expected_time"]), float(item["time_taken"])) for item in rows]
        )
        normalized_speed = _clamp(speed / 1.2, 0.0, 1.0)
        weakness = (1.0 - accuracy) * 0.7 + (1.0 - normalized_speed) * 0.3
        weakness_scores.append((topic, weakness))

    weakness_scores.sort(key=lambda item: item[1], reverse=True)
    return weakness_scores[:top_n]


@dataclass
class StructuralFeatures:
    recursion_usage: bool
    loop_count: int
    nested_depth: int
    dictionary_usage: bool
    sorting_calls: int
    binary_search_pattern: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "recursion_usage": self.recursion_usage,
            "loop_count": self.loop_count,
            "nested_depth": self.nested_depth,
            "dictionary_usage": self.dictionary_usage,
            "sorting_calls": self.sorting_calls,
            "binary_search_pattern": self.binary_search_pattern,
        }


class _StructureVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.current_function: str | None = None
        self.recursion_usage = False
        self.loop_count = 0
        self.max_depth = 0
        self.current_depth = 0
        self.dictionary_usage = False
        self.sorting_calls = 0
        self.binary_search_pattern = False

    def _enter_nested(self) -> None:
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)

    def _exit_nested(self) -> None:
        self.current_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        previous = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = previous

    def visit_For(self, node: ast.For) -> Any:
        self.loop_count += 1
        self._enter_nested()
        self.generic_visit(node)
        self._exit_nested()

    def visit_While(self, node: ast.While) -> Any:
        self.loop_count += 1
        if self._looks_like_binary_search(node):
            self.binary_search_pattern = True
        self._enter_nested()
        self.generic_visit(node)
        self._exit_nested()

    def visit_If(self, node: ast.If) -> Any:
        self._enter_nested()
        self.generic_visit(node)
        self._exit_nested()

    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Name):
            if self.current_function and node.func.id == self.current_function:
                self.recursion_usage = True
            if node.func.id in {"sorted", "sort"}:
                self.sorting_calls += 1
            if node.func.id == "dict":
                self.dictionary_usage = True

        if isinstance(node.func, ast.Attribute) and node.func.attr == "sort":
            self.sorting_calls += 1

        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> Any:
        self.dictionary_usage = True
        self.generic_visit(node)

    def _looks_like_binary_search(self, node: ast.While) -> bool:
        """
        Heuristic pattern: while low <= high with mid=(low+high)//2 and array[mid] usage.
        """
        while_text = ast.dump(node.test)
        guard_pattern = "LtE" in while_text or "Lt" in while_text

        has_mid_assignment = False
        has_mid_subscript = False

        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign):
                target_names = [target.id for target in inner.targets if isinstance(target, ast.Name)]
                if "mid" in target_names:
                    expr = ast.dump(inner.value)
                    if "FloorDiv" in expr and ("low" in expr or "left" in expr):
                        has_mid_assignment = True
            if isinstance(inner, ast.Subscript):
                segment = ast.dump(inner)
                if "mid" in segment:
                    has_mid_subscript = True

        return guard_pattern and has_mid_assignment and has_mid_subscript


def extract_structural_features(code: str) -> StructuralFeatures:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return StructuralFeatures(False, 0, 0, False, 0, False)

    visitor = _StructureVisitor()
    visitor.visit(tree)

    return StructuralFeatures(
        recursion_usage=visitor.recursion_usage,
        loop_count=visitor.loop_count,
        nested_depth=visitor.max_depth,
        dictionary_usage=visitor.dictionary_usage,
        sorting_calls=visitor.sorting_calls,
        binary_search_pattern=visitor.binary_search_pattern,
    )


def _topic_rows(attempts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        grouped[row["topic"]].append(row)
    return grouped


def compute_topic_mastery_scores(attempts: list[dict[str, Any]]) -> dict[str, float]:
    """
    Weighted mastery score (0-100):
      55% accuracy + 25% speed quality + 20% confidence alignment,
      scaled by a light sample-size confidence factor.
    """
    grouped = _topic_rows(attempts)
    scores: dict[str, float] = {}

    for topic, rows in grouped.items():
        accuracy = _safe_mean([float(item["correct"]) for item in rows])
        speed_quality = _clamp(
            _safe_mean(
                [_speed_index(float(item["expected_time"]), float(item["time_taken"])) for item in rows]
            )
            / 1.5,
            0.0,
            1.0,
        )
        confidence_alignment = _safe_mean(
            [1.0 - abs((float(item["confidence"]) / 100.0) - float(item["correct"])) for item in rows]
        )

        base = 0.55 * accuracy + 0.25 * speed_quality + 0.20 * confidence_alignment
        sample_factor = 0.7 + 0.3 * _clamp(len(rows) / 5.0, 0.0, 1.0)
        scores[topic] = 100.0 * base * sample_factor

    return scores


def compute_error_recurrence_index(attempts: list[dict[str, Any]]) -> dict[str, float]:
    grouped = _topic_rows(attempts)
    results: dict[str, float] = {}

    for topic, rows in grouped.items():
        errors = [str(item["error_tag"]) for item in rows if not item["correct"] and item.get("error_tag")]
        if not errors:
            results[topic] = 0.0
            continue

        counter = Counter(errors)
        dominant = max(counter.values())
        recurrence = dominant / len(errors)
        results[topic] = 100.0 * recurrence

    return results


def _parse_timestamp(ts: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return datetime.min


def compute_performance_trends(attempts: list[dict[str, Any]]) -> dict[str, dict[str, float | str]]:
    grouped = _topic_rows(attempts)
    trends: dict[str, dict[str, float | str]] = {}

    for topic, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: _parse_timestamp(str(item["timestamp"])))
        if len(ordered) < 2:
            trends[topic] = {
                "accuracy_trend": 0.0,
                "speed_trend": 0.0,
                "direction": "insufficient_data",
            }
            continue

        split = max(1, len(ordered) // 2)
        early = ordered[:split]
        recent = ordered[split:]

        early_accuracy = _safe_mean([float(item["correct"]) for item in early])
        recent_accuracy = _safe_mean([float(item["correct"]) for item in recent])
        accuracy_delta = recent_accuracy - early_accuracy

        early_speed = _safe_mean(
            [_speed_index(float(item["expected_time"]), float(item["time_taken"])) for item in early]
        )
        recent_speed = _safe_mean(
            [_speed_index(float(item["expected_time"]), float(item["time_taken"])) for item in recent]
        )
        speed_delta = recent_speed - early_speed

        if accuracy_delta > 0.1 or speed_delta > 0.1:
            direction = "improving"
        elif accuracy_delta < -0.1 or speed_delta < -0.1:
            direction = "declining"
        else:
            direction = "stable"

        trends[topic] = {
            "accuracy_trend": accuracy_delta,
            "speed_trend": speed_delta,
            "direction": direction,
        }

    return trends


def build_cli_report(attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return "No attempts found. Solve at least one problem to generate analytics."

    accuracy = compute_accuracy_per_topic(attempts)
    avg_dev = compute_average_time_deviation(attempts)
    speed = compute_average_speed_index(attempts)
    calibration = compute_confidence_calibration_score(attempts)
    weakest = compute_weakest_topics(attempts)

    mastery = compute_topic_mastery_scores(attempts)
    error_recurrence = compute_error_recurrence_index(attempts)
    trends = compute_performance_trends(attempts)

    lines = [
        "=== Skill Intelligence Report ===",
        f"Total Attempts: {len(attempts)}",
        "",
        "[Phase 1 Metrics]",
        "Accuracy by Topic:",
    ]

    for topic, score in sorted(accuracy.items()):
        lines.append(f"  - {topic}: {score:.1f}%")

    lines.extend(
        [
            f"Average Time Deviation (actual-expected): {avg_dev:+.2f} minutes",
            f"Average Speed Index (expected/actual): {speed:.2f}",
            f"Confidence Calibration Score: {calibration:.1f}/100",
            "Weakest Topics:",
        ]
    )

    for topic, weakness_score in weakest:
        lines.append(f"  - {topic}: weakness={weakness_score:.2f}")

    lines.extend(["", "[Phase 3 Skill Modeling]", "Topic Mastery Ranking:"])

    ranked_mastery = sorted(mastery.items(), key=lambda item: item[1], reverse=True)
    for topic, score in ranked_mastery:
        lines.append(f"  - {topic}: {score:.1f}/100")

    lines.append("Error Recurrence Index by Topic:")
    for topic, score in sorted(error_recurrence.items()):
        lines.append(f"  - {topic}: {score:.1f}%")

    lines.append("Performance Trend by Topic:")
    for topic, data in sorted(trends.items()):
        lines.append(
            "  - "
            f"{topic}: {data['direction']} "
            f"(accuracy_delta={float(data['accuracy_trend']):+.2f}, "
            f"speed_delta={float(data['speed_trend']):+.2f})"
        )

    return "\n".join(lines)
