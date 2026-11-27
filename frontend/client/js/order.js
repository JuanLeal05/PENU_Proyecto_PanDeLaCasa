// pedido.html?id=<orderId>&code=<code>: seguimiento con polling (ADR-004).
// - Polling cada pollIntervalMs (20 s) mientras el estado no sea final.
// - Se PAUSA con la pestaña oculta (visibilitychange) y se DETIENE en estados finales.
import { api, config, FINAL_STATUSES, STATUS_LABELS } from "./api.js";
import { clear, confirmDialog, el, formatCOP, formatDate, formatSlot, formatTime, showMessage } from "./util.js";

const FLOW = ["CONFIRMADO", "EN_PREPARACION", "LISTO_PARA_RECOGER", "ENTREGADO"];
const STATUS_HINTS = {
  CONFIRMADO: "Recibimos tu pedido. Te avisaremos aquí cuando empecemos a prepararlo.",
  EN_PREPARACION: "Estamos preparando tu pedido.",
  LISTO_PARA_RECOGER: "¡Tu pedido está listo! Acércate a la tienda y muestra tu código.",
  ENTREGADO: "Pedido entregado. ¡Gracias por comprar en Pan de la Casa!",
  CANCELADO: "Este pedido fue cancelado.",
  NO_RECOGIDO: "El pedido no se recogió a tiempo.",
};

const params = new URLSearchParams(window.location.search);
const orderId = params.get("id");
const code = (params.get("code") || "").toUpperCase();

const view = document.getElementById("pedido");
const notice = document.getElementById("mensaje-pedido");
const refreshButton = document.getElementById("actualizar");
const cancelButton = document.getElementById("cancelar");
const lastUpdate = document.getElementById("ultima-actualizacion");

let timer = null;
let current = null;
let loading = false;

function renderTimeline(order) {
  const reached = new Map(order.history.map((h) => [h.status, h.at]));
  const isFinalOff = order.status === "CANCELADO" || order.status === "NO_RECOGIDO";
  const steps = isFinalOff
    ? [...FLOW.filter((s) => reached.has(s)), order.status]
    : FLOW;
  const currentIndex = steps.indexOf(order.status);
  return el(
    "ol",
    { className: "linea-tiempo", attrs: { "aria-label": "Estados del pedido" } },
    steps.map((status, index) => {
      const done = index <= currentIndex;
      const at = reached.get(status);
      const classes = ["paso", done ? "paso--hecho" : "", index === currentIndex ? "paso--actual" : "",
        status === "CANCELADO" || status === "NO_RECOGIDO" ? "paso--final-negativo" : ""].filter(Boolean);
      return el("li", { className: classes.join(" "), attrs: { "aria-current": index === currentIndex ? "step" : null } }, [
        el("span", { className: "paso__punto", attrs: { "aria-hidden": "true" } }),
        el("span", { className: "paso__nombre", text: STATUS_LABELS[status] || status }),
        at ? el("span", { className: "paso__hora", text: formatTime(at) }) : null,
      ]);
    }),
  );
}

function render(order) {
  clear(view);
  const isFinal = FINAL_STATUSES.has(order.status);
  view.append(
    el("div", { className: "pedido__codigo" }, [
      el("span", { className: "pedido__codigo-etiqueta", text: "Código para recoger" }),
      el("strong", { className: "pedido__codigo-valor", text: code, attrs: { "aria-label": `Código ${code.split("").join(" ")}` } }),
    ]),
    el("p", { className: `pedido__estado pedido__estado--${order.status.toLowerCase()}`, attrs: { role: "status" } }, [
      el("strong", { text: order.statusLabel || STATUS_LABELS[order.status] }),
      ` — ${STATUS_HINTS[order.status] || ""}`,
    ]),
    el("p", { className: "pedido__franja" }, [
      "Recoge el ",
      el("strong", { text: formatDate(order.pickupDate) }),
      " entre las ",
      el("strong", { text: formatSlot(order.pickupSlot) }),
      " y 30 minutos después.",
    ]),
    renderTimeline(order),
    el("h2", { text: "Detalle" }),
    el(
      "ul",
      { className: "detalle", attrs: { role: "list" } },
      order.items.map((item) =>
        el("li", {}, [
          el("span", { text: `${item.quantity} × ${item.name}` }),
          el("span", { text: formatCOP(item.subtotal) }),
        ]),
      ),
    ),
    el("p", { className: "detalle__total" }, [el("span", { text: "Total a pagar en tienda" }), el("strong", { text: formatCOP(order.total) })]),
  );
  cancelButton.hidden = order.status !== "CONFIRMADO";
  refreshButton.hidden = isFinal;
  lastUpdate.textContent = isFinal ? "" : `Se actualiza solo cada ${Math.round(config.pollIntervalMs / 1000)} s.`;
}

function stopPolling() {
  window.clearTimeout(timer);
  timer = null;
}

function schedule() {
  stopPolling();
  if (!current || FINAL_STATUSES.has(current.status) || document.hidden) return;
  timer = window.setTimeout(load, config.pollIntervalMs);
}

async function load() {
  if (loading) return;
  loading = true;
  try {
    const order = await api.getOrder(orderId, code);
    const changed = current && current.status !== order.status;
    current = order;
    render(order);
    if (changed) showMessage(notice, `Tu pedido ahora está: ${order.statusLabel}.`, "ok", 6000);
    else if (!changed && notice.classList.contains("aviso--error")) showMessage(notice, "");
  } catch (err) {
    if (err && err.status === 404) {
      stopPolling();
      clear(view);
      cancelButton.hidden = true;
      refreshButton.hidden = true;
      showMessage(notice, "No encontramos ese pedido. Revisa el enlace.", "error");
      loading = false;
      return;
    }
    showMessage(notice, "No pudimos actualizar el estado. Lo intentaremos de nuevo en unos segundos.", "error");
  } finally {
    loading = false;
  }
  schedule();
}

refreshButton.addEventListener("click", () => {
  stopPolling();
  load();
});

cancelButton.addEventListener("click", async () => {
  const ok = await confirmDialog({
    title: "¿Cancelar el pedido?",
    message: "Liberaremos tu franja y los productos. Esta acción no se puede deshacer.",
    confirmText: "Sí, cancelar",
    cancelText: "No, mantenerlo",
  });
  if (!ok) return;
  cancelButton.disabled = true;
  try {
    current = await api.cancelOrder(orderId, code);
    render(current);
    showMessage(notice, "Cancelaste tu pedido.", "ok");
    stopPolling();
  } catch (err) {
    if (err && err.code === "INVALID_TRANSITION") {
      showMessage(notice, "Ya no se puede cancelar: la panadería empezó a preparar tu pedido.", "error");
      load();
    } else {
      showMessage(notice, "No pudimos cancelar el pedido. Intenta de nuevo.", "error");
    }
  } finally {
    cancelButton.disabled = false;
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopPolling();
  else if (current && !FINAL_STATUSES.has(current.status)) load(); // al volver, se actualiza de una
});

if (config.useMock) document.body.append(el("p", { className: "modo-demo", text: "Modo demo (datos simulados)" }));

if (!orderId || !code) {
  cancelButton.hidden = true;
  refreshButton.hidden = true;
  showMessage(notice, "Este enlace no es válido. Abre el enlace que recibiste al hacer el pedido.", "error");
} else {
  load();
}
