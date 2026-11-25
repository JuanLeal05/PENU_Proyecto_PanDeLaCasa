// Panel del pedido (carrito) + formulario de checkout + envío con Idempotency-Key.
import { api, LIMITS, newIdempotencyKey } from "./api.js";
import { clear, el, formatCOP, formatSlot, showMessage, storage, todayInBogota } from "./util.js";

const ORDERS_KEY = "pdc_orders";
const PHONE_RE = /^3\d{9}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Campo del contrato (details.fields) → id del input en index.html.
const FIELD_INPUTS = {
  "customer.name": "nombre",
  "customer.phone": "celular",
  "customer.email": "email",
  dataConsent: "consentimiento",
  pickupSlot: "franja",
};

const FIELD_MESSAGES = {
  nombre: "Escribe tu nombre (entre 2 y 60 caracteres).",
  celular: "El celular debe tener 10 dígitos y empezar por 3.",
  email: "Revisa el correo o déjalo vacío.",
  consentimiento: "Debes autorizar el tratamiento de datos para hacer el pedido.",
  franja: "Elige una franja de recogida.",
};

/** Pedidos de hoy guardados en este navegador (enlace "Mis pedidos de hoy"). */
export function savedOrders() {
  const today = todayInBogota();
  return (storage.get(ORDERS_KEY, []) || []).filter((o) => o && o.pickupDate === today);
}

function saveOrder(order) {
  const today = todayInBogota();
  const others = (storage.get(ORDERS_KEY, []) || []).filter((o) => o && o.pickupDate === today && o.orderId !== order.orderId);
  storage.set(ORDERS_KEY, [
    ...others,
    { orderId: order.orderId, code: order.code, pickupSlot: order.pickupSlot, pickupDate: order.pickupDate, total: order.total },
  ]);
}

export function orderUrl(orderId, code) {
  return `/pedido.html?${new URLSearchParams({ id: orderId, code }).toString()}`;
}

export class Checkout {
  /**
   * @param {object} deps
   * @param {Cart} deps.cart
   * @param {() => {catalogById: Map, availability: object|null}} deps.getState
   * @param {() => Promise<void>} deps.reloadAvailability
   * @param {(ids: Set<string>) => void} deps.onHighlight  marca productos con problema en el catálogo
   */
  constructor({ cart, getState, reloadAvailability, onHighlight }) {
    this.cart = cart;
    this.getState = getState;
    this.reloadAvailability = reloadAvailability;
    this.onHighlight = onHighlight;
    this.attempt = null; // { key, fingerprint }: una Idempotency-Key por intento de compra
    this.sending = false;

    this.form = document.getElementById("checkout");
    this.lines = document.getElementById("lineas");
    this.total = document.getElementById("total");
    this.summary = document.getElementById("resumen-limites");
    this.slotSelect = document.getElementById("franja");
    this.submitButton = document.getElementById("confirmar");
    this.message = document.getElementById("mensaje-checkout");
    this.mobileBar = document.getElementById("barra-carrito");
    this.mobileBarText = document.getElementById("barra-carrito-texto");

    this.form.addEventListener("submit", (event) => {
      event.preventDefault();
      this.submit();
    });
    for (const id of Object.values(FIELD_INPUTS)) {
      const input = document.getElementById(id);
      input.addEventListener("input", () => this.setFieldError(id, null));
      input.addEventListener("change", () => this.setFieldError(id, null));
    }
    this.cart.onChange(() => {
      this.attempt = null; // si cambia el carrito, el intento anterior ya no aplica
      this.renderCart();
    });
  }

  // --- carrito ---------------------------------------------------------------------------------

