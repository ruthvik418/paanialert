// Text helpers. Each takes the translate function `t` from useLang().

export function ago(iso, t) {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (mins < 1) return t("justNow");
  if (mins < 60) return t("minsAgo", { n: mins });
  const hours = Math.round(mins / 60);
  if (hours < 48) return t("hoursAgo", { n: hours });
  return t("daysAgo", { n: Math.round(hours / 24) });
}

export const levelLabel = (level, t) => t(`level_${level}`);
export const statusLabel = (status, t) => t(`status_${status}`);

export function describeReport(r, t) {
  const parts = [];
  if (["sewage", "chemical", "other"].includes(r.smell)) parts.push(t(`smell_${r.smell}`));
  if (["yellow", "brown", "black", "cloudy"].includes(r.colour)) parts.push(t(`colour_${r.colour}`));
  if (["salty", "bad"].includes(r.taste)) parts.push(t(`taste_${r.taste}`));
  if (r.since_days != null) parts.push(r.since_days === 1 ? t("oneDay") : t("nDays", { n: r.since_days }));
  return parts.join(" · ") || t("detailsUnclear");
}

export function sickLabel(r, t) {
  if (r.sick_count == null) return t("sickNotAsked");
  if (r.sick_count === 0) return t("nobodySick");
  const symptoms = (r.symptoms || []).map((s) => t(`symptom_${s}`)).join(", ");
  return t("nSick", { n: r.sick_count }) + (symptoms ? ` (${symptoms})` : "");
}
