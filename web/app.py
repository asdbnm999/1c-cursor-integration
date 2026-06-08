"""Точка входа веб-приложения 1C:Cursor."""

from __future__ import annotations

import argparse
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from flask import Flask, jsonify

from web.paths import DEFAULT_HOST, DEFAULT_PORT
from web.routes import create_blueprints
from web.routes.dashboard import dashboard_api_bp
from web.routes.kb import register_kb_blueprints
from web.routes.mcp import mcp_api_bp, mcp_page_bp
from web.routes.plugins import plugins_api_bp, plugins_page_bp
from web.routes.rules import rules_api_bp, rules_page_bp
from web.settings import get_palette, load_settings


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024

    @app.context_processor
    def inject_globals():
        return {
            "ui_palette": get_palette(),
        }

    for bp in create_blueprints():
        app.register_blueprint(bp)
    app.register_blueprint(plugins_page_bp)
    app.register_blueprint(plugins_api_bp)
    app.register_blueprint(mcp_page_bp)
    app.register_blueprint(mcp_api_bp)
    app.register_blueprint(dashboard_api_bp)
    app.register_blueprint(rules_page_bp)
    app.register_blueprint(rules_api_bp)
    register_kb_blueprints(app)

    from packages.kb.indexer.api_auth import register_api_auth
    from packages.kb.indexer.watcher import restore_watchers

    register_api_auth(app)
    restored = restore_watchers()
    if restored:
        app.logger.info("KB watch restored: %s", ", ".join(restored))

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "1c-cursor-web"})

    @app.route("/api/settings/ui", methods=["GET"])
    def get_ui_settings():
        settings = load_settings()
        return jsonify({"palette": settings.get("ui", {}).get("palette", "midnight")})

    @app.route("/api/settings/ui", methods=["PUT"])
    def put_ui_settings():
        from flask import request

        from web.settings import load_settings, save_settings

        payload = request.get_json(silent=True) or {}
        palette = payload.get("palette", "midnight")
        if palette not in {"midnight", "ocean", "forest", "ember"}:
            return jsonify({"error": "Неизвестная палитра"}), 400
        settings = load_settings()
        settings.setdefault("ui", {})["palette"] = palette
        save_settings(settings)
        return jsonify({"palette": palette})

    return app


app = create_app()


def _browser_url(host: str, port: int) -> str:
    """URL для открытия в браузере (всегда loopback, ТЗ §5.3)."""
    if host in {"0.0.0.0", "::", "[::]"}:
        return f"http://127.0.0.1:{port}/"
    return f"http://{host}:{port}/"


def _schedule_browser_open(host: str, port: int) -> None:
    """Открыть UI после готовности /api/health (фоновый поток)."""
    page_url = _browser_url(host, port)
    health_url = f"http://127.0.0.1:{port}/api/health"

    def _worker() -> None:
        for _ in range(60):
            try:
                with urllib.request.urlopen(health_url, timeout=0.5) as resp:
                    if resp.status == 200:
                        webbrowser.open(page_url)
                        return
            except (urllib.error.URLError, OSError, TimeoutError):
                pass
            time.sleep(0.1)
        webbrowser.open(page_url)

    threading.Thread(target=_worker, daemon=True, name="1c-cursor-open-browser").start()


def main() -> None:
    parser = argparse.ArgumentParser(description="1C:Cursor — веб-интерфейс настройки среды 1С в Cursor")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Не открывать браузер автоматически (CI, удалённый доступ)",
    )
    args = parser.parse_args()

    app = create_app()
    page_url = _browser_url(args.host, args.port)
    print(f"1C:Cursor → {page_url}")
    if not args.no_browser:
        _schedule_browser_open(args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
