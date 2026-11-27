// Shell del panel: login, navegación por hash (#/pedidos #/productos #/inventario #/estadisticas)
// y montaje/desmontaje de vistas (cada vista devuelve una función de limpieza).
import { setUnauthorizedHandler } from "./api.js";
import { getSession, handleRedirect, isMock, login, logout } from "./auth.js";
import { inventoryView } from "./views/inventory.js";
import { ordersView } from "./views/orders.js";
import { productsView } from "./views/products.js";
import { statsView } from "./views/stats.js";
import { clear, el, showMessage } from "/js/util.js";

const ROUTES = {
  "#/pedidos": { title: "Pedidos", view: ordersView },
  "#/productos": { title: "Productos", view: productsView },
  "#/inventario": { title: "Inventario", view: inventoryView },
  "#/estadisticas": { title: "Estadísticas", view: statsView },
};
const DEFAULT_ROUTE = "#/pedidos";

const loginScreen = document.getElementById("pantalla-login");
const appScreen = document.getElementById("pantalla-app");
const loginButton = document.getElementById("boton-login");
const loginMessage = document.getElementById("mensaje-login");
const logoutButton = document.getElementById("boton-logout");
const userLabel = document.getElementById("usuario");
const viewRoot = document.getElementById("vista");
const toast = document.getElementById("notificacion");

let unmount = null;

function notify(text, kind = "ok") {
  showMessage(toast, text, kind, 4000);
}

function showLogin(text) {
  if (unmount) unmount();
  unmount = null;
  appScreen.hidden = true;
  loginScreen.hidden = false;
  loginButton.textContent = isMock ? "Entrar (mock)" : "Iniciar sesión";
  if (text) showMessage(loginMessage, text, "error");
  loginButton.focus();
}

function route() {
  const session = getSession();
  if (!session) {
    showLogin();
    return;
  }
  loginScreen.hidden = true;
  appScreen.hidden = false;
  userLabel.textContent = session.username;

  const hash = ROUTES[window.location.hash] ? window.location.hash : DEFAULT_ROUTE;
  if (window.location.hash !== hash) {
    window.history.replaceState({}, "", hash);
  }
  for (const link of document.querySelectorAll(".nav a")) {
    if (link.getAttribute("href") === hash) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (unmount) unmount();
  clear(viewRoot);
  const { title, view } = ROUTES[hash];
  document.title = `${title} · Pan de la Casa (admin)`;
  unmount = view(viewRoot, { notify }) || null;
  const heading = document.getElementById("vista-titulo");
  if (heading) heading.focus({ preventScroll: true });
}

loginButton.addEventListener("click", async () => {
  loginButton.disabled = true;
  try {
    await login();
    if (isMock) route();
  } catch (err) {
    showMessage(loginMessage, err.message, "error");
  } finally {
    loginButton.disabled = false;
  }
});
logoutButton.addEventListener("click", logout);
window.addEventListener("hashchange", route);
setUnauthorizedHandler(() => showLogin("Tu sesión expiró. Inicia sesión de nuevo."));

async function start() {
  if (isMock) document.body.append(el("p", { className: "modo-demo", text: "Modo demo (datos simulados)" }));
  const result = await handleRedirect();
  if (result !== "none" && result !== "ok") {
    showLogin(result);
    return;
  }
  route();
}

start();
