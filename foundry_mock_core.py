from __future__ import annotations

import json
import os
from pathlib import Path

from azure.identity import ClientSecretCredential
from openai import AzureOpenAI


DEFAULT_SCOPE = "https://cognitiveservices.azure.com/.default"
DEFAULT_API_VERSION = "2024-08-01-preview"


def first_nonempty(*values: str | None, default: str | None = None) -> str | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        file_config = json.load(file)

    return {
        "OPENAI_ENDPOINT": first_nonempty(os.getenv("OPENAI_ENDPOINT"), file_config.get("OPENAI_ENDPOINT")),
        "OPENAI_API_VERSION": first_nonempty(os.getenv("OPENAI_API_VERSION"), file_config.get("OPENAI_API_VERSION"), default=DEFAULT_API_VERSION),
        "OPENAI_MODEL": first_nonempty(os.getenv("OPENAI_MODEL"), file_config.get("OPENAI_MODEL")),
        "AZURE_TENANT_ID": first_nonempty(os.getenv("AZURE_TENANT_ID"), file_config.get("AZURE_TENANT_ID")),
        "AZURE_CLIENT_ID": first_nonempty(os.getenv("AZURE_CLIENT_ID"), file_config.get("AZURE_CLIENT_ID")),
        "AZURE_CLIENT_SECRET": first_nonempty(os.getenv("AZURE_CLIENT_SECRET"), file_config.get("AZURE_CLIENT_SECRET")),
        "TOKEN_SCOPE": first_nonempty(os.getenv("TOKEN_SCOPE"), file_config.get("TOKEN_SCOPE"), default=DEFAULT_SCOPE),
    }


def validate_config(config: dict) -> None:
    required_keys = [
        "OPENAI_ENDPOINT",
        "OPENAI_MODEL",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
    ]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        raise ValueError(f"Missing required config value(s): {', '.join(missing)}")


def ping_model(config: dict, prompt: str, temperature: float = 0.2) -> tuple[str, dict]:
    credential = ClientSecretCredential(
        tenant_id=config["AZURE_TENANT_ID"],
        client_id=config["AZURE_CLIENT_ID"],
        client_secret=config["AZURE_CLIENT_SECRET"],
    )
    token = credential.get_token(config["TOKEN_SCOPE"])

    client = AzureOpenAI(
        azure_endpoint=config["OPENAI_ENDPOINT"],
        api_version=config["OPENAI_API_VERSION"],
        azure_ad_token_provider=lambda: token.token,
    )

    response = client.chat.completions.create(
        model=config["OPENAI_MODEL"],
        messages=[
            {"role": "system", "content": "You are a concise underwriting assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )

    metadata = {
        "response_id": getattr(response, "id", "unknown"),
        "model": getattr(response, "model", config["OPENAI_MODEL"]),
        "prompt_tokens": getattr(getattr(response, "usage", None), "prompt_tokens", None),
        "completion_tokens": getattr(getattr(response, "usage", None), "completion_tokens", None),
        "total_tokens": getattr(getattr(response, "usage", None), "total_tokens", None),
    }

    return response.choices[0].message.content or "", metadata
