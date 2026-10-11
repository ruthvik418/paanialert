# worker

Owner: B (Agent & WhatsApp)

Reads one message at a time from SQS, runs the agent in `src/agent/`, and sends the reply with `common/twilio_send.py`. Voice notes are transcribed first (`agent/voice.py`) and handled like typed text. Web voice reports queued by `POST /app/report` come through the same queue; their reply is written to the AppRequests table for the page to poll.
