export function ago(iso) {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export const LEVEL_LABEL = { alert: "Alert", watch: "Watch", none: "None" };
export const STATUS_LABEL = {
  open: "Open",
  acknowledged: "Acknowledged",
  fixed: "Fixed",
  false_alarm: "False alarm",
  expired: "Expired",
};

export function describeReport(r) {
  const parts = [];
  if (r.smell && r.smell !== "unknown" && r.smell !== "none") parts.push(`${r.smell} smell`);
  if (r.colour && r.colour !== "unknown" && r.colour !== "clear") parts.push(`${r.colour} water`);
  if (r.taste && r.taste !== "unknown" && r.taste !== "normal") parts.push(`${r.taste} taste`);
  if (r.since_days != null) parts.push(`${r.since_days} day${r.since_days === 1 ? "" : "s"}`);
  return parts.join(" · ") || "Details unclear";
}

export function sickLabel(r) {
  if (r.sick_count == null) return "Sick: not asked";
  if (r.sick_count === 0) return "Nobody sick";
  return `${r.sick_count} sick${r.symptoms?.length ? ` (${r.symptoms.join(", ")})` : ""}`;
}
