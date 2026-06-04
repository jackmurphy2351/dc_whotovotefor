import os

from flask import Flask, render_template

from .config import config
from .data_loader import load_all_content

# Content-Security-Policy directives. script-src is strict ('self' only) — all JS
# lives in external files and there are no inline handlers. style-src allows
# 'unsafe-inline' for the two dynamic width="..." bars (quiz progress, match bar).
_CSP_DIRECTIVES = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data:",
    "font-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "frame-ancestors": "'none'",
    "form-action": "'self'",
}
_CSP_HEADER = "; ".join(f"{k} {v}" for k, v in _CSP_DIRECTIVES.items())


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config[config_name])

    content = load_all_content(app.config["CONTENT_DIR"])
    app.config["CONTENT"] = content

    from .routes.elections import bp as elections_bp
    from .routes.main import bp as main_bp
    from .routes.quiz import bp as quiz_bp
    from .routes.resources import bp as resources_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(elections_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(resources_bp)

    _register_error_handlers(app)
    _register_security_headers(app)

    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(error):  # noqa: ANN001
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(error):  # noqa: ANN001
        return render_template("500.html"), 500


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(response):  # noqa: ANN001
        response.headers["Content-Security-Policy"] = _CSP_HEADER
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # HSTS only over HTTPS (production); avoid pinning local HTTP dev to TLS.
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
