// API simulada para desarrollo local (useMock: true). Imita el contrato 02: mismos cuerpos,
// mismos códigos de error y la misma lógica de franjas (06:00–18:00, franjas de 07:00 a 17:30,
// 10 cupos, 30 min de anticipación). El estado vive en localStorage para que pedido.html lo vea.
//
// Para poder probar de noche: si la hora real está fuera del horario, el mock simula las 08:00.
// El pedido avanza solo: a los 40 s pasa a EN_PREPARACION y a los 80 s a LISTO_PARA_RECOGER,
// para ver el polling funcionando.

const STATE_KEY = "pdc_mock_state";
const CAPACITY = 10;
const OPEN = 6 * 60;
const CLOSE = 18 * 60;
const LEAD = 30;
const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const LABELS = {
  CONFIRMADO: "Confirmado",
  EN_PREPARACION: "En preparación",
  LISTO_PARA_RECOGER: "Listo para recoger",
  ENTREGADO: "Entregado",
  CANCELADO: "Cancelado",
  NO_RECOGIDO: "No recogido",
};

export const MOCK_CATALOG = {
  generatedAt: "2026-11-27T06:00:00-05:00",
  currency: "COP",
  products: [
    { productId: "p-croissant", name: "Croissant", description: "Hojaldre de mantequilla francesa.", category: "Hojaldres", price: 4500, imageUrl: null },
    { productId: "p-roscon-arequipe", name: "Roscón de arequipe", description: "Roscón azucarado relleno de arequipe.", category: "Hojaldres", price: 3500, imageUrl: null },
    { productId: "p-almojabana", name: "Almojábana", description: "Tradicional almojábana de cuajada.", category: "Panes", price: 2500, imageUrl: null },
    { productId: "p-mogolla-integral", name: "Mogolla integral", description: "Mogolla de harina integral con salvado.", category: "Panes", price: 1200, imageUrl: null },
    { productId: "p-pan-queso", name: "Pan de queso", description: "Pan suave relleno de queso campesino.", category: "Panes", price: 1500, imageUrl: null },
    { productId: "p-pan-frances", name: "Pan francés", description: "Baguette pequeña de corteza crujiente.", category: "Panes", price: 800, imageUrl: null },
    { productId: "p-pandebono", name: "Pandebono", description: "Pandebono vallecaucano de yuca y queso.", category: "Panes", price: 2500, imageUrl: null },
    { productId: "p-mantecada", name: "Mantecada", description: "Mantecada casera esponjosa.", category: "Tortas", price: 3000, imageUrl: null },
    { productId: "p-torta-zanahoria", name: "Torta de zanahoria (porción)", description: "Con nueces y cobertura de queso crema.", category: "Tortas", price: 6000, imageUrl: null },
    { productId: "p-galletas-avena", name: "Galletas de avena (x6)", description: "Seis galletas de avena y uvas pasas.", category: "Galletas", price: 5000, imageUrl: null },
    { productId: "p-cafe-tinto", name: "Café tinto", description: "Tinto colombiano recién colado.", category: "Bebidas", price: 2500, imageUrl: null },
    { productId: "p-chocolate-caliente", name: "Chocolate caliente", description: "Chocolate santafereño en taza grande.", category: "Bebidas", price: 4000, imageUrl: null },
  ],
};

const INITIAL_STOCK = {
  "p-croissant": 42, "p-roscon-arequipe": 3, "p-almojabana": 30, "p-mogolla-integral": 25,
  "p-pan-queso": 0, "p-pan-frances": 120, "p-pandebono": 18, "p-mantecada": 12,
  "p-torta-zanahoria": 5, "p-galletas-avena": 8, "p-cafe-tinto": 60, "p-chocolate-caliente": 40,
};

function pad(n) {
  return String(n).padStart(2, "0");
}

