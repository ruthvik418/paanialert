# webhook

Owner: A (Backend & alerts)

Twilio calls `POST /whatsapp` here. Validate the Twilio signature, put the message on SQS, and reply instantly with TwiML. The real work happens in `src/worker/`.
