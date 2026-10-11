// Screenshots of /report, /public and the officials' dashboard with made-up data, for design reviews.
//
//   npm run build && npx vite preview --port 4173 &
//   node scripts/screenshots.mjs ../docs/screenshots/after [--lang hi]
//
// The API is never called: every fetch is answered from the fixtures below, which follow
// scripts/fake_reports.py (same names, Hinglish/Hindi messages, reports jittered around a point).
// Uses the installed Chrome (channel "chrome"), so Playwright doesn't download a browser.
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE_URL || "http://localhost:4173";
const OUT = process.argv[2] || "screenshots";
const LANG = process.argv.includes("--lang") ? process.argv[process.argv.indexOf("--lang") + 1] : "en";
const SIZES = { phone: { width: 360, height: 780 }, desktop: { width: 1440, height: 900 } };

/* Fixtures */

let seed = 7;
const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const pick = (xs) => xs[Math.floor(rand() * xs.length)];
const minsAgo = (m) => new Date(Date.now() - m * 60000).toISOString();
const NAMES = ["Sunita Verma", "Ramesh Yadav", "Pooja Sharma", "Imran Khan", "Kavita Patel", "Rajesh Malviya",
  "Anita Joshi", "Mohd. Salim", "Neha Rathore", "Suresh Chouhan", "Rekha Solanki", "Arjun Mehta"];
const COLOUR_WORDS = { hinglish: { yellow: "peela", brown: "bhura", cloudy: "gandla" }, hi: { yellow: "पीला", brown: "भूरा", cloudy: "मटमैला" } };

function message(lang, smell, colour, days, sick) {
  const c = COLOUR_WORDS[lang][colour];
  if (lang === "hi") return `नल का पानी ${c} आ रहा है${smell === "sewage" ? ", गटर जैसी बदबू है" : ", अजीब गंध है"}, ${days} दिन से।${sick ? " बच्चे को उल्टी दस्त हो रहे हैं।" : " पीने लायक नहीं है।"}`;
  return `Nal ka paani ${c} aa raha hai${smell === "sewage" ? ", gutter jaisi badboo hai" : ", ajeeb smell hai"}, ${days} din se.${sick ? " Bete ko loose motion ho rahe hain." : " Peene layak nahi hai."}`;
}

function jitter(lat, lon, metres) {
  const a = rand() * 2 * Math.PI, d = rand() * metres;
  return [lat + (d * Math.cos(a)) / 111320, lon + (d * Math.sin(a)) / (111320 * Math.cos((lat * Math.PI) / 180))];
}

let n = 0;
function reports(lat, lon, area, count, sick, startMins) {
  return Array.from({ length: count }, (_, i) => {
    const [rlat, rlon] = jitter(lat, lon, 300);
    const smell = pick(["sewage", "sewage", "other"]), colour = pick(["yellow", "brown", "cloudy"]);
    const days = 1 + Math.floor(rand() * 3), lang = pick(["hinglish", "hinglish", "hi"]), isSick = i < sick;
    n += 1;
    return {
      report_id: `fake-${(0x5a3c1e + n * 7919).toString(16)}`, created_at: minsAgo(startMins + i * 37),
      lat: +rlat.toFixed(6), lon: +rlon.toFixed(6), area, smell, colour, taste: "unknown", since_days: days,
      sick_count: isSick ? 1 + (i % 2) : 0, symptoms: isSick ? ["diarrhoea", "vomiting"] : [], lang, source: "pipe",
      text: message(lang, smell, colour, days, isSick), profile_name: NAMES[n % NAMES.length], phone_masked: "+91 98•••••210",
      extracted_by: n % 5 === 0 ? "keywords" : "agent:apac.amazon.nova-lite-v1:0", channel: n % 3 === 0 ? "app" : "whatsapp",
      status: n === 2 ? "reviewing" : "new",
    };
  });
}

