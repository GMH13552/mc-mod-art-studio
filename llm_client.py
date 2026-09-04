#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal OpenAI-compatible text-LLM client for run_pipeline.py --llm-cmd.

API key 一律从环境变量读取，绝不写入脚本/仓库：
    LLM_API_KEY     必填
    LLM_BASE_URL    可选，默认 https://api.openai.com/v1
    LLM_MODEL       可选，默认 gpt-4o-mini（换成任意兼容 chat/completions 的文本模型）

用法：
    export LLM_API_KEY=sk-xxxx
    python3 llm_client.py --prompt-file prompt.txt > raw_answer.txt
    python3 run_pipeline.py --query "异形水晶法杖" \
        --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out out/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    if args.prompt:
        return args.prompt
    raise SystemExit("ERROR: need --prompt-file or a prompt argument")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAI-compatible text LLM client (env-key only)")
    parser.add_argument("--prompt-file", help="path to prompt text file")
    parser.add_argument("prompt", nargs="?", help="inline prompt text (alternative to --prompt-file)")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o-mini"))
    parser.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("LLM_MAX_TOKENS", "4096")))
    args = parser.parse_args(argv)

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print(
            "ERROR: LLM_API_KEY is not set.\n"
            "  export LLM_API_KEY=sk-xxxx\n"
            "  (optionally export LLM_BASE_URL and LLM_MODEL)",
            file=sys.stderr,
        )
        return 2

    prompt = _read_prompt(args)
    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    url = args.base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            "User-Agent": "mc-mod-art-studio/1.0 (+https://github.com/GMH13552/mc-mod-art-studio)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        print("ERROR: LLM call failed: %s" % exc, file=sys.stderr)
        return 1

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("ERROR: unexpected LLM response: %s" % json.dumps(data)[:500], file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())