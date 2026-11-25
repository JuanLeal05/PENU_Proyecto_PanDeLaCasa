// Catálogo agrupado por categoría. Los datos del catálogo vienen del JSON estático (CloudFront) y
// el stock de /api/availability: se combinan aquí.
import { clear, el, formatCOP, safeUrl } from "./util.js";

const LOW_STOCK = 5;

function productImage(product) {
  const src = safeUrl(product.imageUrl);
  if (src) {
    return el("img", {
      className: "producto__foto",
      attrs: { src, alt: product.name, loading: "lazy", decoding: "async", width: 320, height: 240 },
    });
  }
  // Sin foto: una inicial sobre fondo cálido (decorativa).
  return el("div", { className: "producto__foto producto__foto--vacia", attrs: { "aria-hidden": "true" } }, [
    el("span", { text: product.name.charAt(0) }),
  ]);
}

function stockBadge(stock) {
  if (stock === undefined) return null;
  if (stock <= 0) return el("span", { className: "etiqueta etiqueta--agotado", text: "Agotado" });
  if (stock <= LOW_STOCK) return el("span", { className: "etiqueta etiqueta--pocos", text: `Quedan ${stock}` });
  return null;
}

/**
 * Pinta el catálogo en `container`.
 * - `stock`: { productId: unidades } (los productos sin entrada no están activos hoy).
 * - `canOrder`: false si la tienda está cerrada.
 * - `cart` / `onAdd(productId)`: estado del carrito y acción del botón.
 */
export function renderCatalog(container, { catalog, stock, canOrder, cart, onAdd, highlight = new Set() }) {
  clear(container);
  const byCategory = new Map();
  for (const product of catalog.products || []) {
    if (stock && !(product.productId in stock)) continue; // inactivo hoy
    if (!byCategory.has(product.category)) byCategory.set(product.category, []);
    byCategory.get(product.category).push(product);
  }
  if (!byCategory.size) {
    container.append(el("p", { className: "vacio", text: "Hoy no hay productos disponibles. Vuelve pronto." }));
    return;
  }

  for (const [category, products] of byCategory) {
    const headingId = `cat-${category.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    const list = el("ul", { className: "productos", attrs: { role: "list" } });
    for (const product of products) {
      const available = stock ? stock[product.productId] : undefined;
      const inCart = cart.quantity(product.productId);
      const reason = canOrder ? cart.blockReason(product.productId, available) : "Tienda cerrada";
      const button = el("button", {
        className: "boton boton--primario producto__agregar",
        type: "button",
        text: available === 0 ? "Agotado" : "Agregar",
        disabled: Boolean(reason),
        attrs: {
          "aria-label": `Agregar ${product.name} al pedido`,
          title: reason || null,
        },
        on: { click: () => onAdd(product.productId) },
      });
      list.append(
        el("li", {
          className: `producto${highlight.has(product.productId) ? " producto--alerta" : ""}`,
          dataset: { productId: product.productId },
        }, [
          productImage(product),
          el("div", { className: "producto__cuerpo" }, [
            el("div", { className: "producto__titulo" }, [
              el("h3", { text: product.name }),
              stockBadge(available),
            ]),
            product.description ? el("p", { className: "producto__descripcion", text: product.description }) : null,
            el("div", { className: "producto__pie" }, [
              el("span", { className: "producto__precio", text: formatCOP(product.price) }),
              inCart ? el("span", { className: "producto__en-carrito", text: `${inCart} en tu pedido` }) : null,
              button,
            ]),
          ]),
        ]),
      );
    }
    container.append(
      el("section", { className: "categoria", attrs: { "aria-labelledby": headingId } }, [
        el("h2", { text: category, attrs: { id: headingId } }),
        list,
      ]),
    );
  }
}
