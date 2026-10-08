import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl/dist/maplibre-gl-csp";
import workerUrl from "maplibre-gl/dist/maplibre-gl-csp-worker.js?url";

// Load MapLibre's tile worker from our own origin instead of a blob: URL. Tile requests come
// from that worker, and the Amazon Location key only accepts requests whose Referer is our site.
maplibregl.setWorkerUrl(workerUrl);

const KEY = import.meta.env.VITE_LOCATION_KEY;
const REGION = import.meta.env.VITE_LOCATION_REGION || "ap-south-1";
const STYLE = KEY
  ? `https://maps.geo.${REGION}.amazonaws.com/v2/styles/Standard/descriptor?key=${KEY}&color-scheme=Light`
  : "https://tiles.openfreemap.org/styles/liberty";

export const PLACES = {
  indore: { label: "Indore", center: [75.8577, 22.7196], zoom: 12 },
  delhi: { label: "Delhi", center: [77.209, 28.6139], zoom: 11 },
};

const LEVEL_COLOUR = ["match", ["get", "level"], "alert", "#c62828", "watch", "#e09100", "#7a8794"];

// A cluster covers roughly 500 m; this keeps the circle that size on the ground at any zoom.
const RADIUS_500M = ["interpolate", ["exponential", 2], ["zoom"], 10, 3.5, 18, 887];

function toGeoJSON(items, props) {
  return {
    type: "FeatureCollection",
    features: items
      .filter((i) => props.lat(i) != null && props.lon(i) != null)
      .map((i) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [props.lon(i), props.lat(i)] },
        properties: props.fields(i),
      })),
  };
}

export default function MapView({ reports = [], clusters = [], place = "indore", onSelectCluster, onSelectReport }) {
  const box = useRef(null);
  const map = useRef(null);
  const ready = useRef(false);
  const latest = useRef({ reports, clusters });
  latest.current = { reports, clusters };

  useEffect(() => {
    const m = new maplibregl.Map({
      container: box.current,
      style: STYLE,
      center: PLACES[place].center,
      zoom: PLACES[place].zoom,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("clusters", { type: "geojson", data: toGeoJSON([], clusterProps) });
      m.addSource("reports", { type: "geojson", data: toGeoJSON([], reportProps) });
      m.addLayer({
        id: "clusters", type: "circle", source: "clusters",
        paint: {
          "circle-radius": RADIUS_500M,
          "circle-color": LEVEL_COLOUR,
          "circle-opacity": ["case", ["get", "closed"], 0.12, 0.22],
          "circle-stroke-color": LEVEL_COLOUR,
          "circle-stroke-width": 2,
        },
      });
      m.addLayer({
        id: "reports", type: "circle", source: "reports",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 4, 16, 8],
          "circle-color": "#1f4fd1",
          "circle-stroke-color": ["case", ["get", "sick"], "#c62828", "#ffffff"],
          "circle-stroke-width": ["case", ["get", "sick"], 3, 1.5],
        },
      });
      m.on("click", "clusters", (e) => onSelectCluster?.(e.features[0].properties.cluster_id));
      m.on("click", "reports", (e) => onSelectReport?.(e.features[0].properties.report_id));
      for (const id of ["clusters", "reports"]) {
        m.on("mouseenter", id, () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", id, () => (m.getCanvas().style.cursor = ""));
      }
      ready.current = true;
      push(m, latest.current);
    });
    map.current = m;
    return () => { ready.current = false; m.remove(); };
    // The map is created once; data and place changes are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (map.current && ready.current) push(map.current, { reports, clusters });
  }, [reports, clusters]);

  useEffect(() => {
    if (map.current) map.current.flyTo({ center: PLACES[place].center, zoom: PLACES[place].zoom });
  }, [place]);

  return <div ref={box} className="map" role="region" aria-label="Map of reports and clusters" />;
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
    closed: !["open", "acknowledged"].includes(c.status),
  }),
};

function push(m, { reports, clusters }) {
  m.getSource("reports")?.setData(toGeoJSON(reports, reportProps));
  m.getSource("clusters")?.setData(toGeoJSON(clusters, clusterProps));
}
