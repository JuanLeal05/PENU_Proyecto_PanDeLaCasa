// Configuración de ejemplo para desarrollo LOCAL (contrato 04 §5).
//
// En los ambientes reales este archivo NO se usa: el pipeline genera /config.js a partir de los
// outputs de Terraform. Para trabajar en local:
//   cp frontend/client/config.example.js frontend/client/config.js   (config.js está en .gitignore)
//
// Con useMock: true los frontends usan respuestas simuladas (js/mock.js) y no llaman a ninguna URL.
// Para probar contra dev: useMock: false y las URLs que entregue Juan Pablo, con este formato:
//   apiBase:    "https://<api-id>.execute-api.us-east-1.amazonaws.com"
//   assetsBase: "https://<distribucion>.cloudfront.net/assets"
//   cognito.domain: "https://<prefijo>.auth.us-east-1.amazoncognito.com"
window.APP_CONFIG = {
  env: "local",
  apiBase: "",
  assetsBase: "",
  cognito: {
    domain: "",
    clientId: "",
    redirectUri: "http://localhost:5500/admin/index.html",
    logoutUri: "http://localhost:5500/admin/index.html"
  },
  pollIntervalMs: 20000,
  useMock: true
};
