# PaaniAlert

Early warning for unsafe drinking water. Residents report bad water on WhatsApp or from a web page on their phone, in Hindi or English, as text, a voice note or a photo. When several reports cluster in one area, PaaniAlert warns everyone nearby to boil their water and alerts the officials responsible, escalating if nobody acts.

Built by Team Crystal Red for the WeMakeDevs × AWS Environmental Hacks, Oct 8–11, 2026 (Heat and Water track).

## Why

In December 2025, sewage leaked into a drinking-water pipeline in Bhagirathpura, Indore. 32 people died and about 1,400 fell ill. Residents had complained about foul, discoloured water before people got sick, but the complaints were scattered and nobody connected them. A judicial panel later called the deaths preventable.

Disease surveillance reacts once patients reach hospitals. Complaints about the water come days earlier. PaaniAlert moves the alarm to the complaints.

## How it works

1. **Report.** A resident messages the WhatsApp bot, or opens the web report page (`/report`) with no sign-up. An AI agent pulls out the smell, colour, taste, how long it has been happening and whether anyone is sick, asks for a location pin, and replies with conservative advice: boil water, ORS, call 108 for blood in stool or dehydration.
2. **Detect.** Every 15 minutes a cluster check looks at each area over the last 48 hours. 3+ distinct phones is a Watch; 5+ phones or 2+ sick households is an Alert.
3. **Alert.** Subscribers nearby get a boil-water advisory as text and a Hindi voice note on WhatsApp, or a browser notification if they turned on "Warn me about my area" on the web page. The ward engineer is notified, and the district health officer if nobody acts within 24 hours.
4. **Act.** Officials review reports on the dashboard, mark them resolved or false (false reports are left out of the cluster rule), and can issue a boil-water or do-not-use warning for a 500 m, 1 km or 2 km radius, then lift it with an all-clear.

On normal days in Delhi, people can send a photo of a TDS meter and learn whether they need an RO purifier at all.

## Architecture

```
WhatsApp (Twilio) ─► API Gateway ─► Lambda (instant reply) ─► SQS ─► Lambda worker ─► Strands agent (Amazon Bedrock)
                                                                                     ├─ Amazon Location Service
                                                                                     ├─ DynamoDB · S3
                                                                                     └─ Transcribe · Polly (Hindi voice)
Web report page (/report) ─► API Gateway ─► Lambda (same worker logic, photos to S3)
EventBridge (every 15 min) ─► Lambda cluster check ─► SNS (officials) + WhatsApp and web push advisories (residents)
Amplify dashboard ◄─ API Gateway ◄─ Lambda API
Deployed with AWS SAM · logs in CloudWatch · region ap-south-1 (Mumbai)
```

## Repo layout

| Path | What | Owner |
|---|---|---|
| `template.yaml` | Every AWS resource | A · Backend & alerts |
| `src/common/` | Shared config, records, DynamoDB helpers | A (B owns `twilio_send.py`) |
| `src/webhook/` | Twilio webhook: validate, queue, reply instantly | A |
| `src/worker/` | Queue consumer: runs the agent, sends the reply | B · Agent & WhatsApp |
| `src/agent/` | Prompts, tools, voice, TDS check | B |
| `src/cluster/` | Cluster rule and the scheduled check | A |
| `src/api/` | Dashboard API | A |
| `dashboard/` | React + MapLibre dashboard on Amplify | C · Dashboard & story |
| `data/` | Test messages, Indore replay, Delhi area profiles | C (A owns `area_profiles.json`) |
| `scripts/` | Fake reports, replay, extraction eval | A, B |
| `tests/` | Unit tests | A, B |
| `docs/` | Sources, video script, writeup | C |

All Lambda functions share one code folder (`src/`), so anything in `src/common/` can be imported everywhere. Libraries are listed in `layer/requirements.txt` and shipped as one Lambda layer.

## Getting started

Prerequisites: Git, Python 3.12, Node.js 20+, AWS CLI v2, AWS SAM CLI, and an AWS profile named `paani` for the team account in `ap-south-1`.

