# worker

Owner: B (Agent & WhatsApp)

Reads one message at a time from SQS, runs the agent in `src/agent/`, and sends the reply with `common/twilio_send.py`.
