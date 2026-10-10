// The officials' status vocabulary, drawn the same way everywhere (lists, details, Activity log, legend).
// Colour always comes with an icon and a word, never on its own. Colours: theme.js / styles.css.
import { ArrowUp, CheckCircle, Circle, Clock, DeviceMobile, Envelope, Eye, Info, Warning, WarningCircle, WarningOctagon, XCircle } from "@phosphor-icons/react";

const LEVEL_ICON = { alert: WarningOctagon, watch: Eye, none: Info };
const STATUS_ICON = { open: Circle, acknowledged: Eye, fixed: CheckCircle, false_alarm: XCircle, expired: Clock };

export function LevelBadge({ level, children }) {
  const Icon = LEVEL_ICON[level] || Info;
  return <span className={`severity ${level}`}><Icon size={14} weight="fill" aria-hidden="true" />{children}</span>;
}

export function StatusBadge({ status, children }) {
  const Icon = STATUS_ICON[status] || Circle;
  return <span className={`status ${status}`}><Icon size={14} weight={status === "open" ? "bold" : "fill"} aria-hidden="true" />{children}</span>;
}

// An official warning: red outline (boil) or solid red (don't use), like its circle on the map.
export function WarningBadge({ kind, lifted, children }) {
  return <span className={`warning-badge ${kind}${lifted ? " lifted" : ""}`}><Warning size={14} weight={kind === "do_not_use" ? "fill" : "bold"} aria-hidden="true" />{children}</span>;
}

export function AppIcon({ size = 14 }) {
  return <DeviceMobile size={size} weight="bold" aria-hidden="true" />;
}

// Tone and icon of one Activity log row.
export function activityTone(row) {
  if (row.ok === false) return ["alert", WarningCircle];
  switch (row.kind) {
    case "level": return row.level === "alert" ? ["alert", WarningOctagon] : ["watch", Eye];
    case "warning_issued": case "warning": case "advisory": return ["warning", Warning];
    case "warning_lifted": case "warning_all_clear": case "all_clear": return ["fixed", CheckCircle];
    case "status": return row.status === "fixed" ? ["fixed", CheckCircle] : row.status === "false_alarm" ? ["false_alarm", XCircle] : ["neutral", Eye];
    case "report_status": return row.status === "resolved" ? ["fixed", CheckCircle] : row.status === "false_report" ? ["false_alarm", XCircle] : ["neutral", Eye];
    case "sns": return ["neutral", Envelope];
    case "escalated": return ["watch", ArrowUp];
    default: return ["neutral", Circle];
  }
}