  renderCart() {
    const { catalogById, availability } = this.getState();
    const stock = availability ? availability.stock : {};
    clear(this.lines);
    let total = 0;
    for (const [productId, qty] of Object.entries(this.cart.items)) {
      const product = catalogById.get(productId);
      if (!product) continue;
      const subtotal = product.price * qty;
      total += subtotal;
      const available = stock[productId];
      const short = available !== undefined && qty > available;
      this.lines.append(
        el("li", { className: `linea${short ? " linea--alerta" : ""}` }, [
          el("div", { className: "linea__info" }, [
            el("span", { className: "linea__nombre", text: product.name }),
            el("span", { className: "linea__precio", text: `${formatCOP(product.price)} c/u` }),
            short ? el("span", { className: "linea__aviso", text: `Solo quedan ${available}` }) : null,
          ]),
          el("div", { className: "linea__cantidad", attrs: { role: "group", "aria-label": `Cantidad de ${product.name}` } }, [
            el("button", {
              className: "boton-icono", type: "button", text: "−",
              attrs: { "aria-label": `Quitar un ${product.name}` },
              on: { click: () => this.cart.decrease(productId) },
            }),
            el("span", { className: "linea__numero", text: qty, attrs: { "aria-live": "polite" } }),
            el("button", {
              className: "boton-icono", type: "button", text: "+",
              disabled: Boolean(this.cart.blockReason(productId, available)),
              attrs: { "aria-label": `Agregar un ${product.name}` },
              on: { click: () => this.cart.add(productId, available) },
            }),
          ]),
          el("span", { className: "linea__subtotal", text: formatCOP(subtotal) }),
        ]),
      );
    }
    const empty = this.cart.units === 0;
    if (empty) this.lines.append(el("li", { className: "vacio", text: "Aún no has agregado productos." }));
    this.total.textContent = formatCOP(total);
    this.summary.textContent = `${this.cart.units} de ${LIMITS.maxUnits} unidades · ${this.cart.lines} de ${LIMITS.maxLines} productos`;
    this.mobileBar.hidden = empty;
    this.mobileBarText.textContent = `Ver pedido · ${this.cart.units} ${this.cart.units === 1 ? "unidad" : "unidades"} · ${formatCOP(total)}`;
    this.updateSubmitState();
  }

  // --- franjas ---------------------------------------------------------------------------------

  renderSlots() {
    const { availability } = this.getState();
    const previous = this.slotSelect.value;
    clear(this.slotSelect);
    const available = availability && availability.storeOpen ? availability.slots.filter((s) => s.available) : [];
    this.slotSelect.append(el("option", { value: "", text: available.length ? "Elige una franja" : "No hay franjas disponibles" }));
    for (const slot of available) {
      const remaining = slot.remaining === 1 ? "queda 1 cupo" : `quedan ${slot.remaining}`;
      this.slotSelect.append(el("option", { value: slot.slot, text: `${formatSlot(slot.slot)} · ${remaining}` }));
    }
    if (available.some((s) => s.slot === previous)) this.slotSelect.value = previous;
    this.slotSelect.disabled = !available.length;
    this.updateSubmitState();
  }

  updateSubmitState() {
    const { availability } = this.getState();
    const open = Boolean(availability && availability.storeOpen);
    const hasSlots = !this.slotSelect.disabled;
    this.submitButton.disabled = this.sending || !open || !hasSlots || this.cart.units === 0;
  }

  // --- validación local (el backend valida igual) ----------------------------------------------

  setFieldError(inputId, message) {
    const input = document.getElementById(inputId);
    const error = document.getElementById(`${inputId}-error`);
    if (!input || !error) return;
    input.setAttribute("aria-invalid", message ? "true" : "false");
    error.textContent = message || "";
    error.hidden = !message;
  }

  readForm() {
    const value = (id) => document.getElementById(id).value.trim();
    return {
      name: value("nombre"),
      phone: value("celular").replace(/\s+/g, ""),
      email: value("email"),
      consent: document.getElementById("consentimiento").checked,
      slot: this.slotSelect.value,
    };
  }

  validate(data) {
    const errors = {}; // en el orden visual del formulario: el foco va al primer error
    if (!data.slot) errors.franja = FIELD_MESSAGES.franja;
    if (data.name.length < 2 || data.name.length > 60) errors.nombre = FIELD_MESSAGES.nombre;
    if (!PHONE_RE.test(data.phone)) errors.celular = FIELD_MESSAGES.celular;
    if (data.email && !EMAIL_RE.test(data.email)) errors.email = FIELD_MESSAGES.email;
    if (!data.consent) errors.consentimiento = FIELD_MESSAGES.consentimiento;
    for (const id of Object.values(FIELD_INPUTS)) this.setFieldError(id, errors[id] || null);
    const first = Object.keys(errors)[0];
    if (first) document.getElementById(first).focus();
    return !first;
  }

  // --- envío -----------------------------------------------------------------------------------

  async submit() {
    if (this.sending) return; // evita el doble clic
    showMessage(this.message, "");
    if (this.cart.units === 0) {
      showMessage(this.message, "Agrega al menos un producto.", "error");
      return;
    }
    const data = this.readForm();
    if (!this.validate(data)) return;

    const body = {
      customer: { name: data.name, phone: data.phone, ...(data.email ? { email: data.email } : {}) },
      pickupSlot: data.slot,
      items: this.cart.toOrderItems(),
      dataConsent: true,
    };
    // Misma clave solo si es EXACTAMENTE el mismo intento (reintento tras un error de red).
    const fingerprint = JSON.stringify(body);
    if (!this.attempt || this.attempt.fingerprint !== fingerprint) {
      this.attempt = { key: newIdempotencyKey(), fingerprint };
    }

    this.sending = true;
    this.submitButton.textContent = "Enviando…";
    this.updateSubmitState();
    try {
      const { order } = await api.createOrder(body, this.attempt.key);
      this.attempt = null;
      saveOrder(order);
      this.cart.clear();
      window.location.assign(orderUrl(order.orderId, order.code));
    } catch (err) {
      await this.handleError(err);
    } finally {
      this.sending = false;
      this.submitButton.textContent = "Confirmar pedido";
      this.updateSubmitState();
    }
  }

