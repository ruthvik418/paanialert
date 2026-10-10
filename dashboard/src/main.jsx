import React from "react";
import { createRoot } from "react-dom/client";
import "maplibre-gl/dist/maplibre-gl.css";
// Self-hosted fonts (no font requests leave the site). Each file only downloads when a page uses it.
// Residents: Mukta, one family for Devanagari and Latin. Officials: IBM Plex Sans (+ Devanagari for Hindi).
import "@fontsource/mukta/400.css";
import "@fontsource/mukta/600.css";
import "@fontsource/mukta/700.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans-devanagari/400.css";
import "@fontsource/ibm-plex-sans-devanagari/600.css";
import "./styles.css";
import "./resident.css";
import App from "./App.jsx";
import { LangProvider } from "./i18n.js";
import { pageTheme } from "./theme.js";

const theme = pageTheme();
document.documentElement.dataset.theme = theme;
document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f6f5f1" : "#0d1212");

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <LangProvider>
      <App />
    </LangProvider>
  </React.StrictMode>
);
