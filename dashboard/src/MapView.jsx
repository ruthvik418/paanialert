import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl/dist/maplibre-gl-csp";
import workerUrl from "maplibre-gl/dist/maplibre-gl-csp-worker.js?url";
import { Crosshair, WarningCircle } from "@phosphor-icons/react";
import { THEMES } from "./theme.js";

// Load MapLibre's tile worker from our own origin instead of a blob: URL. Tile requests come
// from that worker, and the Amazon Location key only accepts requests whose Referer is our site.
maplibregl.setWorkerUrl(workerUrl);

const KEY = import.meta.env.VITE_LOCATION_KEY;
const REGION = import.meta.env.VITE_LOCATION_REGION || "ap-south-1";
// Dark for the officials' dashboard, light for the resident pages (readable in sunlight).
const styleFor = (theme) => (KEY
  ? `https://maps.geo.${REGION}.amazonaws.com/v2/styles/Standard/descriptor?key=${KEY}&color-scheme=${theme === "light" ? "Light" : "Dark"}`
  : `https://tiles.openfreemap.org/styles/${theme === "light" ? "positron" : "dark"}`);

// "all" fits the map to every report and cluster; with none yet it shows all of India.
export const PLACES = {
  all: { center: [78.9, 22.5], zoom: 4 },
  indore: { center: [75.8577, 22.7196], zoom: 12 },
  delhi: { center: [77.209, 28.6139], zoom: 11 },
};

// Cluster colour by level, or grey once it's closed as a false alarm, green once fixed.
const clusterColour = (c) => ["case",
  ["==", ["get", "status"], "fixed"], c.fixed,
  ["==", ["get", "status"], "false_alarm"], c.falseAlarm,
  ["match", ["get", "level"], "alert", c.alert, "watch", c.watch, c.falseAlarm]];

// A cluster covers roughly 500 m; this keeps the circle that size on the ground at any zoom.
const RADIUS_500M = ["interpolate", ["exponential", 2], ["zoom"], 10, 3.5, 18, 887];

function toGeoJSON(items, props) {
  return {
    type: "FeatureCollection",
    features: items
      .filter((i) => Number.isFinite(props.lat(i)) && Number.isFinite(props.lon(i)) && Math.abs(props.lat(i)) <= 90 && Math.abs(props.lon(i)) <= 180)
      .map((i) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [props.lon(i), props.lat(i)] },
        properties: props.fields(i),
      })),
  };
}

