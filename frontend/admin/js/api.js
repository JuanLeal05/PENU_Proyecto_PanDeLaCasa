// Cliente de las rutas /api/admin/* (contrato 02). Toda llamada lleva Authorization: Bearer.
// Ante un 401 (token vencido o inválido) se borra la sesión y se vuelve a pedir login.
import { clearSession, getToken, isMock } from "./auth.js";
import { adminMock } from "./mock.js";

const cfg = window.APP_CONFIG || {};
const TIMEOUT_MS = 15000;

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details || {};
  }
}

/** Lo llama main.js para volver a la pantalla de login cuando la sesión expira. */
let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

async function request(method, path, body) {
  const token = getToken();
  if (!token) {
    onUnauthorized();
    throw new ApiError(401, "UNAUTHORIZED", "Tu sesión expiró. Inicia sesión de nuevo.");
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetch(`${cfg.apiBase}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "No pudimos conectarnos. Revisa tu conexión.");
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 401) {
    clearSession();
    onUnauthorized();
    throw new ApiError(401, "UNAUTHORIZED", "Tu sesión expiró. Inicia sesión de nuevo.");
  }
  if (response.status === 204) return null;
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (response.ok) return data;
  if (response.status === 429) throw new ApiError(429, "TOO_MANY_REQUESTS", "Demasiadas solicitudes; espera unos segundos.");
  const err = (data && data.error) || {};
  throw new ApiError(response.status, err.code || "INTERNAL_ERROR", err.message || "Ocurrió un error inesperado.", err.details);
}

const query = (params) => {
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
  const qs = new URLSearchParams(clean).toString();
  return qs ? `?${qs}` : "";
};
const enc = encodeURIComponent;

const realApi = {
  listOrders: (date, status) => request("GET", `/api/admin/orders${query({ date, status })}`),
  changeStatus: (orderId, status, reason) =>
    request("PATCH", `/api/admin/orders/${enc(orderId)}/status`, reason ? { status, reason } : { status }),
  listProducts: () => request("GET", "/api/admin/products"),
  createProduct: (data) => request("POST", "/api/admin/products", data),
  updateProduct: (productId, changes) => request("PUT", `/api/admin/products/${enc(productId)}`, changes),
  deactivateProduct: (productId) => request("DELETE", `/api/admin/products/${enc(productId)}`),
  imageUploadUrl: (productId, contentType) =>
    request("POST", `/api/admin/products/${enc(productId)}/image`, { contentType }),
  /** PUT directo a S3 con la URL prefirmada (sin Authorization: la firma va en la URL). */
  async uploadImage(uploadUrl, blob, contentType) {
    let response;
    try {
      response = await fetch(uploadUrl, { method: "PUT", headers: { "Content-Type": contentType }, body: blob });
    } catch {
      throw new ApiError(0, "NETWORK_ERROR", "No se pudo subir la foto.");
    }
    if (!response.ok) throw new ApiError(response.status, "UPLOAD_FAILED", "S3 rechazó la foto. Intenta de nuevo.");
  },
  updateInventory: (items) => request("PUT", "/api/admin/inventory", { items }),
  stats: (date) => request("GET", `/api/admin/stats${query({ date })}`),
};

export const api = isMock ? adminMock(ApiError) : realApi;

/** Transiciones que puede hacer el ADMIN (copia del contrato 01 §2; el backend igual valida). */
export const ADMIN_TRANSITIONS = {
  CONFIRMADO: ["EN_PREPARACION", "CANCELADO"],
  EN_PREPARACION: ["LISTO_PARA_RECOGER", "CANCELADO"],
  LISTO_PARA_RECOGER: ["ENTREGADO", "NO_RECOGIDO"],
};

export const STATUS_LABELS = {
  CONFIRMADO: "Confirmado",
  EN_PREPARACION: "En preparación",
  LISTO_PARA_RECOGER: "Listo para recoger",
  ENTREGADO: "Entregado",
  CANCELADO: "Cancelado",
  NO_RECOGIDO: "No recogido",
};

/** Texto del botón para pasar AL estado indicado. */
export const ACTION_LABELS = {
  EN_PREPARACION: "Empezar a preparar",
  LISTO_PARA_RECOGER: "Marcar listo",
  ENTREGADO: "Entregar",
  CANCELADO: "Cancelar",
  NO_RECOGIDO: "No recogido",
};
