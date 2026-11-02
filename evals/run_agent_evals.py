"""
End-to-end agent evals — talks to real Gemini (text mode), so it needs
GOOGLE_API_KEY in .env or the environment.

For every case in evals/agent_cases.yaml it records which tools the agent
called, resolves each lookup_raaga argument to the knowledge file it actually
loaded, and checks both the loaded files and the final answer.

    uv run python evals/run_agent_evals.py            # all cases
    uv run python evals/run_agent_evals.py -k chalan  # cases whose id contains 'chalan'
    uv run python evals/run_agent_evals.py --repeat 3 # run each case 3x (LLMs are noisy)

Exits non-zero if any case fails.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.session import run_live_session  # noqa: E402
from config import settings  # noqa: E402
from evals.common import resolve_file  # noqa: E402

CASES_PATH = os.path.join(os.path.dirname(__file__), "agent_cases.yaml")
TURN_TIMEOUT_S = 90


@dataclass
class Trace:
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    answer: str = ""

    @property
    def loaded_files(self) -> set[str]:
        files = set()
        for name, args in self.tool_calls:
            if name == "lookup_raaga" and args.get("raaga_name"):
                f = resolve_file(args["raaga_name"])
                if f:
                    files.add(f)
        return files


async def ask(question: str) -> Trace:
    """Run one fresh text session, send one question, collect tools + answer."""
    receive_q: asyncio.Queue = asyncio.Queue()
    send_q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_live_session(receive_q, send_q, text_only=True))
    await receive_q.put({"text": question})

    trace = Trace()
    try:
        while True:
            msg = await asyncio.wait_for(send_q.get(), timeout=TURN_TIMEOUT_S)
            if msg is None or msg.get("type") == "session_closed":
                break
            if "debug_tool" in msg:
                trace.tool_calls.append((msg["debug_tool"], msg.get("debug_args") or {}))
            if "output_text" in msg:
                trace.answer += msg["output_text"]
                break  # text mode emits one final answer per turn
    except TimeoutError:
        trace.answer += "<TIMEOUT>"
    finally:
        await receive_q.put(None)
        await asyncio.wait_for(task, timeout=10)
    return trace


def check(case: dict[str, Any], trace: Trace) -> list[str]:
    """Return a list of failure reasons (empty = pass)."""
    failures = []
    called = [name for name, _ in trace.tool_calls]
    loaded = trace.loaded_files
    answer = trace.answer

    if case.get("no_tools") and called:
        failures.append(f"expected no tools, got {called}")
    for f in case.get("expect_files", []):
        if f not in loaded:
            failures.append(f"did not load {f}.md (loaded: {sorted(loaded) or 'none'})")
    for f in case.get("forbid_files", []):
        if f in loaded:
            failures.append(f"wrongly loaded {f}.md")
    for t in case.get("expect_tools", []):
        if t not in called:
            failures.append(f"did not call {t} (called: {called or 'none'})")
    for group in case.get("answer_must", []):
        if not any(re.search(p, answer, re.I) for p in group):
            failures.append(f"answer missing any of {group}")
    for p in case.get("answer_must_not", []):
        if re.search(p, answer, re.I):
            failures.append(f"answer matched forbidden /{p}/")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", default="", help="only run cases whose id contains this")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("-v", "--verbose", action="store_true", help="print every answer")
    args = parser.parse_args()

    if not settings.google_api_key:
        print("GOOGLE_API_KEY is not set — add it to .env to run agent evals.")
        return 2
    logging.basicConfig(level=logging.WARNING)

    with open(CASES_PATH, encoding="utf-8") as f:
        cases = [c for c in yaml.safe_load(f) if args.k in c["id"]]

    total = passed = 0
    for case in cases:
        for i in range(args.repeat):
            total += 1
            trace = await ask(case["question"])
            failures = check(case, trace)
            tag = case["id"] + (f" #{i + 1}" if args.repeat > 1 else "")
            tools = ", ".join(f"{n}({a.get('raaga_name', '')})" for n, a in trace.tool_calls)
            if failures:
                print(f"FAIL  {tag}\n      Q: {case['question']}\n      tools: {tools or '-'}")
                for r in failures:
                    print(f"      - {r}")
                print(f"      A: {trace.answer.strip()[:400]}")
            else:
                passed += 1
                print(f"PASS  {tag}  [{tools or 'no tools'}]")
                if args.verbose:
                    print(f"      A: {trace.answer.strip()[:400]}")

    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
