// #/productos: tabla (activos e inactivos), formulario de crear/editar, activar/desactivar y foto.
// Foto: archivo → WebP en el navegador con <canvas> (máx. 1200 px, calidad 0.8; optimización FinOps)
//       → POST /image (URL prefirmada) → PUT directo a S3 → PUT /products/{id} con imageKey.
import { api } from "../api.js";
import { viewHeader } from "../ui.js";
import { clear, confirmDialog, el, formatCOP, safeUrl, showMessage } from "/js/util.js";

const MAX_WIDTH = 1200;
const WEBP_QUALITY = 0.8;
const MAX_FILE_BYTES = 15 * 1024 * 1024;

/** Convierte cualquier imagen que el navegador pueda leer a WebP reducida. */
export async function toWebp(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_WIDTH / bitmap.width);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/webp", WEBP_QUALITY));
  // Algunos navegadores antiguos no generan WebP: se cae a JPEG (también aceptado por el contrato).
  if (blob && blob.type === "image/webp") return { blob, contentType: "image/webp" };
  const jpeg = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", WEBP_QUALITY));
  return { blob: jpeg, contentType: "image/jpeg" };
}

const FIELDS = [
  { name: "name", label: "Nombre", type: "text", required: true, maxlength: 80 },
  { name: "category", label: "Categoría", type: "text", required: true, maxlength: 40, list: "categorias" },
  { name: "price", label: "Precio (COP)", type: "number", required: true, min: 1, step: 1 },
  { name: "dailyProduction", label: "Producción diaria", type: "number", required: true, min: 0, step: 1 },
  { name: "description", label: "Descripción", type: "textarea", maxlength: 300 },
];

const FIELD_ERRORS = {
  name: "Entre 2 y 80 caracteres.",
  category: "Entre 2 y 40 caracteres.",
  price: "Entero mayor que 0.",
  dailyProduction: "Entero de 0 o más.",
  description: "Máximo 300 caracteres.",
  active: "Valor inválido.",
};

