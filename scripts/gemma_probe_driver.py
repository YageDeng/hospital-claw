#!/usr/bin/env python3
"""Gemma probe driver for SKILL_E2E_AGENT_DRIVER.

Usage: python3 gemma_probe_driver.py <payload.json>

Reads the probe payload JSON, sends the prompt to Ollama,
and exits 0 (PASS) or non-zero (FAIL).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: gemma_probe_driver.py <payload.json>", file=sys.stderr)
        return 1

    payload_path = sys.argv[1]
    with open(payload_path, encoding="utf-8") as f:
        payload = json.load(f)

    prompt = payload.get("prompt", "")
    if not prompt:
        print("FAIL: empty prompt in payload")
        return 1

    model = os.environ.get("SKILL_E2E_GEMMA_MODEL", "gemma4:e4b")
    ollama_url = os.environ.get("SKILL_E2E_OLLAMA_URL", "http://127.0.0.1:11434")
    timeout = int(os.environ.get("SKILL_E2E_PROBE_TIMEOUT", "120"))

    request_body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=request_body,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"FAIL: Ollama request error: {exc}")
        return 1

    content = data.get("message", {}).get("content", "")
    if not content:
        print("FAIL: empty response from Ollama")
        return 1

    # Check for genuine refusal / error indicators
    lower = content.lower()
    refusal_phrases = (
        "i'm sorry",
        "i cannot assist",
        "i can't assist",
        "i will not",
        "i won't",
        "inappropriate",
        "harmful",
        "illegal",
        "not possible to help",
        "error:",
    )
    for phrase in refusal_phrases:
        if phrase in lower:
            print(f"FAIL: model refused or errored: {content[:200]}")
            return 1

    print(f"PASS: {content[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
