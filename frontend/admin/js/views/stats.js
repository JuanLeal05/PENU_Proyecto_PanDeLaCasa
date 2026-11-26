// #/estadisticas: tarjetas del día + barras CSS (sin librerías) de pedidos por franja y unidades
// por producto. Cada barra lleva su número visible: no depende solo del color ni del largo.
import { api } from "../api.js";
import { viewHeader } from "../ui.js";
import { clear, el, formatCOP, formatSlot, showMessage, todayInBogota } from "/js/util.js";

function card(label, value, modifier = "") {
  return el("div", { className: `indicador ${modifier}` }, [
    el("span", { className: "indicador__etiqueta", text: label }),
    el("strong", { className: "indicador__valor", text: value }),
  ]);
}

function bars(title, rows, { labelOf, valueOf, max }) {
  const top = Math.max(max ?? 0, ...rows.map(valueOf), 1);
  const id = `barras-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return el("section", { className: "tarjeta grafico", attrs: { "aria-labelledby": id } }, [
    el("h3", { text: title, attrs: { id } }),
    rows.length
      ? el(
          "ul",
          { className: "barras", attrs: { role: "list" } },
          rows.map((row) => {
            const value = valueOf(row);
            return el("li", { className: "barra-fila" }, [
              el("span", { className: "barra-fila__etiqueta", text: labelOf(row) }),
              el("span", { className: "barra-fila__pista", attrs: { "aria-hidden": "true" } }, [
                el("span", { className: "barra-fila__relleno", attrs: { style: `width: ${(value / top) * 100}%` } }),
              ]),
              el("span", { className: "barra-fila__valor", text: value }),
            ]);
          }),
        )
      : el("p", { className: "vacio", text: "Sin datos para esta fecha." }),
  ]);
}

export function statsView(root) {
  const dateInput = el("input", { attrs: { type: "date", "aria-label": "Fecha" }, value: todayInBogota() });
  const message = el("p", { className: "aviso", attrs: { role: "alert" }, hidden: true });
  const content = el("div", { className: "estadisticas", attrs: { "aria-live": "polite" } });
  root.append(viewHeader("Estadísticas", [el("label", { className: "control" }, ["Fecha", dateInput])]), message, content);

  function render(stats) {
    clear(content);
    const s = stats.byStatus;
    content.append(
      el("div", { className: "indicadores" }, [
        card("Pedidos", stats.totalOrders),
        card("Entregados", s.ENTREGADO, "indicador--ok"),
        card("Cancelados", s.CANCELADO, "indicador--alerta"),
        card("No recogidos", s.NO_RECOGIDO, "indicador--alerta"),
        card("Ingresos entregados", formatCOP(stats.revenueDelivered), "indicador--ancho"),
      ]),
      el("p", {
        className: "vista__resumen",
        text: `En curso → Confirmados: ${s.CONFIRMADO} · En preparación: ${s.EN_PREPARACION} · Listos para recoger: ${s.LISTO_PARA_RECOGER}`,
      }),
      el("div", { className: "graficos" }, [
        bars("Pedidos por franja", stats.ordersBySlot, {
          labelOf: (r) => formatSlot(r.slot),
          valueOf: (r) => r.orders,
          max: 10,
        }),
        bars("Unidades por producto", stats.unitsByProduct, {
          labelOf: (r) => r.name,
          valueOf: (r) => r.units,
        }),
      ]),
    );
  }

  async function load() {
    try {
      render(await api.stats(dateInput.value));
      showMessage(message, "");
    } catch (err) {
      if (err.status !== 401) showMessage(message, err.message, "error");
    }
  }

  dateInput.addEventListener("change", load);
  load();
}