// `focus` = {key, lon, lat, title, lines}: fly there and open a card. A new key re-triggers it.
// Pick mode (the report page): `onPick({lat, lon})` on a tap or the "use map centre" button,
// `pin` = {lat, lon, fly} shows a marker there (and flies to it when fly is true).
// `circles` = [{id, lat, lon, radius_m, kind: "boil"|"do_not_use", draft}]: warning areas; a draft is dashed.
// `fitCircle` = one of them to zoom to (when its id or radius changes).
// `theme` = "dark" | "light": map style and status colours (theme.js).
export default function MapView({ reports = [], clusters = [], circles = [], fitCircle, place = "all", label = "Map", focus, onSelectCluster, onSelectReport, onPick, pin, pickCentreLabel, theme = "dark", failedText }) {
  const box = useRef(null);
  const [mapFailed, setMapFailed] = useState(false);
  const map = useRef(null);
  const popup = useRef(null);
  const ready = useRef(false);
  const fitted = useRef(false);
  const marker = useRef(null);
  const latest = useRef({ reports, clusters, circles, place, onSelectCluster, onSelectReport, onPick });
  latest.current = { reports, clusters, circles, place, onSelectCluster, onSelectReport, onPick };

  useEffect(() => {
    const c = THEMES[theme];
    const m = new maplibregl.Map({
      container: box.current,
      style: styleFor(theme),
      center: PLACES[place].center,
      zoom: PLACES[place].zoom,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    // Only a style that can't load means "no map". A missing tile, glyph or a layer error isn't a dead map.
    m.on("error", (e) => { if (!ready.current && !e.sourceId && !e.tile && !m.isStyleLoaded()) setMapFailed(true); });
    m.on("load", () => {
      setMapFailed(false);
      m.getContainer().querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      m.addSource("clusters", { type: "geojson", data: toGeoJSON([], clusterProps) });
      m.addSource("reports", { type: "geojson", data: toGeoJSON([], reportProps) });
      m.addSource("circles", { type: "geojson", data: circlesGeoJSON([]) });
      // Warnings: a red outline (dashed while it's a draft); "don't use" gets a stronger fill than "boil".
      m.addLayer({
        id: "circles-fill", type: "fill", source: "circles",
        paint: { "fill-color": c.warning, "fill-opacity": ["case", ["get", "draft"], 0.14, ["==", ["get", "kind"], "do_not_use"], 0.14, 0.06] },
      });
      // line-dasharray can't depend on data, so issued and draft circles are two layers.
      m.addLayer({
        id: "circles-line", type: "line", source: "circles", filter: ["!", ["get", "draft"]],
        paint: { "line-color": c.warning, "line-width": 2.5 },
      });
      m.addLayer({
        id: "circles-draft", type: "line", source: "circles", filter: ["get", "draft"],
        paint: { "line-color": c.warning, "line-width": 2.5, "line-dasharray": [2, 1.5] },
      });
      m.addLayer({
        id: "clusters", type: "circle", source: "clusters",
        paint: {
          "circle-radius": RADIUS_500M,
          "circle-color": clusterColour(c),
          "circle-opacity": ["case", ["get", "closed"], 0.1, 0.24],
          "circle-stroke-color": clusterColour(c),
          "circle-stroke-width": 2,
        },
      });
      m.addLayer({
        id: "reports", type: "circle", source: "reports",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 4, 16, 8],
          "circle-color": c.report,
          "circle-stroke-color": ["case", ["get", "sick"], c.alert, theme === "light" ? "#ffffff" : "#0d1212"],
          "circle-stroke-width": ["case", ["get", "sick"], 3, 1.5],
        },
      });
      m.on("click", (e) => latest.current.onPick?.({ lat: e.lngLat.lat, lon: e.lngLat.lng }));
      m.on("click", "clusters", (e) => latest.current.onSelectCluster?.(e.features[0].properties.cluster_id));
      m.on("click", "reports", (e) => latest.current.onSelectReport?.(e.features[0].properties.report_id));
      for (const id of ["clusters", "reports"]) {
        m.on("mouseenter", id, () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", id, () => (m.getCanvas().style.cursor = ""));
      }
      ready.current = true;
      push(m, latest.current);
      if (latest.current.place === "all") fitted.current = fitAll(m, latest.current);
    });
    // The box can change size after the map starts (fonts, a warning banner, panels): keep the canvas filling it.
    const resize = new ResizeObserver(() => m.resize());
    resize.observe(box.current);
    map.current = m;
    return () => { resize.disconnect(); ready.current = false; m.remove(); };
    // The map is created once; data and place changes are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!map.current || !ready.current) return;
    push(map.current, { reports, clusters, circles });
    // Zoom to the data the first time it arrives, so a report from anywhere is on screen.
    if (place === "all" && !fitted.current) fitted.current = fitAll(map.current, { reports, clusters });
  }, [reports, clusters, circles]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const m = map.current;
    if (!fitCircle || !m) return;
    const fit = () => {
      const ring = circleRing(fitCircle);
      const bounds = ring.reduce((b, p) => b.extend(p), new maplibregl.LngLatBounds(ring[0], ring[0]));
      m.fitBounds(bounds, { padding: 40, duration: 700 });
    };
    if (ready.current) fit(); else m.once("load", fit);
  }, [fitCircle?.id, fitCircle?.radius_m]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map.current || !ready.current) return;
    if (place === "all") fitAll(map.current, latest.current);
    else map.current.flyTo({ center: PLACES[place].center, zoom: PLACES[place].zoom });
  }, [place]);

  useEffect(() => {
    const m = map.current;
    if (!focus || !m) return;
    const show = () => {
      m.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(m.getZoom(), 14), duration: 1200 });
      popup.current?.remove();
      const card = document.createElement("div");
      card.className = "map-popup";
      const title = document.createElement("strong");
      title.textContent = focus.title;
      card.appendChild(title);
      for (const line of focus.lines.filter(Boolean)) {
        const row = document.createElement("div");
        row.textContent = line; // user-sent text: never inserted as HTML
        card.appendChild(row);
      }
      popup.current = new maplibregl.Popup({ maxWidth: "280px", offset: 12 })
        .setLngLat([focus.lon, focus.lat]).setDOMContent(card).addTo(m);
    };
    if (ready.current) show(); else m.once("load", show);
  }, [focus?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (!pin) { marker.current?.remove(); marker.current = null; return; }
    if (!marker.current) marker.current = new maplibregl.Marker({ color: THEMES[theme].pin });
    marker.current.setLngLat([pin.lon, pin.lat]).addTo(m);
    if (pin.fly) m.flyTo({ center: [pin.lon, pin.lat], zoom: Math.max(m.getZoom(), 15), duration: 900 });
  }, [pin?.lat, pin?.lon, pin?.fly]); // eslint-disable-line react-hooks/exhaustive-deps

  function pickCentre() {
    const c = map.current?.getCenter();
    if (c) onPick?.({ lat: c.lat, lon: c.lng });
  }

  return <><div ref={box} className="map" role="region" aria-label={label} />
    {onPick && pickCentreLabel && <span className="map-crosshair" aria-hidden="true" />}
    {onPick && pickCentreLabel && <button type="button" className="map-pick-centre" onClick={pickCentre}><Crosshair size={20} weight="bold" aria-hidden="true" />{pickCentreLabel}</button>}
    {mapFailed && <div className="map-provider-error" role="status"><WarningCircle size={18} weight="bold" aria-hidden="true" /><span><strong>{failedText?.[0] || "Map tiles unavailable"}</strong><span>{failedText?.[1] || "Use the incident list to review locations while the map service is unavailable."}</span></span></div>}</>;
}