/** "Ahora" en Bogotá como {date, minutes, iso}. Fuera de horario simula las 08:00. */
function mockNow() {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    }).formatToParts(new Date()).map((p) => [p.type, p.value]),
  );
  const date = `${parts.year}-${parts.month}-${parts.day}`;
  let minutes = Number(parts.hour) * 60 + Number(parts.minute);
  let seconds = Number(parts.second);
  if (minutes < OPEN || minutes >= CLOSE - LEAD) {
    minutes = 8 * 60;
    seconds = 0;
  }
  const iso = `${date}T${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}:${pad(seconds)}-05:00`;
  return { date, minutes, iso };
}

function allSlots() {
  const slots = [];
  for (let m = 7 * 60; m <= 17 * 60 + 30; m += 30) slots.push(`${pad(Math.floor(m / 60))}:${pad(m % 60)}`);
  return slots;
}

function toMinutes(slot) {
  const [h, m] = slot.split(":").map(Number);
  return h * 60 + m;
}

function loadState(today) {
  let state = null;
  try {
    state = JSON.parse(window.localStorage.getItem(STATE_KEY));
  } catch {
    state = null;
  }
  if (!state || state.date !== today) {
    // Día nuevo: stock de la producción diaria y algunas franjas ya ocupadas para ver los casos.
    state = {
      date: today,
      stock: { ...INITIAL_STOCK },
      slots: { "07:00": 10, "07:30": 10, "10:00": 8, "11:00": 10, "12:30": 4 },
      orders: {},
      idempotency: {},
    };
  }
  return state;
}

function saveState(state) {
  try {
    window.localStorage.setItem(STATE_KEY, JSON.stringify(state));
  } catch {
    /* sin almacenamiento el mock sigue funcionando en memoria */
  }
}

function delay(ms = 350) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Avance automático del pedido en el mock (simula al personal de la panadería). */
function progress(order) {
  if (order.status === "CANCELADO") return order;
  const elapsed = (Date.now() - order._createdAtMs) / 1000;
  const steps = [
    [40, "EN_PREPARACION"],
    [80, "LISTO_PARA_RECOGER"],
  ];
  for (const [seconds, status] of steps) {
    if (elapsed >= seconds && !order.history.some((h) => h.status === status)) {
      const at = new Date(order._createdAtMs + seconds * 1000);
      order.history.push({ status, at: at.toISOString() });
      order.status = status;
      order.statusLabel = LABELS[status];
    }
  }
  return order;
}

function publicView(order) {
  const { _createdAtMs, _code, ...view } = order;
  return structuredClone(view);
}

function hashBody(body) {
  return JSON.stringify(body, Object.keys(body).sort());
}

