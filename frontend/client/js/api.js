// Cliente de la API (contrato 02). Toda la configuración sale de window.APP_CONFIG (/config.js):
// no hay URLs quemadas. Con useMock: true se usan las respuestas simuladas de mock.js.
import { mockApi } from "./mock.js";

export const config = Object.freeze({
  env: "local",
  apiBase: "",
  assetsBase: "",
  pollIntervalMs: 20000,
  useMock: true,
  ...(window.APP_CONFIG || {}),
});

const TIMEOUT_MS = 10000;

/** Error con el formato del contrato: { error: { code, message, details } }. */
export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details || {};
  }

  /** ¿Vale la pena reintentar con la MISMA Idempotency-Key? (no llegó respuesta definitiva) */
  get retryable() {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }
}

async function request(method, url, { body, headers = {} } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? headers : { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      credentials: "omit",
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "No pudimos conectarnos. Revisa tu conexión e intenta de nuevo.");
  } finally {
    clearTimeout(timer);
  }

  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (response.ok) return { status: response.status, data };

  if (response.status === 429) {
    throw new ApiError(429, "TOO_MANY_REQUESTS", "Hay mucha demanda, intenta en unos segundos.");
  }
  const err = data && data.error ? data.error : {};
  throw new ApiError(
    response.status,
    err.code || "INTERNAL_ERROR",
    err.message || "Ocurrió un error inesperado. Intenta de nuevo.",
    err.details,
  );
}

const realApi = {
  async getCatalog() {
    const { data } = await request("GET", `${config.assetsBase}/catalog/catalog.json`);
    return data;
  },
  async getAvailability() {
    const { data } = await request("GET", `${config.apiBase}/api/availability`);
    return data;
  },
  /** Devuelve { status: 201|200, order }. */
  async createOrder(body, idempotencyKey) {
    const { status, data } = await request("POST", `${config.apiBase}/api/orders`, {
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    });
    return { status, order: data };
  },
  async getOrder(orderId, code) {
    const url = `${config.apiBase}/api/orders/${encodeURIComponent(orderId)}?code=${encodeURIComponent(code)}`;
    const { data } = await request("GET", url);
    return data;
  },
  async cancelOrder(orderId, code) {
    const url = `${config.apiBase}/api/orders/${encodeURIComponent(orderId)}/cancel`;
    const { data } = await request("POST", url, { body: { code } });
    return data;
  },
};

export const api = config.useMock ? mockApi(ApiError) : realApi;

/** UUID v4 para Idempotency-Key (crypto.randomUUID solo existe en contextos seguros). */
export function newIdempotencyKey() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
  const bytes = window.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** Etiquetas de estado (contrato 01 §2). */
export const STATUS_LABELS = {
  CONFIRMADO: "Confirmado",
  EN_PREPARACION: "En preparación",
  LISTO_PARA_RECOGER: "Listo para recoger",
  ENTREGADO: "Entregado",
  CANCELADO: "Cancelado",
  NO_RECOGIDO: "No recogido",
};
export const FINAL_STATUSES = new Set(["ENTREGADO", "CANCELADO", "NO_RECOGIDO"]);

/** Límites del pedido (contrato 01 S7). El backend igual los valida. */
export const LIMITS = Object.freeze({ maxUnits: 20, maxLines: 10 });
