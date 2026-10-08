"""The one place that talks to a language model: headless `claude -p` on the logged-in subscription.

The pattern is creator-watch's: every call is isolated from the user's Claude Code setup so a run
behaves the same everywhere. No tools, no MCP servers, no settings (hence no hooks, skills or
plugins), no slash commands, no session persistence, a one-line system prompt, every `CLAUDE*`
variable stripped from the environment, a fresh temp directory as cwd so no project CLAUDE.md is
found. `--bare` is not used because it refuses the subscription's credentials. The prompt travels on
stdin; the answer comes back as a JSON envelope whose `structured_output` satisfies `--json-schema`.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

SYSTEM_PROMPT = "You are a careful reader of transcripts. Follow the instructions exactly and answer only with the requested JSON."

UNAVAILABLE = ("usage limit", "rate limit", "overloaded", "not logged in", "invalid api key", "authentication",
               "credit balance", "please run /login")


class LlmError(RuntimeError):
    """The call failed for this input (bad output, timeout)."""


class LlmUnavailable(LlmError):
    """The backend is not usable now (limits, auth, missing binary); says nothing about the input."""


def isolated_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k != "AI_AGENT"}
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env


def command(model: str, schema: dict, claude_bin: str = "claude") -> list[str]:
    return [claude_bin, "-p", "--model", model, "--tools", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
            "--system-prompt", SYSTEM_PROMPT,
            "--json-schema", json.dumps(schema), "--output-format", "json"]


def complete_json(prompt: str, schema: dict, *, model: str, timeout: int, claude_bin: str = "claude"):
    """Send the prompt, return the structured output (parsed JSON) or raise."""
    try:
        with tempfile.TemporaryDirectory(prefix="nhi-timeline-llm-") as cwd:
            proc = subprocess.run(command(model, schema, claude_bin), input=prompt, capture_output=True,
                                  text=True, timeout=timeout, cwd=cwd, env=isolated_env())
    except FileNotFoundError as exc:
        raise LlmUnavailable(f"claude binary not found: {claude_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LlmError(f"claude -p timed out after {timeout}s") from exc
    return parse_output(proc.returncode, proc.stdout, proc.stderr)


def parse_output(returncode: int, stdout: str, stderr: str):
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        env = None
    if not isinstance(env, dict):
        text = (stderr or stdout).strip()[:500]
        raise classify(f"claude -p exited {returncode} without a JSON envelope: {text}", text, None)
    if env.get("is_error") or returncode != 0:
        text = str(env.get("result") or stderr or "").strip()[:500]
        raise classify(f"claude -p failed (exit {returncode}, api status {env.get('api_error_status')}): {text}",
                       text, env.get("api_error_status"))
    data = env.get("structured_output")
    if data is None:
        raise LlmError("claude -p returned no structured output (plain text instead): " + str(env.get("result"))[:300])
    return data


def classify(message: str, text: str, status) -> LlmError:
    low = text.lower()
    if status in (401, 403, 429, 529) or (isinstance(status, int) and status >= 500) or any(m in low for m in UNAVAILABLE):
        return LlmUnavailable(message)
    return LlmError(message)
