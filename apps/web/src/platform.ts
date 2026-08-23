/**
 * Where this build reaches the API, and how it proves who it is.
 *
 * This is the only file that differs in behaviour between platforms, which is
 * the whole point of the architecture: web, desktop and mobile run the same UI
 * and differ in `API_BASE` and auth mode.
 *
 *   web / ios / android  -> a hosted API, session auth
 *   macos / windows / linux -> the engine started as a Tauri sidecar on
 *                              127.0.0.1, authenticated with a loopback token
 *
 * The token is handed to the webview by the shell, never bundled: a secret
 * compiled into a binary is a secret you have published.
 */

export type Platform = "web" | "desktop";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
    __VERITRADE__?: { baseUrl?: string; token?: string };
  }
}

export function platform(): Platform {
  return typeof window !== "undefined" && window.__TAURI_INTERNALS__ ? "desktop" : "web";
}

export function apiBase(): string {
  const injected = window.__VERITRADE__?.baseUrl;
  if (injected) return injected;
  // Vite inlines this at build time; CI sets it per target.
  const configured = import.meta.env.VITE_API_BASE as string | undefined;
  if (configured) return configured;
  if (platform() === "desktop") return "http://127.0.0.1:8000";
  // A web build served by the API itself talks to its own origin.
  return window.location.port === "5173" ? "http://127.0.0.1:8000" : window.location.origin;
}

export function authHeaders(): Record<string, string> {
  const token = window.__VERITRADE__?.token;
  return token ? { authorization: `Bearer ${token}` } : {};
}
