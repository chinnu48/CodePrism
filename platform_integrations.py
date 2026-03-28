from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib import error, request

from database import log_attempt, upsert_problems


class IntegrationError(RuntimeError):
    pass


@dataclass
class ImportResult:
    platform: str
    imported: int
    attempted: int
    mode: str
    notes: list[str]


def _http_json(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method=method.upper())
    req.add_header("User-Agent", "skill-intelligence-lab/1.0")
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="ignore")
        raise IntegrationError(f"HTTP {exc.code}: {text[:220]}") from exc
    except error.URLError as exc:
        raise IntegrationError(f"Network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise IntegrationError("Failed to parse JSON response from external platform.") from exc


def _external_problem_id(platform: str, external_key: str) -> int:
    digest = hashlib.sha1(f"{platform}:{external_key}".encode("utf-8")).hexdigest()
    return 1_000_000 + (int(digest[:10], 16) % 800_000_000)


def _map_difficulty(text: str | None) -> str:
    if not text:
        return "Medium"
    value = text.strip().lower()
    if value in {"easy", "e", "newbie"}:
        return "Easy"
    if value in {"medium", "m"}:
        return "Medium"
    if value in {"hard", "h"}:
        return "Hard"
    return "Medium"


def _cf_rating_to_difficulty(rating: int | None) -> str:
    if rating is None:
        return "Medium"
    if rating <= 1200:
        return "Easy"
    if rating <= 1700:
        return "Medium"
    return "Hard"


def _difficulty_to_expected_minutes(difficulty: str) -> float:
    if difficulty == "Easy":
        return 12.0
    if difficulty == "Hard":
        return 25.0
    return 18.0


def _timestamp_from_unix(ts: int | str | None) -> str | None:
    if ts is None:
        return None
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return None
    return datetime.utcfromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_error_tag(raw: str | None) -> str | None:
    if not raw:
        return None
    tag = raw.strip().lower().replace(" ", "_")
    return tag if tag else None


def _upsert_external_problem(
    platform: str,
    external_key: str,
    title: str,
    topic: str,
    difficulty: str,
    concept_tags: list[str],
) -> int:
    pid = _external_problem_id(platform, external_key)
    upsert_problems(
        [
            {
                "id": pid,
                "title": title,
                "topic": topic,
                "difficulty": difficulty,
                "expected_time": _difficulty_to_expected_minutes(difficulty),
                "concept_tags": concept_tags or [platform],
                "description": f"Imported from {platform}.",
                "test_cases": [{"input": None, "output": None}],
                "problem_source": "external",
            }
        ]
    )
    return pid


def import_codeforces_attempts(handle: str, count: int = 50, user_id: int | None = None) -> ImportResult:
    handle = handle.strip()
    if not handle:
        raise IntegrationError("Codeforces handle is required.")
    if count < 1:
        raise IntegrationError("Count must be at least 1.")

    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count={count}"
    data = _http_json(url, method="GET")

    if data.get("status") != "OK":
        raise IntegrationError(f"Codeforces API error: {data.get('comment', 'Unknown error')}")

    submissions = data.get("result", [])
    imported = 0
    attempted = 0

    for item in submissions:
        problem = item.get("problem", {})
        title = str(problem.get("name", "Codeforces Problem"))
        contest_id = problem.get("contestId", "x")
        index = problem.get("index", "x")
        key = f"{contest_id}-{index}"
        tags = [str(tag) for tag in problem.get("tags", []) if tag]
        primary_tag = tags[0] if tags else "codeforces"
        topic = f"Codeforces:{primary_tag}"
        difficulty = _cf_rating_to_difficulty(problem.get("rating"))
        pid = _upsert_external_problem(
            platform="codeforces",
            external_key=key,
            title=title,
            topic=topic,
            difficulty=difficulty,
            concept_tags=tags[:5] if tags else ["codeforces"],
        )

        verdict = str(item.get("verdict", "")).strip()
        correct = verdict == "OK"
        error_tag = None if correct else _normalize_error_tag(verdict or "wrong_answer")
        runtime_ms = item.get("timeConsumedMillis")
        time_taken = max((float(runtime_ms) / 1000.0) / 60.0, 0.1) if runtime_ms else 0.1
        ts = _timestamp_from_unix(item.get("creationTimeSeconds"))
        external_submission_id = str(item.get("id", key))

        attempted += 1
        inserted = log_attempt(
            {
                "problem_id": pid,
                "topic": topic,
                "difficulty": difficulty,
                "time_taken": time_taken,
                "predicted_time": _difficulty_to_expected_minutes(difficulty),
                "confidence": 65 if correct else 45,
                "correct": correct,
                "error_tag": error_tag,
                "structural_features": None,
                "source_platform": "codeforces",
                "external_submission_id": external_submission_id,
                "user_id": user_id,
                "timestamp": ts,
            }
        )
        if inserted:
            imported += 1

    return ImportResult(
        platform="Codeforces",
        imported=imported,
        attempted=attempted,
        mode="public_api",
        notes=["Imported via Codeforces public API user.status endpoint."],
    )


def _leetcode_graphql(
    query: str,
    variables: dict[str, Any],
    session_cookie: str | None = None,
    csrf_token: str | None = None,
) -> dict[str, Any]:
    headers: dict[str, str] = {
        "Referer": "https://leetcode.com/",
    }
    if session_cookie:
        headers["Cookie"] = f"LEETCODE_SESSION={session_cookie}"
    if csrf_token:
        headers["x-csrftoken"] = csrf_token

    payload = {"query": query, "variables": variables}
    result = _http_json(
        "https://leetcode.com/graphql/",
        method="POST",
        payload=payload,
        headers=headers,
    )
    if "errors" in result and result["errors"]:
        raise IntegrationError(str(result["errors"][0]))
    return result.get("data", {})


def _leetcode_question_meta(slug: str) -> tuple[str, list[str]]:
    query = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        difficulty
        topicTags {
          name
        }
      }
    }
    """
    data = _leetcode_graphql(query, {"titleSlug": slug})
    question = (data or {}).get("question") or {}
    difficulty = _map_difficulty(question.get("difficulty"))
    tags = [str(item.get("name")) for item in question.get("topicTags", []) if item.get("name")]
    return difficulty, tags


def import_leetcode_attempts(
    username: str,
    limit: int = 20,
    session_cookie: str | None = None,
    csrf_token: str | None = None,
    user_id: int | None = None,
) -> ImportResult:
    username = username.strip()
    if not username:
        raise IntegrationError("LeetCode username is required.")
    if limit < 1:
        raise IntegrationError("Limit must be at least 1.")

    notes: list[str] = []

    if session_cookie:
        history_query = """
        query submissionList($offset: Int!, $limit: Int!, $lastKey: String) {
          submissionList(offset: $offset, limit: $limit, lastKey: $lastKey) {
            submissions {
              id
              title
              titleSlug
              statusDisplay
              timestamp
            }
          }
        }
        """
        data = _leetcode_graphql(
            history_query,
            {"offset": 0, "limit": limit, "lastKey": None},
            session_cookie=session_cookie,
            csrf_token=csrf_token,
        )
        submissions = (((data or {}).get("submissionList") or {}).get("submissions")) or []
        mode = "authenticated_history"
        notes.append("Imported authenticated submission history using session cookie.")
    else:
        accepted_query = """
        query recentAcSubmissions($username: String!, $limit: Int!) {
          recentAcSubmissionList(username: $username, limit: $limit) {
            id
            title
            titleSlug
            timestamp
          }
        }
        """
        data = _leetcode_graphql(accepted_query, {"username": username, "limit": limit})
        submissions = (data or {}).get("recentAcSubmissionList") or []
        mode = "public_recent_accepted"
        notes.append(
            "Using public endpoint: imports recent accepted submissions only. "
            "Provide session cookie for full history where available."
        )

    imported = 0
    attempted = 0

    for item in submissions:
        slug = str(item.get("titleSlug") or item.get("title") or "leetcode-problem")
        title = str(item.get("title") or slug.replace("-", " ").title())
        difficulty, tags = _leetcode_question_meta(slug)
        topic = f"LeetCode:{(tags[0] if tags else 'general')}"
        pid = _upsert_external_problem(
            platform="leetcode",
            external_key=slug,
            title=title,
            topic=topic,
            difficulty=difficulty,
            concept_tags=tags[:5] if tags else ["leetcode"],
        )

        status_display = item.get("statusDisplay")
        correct = bool(status_display == "Accepted" or status_display is None)
        error_tag = None if correct else _normalize_error_tag(str(status_display))

        attempted += 1
        inserted = log_attempt(
            {
                "problem_id": pid,
                "topic": topic,
                "difficulty": difficulty,
                "time_taken": 0.1,
                "predicted_time": _difficulty_to_expected_minutes(difficulty),
                "confidence": 70 if correct else 40,
                "correct": correct,
                "error_tag": error_tag,
                "structural_features": None,
                "source_platform": "leetcode",
                "external_submission_id": str(item.get("id", slug)),
                "user_id": user_id,
                "timestamp": _timestamp_from_unix(item.get("timestamp")),
            }
        )
        if inserted:
            imported += 1

    return ImportResult(
        platform="LeetCode",
        imported=imported,
        attempted=attempted,
        mode=mode,
        notes=notes,
    )
