from __future__ import annotations

import json
import os
import time
import traceback
from typing import Any

import streamlit as st

from analytics import (
    build_cli_report,
    compute_accuracy_per_topic,
    compute_average_speed_index,
    compute_average_time_deviation,
    compute_confidence_calibration_score,
    compute_error_recurrence_index,
    compute_performance_trends,
    compute_topic_mastery_scores,
    compute_weakest_topics,
    extract_structural_features,
)
from database import fetch_attempts_with_problem_meta, init_db, log_attempt, upsert_problems
from executor import evaluate_submission
from platform_integrations import (
    IntegrationError,
    import_codeforces_attempts,
    import_leetcode_attempts,
)
from problem_engine import load_problems


def _ui_safe_mode() -> bool:
    raw = os.environ.get("SKILL_LAB_UI_SAFE_MODE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@500;700;800&family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
        :root {
            --bg: #f8f6ef;
            --bg-2: #f2f7f0;
            --ink: #101010;
            --muted: #5f6268;
            --line: rgba(16, 16, 16, 0.12);
            --line-strong: rgba(16, 16, 16, 0.24);
            --panel: rgba(255, 252, 244, 0.9);
            --panel-strong: rgba(255, 255, 255, 0.96);
            --accent: #b8ff45;
            --accent-2: #1f64ff;
            --accent-3: #ff6b4a;
            --good: #157347;
            --bad: #c73418;
        }
        html, body, [class*="css"] {
            font-family: "Instrument Sans", sans-serif;
            color: var(--ink);
            background: var(--bg);
        }
        h1, h2, h3, .panel-title {
            font-family: "Syne", sans-serif !important;
            letter-spacing: -0.04em;
        }
        @keyframes drift {
            0% { transform: translateY(0px) translateX(0px); }
            50% { transform: translateY(-8px) translateX(12px) rotate(2deg); }
            100% { transform: translateY(0px) translateX(0px); }
        }
        @keyframes riseIn {
            from { opacity: 0; transform: translateY(14px); }
            to { opacity: 1; transform: translateY(0px); }
        }
        [data-testid="stAppViewContainer"] {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.58), rgba(255, 255, 255, 0.58)),
                repeating-linear-gradient(0deg, rgba(16, 16, 16, 0.03) 0px, rgba(16, 16, 16, 0.03) 1px, transparent 1px, transparent 32px),
                repeating-linear-gradient(90deg, rgba(16, 16, 16, 0.03) 0px, rgba(16, 16, 16, 0.03) 1px, transparent 1px, transparent 32px),
                linear-gradient(145deg, var(--bg) 0%, var(--bg-2) 100%);
        }
        .block-container {
            max-width: 1280px;
            padding-top: 1.25rem;
            padding-bottom: 2.6rem;
        }
        [data-testid="stSidebar"] {
            border-right: 2px solid rgba(255, 255, 255, 0.1);
            background:
                linear-gradient(180deg, rgba(8, 8, 8, 0.98) 0%, rgba(18, 18, 18, 0.98) 100%);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1rem;
        }
        [data-testid="stSidebar"] * {
            color: #f4f0e8;
        }
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] p {
            color: rgba(244, 240, 232, 0.78) !important;
        }
        .ambient {
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: -1;
            overflow: hidden;
        }
        .orb {
            position: absolute;
            border-radius: 28px;
            filter: blur(0px);
            opacity: 0.88;
            animation: drift 14s ease-in-out infinite;
        }
        .orb-a {
            width: 210px;
            height: 18px;
            top: 7%;
            right: 8%;
            background: rgba(184, 255, 69, 0.82);
        }
        .orb-b {
            width: 120px;
            height: 120px;
            top: 64%;
            left: 2%;
            background: rgba(31, 100, 255, 0.14);
            animation-delay: 1.6s;
        }
        .orb-c {
            width: 160px;
            height: 18px;
            bottom: 18%;
            right: 18%;
            background: rgba(255, 107, 74, 0.82);
            animation-delay: 3.2s;
        }
        .hero {
            position: relative;
            overflow: hidden;
            border-radius: 34px;
            padding: 1.7rem;
            margin-bottom: 1rem;
            color: var(--ink);
            background:
                linear-gradient(0deg, rgba(255, 255, 255, 0.56), rgba(255, 255, 255, 0.56)),
                linear-gradient(135deg, rgba(184, 255, 69, 0.7) 0%, rgba(184, 255, 69, 0.2) 42%, rgba(31, 100, 255, 0.12) 100%);
            border: 2px solid var(--line-strong);
            box-shadow: 14px 14px 0 rgba(16, 16, 16, 0.08);
            animation: riseIn 0.52s ease-out;
        }
        .hero::after {
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(135deg, transparent 0 68%, rgba(16, 16, 16, 0.07) 68% 70%, transparent 70%),
                linear-gradient(90deg, transparent 0 88%, rgba(16, 16, 16, 0.05) 88% 100%);
            pointer-events: none;
        }
        .hero-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
            padding: 0.42rem 0.8rem;
            border-radius: 999px;
            border: 1.5px solid var(--ink);
            background: #fffef8;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }
        .hero h1 {
            margin: 0 0 0.45rem 0;
            font-size: 2.9rem;
            font-weight: 800;
            max-width: 780px;
            line-height: 0.95;
        }
        .hero p {
            margin: 0;
            font-size: 1rem;
            line-height: 1.65;
            max-width: 640px;
        }
        .hero-grid {
            margin-top: 1.15rem;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.85rem;
            max-width: 540px;
        }
        .hero-chip {
            background: rgba(255, 255, 255, 0.86);
            border: 1.5px solid var(--ink);
            border-radius: 20px;
            padding: 0.95rem 1rem;
            box-shadow: 6px 6px 0 rgba(16, 16, 16, 0.08);
        }
        .hero-chip .k {
            display: block;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--muted);
        }
        .hero-chip .v {
            display: block;
            margin-top: 0.25rem;
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: -0.04em;
        }
        .glass, .surface-card {
            background: var(--panel);
            border: 1.5px solid var(--line-strong);
            border-radius: 28px;
            padding: 1.1rem 1.15rem;
            box-shadow: 10px 10px 0 rgba(16, 16, 16, 0.05);
            animation: riseIn 0.42s ease-out;
        }
        .surface-card.strong {
            background: var(--panel-strong);
        }
        .surface-card.tight {
            padding: 0.8rem 0.95rem;
        }
        .metric-card {
            border: 1.5px solid var(--line-strong);
            background: var(--panel-strong);
            border-radius: 22px;
            padding: 0.95rem 1rem;
            box-shadow: 8px 8px 0 rgba(16, 16, 16, 0.05);
        }
        .metric-card .label {
            font-size: 0.72rem;
            letter-spacing: 0.12em;
            color: var(--muted);
            text-transform: uppercase;
        }
        .metric-card .value {
            margin-top: 0.3rem;
            font-size: 1.35rem;
            font-weight: 800;
            color: var(--ink);
        }
        .metric-card.good .value { color: var(--good); }
        .metric-card.bad .value { color: var(--bad); }
        .metric-card.info .value { color: var(--accent-2); }
        .section-title {
            margin: 0 0 0.85rem 0;
            letter-spacing: 0.12em;
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .pill {
            display: inline-block;
            padding: 0.48rem 0.82rem;
            border-radius: 999px;
            font-size: 0.78rem;
            margin-right: 0.4rem;
            margin-bottom: 0.45rem;
            color: var(--ink);
            background: rgba(184, 255, 69, 0.24);
            border: 1.5px solid rgba(16, 16, 16, 0.14);
        }
        .panel-title {
            margin: 0 0 0.3rem 0;
            color: var(--ink);
            font-size: 1.45rem;
            font-weight: 800;
        }
        .panel-subtitle {
            margin: 0;
            color: var(--muted);
            font-size: 0.95rem;
            line-height: 1.55;
        }
        .eyebrow {
            margin-bottom: 0.3rem;
            color: var(--muted);
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-weight: 700;
        }
        .meta-grid, .info-strip, .sidebar-stats {
            display: grid;
            gap: 0.75rem;
        }
        .meta-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin: 0.85rem 0 0.1rem;
        }
        .meta-item, .info-box, .sidebar-stat {
            padding: 0.9rem 0.95rem;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.78);
            border: 1.5px solid var(--line);
        }
        .meta-item .label, .info-box .k, .sidebar-stat .k {
            display: block;
            color: var(--muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
        }
        .meta-item .value, .info-box .v, .sidebar-stat .v {
            display: block;
            margin-top: 0.2rem;
            color: var(--ink);
            font-size: 1rem;
            font-weight: 800;
        }
        .difficulty-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.35rem 0.7rem;
            font-size: 0.75rem;
            font-weight: 800;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }
        .difficulty-pill.easy {
            background: rgba(21, 115, 71, 0.12);
            color: var(--good);
        }
        .difficulty-pill.medium {
            background: rgba(31, 100, 255, 0.12);
            color: var(--accent-2);
        }
        .difficulty-pill.hard {
            background: rgba(199, 52, 24, 0.12);
            color: var(--bad);
        }
        .sidebar-card {
            padding: 1rem;
            margin-bottom: 0.85rem;
            border-radius: 26px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.07) 0%, rgba(255, 255, 255, 0.03) 100%);
            border: 1px solid rgba(255, 255, 255, 0.14);
        }
        .sidebar-card h3 {
            margin: 0;
            color: #f8f6ef;
            font-size: 1rem;
            font-family: "Syne", sans-serif;
        }
        .sidebar-card p {
            margin: 0.35rem 0 0;
            color: rgba(248, 246, 239, 0.72);
            font-size: 0.86rem;
            line-height: 1.5;
        }
        .sidebar-stats {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-top: 0.9rem;
            gap: 0.55rem;
        }
        .sidebar-stat {
            background: rgba(184, 255, 69, 0.08);
            border: 1px solid rgba(184, 255, 69, 0.2);
        }
        .sidebar-stat .k {
            color: rgba(248, 246, 239, 0.58);
        }
        .sidebar-stat .v {
            color: #f8f6ef;
        }
        .code-shell {
            padding: 1rem 1.05rem 0.5rem;
        }
        .info-strip {
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin: 0.4rem 0 0.8rem;
            gap: 0.65rem;
        }
        .case-card {
            margin-bottom: 0.7rem;
            padding: 0.85rem 0.95rem;
            border-radius: 22px;
            border: 1.5px solid var(--line);
            background: rgba(255, 255, 255, 0.84);
        }
        .case-card .case-title {
            margin-bottom: 0.35rem;
            color: var(--ink);
            font-size: 0.82rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.12em;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.4rem;
            margin-bottom: 0.8rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            border: 1.5px solid var(--line-strong);
            background: rgba(255, 255, 255, 0.7);
            height: 44px;
            padding: 0 1rem;
            box-shadow: none;
        }
        .stTabs [aria-selected="true"] {
            border-color: var(--ink) !important;
            background: linear-gradient(180deg, rgba(184, 255, 69, 0.82) 0%, rgba(184, 255, 69, 0.66) 100%) !important;
            color: var(--ink) !important;
        }
        .stButton > button {
            border-radius: 999px;
            border: 1.5px solid var(--ink);
            height: 2.8rem;
            font-weight: 700;
            transition: transform 0.15s ease, box-shadow 0.18s ease, background 0.18s ease;
            box-shadow: 6px 6px 0 rgba(16, 16, 16, 0.1);
            background: var(--ink);
            color: #fbf7ef;
        }
        .stButton > button:hover {
            transform: translate(-1px, -1px);
            box-shadow: 8px 8px 0 rgba(16, 16, 16, 0.14);
            background: var(--accent);
            color: var(--ink);
        }
        .stTextArea textarea,
        .stTextInput input,
        .stNumberInput input,
        div[data-baseweb="select"] > div,
        div[data-baseweb="base-input"] > div {
            border-radius: 18px !important;
            border: 1.5px solid var(--line-strong) !important;
            background: rgba(255, 255, 255, 0.88) !important;
            box-shadow: none;
        }
        .stTextArea textarea {
            min-height: 420px;
            line-height: 1.6;
        }
        [data-testid="stDataFrame"] {
            border-radius: 24px;
            overflow: hidden;
            border: 1.5px solid var(--line-strong);
            background: rgba(255, 255, 255, 0.9);
        }
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.82);
            border: 1.5px solid var(--line);
            border-radius: 18px;
            padding: 0.55rem 0.7rem;
        }
        code, pre, [data-testid="stCodeBlock"] {
            font-family: "JetBrains Mono", monospace !important;
            font-size: 0.86rem !important;
        }
        @media (max-width: 1024px) {
            .hero-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .meta-grid, .info-strip {
                grid-template-columns: 1fr;
            }
            .hero h1 {
                font-size: 2.25rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_shell() -> None:
    st.markdown(
        """
        <div class="ambient">
            <span class="orb orb-a"></span>
            <span class="orb orb-b"></span>
            <span class="orb orb-c"></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(attempts: list[dict[str, Any]]) -> None:
    total = len(attempts)
    accuracy = (100 * sum(int(a["correct"]) for a in attempts) / total) if total else 0.0
    speed = compute_average_speed_index(attempts) if total else 0.0
    calibration = compute_confidence_calibration_score(attempts) if total else 0.0
    st.markdown(
        (
            '<div class="hero">'
            '<div class="hero-kicker">Skill LAB</div>'
            "<h1>Practice with pressure, clarity, and visible progress.</h1>"
            "<p>A sharper training board for coding drills: pick a target, write the solution, and see what your "
            "speed, confidence, and accuracy are really doing.</p>"
            '<div class="hero-grid">'
            f'<div class="hero-chip"><span class="k">Attempts</span><span class="v">{total}</span></div>'
            f'<div class="hero-chip"><span class="k">Accuracy</span><span class="v">{accuracy:.1f}%</span></div>'
            f'<div class="hero-chip"><span class="k">Speed Index</span><span class="v">{speed:.2f}</span></div>'
            f'<div class="hero-chip"><span class="k">Calibration</span><span class="v">{calibration:.1f}/100</span></div>'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_metric_card(label: str, value: str, tone: str = "") -> None:
    cls = f"metric-card {tone}".strip()
    st.markdown(
        f'<div class="{cls}"><div class="label">{label}</div><div class="value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def _difficulty_class(difficulty: str) -> str:
    return difficulty.strip().lower()


def _render_sidebar_overview(total_problems: int, filtered_count: int, attempts: list[dict[str, Any]]) -> None:
    solved = sum(1 for item in attempts if item.get("correct"))
    accuracy = (100 * solved / len(attempts)) if attempts else 0.0
    st.sidebar.markdown(
        (
            '<div class="sidebar-card">'
            "<h3>Session Board</h3>"
            "<p>Trim the problem bank, lock in one target, and keep the run focused.</p>"
            '<div class="sidebar-stats">'
            f'<div class="sidebar-stat"><span class="k">Problems</span><span class="v">{total_problems}</span></div>'
            f'<div class="sidebar-stat"><span class="k">Visible</span><span class="v">{filtered_count}</span></div>'
            f'<div class="sidebar-stat"><span class="k">Attempts</span><span class="v">{len(attempts)}</span></div>'
            f'<div class="sidebar-stat"><span class="k">Accuracy</span><span class="v">{accuracy:.0f}%</span></div>'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _bootstrap() -> list[dict[str, Any]]:
    init_db()
    problems = load_problems()
    upsert_problems(problems)
    return problems


def _problem_label(problem: dict[str, Any]) -> str:
    return f"{problem['id']:>2} | {problem['title']} [{problem['topic']} | {problem['difficulty']}]"


def _template_code() -> str:
    return (
        "def solve(*args):\n"
        "    # Write your solution here\n"
        "    return None\n"
    )


def _filtered_problems(
    problems: list[dict[str, Any]],
    search: str,
    topics: list[str],
    difficulties: list[str],
) -> list[dict[str, Any]]:
    rows = problems
    if topics:
        rows = [p for p in rows if p["topic"] in topics]
    if difficulties:
        rows = [p for p in rows if p["difficulty"] in difficulties]
    if search.strip():
        needle = search.lower().strip()
        rows = [
            p
            for p in rows
            if needle in p["title"].lower()
            or needle in p["topic"].lower()
            or any(needle in tag.lower() for tag in p["concept_tags"])
        ]
    return rows


def _render_problem(problem: dict[str, Any]) -> None:
    st.markdown(
        (
            '<div class="surface-card strong">'
            '<div class="section-title">Problem Brief</div>'
            f'<div class="eyebrow">Problem {problem["id"]}</div>'
            f'<h3 class="panel-title">{problem["title"]}</h3>'
            f'<p class="panel-subtitle">{problem["description"]}</p>'
            '<div class="meta-grid">'
            f'<div class="meta-item"><span class="label">Topic</span><span class="value">{problem["topic"]}</span></div>'
            f'<div class="meta-item"><span class="label">Difficulty</span><span class="value"><span class="difficulty-pill {_difficulty_class(problem["difficulty"])}">{problem["difficulty"]}</span></span></div>'
            f'<div class="meta-item"><span class="label">Expected Time</span><span class="value">{problem["expected_time"]} min</span></div>'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown("#### Concept Tags")
    tags_html = "".join([f'<span class="pill">{tag}</span>' for tag in problem["concept_tags"]])
    st.markdown(tags_html, unsafe_allow_html=True)
    with st.expander("Show Test Cases"):
        for idx, case in enumerate(problem["test_cases"], start=1):
            st.markdown(
                (
                    '<div class="case-card">'
                    f'<div class="case-title">Case {idx}</div>'
                    f"<div><b>Input</b><br/><code>{case['input']}</code></div>"
                    f"<div style='margin-top:0.55rem;'><b>Expected</b><br/><code>{case['output']}</code></div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _evaluate_and_log(
    problem: dict[str, Any],
    code: str,
    predicted_time: float,
    confidence: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    correct, error_tag, results = evaluate_submission(problem, code, timeout_seconds=timeout_seconds)
    elapsed = max((time.perf_counter() - t0) / 60.0, 0.1)
    structural = extract_structural_features(code).as_dict()

    log_attempt(
        {
            "problem_id": problem["id"],
            "topic": problem["topic"],
            "difficulty": problem["difficulty"],
            "time_taken": round(elapsed, 4),
            "predicted_time": predicted_time,
            "confidence": confidence,
            "correct": correct,
            "error_tag": error_tag,
            "structural_features": json.dumps(structural),
        }
    )

    return {
        "problem_id": problem["id"],
        "correct": correct,
        "error_tag": error_tag,
        "time_taken": elapsed,
        "results": results,
        "structural": structural,
    }


def _show_submission(result: dict[str, Any]) -> None:
    st.markdown('<div class="section-title">Evaluation Snapshot</div>', unsafe_allow_html=True)
    pass_count = sum(1 for r in result["results"] if r.passed)
    fail_count = len(result["results"]) - pass_count
    a, b, c, d = st.columns(4)
    with a:
        _render_metric_card("Correct", "Yes" if result["correct"] else "No", "good" if result["correct"] else "bad")
    with b:
        _render_metric_card("Elapsed", f"{result['time_taken']:.2f} min", "info")
    with c:
        _render_metric_card("Pass / Fail", f"{pass_count} / {fail_count}", "info")
    with d:
        _render_metric_card("Error Tag", "None" if not result["error_tag"] else str(result["error_tag"]))

    rows: list[dict[str, Any]] = []
    for i, case in enumerate(result["results"], start=1):
        rows.append(
            {
                "Case": i,
                "Status": "PASS" if case.passed else "FAIL",
                "Input": str(case.input_data),
                "Expected": str(case.expected_output),
                "Actual": str(case.actual_output),
                "Error": case.error_tag or "",
            }
        )
    st.markdown("#### Test Case Results")
    st.dataframe(rows, use_container_width=True)

    st.markdown("#### Structural Signals")
    s = result["structural"]
    r1 = st.columns(3)
    r2 = st.columns(3)
    r1[0].metric("Recursion Usage", "Yes" if s["recursion_usage"] else "No")
    r1[1].metric("Loop Count", str(s["loop_count"]))
    r1[2].metric("Nested Depth", str(s["nested_depth"]))
    r2[0].metric("Dictionary Usage", "Yes" if s["dictionary_usage"] else "No")
    r2[1].metric("Sorting Calls", str(s["sorting_calls"]))
    r2[2].metric("Binary Search Pattern", "Yes" if s["binary_search_pattern"] else "No")


def _render_dashboard(attempts: list[dict[str, Any]]) -> None:
    st.markdown('<div class="section-title">Skill Dashboard</div>', unsafe_allow_html=True)
    if not attempts:
        st.info("No attempts yet. Submit code or import external attempts.")
        return

    overall_accuracy = 100 * (sum(int(a["correct"]) for a in attempts) / max(len(attempts), 1))
    avg_speed = compute_average_speed_index(attempts)
    confidence_cal = compute_confidence_calibration_score(attempts)
    avg_dev = compute_average_time_deviation(attempts)

    m = st.columns(4)
    with m[0]:
        _render_metric_card("Total Attempts", str(len(attempts)), "info")
    with m[1]:
        _render_metric_card("Overall Accuracy", f"{overall_accuracy:.1f}%", "good")
    with m[2]:
        _render_metric_card("Speed Index", f"{avg_speed:.2f}", "info")
    with m[3]:
        _render_metric_card("Calibration", f"{confidence_cal:.1f}/100", "info")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="surface-card tight">', unsafe_allow_html=True)
        st.markdown("#### Accuracy by Topic")
        st.bar_chart(compute_accuracy_per_topic(attempts))
        st.markdown("#### Error Recurrence")
        st.bar_chart(compute_error_recurrence_index(attempts))
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="surface-card tight">', unsafe_allow_html=True)
        st.markdown("#### Topic Mastery")
        st.bar_chart(compute_topic_mastery_scores(attempts))
        st.markdown("#### Weakest Topics")
        weakest = compute_weakest_topics(attempts)
        if weakest:
            for topic, score in weakest:
                st.write(f"- {topic}: weakness {score:.2f}")
        else:
            st.write("No data")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        (
            '<div class="info-strip">'
            f'<div class="info-box"><span class="k">Average Time Drift</span><span class="v">{avg_dev:+.2f} min</span></div>'
            f'<div class="info-box"><span class="k">Solved Correctly</span><span class="v">{sum(int(a["correct"]) for a in attempts)}</span></div>'
            f'<div class="info-box"><span class="k">Tracked Topics</span><span class="v">{len({a["topic"] for a in attempts})}</span></div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown("#### Trend Direction")
    trend_rows = []
    for topic, t in compute_performance_trends(attempts).items():
        trend_rows.append(
            {
                "Topic": topic,
                "Direction": t["direction"],
                "Accuracy Delta": round(float(t["accuracy_trend"]), 3),
                "Speed Delta": round(float(t["speed_trend"]), 3),
            }
        )
    st.dataframe(trend_rows, use_container_width=True)

    with st.expander("Full Text Analytics Report"):
        st.code(build_cli_report(attempts), language="text")


def _render_history(attempts: list[dict[str, Any]]) -> None:
    st.markdown('<div class="section-title">Attempt History</div>', unsafe_allow_html=True)
    if not attempts:
        st.info("No attempts recorded yet.")
        return

    rows = []
    for item in reversed(attempts[-150:]):
        rows.append(
            {
                "Timestamp": item["timestamp"],
                "Platform": item.get("source_platform") or "local",
                "Problem ID": item["problem_id"],
                "Topic": item["topic"],
                "Difficulty": item["difficulty"],
                "Correct": bool(item["correct"]),
                "Time (min)": float(item["time_taken"]),
                "Predicted (min)": float(item["predicted_time"]),
                "Confidence": int(item["confidence"]),
                "Error": item["error_tag"] or "",
            }
        )
    st.markdown(
        (
            '<div class="surface-card strong tight">'
            "<div class='eyebrow'>Latest 150 submissions</div>"
            "<h3 class='panel-title'>Session log</h3>"
            "<p class='panel-subtitle'>Review outcome, confidence, timing, and error patterns from recent runs and imports.</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.dataframe(rows, use_container_width=True)


def _render_integrations() -> None:
    st.markdown('<div class="section-title">Platform Integrations</div>', unsafe_allow_html=True)
    st.markdown(
        (
            '<div class="surface-card strong">'
            "<div class='eyebrow'>External Practice Import</div>"
            "<h3 class='panel-title'>Bring in solved problems from other platforms</h3>"
            "<p class='panel-subtitle'>Pull accepted submissions into the same analytics timeline so your dashboard reflects local practice and imported history.</p>"
            "<br/>"
            "<b>What works now:</b> LeetCode and Codeforces import into your local analytics database.<br/>"
            "<b>LeetCode note:</b> Public mode usually returns recent accepted submissions only. "
            "Session cookie mode can import broader history depending on account/session permissions."
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown("")

    platform = st.radio("Platform", ["LeetCode", "Codeforces"], horizontal=True)

    if platform == "LeetCode":
        username = st.text_input("LeetCode Username", placeholder="your_username")
        limit = st.slider("Submission Limit", 1, 100, 20)
        with st.expander("Advanced Auth (optional)", expanded=False):
            st.caption("Use this only if you want to try importing full submission history.")
            session_cookie = st.text_input("LEETCODE_SESSION cookie", type="password")
            csrf_token = st.text_input("CSRF Token (x-csrftoken)", type="password")

        if st.button("Import from LeetCode", type="primary", use_container_width=True):
            try:
                result = import_leetcode_attempts(
                    username=username,
                    limit=limit,
                    session_cookie=session_cookie or None,
                    csrf_token=csrf_token or None,
                )
                st.success(
                    f"{result.platform}: imported {result.imported} new attempts out of {result.attempted} fetched."
                )
                for note in result.notes:
                    st.info(note)
            except IntegrationError as exc:
                st.error(str(exc))

    if platform == "Codeforces":
        handle = st.text_input("Codeforces Handle", placeholder="your_handle")
        count = st.slider("Submission Count", 1, 200, 50)

        if st.button("Import from Codeforces", type="primary", use_container_width=True):
            try:
                result = import_codeforces_attempts(handle=handle, count=count)
                st.success(
                    f"{result.platform}: imported {result.imported} new attempts out of {result.attempted} fetched."
                )
                for note in result.notes:
                    st.info(note)
            except IntegrationError as exc:
                st.error(str(exc))


def main() -> None:
    st.set_page_config(
        page_title="Skill Intelligence Lab",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    safe_mode = _ui_safe_mode()
    if not safe_mode:
        _inject_styles()
        _render_shell()

    try:
        problems = _bootstrap()
        attempts_snapshot = fetch_attempts_with_problem_meta()
    except Exception as exc:  # noqa: BLE001
        st.error("Startup failed while loading data or connecting to the database.")
        st.info(
            "If you configured PostgreSQL, verify `SKILL_LAB_DATABASE_URL` and that your PostgreSQL server is running."
        )
        with st.expander("Technical Details"):
            st.code(traceback.format_exc(), language="text")
        st.caption(f"Error: {exc}")
        return

    if "last_submission" not in st.session_state:
        st.session_state.last_submission = None

    if safe_mode:
        st.warning("UI safe mode is ON (`SKILL_LAB_UI_SAFE_MODE=1`). Custom styling is disabled.")

    _render_hero(attempts_snapshot)

    all_topics = sorted({p["topic"] for p in problems})
    all_diff = sorted({p["difficulty"] for p in problems})

    st.sidebar.markdown("### Practice Studio")
    st.sidebar.caption("Filter hard. Pick one target. Run the test bench.")
    st.sidebar.markdown("---")
    st.sidebar.markdown("## Problem Explorer")
    search = st.sidebar.text_input("Search", placeholder="title/topic/tag")
    topics = st.sidebar.multiselect("Topic Filter", all_topics)
    diffs = st.sidebar.multiselect("Difficulty Filter", all_diff)
    filtered = _filtered_problems(problems, search, topics, diffs)

    if not filtered:
        st.warning("No problems match current filters.")
        return

    selected_id = st.sidebar.selectbox(
        "Choose Problem",
        options=[p["id"] for p in filtered],
        format_func=lambda pid: _problem_label(next(p for p in filtered if p["id"] == pid)),
    )
    selected_problem = next(p for p in filtered if p["id"] == selected_id)
    _render_sidebar_overview(len(problems), len(filtered), attempts_snapshot)

    st.sidebar.markdown("---")
    st.sidebar.markdown("## Submission Settings")
    predicted = st.sidebar.number_input(
        "Predicted Time (min)",
        min_value=0.1,
        max_value=180.0,
        value=float(selected_problem["expected_time"]),
        step=0.5,
    )
    confidence = st.sidebar.slider("Confidence", 0, 100, 70)
    timeout = st.sidebar.slider("Timeout per test (sec)", 1, 10, 3)

    solve_tab, dashboard_tab, integrate_tab, history_tab = st.tabs(
        ["Solve", "Dashboard", "Integrations", "History"]
    )

    with solve_tab:
        left, right = st.columns([1.0, 1.3], gap="large")
        with left:
            _render_problem(selected_problem)
        with right:
            code_key = f"code_{selected_problem['id']}"
            if code_key not in st.session_state:
                st.session_state[code_key] = _template_code()

            st.markdown(
                (
                    '<div class="surface-card strong code-shell">'
                    '<div class="section-title">Code Editor</div>'
                    "<h3 class='panel-title'>Implement `solve(...)`</h3>"
                    "<p class='panel-subtitle'>Return the expected value directly. The runner handles input wiring, test execution, and logging.</p>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            code = st.text_area(
                "Write code",
                key=code_key,
                label_visibility="collapsed",
                height=420,
            )
            if st.button("Evaluate", use_container_width=True, type="primary"):
                if not code.strip():
                    st.error("Code cannot be empty.")
                elif "def solve" not in code:
                    st.error("Please define `solve(...)`.")
                else:
                    with st.spinner("Executing tests and updating analytics..."):
                        st.session_state.last_submission = _evaluate_and_log(
                            selected_problem,
                            code,
                            predicted,
                            confidence,
                            timeout,
                        )

        last = st.session_state.last_submission
        if last and last["problem_id"] == selected_problem["id"]:
            st.markdown("---")
            _show_submission(last)

    attempts = fetch_attempts_with_problem_meta()
    with dashboard_tab:
        _render_dashboard(attempts)
    with integrate_tab:
        _render_integrations()
    with history_tab:
        _render_history(attempts)


if __name__ == "__main__":
    main()
