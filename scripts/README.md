# scripts

- `deploy_backend.py`: build the layer if needed, `sam build` and `sam deploy` (add `--layer` after changing `layer/requirements.txt`)
- `deploy_dashboard.py`: build the dashboard and publish it on Amplify Hosting
- `build_layer.py`: build the Lambda dependencies layer for Linux, even from Windows
- `fake_reports.py`: insert test reports near a point without real phones; `--clean` removes them
- `replay.py`: SIMULATION of the Indore outbreak through the real cluster rule; `--load` / `--clean` (see `docs/replay.md`)
- `eval_extraction.py`: score extraction on `data/test_messages.jsonl` (see `docs/eval.md`)
- `pick_model.py`: check which Bedrock models answer through a cross-account role (`--role-arn`), and score them
- `make_app_icons.py`: draw the app icons in `dashboard/public/icons/`