export function mockApi(ApiError) {
  const reject = (code, message, details = {}) => new ApiError(409, code, message, details);

  return {
    async getCatalog() {
      await delay(200);
      return structuredClone(MOCK_CATALOG);
    },

    async getAvailability() {
      await delay();
      const now = mockNow();
      const state = loadState(now.date);
      saveState(state);
      const storeOpen = now.minutes >= OPEN && now.minutes < CLOSE;
      return {
        date: now.date,
        storeOpen,
        openTime: "06:00",
        closeTime: "18:00",
        slots: allSlots().map((slot) => {
          const remaining = Math.max(CAPACITY - (state.slots[slot] || 0), 0);
          const available = storeOpen && remaining > 0 && toMinutes(slot) >= now.minutes + LEAD;
          return { slot, remaining, available };
        }),
        stock: { ...state.stock },
      };
    },

    async createOrder(body, idempotencyKey) {
      await delay(500);
      const now = mockNow();
      const state = loadState(now.date);
      const bodyHash = hashBody(body);
      const previous = state.idempotency[idempotencyKey];
      if (previous) {
        if (previous.hash !== bodyHash) throw reject("IDEMPOTENCY_CONFLICT", "Esta Idempotency-Key ya se usó con un pedido distinto.");
        return { status: 200, order: structuredClone(previous.response) };
      }

      const fields = [];
      const c = body.customer || {};
      if (!c.name || c.name.trim().length < 2 || c.name.trim().length > 60) fields.push("customer.name");
      if (!/^3\d{9}$/.test(c.phone || "")) fields.push("customer.phone");
      if (c.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email)) fields.push("customer.email");
      if (body.dataConsent !== true) fields.push("dataConsent");
      const units = (body.items || []).reduce((sum, i) => sum + i.quantity, 0);
      if (!body.items || !body.items.length || units > 20 || body.items.length > 10) fields.push("items");
      if (fields.length) throw new ApiError(400, "VALIDATION_ERROR", "Revisa los datos del pedido.", { fields });

      if (!allSlots().includes(body.pickupSlot) || toMinutes(body.pickupSlot) < now.minutes + LEAD) {
        throw reject("SLOT_NOT_AVAILABLE", `La franja ${body.pickupSlot} no está disponible.`);
      }
      if ((state.slots[body.pickupSlot] || 0) >= CAPACITY) {
        throw reject("SLOT_FULL", `La franja ${body.pickupSlot} ya no tiene cupos.`);
      }
      const products = Object.fromEntries(MOCK_CATALOG.products.map((p) => [p.productId, p]));
      const missing = body.items.filter((i) => !products[i.productId]).map((i) => i.productId);
      if (missing.length) throw reject("PRODUCT_NOT_FOUND", "Algún producto ya no está disponible.", { productIds: missing });
      const short = body.items.filter((i) => (state.stock[i.productId] || 0) < i.quantity).map((i) => i.productId);
      if (short.length) throw reject("OUT_OF_STOCK", "No hay suficientes unidades de algunos productos.", { productIds: short });

      for (const item of body.items) state.stock[item.productId] -= item.quantity;
      state.slots[body.pickupSlot] = (state.slots[body.pickupSlot] || 0) + 1;
      const items = body.items.map((i) => ({
        productId: i.productId,
        name: products[i.productId].name,
        unitPrice: products[i.productId].price,
        quantity: i.quantity,
        subtotal: products[i.productId].price * i.quantity,
      }));
      const code = Array.from(window.crypto.getRandomValues(new Uint8Array(6)), (b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join("");
      const order = {
        orderId: window.crypto.randomUUID ? window.crypto.randomUUID() : `mock-${Date.now()}`,
        status: "CONFIRMADO",
        statusLabel: LABELS.CONFIRMADO,
        pickupDate: now.date,
        pickupSlot: body.pickupSlot,
        items,
        total: items.reduce((sum, i) => sum + i.subtotal, 0),
        createdAt: now.iso,
        history: [{ status: "CONFIRMADO", at: now.iso }],
        _createdAtMs: Date.now(),
        _code: code,
      };
      state.orders[order.orderId] = order;
      const response = { ...publicView(order), code };
      state.idempotency[idempotencyKey] = { hash: bodyHash, response };
      saveState(state);
      return { status: 201, order: structuredClone(response) };
    },

    async getOrder(orderId, code) {
      await delay();
      const state = loadState(mockNow().date);
      const order = state.orders[orderId];
      if (!order || order._code !== String(code || "").toUpperCase()) {
        throw new ApiError(404, "NOT_FOUND", "No encontramos ese pedido. Revisa el enlace.");
      }
      progress(order);
      saveState(state);
      return publicView(order);
    },

    async cancelOrder(orderId, code) {
      await delay();
      const state = loadState(mockNow().date);
      const order = state.orders[orderId];
      if (!order || order._code !== String(code || "").toUpperCase()) {
        throw new ApiError(404, "NOT_FOUND", "No encontramos ese pedido. Revisa el enlace.");
      }
      progress(order);
      if (order.status !== "CONFIRMADO") {
        throw reject("INVALID_TRANSITION", `El pedido no puede pasar de ${order.statusLabel} a Cancelado.`);
      }
      order.status = "CANCELADO";
      order.statusLabel = LABELS.CANCELADO;
      order.history.push({ status: "CANCELADO", at: mockNow().iso });
      for (const item of order.items) state.stock[item.productId] += item.quantity;
      state.slots[order.pickupSlot] = Math.max((state.slots[order.pickupSlot] || 1) - 1, 0);
      saveState(state);
      return publicView(order);
    },
  };
}