export function productsView(root, { notify }) {
  const message = el("p", { className: "aviso", attrs: { role: "alert" }, hidden: true });
  const newButton = el("button", { className: "boton boton--primario", type: "button", text: "Nuevo producto" });
  const table = el("div", { className: "tabla-contenedor" });
  const formPanel = el("section", { className: "tarjeta formulario-producto", hidden: true, attrs: { "aria-labelledby": "form-producto-titulo" } });
  const categories = el("datalist", { attrs: { id: "categorias" } });
  root.append(viewHeader("Productos", [newButton]), message, formPanel, table, categories);

  let products = [];

  // --- formulario ------------------------------------------------------------------------------

  function openForm(product = null) {
    clear(formPanel);
    formPanel.hidden = false;
    const inputs = {};
    const form = el("form", { className: "formulario", attrs: { novalidate: true } });
    for (const field of FIELDS) {
      const id = `producto-${field.name}`;
      const input = field.type === "textarea"
        ? el("textarea", { attrs: { id, rows: 2, maxlength: field.maxlength } })
        : el("input", { attrs: { id, type: field.type, required: field.required, maxlength: field.maxlength, min: field.min, step: field.step, list: field.list, inputmode: field.type === "number" ? "numeric" : null } });
      input.value = product ? product[field.name] ?? "" : "";
      inputs[field.name] = input;
      form.append(
        el("div", { className: "campo" }, [
          el("label", { text: field.label, attrs: { for: id } }),
          input,
          el("p", { className: "campo__error", attrs: { id: `${id}-error` }, hidden: true }),
        ]),
      );
    }
    const active = el("input", { attrs: { id: "producto-active", type: "checkbox" } });
    active.checked = product ? product.active : true;
    form.append(el("div", { className: "campo campo--check" }, [active, el("label", { text: "Activo (visible en el catálogo)", attrs: { for: "producto-active" } })]));

    const formMessage = el("p", { className: "aviso", attrs: { role: "alert" }, hidden: true });
    const submit = el("button", { className: "boton boton--primario", type: "submit", text: product ? "Guardar cambios" : "Crear producto" });
    form.append(
      formMessage,
      el("div", { className: "acciones" }, [
        submit,
        el("button", { className: "boton boton--secundario", type: "button", text: "Cerrar", on: { click: () => { formPanel.hidden = true; } } }),
      ]),
    );

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      for (const name of Object.keys(inputs)) setError(name, null);
      const data = {
        name: inputs.name.value.trim(),
        category: inputs.category.value.trim(),
        price: Number(inputs.price.value),
        dailyProduction: Number(inputs.dailyProduction.value),
        description: inputs.description.value.trim(),
        active: active.checked,
      };
      const local = [];
      if (data.name.length < 2) local.push("name");
      if (data.category.length < 2) local.push("category");
      if (!Number.isInteger(data.price) || data.price < 1) local.push("price");
      if (!Number.isInteger(data.dailyProduction) || data.dailyProduction < 0) local.push("dailyProduction");
      if (local.length) {
        local.forEach((f) => setError(f, FIELD_ERRORS[f]));
        inputs[local[0]].focus();
        return;
      }
      submit.disabled = true;
      try {
        if (product) {
          // Solo se envía lo que cambió (actualización parcial).
          const changes = Object.fromEntries(Object.entries(data).filter(([k, v]) => product[k] !== v));
          if (Object.keys(changes).length) await api.updateProduct(product.productId, changes);
          notify(`Producto "${data.name}" actualizado.`);
        } else {
          const created = await api.createProduct(data);
          notify(`Producto "${created.name}" creado (${created.productId}).`);
        }
        formPanel.hidden = true;
        await load();
      } catch (err) {
        for (const field of err.details?.fields || []) setError(field, FIELD_ERRORS[field] || "Valor inválido.");
        showMessage(formMessage, err.message, "error");
      } finally {
        submit.disabled = false;
      }
    });

    function setError(name, text) {
      const input = inputs[name];
      const error = document.getElementById(`producto-${name}-error`);
      if (!input || !error) return;
      input.setAttribute("aria-invalid", text ? "true" : "false");
      error.textContent = text || "";
      error.hidden = !text;
    }

    formPanel.append(el("h3", { text: product ? `Editar ${product.name}` : "Nuevo producto", attrs: { id: "form-producto-titulo" } }), form);
    inputs.name.focus();
    formPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // --- foto ------------------------------------------------------------------------------------

  async function uploadPhoto(product, file, statusNode) {
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > MAX_FILE_BYTES) {
      showMessage(message, "Elige una imagen (JPEG, PNG o WebP) de máximo 15 MB.", "error", 6000);
      return;
    }
    try {
      statusNode.textContent = "Optimizando…";
      const { blob, contentType } = await toWebp(file);
      statusNode.textContent = "Subiendo…";
      const { uploadUrl, imageKey } = await api.imageUploadUrl(product.productId, contentType);
      await api.uploadImage(uploadUrl, blob, contentType);
      await api.updateProduct(product.productId, { imageKey });
      notify(`Foto de "${product.name}" actualizada (${Math.round(blob.size / 1024)} KB). Se verá en el catálogo en ≤ 60 s.`);
      await load();
    } catch (err) {
      statusNode.textContent = "";
      showMessage(message, err.message || "No se pudo procesar la foto.", "error", 8000);
    }
  }

  // --- tabla -----------------------------------------------------------------------------------

  async function toggleActive(product) {
    if (product.active) {
      const ok = await confirmDialog({
        title: `¿Desactivar "${product.name}"?`,
        message: "Dejará de aparecer en el catálogo. Los pedidos existentes no cambian.",
        confirmText: "Desactivar",
        cancelText: "Volver",
      });
      if (!ok) return;
    }
    try {
      if (product.active) await api.deactivateProduct(product.productId);
      else await api.updateProduct(product.productId, { active: true });
      notify(`"${product.name}" ${product.active ? "desactivado" : "activado"}.`);
      await load();
    } catch (err) {
      showMessage(message, err.message, "error", 6000);
    }
  }

  function render() {
    clear(table);
    clear(categories);
    for (const category of new Set(products.map((p) => p.category))) categories.append(el("option", { value: category }));
    if (!products.length) {
      table.append(el("p", { className: "vacio", text: "Aún no hay productos." }));
      return;
    }
    const rows = products.map((product) => {
      const photoStatus = el("span", { className: "foto__estado", attrs: { "aria-live": "polite" } });
      const fileId = `foto-${product.productId}`;
      const fileInput = el("input", {
        className: "visualmente-oculto",
        attrs: { id: fileId, type: "file", accept: "image/jpeg,image/png,image/webp" },
        on: { change: (e) => uploadPhoto(product, e.target.files[0], photoStatus) },
      });
      const src = safeUrl(product.imageUrl);
      return el("tr", { className: product.active ? "" : "fila--inactiva" }, [
        el("td", { className: "celda-foto" }, [
          src ? el("img", { attrs: { src, alt: "", width: 56, height: 56, loading: "lazy" } }) : el("span", { className: "sin-foto", text: "Sin foto" }),
        ]),
        el("th", { attrs: { scope: "row" } }, [
          el("span", { text: product.name }),
          el("span", { className: "celda__sub", text: product.productId }),
        ]),
        el("td", { text: product.category }),
        el("td", { className: "num", text: formatCOP(product.price) }),
        el("td", { className: "num", text: `${product.stock} / ${product.dailyProduction}` }),
        el("td", {}, [el("span", { className: `estado ${product.active ? "estado--entregado" : "estado--cancelado"}`, text: product.active ? "Activo" : "Inactivo" })]),
        el("td", { className: "acciones-fila" }, [
          el("button", { className: "boton boton--chico boton--secundario", type: "button", text: "Editar", attrs: { "aria-label": `Editar ${product.name}` }, on: { click: () => openForm(product) } }),
          fileInput,
          el("label", { className: "boton boton--chico boton--secundario", text: "Foto", attrs: { for: fileId, "aria-label": `Subir foto de ${product.name}` } }),
          el("button", {
            className: `boton boton--chico ${product.active ? "boton--peligro-suave" : "boton--primario"}`,
            type: "button",
            text: product.active ? "Desactivar" : "Activar",
            attrs: { "aria-label": `${product.active ? "Desactivar" : "Activar"} ${product.name}` },
            on: { click: () => toggleActive(product) },
          }),
          photoStatus,
        ]),
      ]);
    });
    table.append(
      el("table", { className: "tabla" }, [
        el("caption", { className: "visualmente-oculto", text: "Productos de la panadería" }),
        el("thead", {}, [
          el("tr", {}, ["Foto", "Producto", "Categoría", "Precio", "Stock / producción", "Estado", "Acciones"].map((h) => el("th", { text: h, attrs: { scope: "col" } }))),
        ]),
        el("tbody", {}, rows),
      ]),
    );
  }

  async function load() {
    try {
      products = (await api.listProducts()).products;
      render();
    } catch (err) {
      if (err.status !== 401) showMessage(message, err.message, "error");
    }
  }

  newButton.addEventListener("click", () => openForm());
  load();
}
