// API admin simulada (useMock: true). Mismos cuerpos y códigos de error que el contrato 02.
// Los datos son FICTICIOS y viven en localStorage para sobrevivir a una recarga.
import { todayInBogota } from "/js/util.js";

const KEY = "pdc_admin_mock";
const LABELS = {
  CONFIRMADO: "Confirmado",
  EN_PREPARACION: "En preparación",
  LISTO_PARA_RECOGER: "Listo para recoger",
  ENTREGADO: "Entregado",
  CANCELADO: "Cancelado",
  NO_RECOGIDO: "No recogido",
};
const ADMIN = {
  CONFIRMADO: ["EN_PREPARACION", "CANCELADO"],
  EN_PREPARACION: ["LISTO_PARA_RECOGER", "CANCELADO"],
  LISTO_PARA_RECOGER: ["ENTREGADO", "NO_RECOGIDO"],
};
const IMAGE_TYPES = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp" };
const imageBlobs = new Map(); // imageKey → blob: URL (solo en memoria)

const PRODUCTS = [
  ["p-croissant", "Croissant", "Hojaldre de mantequilla francesa.", "Hojaldres", 4500, 60, 42],
  ["p-roscon-arequipe", "Roscón de arequipe", "Roscón azucarado relleno de arequipe.", "Hojaldres", 3500, 40, 3],
  ["p-almojabana", "Almojábana", "Tradicional almojábana de cuajada.", "Panes", 2500, 60, 30],
  ["p-pan-queso", "Pan de queso", "Pan suave relleno de queso campesino.", "Panes", 1500, 80, 0],
  ["p-pan-frances", "Pan francés", "Baguette pequeña de corteza crujiente.", "Panes", 800, 120, 95],
  ["p-mantecada", "Mantecada", "Mantecada casera esponjosa.", "Tortas", 3000, 30, 12],
  ["p-cafe-tinto", "Café tinto", "Tinto colombiano recién colado.", "Bebidas", 2500, 80, 60],
];

const NAMES = ["Ana Pérez", "Carlos Gómez", "Luisa Martínez", "Jorge Ramírez", "Sofía Herrera", "Andrés Castro", "Valentina Ruiz", "Mateo López"];

function pad(n) {
  return String(n).padStart(2, "0");
}

function iso(date, time) {
  return `${date}T${time}:00-05:00`;
}