const A = reports(22.7196, 75.8577, "Rajwada, Indore", 6, 3, 14);
const B = reports(22.7533, 75.8937, "Vijay Nagar, Indore", 3, 0, 160);
const C = reports(28.6519, 77.2315, "Chandni Chowk, Delhi", 2, 0, 600);
const REPORTS = [...A, ...B, ...C];
const CLUSTERS = [
  { cluster_id: "c-indore-rajwada", cells: [], centre_lat: 22.7196, centre_lon: 75.8577, level: "alert", report_count: 6, distinct_phones: 6,
    sick_households: 3, severity: 9.4, status: "open", first_seen: minsAgo(220), alert_at: minsAgo(180), report_ids: A.map((r) => r.report_id) },
  { cluster_id: "c-indore-vijaynagar", cells: [], centre_lat: 22.7533, centre_lon: 75.8937, level: "watch", report_count: 3, distinct_phones: 3,
    sick_households: 0, severity: 3.1, status: "acknowledged", first_seen: minsAgo(260), status_at: minsAgo(90), report_ids: B.map((r) => r.report_id) },
  { cluster_id: "c-delhi-chandni", cells: [], centre_lat: 28.6519, centre_lon: 77.2315, level: "watch", report_count: 2, distinct_phones: 2,
    sick_households: 0, severity: 2.0, status: "fixed", first_seen: minsAgo(1500), status_at: minsAgo(300), report_ids: C.map((r) => r.report_id) },
];
const ADVISORIES = [
  { advisory_id: "adv-1", lat: 22.7196, lon: 75.8577, radius_m: 1000, kind: "boil", created_at: minsAgo(150), status: "active",
    note: "Tanker water at the ward office from 4 pm.", whatsapp_to: ["a", "b", "c", "d"], app_to: ["e", "f"], cluster_id: "c-indore-rajwada" },
  { advisory_id: "adv-0", lat: 22.7533, lon: 75.8937, radius_m: 500, kind: "do_not_use", created_at: minsAgo(2000), status: "lifted",
    lifted_at: minsAgo(1400), whatsapp_to: ["a", "b"], app_to: [] },
];
const ACTIVITY = [
  { activity_id: "a9", at: minsAgo(20), kind: "report_status", status: "reviewing", note: "Engineer visiting at 5 pm", ip: "10.0.4.12" },
  { activity_id: "a8", at: minsAgo(150), kind: "warning_issued", cluster_id: "c-indore-rajwada", warning: "boil", radius_m: 1000, recipients: 6, ip: "10.0.4.12" },
  { activity_id: "a7", at: minsAgo(150), kind: "warning", cluster_id: "c-indore-rajwada", channel: "whatsapp", to: "4 subscribers", ok: true },
  { activity_id: "a6", at: minsAgo(150), kind: "warning", cluster_id: "c-indore-rajwada", channel: "push", to: "2 devices", ok: false, error: "subscription expired" },
  { activity_id: "a5", at: minsAgo(180), kind: "sns", cluster_id: "c-indore-rajwada", to: "ward", ok: true },
  { activity_id: "a4", at: minsAgo(180), kind: "advisory", cluster_id: "c-indore-rajwada", channel: "whatsapp", ok: true },
  { activity_id: "a3", at: minsAgo(181), kind: "level", cluster_id: "c-indore-rajwada", level: "alert", report_count: 6 },
  { activity_id: "a2", at: minsAgo(90), kind: "status", cluster_id: "c-indore-vijaynagar", status: "acknowledged", ip: "10.0.4.12" },
  { activity_id: "a1", at: minsAgo(250), kind: "level", cluster_id: "c-indore-vijaynagar", level: "watch", report_count: 3 },
];
const REPLY = {
  en: "✅ Report saved: yellow water, sewage smell, for 2 days, 2 sick at home.\n\nPlease boil drinking water for at least 1 minute. Give ORS for loose motions. Blood in stool or signs of dehydration: call 108.",
  hi: "✅ शिकायत दर्ज: पीला पानी, बदबू, 2 दिन से, घर में 2 बीमार।\n\nपीने का पानी कम से कम 1 मिनट उबालकर पिएं। दस्त हो तो ORS दें। मल में खून या पानी की कमी के लक्षण हों तो 108 पर कॉल करें।",
};

// Step 2 on /report: the device location (granted, at Rajwada), then the zoom-in.
async function useMyLocation(page) {
  await page.locator("fieldset.rs-step").nth(1).locator(".rs-button-secondary").click();
  await page.waitForTimeout(1500);
}

function answer(path, method) {
  if (path === "/health") return { ok: true };
  if (path === "/reports") return { reports: REPORTS };
  if (path === "/clusters") return { clusters: CLUSTERS };
  if (path === "/activity") return { activity: ACTIVITY };
  if (path === "/advisories" && method === "GET") return { advisories: ADVISORIES };
  if (path === "/advisories/preview") return { total: 41, whatsapp: 33, app: 8, cells: 4 };
  if (path === "/public/clusters") return { clusters: CLUSTERS.filter((c) => ["open", "acknowledged"].includes(c.status)).map((c) => ({
    level: c.level, lat: +c.centre_lat.toFixed(3), lon: +c.centre_lon.toFixed(3), report_count: c.report_count,
    sick_households: c.sick_households, status: c.status, first_seen: c.first_seen, alert_at: c.alert_at || null })) };
  if (path === "/public/advisories") return { advisories: ADVISORIES.filter((a) => a.status === "active").map(({ lat, lon, radius_m, kind, created_at }) => ({ lat, lon, radius_m, kind, created_at })) };
  if (path === "/app/area") return { area: "Rajwada, Indore" };
  if (path === "/app/report") return { reply: REPLY[LANG] || REPLY.en, report_id: "fake-new", saved: true };
  return null;
}

