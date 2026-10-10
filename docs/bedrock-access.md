# How the agent reaches its models

The agent calls Bedrock's **OpenAI-compatible `bedrock-mantle` endpoint in Mumbai (`ap-south-1`)**, authenticated with a Bedrock API key. Message text never leaves India, and the friend's cross-account role is no longer needed.

## Why Mantle

On our team account (908027384294), `bedrock-runtime` Converse fails with `ValidationException: Operation not allowed`, but the Bedrock console playground works. The playground uses `bedrock-mantle` (`https://bedrock-mantle.<region>.api.aws/v1`, OpenAI Chat Completions and Responses, no Converse), and so does the agent now.

## Settings

| Stack parameter | Worker env var | Default |
|---|---|---|
| `ModelEndpoint` | `MODEL_ENDPOINT` | `mantle` (or `runtime` for the old Converse path) |
| `MantleRegion` | `MANTLE_REGION` | `ap-south-1` |
| `ModelIds` | `MODEL_IDS` | `deepseek.v3.1,qwen.qwen3-235b-a22b-2507,qwen.qwen3-vl-235b-a22b-instruct` |

The API key is the SecureString `/paanialert/bedrock_api_key`. The worker reads it through `common.config.secret("bedrock_api_key")`; it is never in code, `template.yaml` or logs. To replace it (Git Bash; reads the key without echoing it or saving it in shell history):

```bash
MSYS_NO_PATHCONV=1 bash -c 'read -rsp "Key: " K; aws ssm put-parameter --profile paani --type SecureString --overwrite --name /paanialert/bedrock_api_key --value "$K"'
```

Bedrock API keys expire. If every message starts falling back to keywords, check the key first.

## Which models

Probed on Oct 10 in `ap-south-1`: a plain chat, then two `save_report` tool calls (one Hinglish, one Devanagari) with our system prompt.

| Order | Model | Result |
|---|---|---|
| 1 | **DeepSeek V3.1** (`deepseek.v3.1`) | 2/2 tool calls, fastest (~0.75 s); once sent JSON that didn't parse in an earlier probe |
| 2 | **Qwen3 235B** (`qwen.qwen3-235b-a22b-2507`) | 2/2, ~1.1 s |
| 3 | **Qwen3 VL 235B** (`qwen.qwen3-vl-235b-a22b-instruct`) | 2/2, ~2.3 s; reads images, but we don't send photos to the model yet |

On the 50 test messages through the live bot's path, every model often asks for a location pin instead of saving, which the runner counts as a failure (DeepSeek V3.1 almost always; it saved 2 of 50). See `docs/eval.md`.

Not chosen: DeepSeek V3.2 and Gemma 3 27B (replied without calling the tool), gpt-oss 120B, Mistral Large 3 and GLM 4.7 (1/2 each), Kimi K2.5 and Qwen3 Next 80B (2/2 but slower). Llama 4 Maverick isn't offered on Mantle.

## When a model counts as failed

`src/agent/runner.py` tries the models in order and moves to the next one, logging `model <id> failed: <reason>` at warning level, when a model:

- raises an error (timeout, HTTP error, bad key),
- makes a malformed `save_report` call (JSON that doesn't parse, or arguments that fail the schema), or
- doesn't save a report although its reply says "saved", or the message is clearly a complaint (`fallback.is_complaint`).

If every model fails, the worker saves the complaint with keyword extraction instead, so a complaint is never lost. Each report's `extracted_by` says which one read it (`agent:deepseek.v3.1` or `keywords`), and the dashboard shows it as a small label on each report.

## Privacy note for the writeup

Message text is processed by Bedrock in `ap-south-1` (Mumbai), in our own account. Phone numbers are never sent to the model; reports are stored only in our account in Mumbai.

## The old Converse path

`ModelEndpoint=runtime` still calls `bedrock-runtime` Converse in `BedrockRegion`, optionally through a role in another account (`BedrockRoleArn`). That was the workaround while our account was blocked; it isn't used now. `scripts/pick_model.py` checks models on that path only.
