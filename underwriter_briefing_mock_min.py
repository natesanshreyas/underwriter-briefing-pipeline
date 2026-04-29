#!/usr/bin/env python3
"""
Bare-bones Foundry auth + model ping demo.

Purpose:
- Load config from JSON
- Authenticate with service principal
- Make one chat completion call
- Print minimal proof that the call succeeded
"""

from __future__ import annotations

import sys
from foundry_mock_core import load_config, ping_model, validate_config


DEMO_PROMPT = "Write a 2-sentence underwriting summary for a mid-market manufacturing renewal."


def main() -> int:
    config_file = sys.argv[1] if len(sys.argv) > 1 else "secrets_foundry_demo.json"

    try:
        config = load_config(config_file)
        validate_config(config)

        print(f"Config loaded: {config_file}")

        print(f"Pinging model: {config['OPENAI_MODEL']}")
        text, metadata = ping_model(config, DEMO_PROMPT, temperature=0)
        print("Auth OK: token acquired")
        print("Call succeeded")
        print(f"Response ID: {metadata['response_id']}")
        print(f"Output preview: {text[:160]}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