/* Shots */

const SHOTS = [
  { name: "report", path: "/report" },
  { name: "report-sent", path: "/report", sizes: ["phone", "desktop"], async act(page) {
    // Fill in the form the same way in the old and new design: words, then the map centre, then Send.
    const box = page.locator("textarea").first();
    if (await page.locator(".rs-tile").count()) {
      // Tap-to-report: yellow water, bad smell, 2 people sick.
      await page.locator(".rs-tile").nth(1).click();
      await page.locator(".rs-swatch").first().click();
      await page.locator(".rs-tile").nth(0).click();
      await page.locator(".rs-tile").nth(3).click();
      await page.locator(".rs-stepper button").nth(1).click();
    } else {
      await box.fill("Nal ka paani peela aa raha hai, badboo hai, 2 din se. 2 log bimar.");
    }
    await useMyLocation(page);
    await page.locator("button[type=submit]").click();
    await page.waitForTimeout(800);
  } },
  { name: "report-tiles", path: "/report", sizes: ["phone"], after: true, async act(page) {
    await page.locator(".rs-tile").nth(1).click();
    await page.locator(".rs-swatch").first().click();
    await page.locator(".rs-tile").nth(0).click();
    await page.locator(".rs-tile").nth(3).click();
    await page.locator(".rs-stepper button").nth(1).click();
    await useMyLocation(page);
  } },
  { name: "public", path: "/public" },
  { name: "dashboard", path: "/" },
  { name: "dashboard-incident", path: "/", sizes: ["desktop"], async act(page) {
    await page.locator(".nav-item", { hasText: "Live incidents" }).click();
    await page.locator(".queue-select").first().click();
    await page.waitForTimeout(1200);
  } },
  { name: "dashboard-warning", path: "/", sizes: ["desktop"], async act(page) {
    await page.locator(".nav-item", { hasText: "Live incidents" }).click();
    await page.locator(".queue-select").first().click();
    await page.locator("button", { hasText: "Issue Warning" }).first().click();
    await page.waitForTimeout(1500);
  } },
  { name: "dashboard-activity", path: "/", sizes: ["desktop"], async act(page) {
    await page.locator(".nav-item", { hasText: "Activity log" }).click();
    await page.waitForTimeout(600);
  } },
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
const redesigned = !process.argv.includes("--before");
for (const shot of SHOTS.filter((s) => redesigned || !s.after)) {
  for (const size of shot.sizes || ["phone", "desktop"]) {
    const context = await browser.newContext({ viewport: SIZES[size], deviceScaleFactor: 1, serviceWorkers: "block",
      geolocation: { latitude: 22.7196, longitude: 75.8577 }, permissions: ["geolocation"], locale: LANG === "hi" ? "hi-IN" : "en-IN" });
    await context.addInitScript(([lang]) => {
      sessionStorage.setItem("paanialert-dashboard-key", "screenshot-key");
      localStorage.setItem("paanialert-lang", lang);
      localStorage.setItem("paanialert-last-pin", JSON.stringify({ lat: 22.7201, lon: 75.8581 }));   // inside the active warning
    }, [LANG]);
    const page = await context.newPage();
    await page.route("**/*", (route) => {
      const req = route.request();
      // The API: same origin when VITE_API_URL is empty, otherwise API Gateway. Map tiles pass through.
      const api = req.url().startsWith(BASE) || new URL(req.url()).hostname.includes(".execute-api.");
      if (!["fetch", "xhr"].includes(req.resourceType()) || !api) return route.continue();
      const body = answer(new URL(req.url()).pathname, req.method());
      return body ? route.fulfill({ json: body }) : route.fulfill({ status: 404, json: { error: "not in fixtures" } });
    });
    await page.goto(BASE + shot.path, { waitUntil: "load" });
    await page.waitForTimeout(6000);   // map tiles and the fit-to-data animation
    if (shot.act) await shot.act(page);
    const file = join(OUT, `${shot.name}-${size === "phone" ? "360" : "1440"}${LANG === "en" ? "" : `-${LANG}`}.png`);
    await page.screenshot({ path: file, fullPage: size === "phone" && !shot.name.startsWith("dashboard-") });
    console.log("saved", file);
    await context.close();
  }
}
await browser.close();
