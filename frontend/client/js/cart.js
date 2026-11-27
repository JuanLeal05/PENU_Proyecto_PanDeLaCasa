// Carrito: cantidades por producto, límites del contrato 01 S7 y persistencia en localStorage.
// El carrito es del día (pan fresco): si se guardó otro día, se descarta.
import { LIMITS } from "./api.js";
import { storage, todayInBogota } from "./util.js";

const CART_KEY = "pdc_cart";

export class Cart {
  constructor() {
    const saved = storage.get(CART_KEY);
    this.items = saved && saved.date === todayInBogota() && saved.items ? { ...saved.items } : {};
    this.listeners = new Set();
  }

  onChange(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  _changed() {
    storage.set(CART_KEY, { date: todayInBogota(), items: this.items });
    for (const listener of this.listeners) listener(this);
  }

  get units() {
    return Object.values(this.items).reduce((sum, qty) => sum + qty, 0);
  }

  get lines() {
    return Object.keys(this.items).length;
  }

  quantity(productId) {
    return this.items[productId] || 0;
  }

  /**
   * ¿Se puede sumar una unidad? Devuelve null si sí, o el motivo en texto si no.
   * `stock` es el stock disponible de ese producto (de /api/availability).
   */
  blockReason(productId, stock) {
    const current = this.quantity(productId);
    if (stock !== undefined && current + 1 > stock) {
      return stock === 0 ? "Agotado" : `Solo quedan ${stock}`;
    }
    if (this.units + 1 > LIMITS.maxUnits) return `Máximo ${LIMITS.maxUnits} unidades por pedido`;
    if (!current && this.lines + 1 > LIMITS.maxLines) return `Máximo ${LIMITS.maxLines} productos distintos`;
    return null;
  }

  add(productId, stock) {
    const reason = this.blockReason(productId, stock);
    if (reason) return reason;
    this.items[productId] = this.quantity(productId) + 1;
    this._changed();
    return null;
  }

  decrease(productId) {
    const current = this.quantity(productId);
    if (current <= 1) delete this.items[productId];
    else this.items[productId] = current - 1;
    this._changed();
  }

  remove(productId) {
    delete this.items[productId];
    this._changed();
  }

  clear() {
    this.items = {};
    this._changed();
  }

  /**
   * Ajusta el carrito al stock real (tras recargar la disponibilidad o un OUT_OF_STOCK).
   * Devuelve los productId que se recortaron.
   */
  fitToStock(stock) {
    const trimmed = [];
    for (const [productId, qty] of Object.entries(this.items)) {
      const available = stock[productId];
      if (available === undefined) continue;
      if (available <= 0) {
        delete this.items[productId];
        trimmed.push(productId);
      } else if (qty > available) {
        this.items[productId] = available;
        trimmed.push(productId);
      }
    }
    if (trimmed.length) this._changed();
    return trimmed;
  }

  /** Líneas para el cuerpo de POST /api/orders (el precio NO se envía: lo pone el backend). */
  toOrderItems() {
    return Object.entries(this.items).map(([productId, quantity]) => ({ productId, quantity }));
  }

  /** Huella del carrito: si cambia, se descarta la Idempotency-Key del intento anterior. */
  fingerprint() {
    return JSON.stringify(Object.entries(this.items).sort());
  }
}
