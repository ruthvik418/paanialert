# dashboard

Owner: C (Dashboard & story)

React + MapLibre on AWS Amplify Hosting. The officials view reads the existing PaaniAlert API.

- Live: https://main.dy95ki8l9ef8x.amplifyapp.com (officials, needs the dashboard key)
- Public: https://main.dy95ki8l9ef8x.amplifyapp.com/public (no key)

## Run locally

```bash
cp .env.example .env.local      # API URL is public; the map key is optional
npm install
npm run dev                     # http://localhost:5173
```

The existing officials API accepts a shared `x-dashboard-key`. It is entered on the passcode screen and stored in session storage for that tab. It is not bundled into JavaScript, but it is sent with browser API requests and is visible to that signed-in browser. Restrict it to trusted administrators. This backend does not currently provide user identities or server-issued sessions; replacing the shared key requires a backend authentication change.
Get it with `aws ssm get-parameter --profile paani --name /paanialert/dashboard_key --with-decryption --query Parameter.Value --output text`.

With `VITE_LOCATION_KEY` empty, the map uses OpenFreeMap's public Dark style, with attribution supplied by MapLibre. An optional browser-restricted Amazon Location key can be set for production tiles. Never put the dashboard key, AWS credentials, or other privileged secrets in `VITE_*` variables.

## Deploy

```bash
python ../scripts/deploy_dashboard.py
```

It builds with the stack's API URL and the map key, uploads `dist/` to Amplify and waits until it's live.

## What's here

- `src/App.jsx`: passcode screen and public cluster page at `/public`
- `src/OperationsDashboard.jsx`: officials command centre, incident search and filters, workflow actions, metrics, notification history and activity log
- `src/MapView.jsx`: MapLibre map; clusters drawn ~500 m wide, reports as dots (red ring = someone sick)
- `src/api.js`: existing API calls; dashboard data refreshes every 15 seconds

The map loads MapLibre's worker from our own origin (`setWorkerUrl`) because the Amazon Location key only accepts requests whose Referer is the dashboard's URL.
