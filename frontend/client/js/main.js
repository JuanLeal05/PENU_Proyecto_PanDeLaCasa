// Entrada de index.html: carga en paralelo el catálogo (JSON estático) y la disponibilidad (API).
import { api, config } from "./api.js";
import { Cart } from "./cart.js";
import { renderCatalog } from "./catalog.js";
import { Checkout, renderSavedOrders } from "./checkout.js";
import { el, showMessage } from "./util.js";

const state = {
  catalog: null,
  catalogById: new Map(),
  availability: null,
  highlight: new Set(),
};

const cart = new Cart();
const productsContainer = document.getElementById("lista-productos");
const storeNotice = document.getElementById("estado-tienda");

function canOrder() {
  return Boolean(state.availability && state.availability.storeOpen);
}

function render() {
  if (!state.catalog) return;
  renderCatalog(productsContainer, {
    catalog: state.catalog,
    stock: state.availability ? state.availability.stock : null,
    canOrder: canOrder(),
    cart,
    highlight: state.highlight,
    onAdd: (productId) => {
      const stock = state.availability ? state.availability.stock[productId] : undefined;
      const reason = cart.add(productId, stock);
      if (reason) showMessage(storeNotice, reason, "info", 4000);
    },
  });
  checkout.renderCart();
}

function renderStoreNotice() {
  const a = state.availability;
  if (!a) {
    showMessage(storeNotice, "No pudimos consultar los cupos de hoy. Puedes ver el catálogo; intenta de nuevo en un momento.", "error");
    return;
  }
  if (!a.storeOpen) {
    showMessage(storeNotice, "Estamos cerrados; vuelve mañana a las 6:00 a.m.", "info");
  } else if (!a.slots.some((s) => s.available)) {
    showMessage(storeNotice, "Por hoy ya no quedan franjas de recogida disponibles. ¡Te esperamos mañana!", "info");
  } else {
    showMessage(storeNotice, "");
  }
}

async function reloadAvailability() {
  try {
    state.availability = await api.getAvailability();
  } catch {
    state.availability = null;
  }
  renderStoreNotice();
  checkout.renderSlots();
  render();
}

const checkout = new Checkout({
  cart,
  getState: () => state,
  reloadAvailability,
  onHighlight: (ids) => {
    state.highlight = ids;
    render();
  },
});

cart.onChange(render);

document.getElementById("barra-carrito").addEventListener("click", () => {
  const panel = document.getElementById("carrito");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
  document.getElementById("carrito-titulo").focus({ preventScroll: true });
});

async function start() {
  if (config.useMock) {
    document.body.append(el("p", { className: "modo-demo", text: "Modo demo (datos simulados)" }));
  }
  renderSavedOrders(document.getElementById("lista-mis-pedidos"));
  productsContainer.setAttribute("aria-busy", "true");

  const [catalogResult, availabilityResult] = await Promise.allSettled([api.getCatalog(), api.getAvailability()]);
  productsContainer.setAttribute("aria-busy", "false");

  if (catalogResult.status !== "fulfilled" || !catalogResult.value) {
    showMessage(storeNotice, "No pudimos cargar el catálogo. Recarga la página en un momento.", "error");
    productsContainer.textContent = "";
    return;
  }
  state.catalog = catalogResult.value;
  state.catalogById = new Map((state.catalog.products || []).map((p) => [p.productId, p]));
  state.availability = availabilityResult.status === "fulfilled" ? availabilityResult.value : null;

  // Si un producto del carrito guardado ya no existe o se agotó, se ajusta.
  for (const productId of Object.keys(cart.items)) {
    if (!state.catalogById.has(productId)) cart.remove(productId);
  }
  if (state.availability) cart.fitToStock(state.availability.stock);

  renderStoreNotice();
  checkout.renderSlots();
  render();
}

start();