function seed() {
  const date = todayInBogota();
  const products = Object.fromEntries(
    PRODUCTS.map(([productId, name, description, category, price, dailyProduction, stock]) => [
      productId,
      { productId, name, description, category, price, dailyProduction, stock, active: true, imageKey: null, updatedAt: iso(date, "05:30") },
    ]),
  );
  products["p-pan-viejo"] = { productId: "p-pan-viejo", name: "Pan viejo", description: "Producto descontinuado.", category: "Panes", price: 900, dailyProduction: 0, stock: 0, active: false, imageKey: null, updatedAt: iso(date, "05:30") };

  const plan = [
    ["07:00", "ENTREGADO"], ["07:00", "ENTREGADO"], ["07:30", "ENTREGADO"], ["08:00", "NO_RECOGIDO"],
    ["08:30", "CANCELADO"], ["09:00", "LISTO_PARA_RECOGER"], ["09:00", "EN_PREPARACION"], ["09:30", "CONFIRMADO"],
    ["10:00", "CONFIRMADO"], ["10:00", "CONFIRMADO"], ["10:30", "CONFIRMADO"], ["11:00", "EN_PREPARACION"],
  ];
  const orders = {};
  plan.forEach(([slot, status], index) => {
    const [h, m] = slot.split(":").map(Number);
    const createdMinutes = Math.max(h * 60 + m - 60 + index, 6 * 60);
    const createdAt = iso(date, `${pad(Math.floor(createdMinutes / 60))}:${pad(createdMinutes % 60)}`);
    const lineProducts = [PRODUCTS[index % PRODUCTS.length], PRODUCTS[(index + 2) % PRODUCTS.length]];
    const items = lineProducts.map(([productId, name, , , price], i) => {
      const quantity = 1 + ((index + i) % 3);
      return { productId, name, unitPrice: price, quantity, subtotal: price * quantity };
    });
    const history = [{ status: "CONFIRMADO", at: createdAt, by: "customer" }];
    const flow = { EN_PREPARACION: ["EN_PREPARACION"], LISTO_PARA_RECOGER: ["EN_PREPARACION", "LISTO_PARA_RECOGER"],
      ENTREGADO: ["EN_PREPARACION", "LISTO_PARA_RECOGER", "ENTREGADO"], CANCELADO: ["CANCELADO"],
      NO_RECOGIDO: ["EN_PREPARACION", "LISTO_PARA_RECOGER", "NO_RECOGIDO"] }[status] || [];
    for (const s of flow) history.push({ status: s, at: createdAt, by: s === "NO_RECOGIDO" ? "system" : "admin-demo" });
    const orderId = `mock-${pad(index)}-${slot.replace(":", "")}`;
    orders[orderId] = {
      orderId, code: `DEMO${pad(index)}`.slice(0, 6), status, statusLabel: LABELS[status],
      pickupDate: date, pickupSlot: slot, items, total: items.reduce((s, i) => s + i.subtotal, 0), createdAt,
      customer: { name: NAMES[index % NAMES.length], phone: `300555${pad(index)}${pad(index)}`.slice(0, 10), email: null },
      history,
    };
  });
  return { date, products, orders };
}

function load() {
  try {
    const state = JSON.parse(window.localStorage.getItem(KEY));
    if (state && state.date === todayInBogota()) return state;
  } catch {
    /* sin almacenamiento */
  }
  return seed();
}

function save(state) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* sin almacenamiento */
  }
}

const delay = (ms = 250) => new Promise((resolve) => setTimeout(resolve, ms));
const nowIso = () => new Date().toISOString();
const clone = (v) => structuredClone(v);

function productView(product) {
  const imageUrl = product.imageKey ? imageBlobs.get(product.imageKey) || null : null;
  const { imageKey, ...rest } = product;
  return { ...rest, imageUrl };
}

function slugify(text) {
  return text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "producto";
}

const sortProducts = (a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name);

