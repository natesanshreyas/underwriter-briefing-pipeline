# Foundry Mock Demo (Service Principal)

This demo shows a minimal end-to-end call to Azure OpenAI / Foundry using:
- Service principal authentication
- A local JSON config file
- A single chat completion request

Primary files:
- `underwriter_briefing_mock.py`
- `secrets_foundry_demo.json`

## What this demo does

1. Loads config values from `secrets_foundry_demo.json`.
2. Optionally allows environment variables to override file values.
3. Uses `ClientSecretCredential` to request an Azure AD token.
4. Calls the model deployment with one fixed prompt.
5. Prints quick proof of success (`Response ID` + output preview).

## Prerequisites

- Python 3.10+
- Access to your Azure OpenAI / Foundry endpoint
- Service principal with appropriate access on the target resource

Install dependencies:

```bash
pip install -r requirements_foundry_demo.txt
```

## Configure secrets

Edit `secrets_foundry_demo.json`:

```json
{
  "OPENAI_ENDPOINT": "https://<your-resource>.services.ai.azure.com/",
  "OPENAI_MODEL": "<your-deployment-name>",
  "AZURE_TENANT_ID": "<tenant-id>",
  "AZURE_CLIENT_ID": "<client-id>",
  "AZURE_CLIENT_SECRET": "<client-secret>"
}
```

Notes:
- `OPENAI_API_VERSION` is not required in the file (default is in code).
- `TOKEN_SCOPE` is not required in the file (default is in code).

## Run

Default config file:

```bash
python3 underwriter_briefing_mock.py
```

Custom config path:

```bash
python3 underwriter_briefing_mock.py /path/to/config.json
```

## Expected output

You should see lines similar to:

```text
Config loaded: secrets_foundry_demo.json
Pinging model: <deployment>
Auth OK: token acquired
Call succeeded
Response ID: <chatcmpl-...>
Output preview: <first part of model output>
```

## How it works (code flow)

- `underwriter_briefing_mock.py`
  - Loads config and validates required fields.
  - Calls shared helper to perform token + model request.

- `foundry_mock_core.py`
  - `load_config(...)`: reads JSON and applies env overrides.
  - `validate_config(...)`: enforces required values.
  - `ping_model(...)`: acquires token and calls chat completions.

## Defaults in code

Defined in `foundry_mock_core.py`:
- API version: `2024-08-01-preview`
- Token scope: `https://cognitiveservices.azure.com/.default`

## Troubleshooting

- `Config file not found`:
  - Confirm path and current working directory.

- `Missing required config value(s)`:
  - Fill all fields in `secrets_foundry_demo.json`.

- Auth/token errors:
  - Verify tenant/client/secret values.
  - Verify the service principal has access to the target Azure resource.

- Deployment/model errors:
  - Ensure `OPENAI_MODEL` exactly matches your deployment name.
