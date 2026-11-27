// #/pedidos: pedidos del día agrupados por franja (con ocupación "7/10"), filtro por estado,
// solo los botones de las transiciones permitidas y refresco automático cada 30 s.
import { ACTION_LABELS, ADMIN_TRANSITIONS, api, STATUS_LABELS } from "../api.js";
import { autoRefresh, promptDialog, viewHeader } from "../ui.js";
import { clear, el, formatCOP, formatSlot, formatTime, showMessage, todayInBogota } from "/js/util.js";

const REFRESH_MS = 30000;
const CAPACITY = 10;

export function ordersView(root, { notify }) {
  const dateInput = el("input", { attrs: { type: "date", id: "fecha-pedidos", "aria-label": "Fecha" }, value: todayInBogota() });
  const statusSelect = el("select", { attrs: { id: "estado-pedidos", "aria-label": "Filtrar por estado" } }, [
    el("option", { value: "", text: "Todos los estados" }),
    ...Object.entries(STATUS_LABELS).map(([value, text]) => el("option", { value, text })),
  ]);
  const refreshButton = el("button", { className: "boton boton--secundario", type: "button", text: "Actualizar" });
  const summary = el("p", { className: "vista__resumen", attrs: { "aria-live": "polite" } });
  const message = el("p", { className: "aviso", attrs: { role: "alert" }, hidden: true });
  const board = el("div", { className: "franjas", attrs: { "aria-busy": "true" } });

  root.append(
    viewHeader("Pedidos", [
      el("label", { className: "control" }, ["Fecha", dateInput]),
      el("label", { className: "control" }, ["Estado", statusSelect]),
      refreshButton,
    ]),
    summary,
    message,
    board,
  );

  let busy = new Set(); // pedidos con una acción en curso (evita doble clic)

  async function changeStatus(order, status) {
    let reason;
    if (status === "CANCELADO") {
      reason = await promptDialog({
        title: `¿Cancelar el pedido ${order.code}?`,
        message: "Se devolverá el stock y se liberará el cupo de la franja.",
        label: "Motivo (opcional)",
        confirmText: "Cancelar pedido",
      });
      if (reason === null) return;
    }
    busy.add(order.orderId);
    render(lastData);
    try {
      await api.changeStatus(order.orderId, status, reason || undefined);
      notify(`Pedido ${order.code}: ${STATUS_LABELS[status]}.`, "ok");
    } catch (err) {
      const text = err.code === "INVALID_TRANSITION"
        ? `El pedido ${order.code} cambió mientras tanto; recargamos la lista.`
        : err.message;
      showMessage(message, text, "error", 6000);
    } finally {
      busy.delete(order.orderId);
      await load();
    }
  }

  function orderCard(order) {
    const actions = (ADMIN_TRANSITIONS[order.status] || []).map((status) =>
      el("button", {
        className: `boton boton--chico ${status === "CANCELADO" || status === "NO_RECOGIDO" ? "boton--peligro-suave" : "boton--primario"}`,
        type: "button",
        text: ACTION_LABELS[status],
        disabled: busy.has(order.orderId),
        attrs: { "aria-label": `${ACTION_LABELS[status]} pedido ${order.code}` },
        on: { click: () => changeStatus(order, status) },
      }),
    );
    return el("li", { className: `pedido-admin pedido-admin--${order.status.toLowerCase()}` }, [
      el("div", { className: "pedido-admin__cabecera" }, [
        el("strong", { className: "pedido-admin__codigo", text: order.code }),
        el("span", { className: `estado estado--${order.status.toLowerCase()}`, text: STATUS_LABELS[order.status] }),
      ]),
      el("p", { className: "pedido-admin__cliente" }, [
        el("span", { text: order.customer?.name || "" }),
        order.customer?.phone ? el("a", { text: order.customer.phone, attrs: { href: `tel:${order.customer.phone}` } }) : null,
      ]),
      el(
        "ul",
        { className: "pedido-admin__items", attrs: { role: "list" } },
        order.items.map((i) => el("li", { text: `${i.quantity} × ${i.name}` })),
      ),
      el("p", { className: "pedido-admin__pie" }, [
        el("span", { text: `Pedido a las ${formatTime(order.createdAt)}` }),
        el("strong", { text: formatCOP(order.total) }),
      ]),
      actions.length ? el("div", { className: "pedido-admin__acciones" }, actions) : null,
    ]);
  }

  let lastData = null;

  function render(data) {
    clear(board);
    if (!data) return;
    const bySlot = new Map();
    for (const order of data.orders) {
      if (!bySlot.has(order.pickupSlot)) bySlot.set(order.pickupSlot, []);
      bySlot.get(order.pickupSlot).push(order);
    }
    const active = data.orders.filter((o) => o.status !== "CANCELADO").length;
    summary.textContent = statusSelect.value
      ? `${data.orders.length} pedidos en estado ${STATUS_LABELS[statusSelect.value]}`
      : `${data.orders.length} pedidos · ${active} sin contar cancelados`;
    if (!data.orders.length) {
      board.append(el("p", { className: "vacio", text: "No hay pedidos para esta fecha y filtro." }));
      return;
    }
    for (const [slot, orders] of bySlot) {
      const occupied = orders.filter((o) => o.status !== "CANCELADO").length;
      const headingId = `franja-${slot.replace(":", "")}`;
      board.append(
        el("section", { className: "franja", attrs: { "aria-labelledby": headingId } }, [
          el("h3", { attrs: { id: headingId } }, [
            formatSlot(slot),
            el("span", {
              className: `ocupacion${occupied >= CAPACITY ? " ocupacion--llena" : ""}`,
              text: statusSelect.value ? `${orders.length}` : `${occupied}/${CAPACITY}`,
              attrs: { title: statusSelect.value ? "Pedidos con el filtro" : "Cupos ocupados" },
            }),
          ]),
          el("ul", { className: "franja__pedidos", attrs: { role: "list" } }, orders.map(orderCard)),
        ]),
      );
    }
  }

  async function load() {
    board.setAttribute("aria-busy", "true");
    try {
      lastData = await api.listOrders(dateInput.value, statusSelect.value);
      render(lastData);
      if (message.classList.contains("aviso--error") && !message.hidden) return;
      showMessage(message, "");
    } catch (err) {
      if (err.status !== 401) showMessage(message, err.message, "error");
    } finally {
      board.setAttribute("aria-busy", "false");
    }
  }

  dateInput.addEventListener("change", load);
  statusSelect.addEventListener("change", load);
  refreshButton.addEventListener("click", load);
  load();
  const stop = autoRefresh(load, REFRESH_MS);
  return () => {
    stop();
    busy = new Set();
  };
}
