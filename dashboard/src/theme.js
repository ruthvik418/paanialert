// One status colour system for every surface: badges, lists, the Activity log, and the map.
// The same values are CSS variables in styles.css (dark, officials) and resident.css (light, residents).
//   watch = amber, alert = red, fixed / all clear = green, false alarm = grey, warning = red outline.

export const THEMES = {
  dark: {
    watch: "#e2b15b",
    alert: "#f0776b",
    fixed: "#6fc48e",
    falseAlarm: "#8f9c99",
    warning: "#f0776b",
    report: "#d3dcda",      // a resident's report: neutral, so it never reads as a status
    pin: "#5fb9d6",
  },
  light: {
    watch: "#b7791f",
    alert: "#c0352b",
    fixed: "#1f7a46",
    falseAlarm: "#6b716f",
    warning: "#c0352b",
    report: "#41484a",
    pin: "#1a5fb4",         // the water-blue accent
  },
};

// The page decides the theme: the officials' dashboard is dark, the resident pages are light.
export function pageTheme(path = window.location.pathname) {
  const p = path.replace(/\/$/, "");
  return p === "/report" || p === "/public" ? "light" : "dark";
}