const reportProps = {
  lat: (r) => r.lat, lon: (r) => r.lon,
  fields: (r) => ({ report_id: r.report_id, sick: (r.sick_count || 0) > 0 }),
};
const clusterProps = {
  lat: (c) => c.centre_lat ?? c.lat, lon: (c) => c.centre_lon ?? c.lon,
  fields: (c) => ({
    cluster_id: c.cluster_id || "",
    level: c.level,
    status: c.status || "open",
    closed: !["open", "acknowledged"].includes(c.status),
  }),
};

function fitAll(m, { reports, clusters }) {
  const points = [
    ...reports.filter((r) => Number.isFinite(r.lat) && Number.isFinite(r.lon) && Math.abs(r.lat) <= 90 && Math.abs(r.lon) <= 180).map((r) => [r.lon, r.lat]),
    ...clusters.map((c) => [c.centre_lon ?? c.lon, c.centre_lat ?? c.lat]).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y) && Math.abs(x) <= 180 && Math.abs(y) <= 90),
  ];
  if (points.length === 0) {
    m.flyTo({ center: PLACES.all.center, zoom: PLACES.all.zoom });
    return false;
  }
  if (points.length === 1) {
    m.flyTo({ center: points[0], zoom: 13 });
    return true;
  }
  const bounds = points.reduce((b, p) => b.extend(p), new maplibregl.LngLatBounds(points[0], points[0]));
  m.fitBounds(bounds, { padding: 60, maxZoom: 14, duration: 800 });
  return true;
}

// A circle on the ground as a 64-point polygon ring ([lon, lat] pairs).
function circleRing({ lat, lon, radius_m }) {
  const ring = [];
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    ring.push([lon + (radius_m * Math.sin(a)) / (111320 * Math.cos((lat * Math.PI) / 180)), lat + (radius_m * Math.cos(a)) / 111320]);
  }
  return ring;
}

function circlesGeoJSON(circles) {
  return {
    type: "FeatureCollection",
    features: circles.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lon) && c.radius_m > 0).map((c) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [circleRing(c)] },
      properties: { kind: c.kind, draft: Boolean(c.draft) },
    })),
  };
}

function push(m, { reports, clusters, circles = [] }) {
  m.getSource("circles")?.setData(circlesGeoJSON(circles));
  m.getSource("reports")?.setData(toGeoJSON(reports, reportProps));
  m.getSource("clusters")?.setData(toGeoJSON(clusters, clusterProps));
}
