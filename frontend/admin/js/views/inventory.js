// #/inventario: stock y producción diaria editables; "Guardar todo" envía solo las filas cambiadas
// en un PUT /api/admin/inventory. Atajo: copiar la producción diaria al stock y guardar.
import { api } from "../api.js";
import { viewHeader } from "../ui.js";
import { clear, confirmDialog, el, showMessage } from "/js/util.js";

const MAX = 10000;

export function inventoryView(root, { notify }) {
  const message = el("p", { className: "aviso", attrs: { role: "alert" }, hidden: true });
  const saveButton = el("button", { className: "boton boton--primario", type: "button", text: "Guardar todo", disabled: true });
  const resetButton = el("button", { className: "boton boton--secundario", type: "button", text: "Restablecer stock a la producción diaria" });
  const table = el("div", { className: "tabla-contenedor" });
  root.append(
    viewHeader("Inventario", [resetButton, saveButton]),
    el("p", { className: "vista__resumen", text: "El stock se restablece solo a las 5:30 a. m. Aquí puedes ajustarlo durante el día." }),
    message,
    table,
  );

  let products = [];
  const inputs = new Map(); // productId → { stock, daily }

  function readRow(productId) {
    const { stock, daily } = inputs.get(productId);
    return { stock: Number(stock.value), dailyProduction: Number(daily.value) };
  }

  function validNumber(value) {
    return Number.isInteger(value) && value >= 0 && value <= MAX;
  }

  function changedItems() {
    const items = [];
    for (const product of products) {
      const { stock, dailyProduction } = readRow(product.productId);
      if (stock === product.stock && dailyProduction === product.dailyProduction) continue;
      const item = { productId: product.productId, stock };
      if (dailyProduction !== product.dailyProduction) item.dailyProduction = dailyProduction;
      items.push(item);
    }
    return items;
  }

  function refreshState() {
    let invalid = false;
    for (const product of products) {
      const { stock, daily } = inputs.get(product.productId);
      for (const input of [stock, daily]) {
        const bad = !validNumber(Number(input.value)) || input.value === "";
        input.setAttribute("aria-invalid", bad ? "true" : "false");
        invalid ||= bad;
      }
    }
    const changes = changedItems().length;
    saveButton.disabled = invalid || changes === 0;
    saveButton.textContent = changes ? `Guardar todo (${changes})` : "Guardar todo";
  }

  async function save(items) {
    saveButton.disabled = true;
    try {
      await api.updateInventory(items);
      notify(`Inventario actualizado (${items.length} ${items.length === 1 ? "producto" : "productos"}).`);
      await load();
    } catch (err) {
      showMessage(message, err.message, "error", 8000);
      refreshState();
    }
  }

  function render() {
    clear(table);
    inputs.clear();
    const rows = products.map((product) => {
      const stock = el("input", { attrs: { type: "number", min: 0, max: MAX, step: 1, inputmode: "numeric", "aria-label": `Stock de ${product.name}` }, value: product.stock, on: { input: refreshState } });
      const daily = el("input", { attrs: { type: "number", min: 0, max: MAX, step: 1, inputmode: "numeric", "aria-label": `Producción diaria de ${product.name}` }, value: product.dailyProduction, on: { input: refreshState } });
      inputs.set(product.productId, { stock, daily });
      return el("tr", { className: product.active ? "" : "fila--inactiva" }, [
        el("th", { attrs: { scope: "row" } }, [el("span", { text: product.name }), product.active ? null : el("span", { className: "celda__sub", text: "Inactivo" })]),
        el("td", { text: product.category }),
        el("td", { className: "num" }, [stock]),
        el("td", { className: "num" }, [daily]),
      ]);
    });
    table.append(
      el("table", { className: "tabla tabla--inventario" }, [
        el("caption", { className: "visualmente-oculto", text: "Inventario del día" }),
        el("thead", {}, [el("tr", {}, ["Producto", "Categoría", "Stock hoy", "Producción diaria"].map((h) => el("th", { text: h, attrs: { scope: "col" } })))]),
        el("tbody", {}, rows),
      ]),
    );
    refreshState();
  }

  async function load() {
    try {
      products = (await api.listProducts()).products;
      render();
    } catch (err) {
      if (err.status !== 401) showMessage(message, err.message, "error");
    }
  }

  saveButton.addEventListener("click", () => save(changedItems()));
  resetButton.addEventListener("click", async () => {
    const ok = await confirmDialog({
      title: "¿Restablecer el stock?",
      message: "El stock de cada producto activo pasará a ser igual a su producción diaria.",
      confirmText: "Restablecer y guardar",
      cancelText: "Volver",
    });
    if (!ok) return;
    const items = products
      .filter((p) => p.active)
      .map((p) => ({ productId: p.productId, stock: readRow(p.productId).dailyProduction, dailyProduction: readRow(p.productId).dailyProduction }));
    await save(items);
  });
  load();
}
