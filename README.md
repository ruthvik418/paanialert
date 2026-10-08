# PaaniAlert

Early warning for unsafe drinking water. Residents report bad water on WhatsApp, in Hindi or English, as text, a voice note or a photo. When several reports cluster in one area, PaaniAlert warns everyone nearby to boil their water and alerts the officials responsible, escalating if nobody acts.

Built by Team Crystal Red for the WeMakeDevs × AWS Environmental Hacks, Oct 8–11, 2026 (Heat and Water track).

## Why

In December 2025, sewage leaked into a drinking-water pipeline in Bhagirathpura, Indore. 32 people died and about 1,400 fell ill. Residents had complained about foul, discoloured water before people got sick, but the complaints were scattered and nobody connected them. A judicial panel later called the deaths preventable.

Disease surveillance reacts once patients reach hospitals. Complaints about the water come days earlier. PaaniAlert moves the alarm to the complaints.

## How it works

1. **Report.** A resident messages the WhatsApp bot. An AI agent pulls out the smell, colour, taste, how long it has been happening and whether anyone is sick, asks for a location pin, and replies with conservative advice: boil water, ORS, call 108 for blood in stool or dehydration.
2. **Detect.** Every 15 minutes a cluster check looks at each area over the last 48 hours. 3+ distinct phones is a Watch; 5+ phones or 2+ sick households is an Alert.
3. **Alert.** Subscribers nearby get a boil-water advisory as text and a Hindi voice note. The ward engineer is notified, and the district health officer if nobody acts within 24 hours.

On normal days in Delhi, people can send a photo of a TDS meter and learn whether they need an RO purifier at all.

## Architecture

```
WhatsApp (Twilio) ─► API Gateway ─► Lambda (instant reply) ─► SQS ─► Lambda worker ─► Strands agent (Amazon Bedrock)
                                                                                     ├─ Amazon Location Service
                                                                                     ├─ DynamoDB · S3
                                                                                     └─ Transcribe · Polly (Hindi voice)
EventBridge (every 15 min) ─► Lambda cluster check ─► SNS (officials) + WhatsApp advisories (residents)
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
| Dashboard API | `https://ayx7njx4g6.execute-api.ap-south-1.amazonaws.com` (`/reports`, `/clusters`, `/public/clusters`) |
| Officials dashboard | `https://main.dy95ki8l9ef8x.amplifyapp.com` (needs the dashboard key) |
| Public cluster page | `https://main.dy95ki8l9ef8x.amplifyapp.com/public` |

### Try it without five phones

```bash
python scripts/fake_reports.py --near 22.7196,75.8577 --phones 5 --sick 2 --check   # makes an Alert
python scripts/fake_reports.py --clean                                              # removes all fake data
```

Fake reports use made-up phone hashes, so nobody is messaged. To get the official emails, subscribe an address to the `WardEngineerTopicArn` and `HealthOfficerTopicArn` stack outputs (SNS console → Subscriptions → Create subscription → Email) and confirm it. For a demo of escalation, deploy with `--parameter-overrides EscalateAfterMin=10`.

If Bedrock is unavailable, the worker falls back to keyword extraction (`src/agent/fallback.py`) so reports, clusters and alerts keep working. To run the model calls through another account, deploy with `--parameter-overrides BedrockRoleArn=<role arn>`.

## Working together

- Small pull requests into `main`. Whoever merges deploys.
- The shared records in `src/common/models.py` are the contract between the three of us. Change a field only after telling the team.
- No secrets in code, commits, chat or screenshots.

## Team

Team Crystal Red: J Lokesh Rao, Jaya Ruthvik Parasu, Shrikar Tadkasat.
