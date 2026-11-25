// Piezas de UI propias del panel (las genéricas vienen de /js/util.js del sitio del cliente).
import { el } from "/js/util.js";

/**
 * Diálogo con un campo de texto opcional (p. ej. el motivo de una cancelación).
 * Resuelve con el texto (puede ser "") o con null si se cancela.
 */
export function promptDialog({ title, message, label, confirmText = "Confirmar", cancelText = "Volver", maxLength = 200 }) {
  return new Promise((resolve) => {
    const titleId = `dlg-${Math.random().toString(36).slice(2)}`;
    const inputId = `${titleId}-input`;
    const input = el("textarea", { attrs: { id: inputId, rows: 3, maxlength: maxLength } });
    const form = el("form", { className: "dialogo__form", attrs: { method: "dialog" } }, [
      el("h2", { text: title, attrs: { id: titleId } }),
      message ? el("p", { text: message }) : null,
      el("label", { text: label, attrs: { for: inputId } }),
      input,
    ]);
    const dialog = el("dialog", { className: "dialogo", attrs: { "aria-labelledby": titleId } }, [form]);
    const done = (value) => {
      dialog.close();
      dialog.remove();
      resolve(value);
    };
    form.append(
      el("div", { className: "dialogo__acciones" }, [
        el("button", { className: "boton boton--secundario", type: "button", text: cancelText, on: { click: () => done(null) } }),
        el("button", { className: "boton boton--peligro", type: "submit", text: confirmText }),
      ]),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      done(input.value.trim());
    });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      done(null);
    });
    document.body.append(dialog);
    dialog.showModal();
    input.focus();
  });
}

/** Refresco periódico que se pausa con la pestaña oculta. Devuelve una función para detenerlo. */
export function autoRefresh(callback, intervalMs) {
  let timer = null;
  const start = () => {
    stop();
    timer = window.setInterval(callback, intervalMs);
  };
  const stop = () => {
    if (timer) window.clearInterval(timer);
    timer = null;
  };
  const onVisibility = () => {
    if (document.hidden) stop();
    else {
      callback();
      start();
    }
  };
  document.addEventListener("visibilitychange", onVisibility);
  if (!document.hidden) start();
  return () => {
    stop();
    document.removeEventListener("visibilitychange", onVisibility);
  };
}

/** Encabezado estándar de una vista: título + controles. */
export function viewHeader(title, controls = []) {
  return el("div", { className: "vista__encabezado" }, [
    el("h2", { text: title, attrs: { id: "vista-titulo", tabindex: "-1" } }),
    el("div", { className: "vista__controles" }, controls),
  ]);
}
