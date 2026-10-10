# How the agent reaches its models

The agent calls Bedrock's **OpenAI-compatible `bedrock-mantle` endpoint in Mumbai (`ap-south-1`)**, authenticated with **short-lived tokens signed from the worker's own IAM role**. There is no stored key, message text never leaves India, and the friend's cross-account role is no longer needed.

## Why Mantle

On our team account (908027384294), `bedrock-runtime` Converse fails with `ValidationException: Operation not allowed`, but the Bedrock console playground works. The playground uses `bedrock-mantle` (`https://bedrock-mantle.<region>.api.aws/v1`, OpenAI Chat Completions and Responses, no Converse), and so does the agent now.

## Settings

| Stack parameter | Worker env var | Value (pinned in `samconfig.toml`) |
|---|---|---|
| `ModelEndpoint` | `MODEL_ENDPOINT` | `mantle` (or `runtime` for the old Converse path) |
| `MantleRegion` | `MANTLE_REGION` | `ap-south-1` |
| `ModelIds` | `MODEL_IDS` | `qwen.qwen3-235b-a22b-2507,qwen.qwen3-vl-235b-a22b-instruct` |

`sam deploy` keeps a parameter's previous value unless it's overridden, so change these in `samconfig.toml`, not only in `template.yaml`.

**Auth.** Strands' `OpenAIModel(bedrock_mantle_config=...)` signs a fresh bearer token from the worker role's credentials on every request (`aws-bedrock-token-generator`, no network call). The worker role has only `bedrock-mantle:CreateInference` on `project/*` in `MantleRegion` and `bedrock-mantle:CallWithBearerToken` limited to `SHORT_TERM` tokens, and is explicitly denied the old `/paanialert/bedrock_api_key` parameter. Locally, the same works from your `paani` login (needs `botocore[crt]`, in `requirements-dev.txt`).

## Which models

Probed on Oct 10 in `ap-south-1`, then scored on our 50 test messages (`docs/eval.md`):

| Order | Model | Why |
|---|---|---|
| 1 | **Qwen3 235B** (`qwen.qwen3-235b-a22b-2507`) | Read all 50 test messages correctly enough for 90–92% all-five-fields; ~1.2 s median |
| 2 | **Qwen3 VL 235B** (`qwen.qwen3-vl-235b-a22b-instruct`) | Backup; also reads images, but we don't send photos to the model yet |

Dropped: DeepSeek V3.1 (as a conversation agent it saved only 2 of 50 complaints, asking for a location instead). Not chosen: DeepSeek V3.2 and Gemma 3 27B (didn't call tools), gpt-oss 120B, Mistral Large 3 and GLM 4.7 (1/2 in the tool probe), Kimi K2.5 and Qwen3 Next 80B (slower). Llama 4 Maverick isn't offered on Mantle.

## How a message is read

`src/agent/runner.py` separates extraction from conversation:

1. The model fills `ReportFields` (Pydantic, with our conventions in the field descriptions) through Strands structured output. If it answers in text instead, Strands forces the tool call; if its JSON doesn't parse, validation fails and it tries again.
2. Code decides whether it's a complaint (any smell, colour or taste that isn't unknown, or someone sick), saves it with `extracted_by = "agent:<model id>"`, and replies from `prompts.py`: one line of what was understood, the standard advice, and a location request if there's no pin.
3. Anything else (greetings, questions) gets a short model reply, or `WELCOME`.

A model that errors or never returns valid fields is logged (`model <label> failed: …`, warning) and the next one is tried. If all fail, the worker saves the complaint with keyword extraction (`extracted_by = "keywords"`), so a complaint is never lost. The dashboard shows `extracted_by` as a small label on each report.

## Privacy note for the writeup

Message text is processed by Bedrock in `ap-south-1` (Mumbai), in our own account. Phone numbers are never sent to the model; reports are stored only in our account in Mumbai.

## The old Converse path

`ModelEndpoint=runtime` still calls `bedrock-runtime` Converse in `BedrockRegion`, optionally through a role in another account (`BedrockRoleArn`). That was the workaround while our account was blocked; it isn't used now. `scripts/pick_model.py` checks models on that path only.
