# dashboard

Owner: C (Dashboard & story)

React + MapLibre on AWS Amplify Hosting, with Amazon Location map tiles.

- Live: https://main.dy95ki8l9ef8x.amplifyapp.com (officials, needs the dashboard key)
- Public: https://main.dy95ki8l9ef8x.amplifyapp.com/public (no key)

## Run locally

```bash
cp .env.example .env.local      # fill in VITE_LOCATION_KEY, or leave it empty for OpenFreeMap tiles
npm install
npm run dev                     # http://localhost:5173
```

The dashboard key is typed in on the passcode screen and kept only in that browser tab.
Get it with `aws ssm get-parameter --profile paani --name /paanialert/dashboard_key --with-decryption --query Parameter.Value --output text`.

## Deploy

```bash
python ../scripts/deploy_dashboard.py
```

It builds with the stack's API URL and the map key, uploads `dist/` to Amplify and waits until it's live.

## What's here

- `src/App.jsx`: passcode screen, officials view (map, clusters with Acknowledge / Fixed / False alarm, reports), public page at `/public`
- `src/MapView.jsx`: MapLibre map; clusters drawn ~500 m wide, reports as dots (red ring = someone sick)
- `src/api.js`: calls to the dashboard API; refreshes every 30 seconds

The map loads MapLibre's worker from our own origin (`setWorkerUrl`) because the Amazon Location key only accepts requests whose Referer is the dashboard's URL.
