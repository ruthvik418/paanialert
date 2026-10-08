# cluster

Owner: A (Backend & alerts)

`rule.py` holds the cluster rule as a pure function, `evaluate(reports, now)`, so tests and the Indore replay can reuse it. `app.py` runs it every 15 minutes and sends alerts on changes.
