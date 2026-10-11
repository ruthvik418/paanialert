# agent

Owner: B (Agent & WhatsApp)

Reading a resident's message: the extraction and chat prompts and every fixed reply (`prompts.py`), model calls on Amazon Bedrock with Strands structured output (`runner.py`), the keyword fallback when no model answers (`fallback.py`), saving the report (`reports.py`), copying WhatsApp media to S3 (`media.py`), and voice-note transcription with Amazon Transcribe (`voice.py`).
