// Autenticación del panel: Cognito Hosted UI con Authorization Code + PKCE (sin client secret).
// El access_token vive solo en sessionStorage (se borra al cerrar la pestaña).
// En modo mock no hay login real: "Entrar (mock)" simula la sesión.
import { storage } from "/js/util.js";

const cfg = window.APP_CONFIG || {};
const cognito = cfg.cognito || {};
export const isMock = cfg.useMock !== false;

const SESSION_KEY = "pdc_admin_session";
const PKCE_KEY = "pdc_admin_pkce";
const EXPIRY_MARGIN_MS = 60 * 1000;

function base64url(bytes) {
  let binary = "";
  for (const b of new Uint8Array(bytes)) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomString(length) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
  const bytes = window.crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
}

async function sha256(text) {
  return window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
}

/** Lee el payload de un JWT (sin validar: la firma la valida API Gateway). Solo para mostrar el usuario. */
function jwtPayload(token) {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(decodeURIComponent(escape(atob(part))));
  } catch {
    return {};
  }
}

export function getSession() {
  const session = storage.get(SESSION_KEY, null, "session");
  if (!session || !session.accessToken) return null;
  if (Date.now() > session.expiresAt - EXPIRY_MARGIN_MS) {
    storage.remove(SESSION_KEY, "session");
    return null;
  }
  return session;
}

export function getToken() {
  const session = getSession();
  return session ? session.accessToken : null;
}

export function clearSession() {
  storage.remove(SESSION_KEY, "session");
}

/** Inicia el login: genera verifier + challenge + state y redirige al Hosted UI. */
export async function login() {
  if (isMock) {
    storage.set(SESSION_KEY, { accessToken: "mock-token", expiresAt: Date.now() + 8 * 3600 * 1000, username: "admin-demo" }, "session");
    return;
  }
  if (!cognito.domain || !cognito.clientId || !cognito.redirectUri) {
    throw new Error("Falta la configuración de Cognito en /config.js.");
  }
  const verifier = randomString(64);
  const state = randomString(32);
  storage.set(PKCE_KEY, { verifier, state }, "session");
  const challenge = base64url(await sha256(verifier));
  const params = new URLSearchParams({
    response_type: "code",
    client_id: cognito.clientId,
    redirect_uri: cognito.redirectUri,
    scope: "openid email profile",
    code_challenge_method: "S256",
    code_challenge: challenge,
    state,
  });
  window.location.assign(`${cognito.domain}/oauth2/authorize?${params.toString()}`);
}

/**
 * Si la URL trae ?code=&state= (vuelta del Hosted UI), canjea el código por tokens.
 * Devuelve: "none" (no era una vuelta de login), "ok" o un mensaje de error.
 */
export async function handleRedirect() {
  const params = new URLSearchParams(window.location.search);
  const cleanUrl = () => window.history.replaceState({}, document.title, window.location.pathname + window.location.hash);
  if (params.has("error")) {
    cleanUrl();
    return `Cognito rechazó el inicio de sesión (${params.get("error")}).`;
  }
  if (!params.has("code")) return "none";

  const pkce = storage.get(PKCE_KEY, null, "session");
  storage.remove(PKCE_KEY, "session");
  cleanUrl();
  if (!pkce || pkce.state !== params.get("state")) {
    return "La respuesta de inicio de sesión no es válida. Intenta de nuevo.";
  }
  try {
    const response = await fetch(`${cognito.domain}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: cognito.clientId,
        code: params.get("code"),
        redirect_uri: cognito.redirectUri,
        code_verifier: pkce.verifier,
      }),
    });
    if (!response.ok) return "No pudimos completar el inicio de sesión. Intenta de nuevo.";
    const tokens = await response.json();
    const claims = jwtPayload(tokens.access_token);
    storage.set(
      SESSION_KEY,
      {
        accessToken: tokens.access_token,
        expiresAt: Date.now() + Number(tokens.expires_in || 3600) * 1000,
        username: claims.username || claims["cognito:username"] || "admin",
      },
      "session",
    );
    return "ok";
  } catch {
    return "No pudimos conectarnos con el servicio de inicio de sesión.";
  }
}

/** Cierra la sesión local y en Cognito. */
export function logout() {
  clearSession();
  if (isMock || !cognito.domain) {
    window.location.reload();
    return;
  }
  const params = new URLSearchParams({ client_id: cognito.clientId, logout_uri: cognito.logoutUri || cognito.redirectUri });
  window.location.assign(`${cognito.domain}/logout?${params.toString()}`);
}
