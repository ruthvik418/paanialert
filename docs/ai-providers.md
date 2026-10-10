# AI models when Bedrock is unavailable

The agent tries models in this order (`src/agent/runner.py`):

1. **Bedrock**: the models in the `ModelIds` stack parameter (Qwen3 235B, then Qwen3 VL) through the `bedrock-mantle` endpoint in our account (see `docs/bedrock-access.md`)
2. **Claude** through Anthropic's API, only if `/paanialert/anthropic_api_key` exists in SSM
3. **Gemini** through Google's API, only if `/paanialert/gemini_api_key` exists in SSM
4. If none answers: keyword extraction (`src/agent/fallback.py`)

Everything else (WhatsApp webhook, database, clusters, alerts, dashboard) stays on AWS, and the agent is built with the AWS open-source Strands Agents SDK, so the project still meets the hackathon's AWS requirement. When Bedrock works again it is tried first, with no change needed.

## Add a Gemini key (free, no card)

1. Go to <https://aistudio.google.com>, sign in with a Google account, click **Get API key → Create API key**, and copy it.
2. In Command Prompt (the key is pasted at a prompt, never typed into the command or shared in chat):

```bat
set /p GEMINI_KEY=Paste your Gemini API key and press Enter: 
aws ssm put-parameter --profile paani --region ap-south-1 --type SecureString --name /paanialert/gemini_api_key --value %GEMINI_KEY%
set GEMINI_KEY=
```

No redeploy is needed: the worker checks for keys every 5 minutes. Send a WhatsApp message after that; the worker log shows `answered by gemini:gemini-2.5-flash`.

Note: on Google's free tier, Google may use prompts to improve its products. Message text goes to Google; phone numbers never do. Mention this in the writeup, or use a paid key.

## Add a Claude key (better quality, prepaid credits)

Create a key at <https://console.anthropic.com> (needs prepaid credits), then store it the same way under `/paanialert/anthropic_api_key`. Claude is tried before Gemini.

## Change the model names

`ClaudeModel` (default `claude-haiku-5-5`) and `GeminiModel` (default `gemini-2.5-flash`) are stack parameters. If the worker log says a model name isn't found, deploy with e.g. `--parameter-overrides GeminiModel=<name from Google AI Studio>`.

## Remove a key

```bat
aws ssm delete-parameter --profile paani --region ap-south-1 --name /paanialert/gemini_api_key
```
