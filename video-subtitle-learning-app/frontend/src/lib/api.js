const EXPLICIT_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

function isTauriDesktopRuntime() {
  if (typeof window === "undefined") return false;
  const hostname = window.location.hostname || "";
  const port = window.location.port || "";
  const protocol = window.location.protocol || "";
  const userAgent = typeof navigator !== "undefined" ? navigator.userAgent || "" : "";

  if (protocol === "tauri:" || protocol === "asset:") return true;
  if (hostname === "tauri.localhost" || hostname.endsWith(".tauri.localhost")) return true;
  if ((window.__TAURI_INTERNALS__ || userAgent.includes("Tauri")) && port !== "5173") return true;
  return false;
}

function resolveDefaultApiBaseUrl() {
  if (typeof window === "undefined") return "";
  if (isTauriDesktopRuntime()) return "http://127.0.0.1:8000";
  const protocol = window.location.protocol;
  if (protocol === "http:" || protocol === "https:") return "";
  return "http://127.0.0.1:8000";
}

const API_BASE_URL = EXPLICIT_API_BASE_URL || resolveDefaultApiBaseUrl();

export function apiUrl(path = "") {
  if (!path) return API_BASE_URL || "";
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
}

export function apiFetch(path, options) {
  return fetch(apiUrl(path), options);
}