  async handleError(err) {
    if (!err || !err.code) {
      showMessage(this.message, "Ocurrió un error inesperado. Intenta de nuevo.", "error");
      return;
    }
    // Respuesta definitiva del servidor → el próximo intento usa otra clave.
    if (!err.retryable) this.attempt = null;

    switch (err.code) {
      case "SLOT_FULL":
        showMessage(this.message, "Esa franja se llenó; elige otra. Tu carrito sigue intacto.", "error");
        await this.reloadAvailability();
        this.slotSelect.value = "";
        this.slotSelect.focus();
        break;
      case "OUT_OF_STOCK": {
        await this.reloadAvailability();
        const ids = new Set(err.details.productIds || []);
        this.onHighlight(ids);
        const { availability, catalogById } = this.getState();
        const names = [...ids].map((id) => catalogById.get(id)?.name || id).join(", ");
        this.cart.fitToStock(availability ? availability.stock : {});
        showMessage(
          this.message,
          `No alcanzan las unidades de: ${names}. Ajustamos tu pedido a lo disponible; revísalo y confirma de nuevo.`,
          "error",
        );
        break;
      }
      case "PRODUCT_NOT_FOUND": {
        for (const id of err.details.productIds || []) this.cart.remove(id);
        await this.reloadAvailability();
        showMessage(this.message, "Algún producto ya no está disponible y lo quitamos de tu pedido.", "error");
        break;
      }
      case "STORE_CLOSED":
        await this.reloadAvailability();
        showMessage(this.message, "La tienda ya no recibe pedidos por hoy (de 6:00 a.m. a 6:00 p.m.).", "error");
        break;
      case "SLOT_NOT_AVAILABLE":
        await this.reloadAvailability();
        showMessage(this.message, "Esa franja ya no está disponible (debe empezar en al menos 30 minutos). Elige otra.", "error");
        break;
      case "VALIDATION_ERROR": {
        const fields = err.details.fields || [];
        for (const field of fields) {
          const inputId = FIELD_INPUTS[field];
          if (inputId) this.setFieldError(inputId, FIELD_MESSAGES[inputId]);
        }
        const cartProblem = fields.some((f) => f === "items" || f.startsWith("items["));
        showMessage(
          this.message,
          cartProblem
            ? `Revisa tu pedido: máximo ${LIMITS.maxUnits} unidades y ${LIMITS.maxLines} productos distintos.`
            : "Revisa los campos marcados.",
          "error",
        );
        const first = fields.map((f) => FIELD_INPUTS[f]).find(Boolean);
        if (first) document.getElementById(first).focus();
        break;
      }
      case "TOO_MANY_REQUESTS":
        showMessage(this.message, "Hay mucha demanda, intenta en unos segundos.", "error");
        break;
      case "NETWORK_ERROR":
        showMessage(this.message, `${err.message} Si vuelves a intentar, no se creará un pedido duplicado.`, "error");
        break;
      case "IDEMPOTENCY_CONFLICT":
        showMessage(this.message, "Tu pedido cambió mientras se enviaba. Revisa “Mis pedidos de hoy” y vuelve a intentar.", "error");
        break;
      default:
        showMessage(this.message, "No pudimos crear el pedido. Intenta de nuevo en un momento.", "error");
    }
  }
}

/** Lista "Mis pedidos de hoy" (solo lo guardado en este navegador). */
export function renderSavedOrders(container) {
  clear(container);
  const orders = savedOrders();
  if (!orders.length) {
    container.append(el("p", { className: "vacio", text: "Todavía no has hecho pedidos hoy desde este navegador." }));
    return;
  }
  const list = el("ul", { className: "mis-pedidos", attrs: { role: "list" } });
  for (const order of orders) {
    list.append(
      el("li", {}, [
        el("a", { attrs: { href: orderUrl(order.orderId, order.code) } }, [
          el("strong", { text: `Código ${order.code}` }),
          ` · recoge a las ${formatSlot(order.pickupSlot)} · ${formatCOP(order.total)}`,
        ]),
      ]),
    );
  }
  container.append(list);
}
