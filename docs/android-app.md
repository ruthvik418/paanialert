# Android app (PWABuilder)

The report page (`/report`) is an installable web app (PWA). PWABuilder wraps it as an Android app
(a Trusted Web Activity): the app opens the live site full screen, so every web deploy updates the app too.

What makes it work, all in `dashboard/public/`:

- `manifest.webmanifest`: name, colours, `start_url` `/report?source=app`, icons (`icons/`, drawn by `scripts/make_app_icons.py`)
- `sw.js`: service worker (push warnings, plus `offline.html` when there's no connection; API calls are never cached)
- `.well-known/assetlinks.json`: proves the app and the site belong together. **A placeholder until step 4.**

`scripts/deploy_dashboard.py` tells Amplify to serve these as real files with the right content types.

## Steps

1. Open https://www.pwabuilder.com, enter `https://main.dy95ki8l9ef8x.amplifyapp.com/report`, press **Start**,
   then **Package for stores → Android → Generate Package**.
2. In the options set **Package ID** to `org.paanialert.app` (app name PaaniAlert). Keep **Signing key: New**.
3. Download the zip. It holds the APK (to install directly), the AAB (for the Play Store), the signing key
   (`signing.keystore` + `signing-key-info.txt`) and an `assetlinks.json`.
   **Keep the signing key safe** (team password manager): every update of the app must be signed with it.
   It is in `.gitignore`; never commit it.
4. Replace `dashboard/public/.well-known/assetlinks.json` with the `assetlinks.json` from the zip, commit it,
   and redeploy:

       python scripts/deploy_dashboard.py

   Check that https://main.dy95ki8l9ef8x.amplifyapp.com/.well-known/assetlinks.json shows the new fingerprint.
   Until this is done the app still works but shows a browser address bar at the top.
5. Install the APK on an Android phone: copy it over (or download it on the phone), open it and allow
   **Install unknown apps** for the app you opened it with (Files or Chrome) when Android asks.

If the address bar still shows after step 4, close the app fully and open it again (Android caches the check);
if it stays, clear the app's storage, or check that the fingerprint in `assetlinks.json` matches
`signing-key-info.txt`.
