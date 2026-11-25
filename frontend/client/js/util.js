// Utilidades de UI compartidas por el sitio del cliente.
// Regla de seguridad: los datos de la API se pintan SIEMPRE con textContent o creando nodos
// (función el()); nunca con innerHTML.

const copFormatter = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

/** 4500 → "$ 4.500" */
export function formatCOP(value) {
  return copFormatter.format(Number(value) || 0).replace(/ /g, " ");
}

/** "2026-11-27" → "viernes 27 de noviembre" (sin depender de la zona horaria del navegador). */
export function formatDate(isoDate) {
  const [y, m, d] = String(isoDate).split("-").map(Number);
  if (!y || !m || !d) return String(isoDate || "");
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(date);
}

/** "10:00" → "10:00 a. m." / "14:30" → "2:30 p. m." */
export function formatSlot(slot) {
  const [h, m] = String(slot).split(":").map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return String(slot || "");
  const suffix = h < 12 ? "a. m." : "p. m.";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${String(m).padStart(2, "0")} ${suffix}`;
}

/** Hora (HH:MM) de un timestamp ISO con offset, mostrada en hora de Bogotá. */
export function formatTime(isoTimestamp) {
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-CO", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Bogota",
  }).format(date);
}

/**
 * Crea un elemento DOM de forma segura.
 *   el("p", { className: "x", text: "hola" }, [hijo1, "texto"])
 * - `text` usa textContent.  - `attrs` usa setAttribute.  - `on` registra eventos.
 */
export function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  const { text, className, attrs, on, dataset, ...props } = options;
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === false || value === null || value === undefined) continue;
      node.setAttribute(key, value === true ? "" : String(value));
    }
  }
  if (dataset) Object.assign(node.dataset, dataset);
  for (const [key, value] of Object.entries(props)) node[key] = value;
  if (on) {
    for (const [event, handler] of Object.entries(on)) node.addEventListener(event, handler);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** Vacía un nodo (sin innerHTML). */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

/** localStorage/sessionStorage pueden fallar (modo privado, cuota): siempre en try/catch. */
export const storage = {
  get(key, fallback = null, area = "local") {
    try {
      const raw = (area === "session" ? window.sessionStorage : window.localStorage).getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value, area = "local") {
    try {
      (area === "session" ? window.sessionStorage : window.localStorage).setItem(key, JSON.stringify(value));
      return true;
    } catch {
      return false;
    }
  },
  remove(key, area = "local") {
    try {
      (area === "session" ? window.sessionStorage : window.localStorage).removeItem(key);
    } catch {
      /* sin almacenamiento: no pasa nada */
    }
  },
};

/** Fecha de hoy en Bogotá (YYYY-MM-DD), independiente de la zona del navegador. */
export function todayInBogota() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  return parts; // en-CA ya formatea como YYYY-MM-DD
}

/** Solo URLs http(s) o relativas al sitio; descarta cualquier otro esquema. */
export function safeUrl(url) {
  if (typeof url !== "string" || !url) return null;
  if (url.startsWith("/") && !url.startsWith("//")) return url;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/**
 * Mensaje en una región aria-live. kind: "info" | "ok" | "error".
 * Si `timeoutMs` > 0, se oculta solo.
 */
export function showMessage(region, text, kind = "info", timeoutMs = 0) {
  if (!region) return;
  region.hidden = !text;
  region.className = `aviso aviso--${kind}`;
  region.textContent = text || "";
  if (timeoutMs > 0 && text) {
    window.clearTimeout(region._timer);
    region._timer = window.setTimeout(() => {
      region.hidden = true;
    }, timeoutMs);
  }
}

/**
 * Modal de confirmación propio (sin confirm()). Devuelve una promesa con true/false.
 * Usa <dialog> nativo: atrapa el foco y se cierra con Escape.
 */
export function confirmDialog({ title, message, confirmText = "Confirmar", cancelText = "Volver" }) {
  return new Promise((resolve) => {
    const titleId = `dlg-${Math.random().toString(36).slice(2)}`;
    const dialog = el("dialog", { className: "dialogo", attrs: { "aria-labelledby": titleId } }, [
      el("h2", { text: title, attrs: { id: titleId } }),
      el("p", { text: message }),
    ]);
    const done = (value) => {
      dialog.close();
      dialog.remove();
      resolve(value);
    };
    const actions = el("div", { className: "dialogo__acciones" }, [
      el("button", { className: "boton boton--secundario", text: cancelText, type: "button", on: { click: () => done(false) } }),
      el("button", { className: "boton boton--peligro", text: confirmText, type: "button", on: { click: () => done(true) } }),
    ]);
    dialog.append(actions);
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      done(false);
    });
    document.body.append(dialog);
    dialog.showModal();
    actions.firstChild.focus();
  });
}