```bash
python -m venv .venv                 # Windows with several Pythons: py -3.12 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

Secrets live in SSM Parameter Store, never in this repo. `hmac_secret` and `dashboard_key` already exist in the team account. Add the Twilio ones once the sandbox is set up (on Git Bash, prefix with `MSYS_NO_PATHCONV=1` so `/paanialert/...` isn't turned into a file path):

```bash
aws ssm put-parameter --profile paani --type SecureString --name /paanialert/twilio_account_sid --value <sid>
aws ssm put-parameter --profile paani --type SecureString --name /paanialert/twilio_auth_token --value <token>
```

Build and deploy in one step (it packages the Python libraries for Lambda's Linux even from Windows, and builds outside the repo so OneDrive can't lock files):

```bash
py -3.12 scripts/deploy_backend.py          # add --layer after changing layer/requirements.txt
python scripts/deploy_dashboard.py          # dashboard → Amplify
```

Read the dashboard key with `aws ssm get-parameter --profile paani --name /paanialert/dashboard_key --with-decryption --query Parameter.Value --output text`.

### Live stack

| What | URL |
|---|---|
| Health check | `https://ayx7njx4g6.execute-api.ap-south-1.amazonaws.com/health` |
| Twilio webhook (POST) | `https://ayx7njx4g6.execute-api.ap-south-1.amazonaws.com/whatsapp` |
| Dashboard API | `https://ayx7njx4g6.execute-api.ap-south-1.amazonaws.com` (`/reports`, `/clusters`, `/advisories`, `/public/clusters`, `/public/advisories`) |
| Officials dashboard | `https://main.dy95ki8l9ef8x.amplifyapp.com` (needs the dashboard key) |
| Web report page | `https://main.dy95ki8l9ef8x.amplifyapp.com/report` (no sign-up) |
| Public warnings page | `https://main.dy95ki8l9ef8x.amplifyapp.com/public` |

Everything is serverless (Lambda, API Gateway, DynamoDB on demand, SQS) and the dashboard is a static build on Amplify Hosting, so nothing needs to be kept running: the stack stays live until it is deleted. To keep it up:

- Turn on termination protection so a stray `sam delete` can't remove it: `aws cloudformation update-termination-protection --enable-termination-protection --stack-name paanialert --profile paani --region ap-south-1`.
- Keep the account's billing valid. The monthly cost budget only emails; it doesn't stop anything.
- Deploy only from a tested `main`. A failed backend deploy rolls back by itself; a bad dashboard deploy can be undone by redeploying an earlier job in the Amplify console.
- `/health` returns `{"ok": true}`; point any uptime monitor at it.

### Try it without five phones

```bash
python scripts/fake_reports.py --near 22.7196,75.8577 --phones 5 --sick 2 --check   # makes an Alert
python scripts/fake_reports.py --clean                                              # removes all fake data
```

Fake reports use made-up phone hashes, so nobody is messaged. To get the official emails, subscribe an address to the `WardEngineerTopicArn` and `HealthOfficerTopicArn` stack outputs (SNS console → Subscriptions → Create subscription → Email) and confirm it. For a demo of escalation, deploy with `--parameter-overrides EscalateAfterMin=10`.

The agent reads each message with Qwen3 235B (Qwen3 VL as backup, `ModelIds` parameter) through Bedrock's OpenAI-compatible `bedrock-mantle` endpoint in Mumbai, authenticated with short-lived tokens from the worker's IAM role. The model fills the report fields (a forced structured-output call); code saves the report and writes the reply. If no model answers, the worker falls back to keyword extraction (`src/agent/fallback.py`) so reports, clusters and alerts keep working; each report's `extracted_by` shows which one read it. See `docs/bedrock-access.md` and `docs/eval.md`.

### Web report app (`/report`)

A second way to report, for people who haven't joined the Twilio sandbox: `https://<dashboard>/report` on a phone. One screen with the reply language (English, हिंदी, Hinglish), the message, a location (browser location or a tap on the map) and an optional photo. It calls the public `POST /app/report` (`src/api/app_report.py`), which runs the same `worker.handle()` as WhatsApp with `channel = "app"` and returns the bot's reply. Photos go straight to S3 under `app-uploads/` through `POST /app/photo-url` (presigned PUT, 5 minutes, JPEG or PNG, at most 5 MB). Both routes are throttled (1 request/s, burst 5, shared by everyone), and each device (a random id kept in the browser) can send 10 reports a day. Officials see app reports with a 📱 label.

If the pin or the device's location is inside an active warning, the page shows a red banner at the top (it checks `GET /public/advisories` on open and every 60 seconds). The "Warn me about my area" switch subscribes the browser to web push for the area around its pin (`POST /app/subscribe`, service worker `/sw.js`, VAPID keys in SSM as `/paanialert/vapid_*`). Automatic Alerts, officials' warnings and all-clears are pushed to those browsers in their language; subscriptions the push service rejects are removed.

## Working together

- Small pull requests into `main`. Whoever merges deploys.
- The shared records in `src/common/models.py` are the contract between the three of us. Change a field only after telling the team.
- No secrets in code, commits, chat or screenshots.

## Team

Team Crystal Red: J Lokesh Rao, Jaya Ruthvik Parasu, Shrikar Tadkasat.