export function adminMock(ApiError) {
  const notFound = (msg) => new ApiError(404, "NOT_FOUND", msg);
  const invalid = (fields) => new ApiError(400, "VALIDATION_ERROR", "Revisa los datos.", { fields });

  return {
    async listOrders(date, status) {
      await delay();
      const state = load();
      const day = date || state.date;
      let orders = Object.values(state.orders).filter((o) => o.pickupDate === day);
      if (status) orders = orders.filter((o) => o.status === status);
      orders.sort((a, b) => a.pickupSlot.localeCompare(b.pickupSlot) || a.createdAt.localeCompare(b.createdAt));
      return { date: day, orders: clone(orders) };
    },

    async changeStatus(orderId, status, reason) {
      await delay();
      const state = load();
      const order = state.orders[orderId];
      if (!order) throw notFound("El pedido no existe.");
      if (!(ADMIN[order.status] || []).includes(status)) {
        throw new ApiError(409, "INVALID_TRANSITION", `El pedido no puede pasar de ${LABELS[order.status]} a ${LABELS[status]}.`, { from: order.status, to: status });
      }
      if (status === "CANCELADO") {
        for (const item of order.items) if (state.products[item.productId]) state.products[item.productId].stock += item.quantity;
      }
      order.status = status;
      order.statusLabel = LABELS[status];
      order.history.push({ status, at: nowIso(), by: "admin-demo" });
      if (reason) console.info("[mock] motivo:", reason);
      save(state);
      return clone(order);
    },

    async listProducts() {
      await delay();
      return { products: Object.values(load().products).sort(sortProducts).map(productView) };
    },

    async createProduct(data) {
      await delay();
      const fields = [];
      if (!data.name || data.name.trim().length < 2) fields.push("name");
      if (!data.category || data.category.trim().length < 2) fields.push("category");
      if (!Number.isInteger(data.price) || data.price < 1) fields.push("price");
      if (!Number.isInteger(data.dailyProduction) || data.dailyProduction < 0) fields.push("dailyProduction");
      if (fields.length) throw invalid(fields);
      const state = load();
      let productId = `p-${slugify(data.name)}`;
      while (state.products[productId]) productId = `p-${slugify(data.name)}-${Math.random().toString(16).slice(2, 6)}`;
      state.products[productId] = { productId, description: "", active: true, ...data, stock: data.dailyProduction, imageKey: null, updatedAt: nowIso() };
      save(state);
      return productView(state.products[productId]);
    },

    async updateProduct(productId, changes) {
      await delay();
      const state = load();
      const product = state.products[productId];
      if (!product) throw notFound("El producto no existe.");
      Object.assign(product, changes, { updatedAt: nowIso() });
      save(state);
      return productView(product);
    },

    async deactivateProduct(productId) {
      await delay();
      const state = load();
      if (!state.products[productId]) throw notFound("El producto no existe.");
      state.products[productId].active = false;
      save(state);
      return null;
    },

    async imageUploadUrl(productId, contentType) {
      await delay();
      if (!IMAGE_TYPES[contentType]) throw invalid(["contentType"]);
      if (!load().products[productId]) throw notFound("El producto no existe.");
      const imageKey = `assets/images/${productId}/${Math.random().toString(16).slice(2, 10)}.${IMAGE_TYPES[contentType]}`;
      return { uploadUrl: `mock-upload:${imageKey}`, imageKey, expiresIn: 300 };
    },

    async uploadImage(uploadUrl, blob) {
      await delay(400);
      imageBlobs.set(uploadUrl.replace("mock-upload:", ""), URL.createObjectURL(blob));
    },

    async updateInventory(items) {
      await delay();
      const state = load();
      const missing = items.filter((i) => !state.products[i.productId]).map((i) => i.productId);
      if (missing.length) throw new ApiError(404, "NOT_FOUND", "Algún producto no existe.", { productIds: missing });
      for (const item of items) {
        const product = state.products[item.productId];
        product.stock = item.stock;
        if (item.dailyProduction !== undefined) product.dailyProduction = item.dailyProduction;
        product.updatedAt = nowIso();
      }
      save(state);
      return { products: items.map((i) => productView(state.products[i.productId])) };
    },

    async stats(date) {
      await delay();
      const state = load();
      const day = date || state.date;
      const orders = Object.values(state.orders).filter((o) => o.pickupDate === day);
      const byStatus = Object.fromEntries(Object.keys(LABELS).map((s) => [s, 0]));
      const units = {};
      const bySlot = {};
      for (let m = 7 * 60; m <= 17 * 60 + 30; m += 30) bySlot[`${pad(Math.floor(m / 60))}:${pad(m % 60)}`] = 0;
      let revenue = 0;
      for (const o of orders) {
        byStatus[o.status] += 1;
        if (o.status === "ENTREGADO") revenue += o.total;
        if (o.status === "CANCELADO") continue;
        bySlot[o.pickupSlot] += 1;
        for (const i of o.items) {
          units[i.productId] = units[i.productId] || { productId: i.productId, name: i.name, units: 0 };
          units[i.productId].units += i.quantity;
        }
      }
      return {
        date: day,
        totalOrders: orders.length,
        byStatus,
        revenueDelivered: revenue,
        unitsByProduct: Object.values(units).sort((a, b) => b.units - a.units || a.name.localeCompare(b.name)),
        ordersBySlot: Object.entries(bySlot).map(([slot, count]) => ({ slot, orders: count })),
      };
    },
  };
}
