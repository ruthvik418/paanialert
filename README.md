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

All Lambda functions share one code folder (`src/`) and one `src/requirements.txt`, so anything in `src/common/` can be imported everywhere.

## Getting started

Prerequisites: Git, Python 3.12, Node.js 20, AWS CLI v2, AWS SAM CLI, and an AWS profile named `paani` for region `ap-south-1`.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

Secrets live in SSM Parameter Store, never in this repo:

```bash
aws ssm put-parameter --profile paani --type SecureString --name /paanialert/twilio_account_sid --value <sid>
aws ssm put-parameter --profile paani --type SecureString --name /paanialert/twilio_auth_token --value <token>
aws ssm put-parameter --profile paani --type SecureString --name /paanialert/hmac_secret --value <random hex>
aws ssm put-parameter --profile paani --type SecureString --name /paanialert/dashboard_key --value <random hex>
```

Deploy:

```bash
sam build
sam deploy --guided --profile paani   # first time; afterwards just `sam deploy`
```

The stack output `ApiUrl` plus `/health` should return `{"ok": true}`.

## Working together

- Small pull requests into `main`. Whoever merges deploys.
- The shared records in `src/common/models.py` are the contract between the three of us. Change a field only after telling the team.
- No secrets in code, commits, chat or screenshots.

## Team

Team Crystal Red: J Lokesh Rao, Jaya Ruthvik Parasu, Shrikar Tadkasat.
