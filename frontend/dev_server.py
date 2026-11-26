"""Servidor local que imita el despliegue en CloudFront (solo biblioteca estándar).

- ``/admin/...``  → ``frontend/admin/``   (prefijo ``admin/`` del bucket web)
- todo lo demás   → ``frontend/client/``  (raíz del bucket web)
- ``/config.js``  → ``client/config.js``; si no existe, ``client/config.example.js`` (modo mock)

Uso:
    cd frontend
    python dev_server.py            # http://localhost:5500 y http://localhost:5500/admin/index.html
    python dev_server.py --port 8080
"""

import argparse
import posixpath
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
CLIENT_DIR = ROOT / "client"
ADMIN_DIR = ROOT / "admin"


class DeployLikeHandler(SimpleHTTPRequestHandler):
    """Elige la carpeta según el prefijo de la URL, como lo hace el despliegue real."""

    def translate_path(self, path: str) -> str:
        url_path = posixpath.normpath(urlsplit(path).path)
        if url_path == "/config.js":
            local = CLIENT_DIR / "config.js"
            return str(local if local.exists() else CLIENT_DIR / "config.example.js")
        if url_path == "/admin" or url_path.startswith("/admin/"):
            self.directory = str(ADMIN_DIR)
            path = path[len("/admin") :] or "/"
        else:
            self.directory = str(CLIENT_DIR)
        # SimpleHTTPRequestHandler ya descarta ".." y segmentos peligrosos dentro de self.directory.
        return super().translate_path(path)

    def end_headers(self) -> None:
        # Sin caché en local: así cada cambio se ve al recargar.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor local de los frontends de Pan de la Casa")
    parser.add_argument("--port", type=int, default=5500)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    handler = partial(DeployLikeHandler, directory=str(CLIENT_DIR))
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"Cliente: http://localhost:{args.port}/")
        print(f"Admin:   http://localhost:{args.port}/admin/index.html")
        print("Ctrl+C para detener.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")


if __name__ == "__main__":
    main()
