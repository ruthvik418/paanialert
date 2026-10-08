# Running the agent's model calls through a friend's AWS account

Bedrock is blocked on our team account (908027384294) until an overdue invoice clears. A friend's account can run just the model calls through a **cross-account role**: their account lets our worker call Bedrock, no keys are shared, and they can switch it off any time by deleting the role. Everything else (reports, phone numbers, alerts) stays in our account. The model calls are billed to their account, usually a few cents for the whole weekend, so ask them first.

## Which models

From the models the friend's account can use:

| Order | Model | Why |
|---|---|---|
| 1 | **Llama 4 Maverick 17B** (`us.meta.llama4-maverick-17b-instruct-v1:0`) | Officially supports Hindi, reads images (water photos, TDS meters), fast and cheap, supports tool calls |
| 2 | **DeepSeek V3.1** (`deepseek.v3-v1:0`) | Strongest text reasoning on the list, good with Hinglish; no images |

Not chosen: Kimi K2 Thinking (thinks before every answer, too slow for WhatsApp), Qwen3 Coder and Devstral (built for code), DeepSeek R1 (no tool calls), Llama 3 / Mistral 7B / Mixtral (older and weaker), Voxtral (speech models; could later replace Transcribe for voice notes).

These are set by the `ModelIds` and `BedrockRegion` stack parameters (defaults: the two above, `us-west-2`). `scripts/pick_model.py` checks which ones actually work and scores them on our 50 test messages before you rely on them.

## Steps for the friend (5 minutes, in their AWS console)

1. **IAM → Roles → Create role → Custom trust policy**, and paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::908027384294:role/paanialert-WorkerFunctionRole-li4AvAGWhyxH",
          "arn:aws:iam::908027384294:user/ruthvik-dev"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

   This trusts only our WhatsApp worker and Ruthvik's login (for testing), not our whole account.

2. **Next → skip the managed policies → name it `PaaniAlertBedrockInvoke` → Create role.**

3. Open the role → **Add permissions → Create inline policy → JSON**, paste, and name it `bedrock-invoke`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "*"
    }
  ]
}
```

4. Send us the role's **ARN** (top of the role page), e.g. `arn:aws:iam::123456789012:role/PaaniAlertBedrockInvoke`. An ARN is an identifier, not a secret.

5. Tell us which **region** the models show up in (Bedrock console, top right), if it isn't `us-west-2`.

## Then, on our side

Check the models and pick the best (uses Ruthvik's `paani` login to step into the role):

```bash
py -3.12 scripts/pick_model.py --role-arn <ROLE ARN> --region us-west-2 --eval
```

Save the settings so every future deploy keeps them. In `samconfig.toml`, under `[default.deploy.parameters]`, add the line the script prints, for example:

```toml
parameter_overrides = "BedrockRoleArn=\"arn:aws:iam::123456789012:role/PaaniAlertBedrockInvoke\" BedrockRegion=\"us-west-2\" ModelIds=\"us.meta.llama4-maverick-17b-instruct-v1:0,deepseek.v3-v1:0\""
```

Then deploy:

```bash
py -3.12 scripts/deploy_backend.py
```

When our own account is unblocked, delete that `parameter_overrides` line, redeploy, and the friend can delete the role.

## Privacy note for the writeup

With this setup, message text is processed in the friend's account in the chosen region (outside India for `us-west-2`). Phone numbers are never sent to the model; reports are stored only in our account in Mumbai.
