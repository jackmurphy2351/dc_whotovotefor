import os

from flask import Flask, g, render_template, request, session, url_for

from .config import config
from .data_loader import load_all_content
from .i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    current_lang,
    format_date,
    load_ui,
    plural,
    translate_ui,
)

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

    content_dir = app.config["CONTENT_DIR"]
    # English is the canonical, validated content; other languages are overlays.
    english = load_all_content(content_dir)
    app.config["CONTENT"] = english
    app.config["CONTENT_BY_LANG"] = {
        lang: english if lang == DEFAULT_LANGUAGE else load_all_content(content_dir, lang)
        for lang in SUPPORTED_LANGUAGES
    }
    app.config["UI_BY_LANG"] = {lang: load_ui(content_dir, lang) for lang in SUPPORTED_LANGUAGES}

    from .routes.elections import bp as elections_bp
    from .routes.main import bp as main_bp
    from .routes.main import root_bp
    from .routes.quiz import bp as quiz_bp
    from .routes.resources import bp as resources_bp

    # Content pages are language-prefixed; root_bp (/, robots.txt, sitemap.xml) is
    # not. The any(...) converter restricts the prefix to supported languages so
    # unknown single-segment URLs 404 instead of redirecting.
    app.register_blueprint(root_bp)
    lang_prefix = "/<any({}):lang_code>".format(",".join(SUPPORTED_LANGUAGES))
    for bp in (main_bp, elections_bp, quiz_bp, resources_bp):
        app.register_blueprint(bp, url_prefix=lang_prefix)

    _register_i18n(app)
    _register_error_handlers(app)
    _register_security_headers(app)

    return app


def _register_i18n(app: Flask) -> None:
    @app.url_value_preprocessor
    def pull_lang_code(endpoint, values):  # noqa: ANN001
        # The any(...) converter already guarantees a supported language.
        if values and "lang_code" in values:
            g.lang = values.pop("lang_code")

    @app.url_defaults
    def add_lang_code(endpoint, values):  # noqa: ANN001
        if "lang_code" in values or not endpoint:
            return
        if app.url_map.is_endpoint_expecting(endpoint, "lang_code"):
            values["lang_code"] = current_lang()

    @app.before_request
    def remember_lang():
        # Persist the active language so the bare "/" redirect honors it later.
        if getattr(g, "lang", None) in SUPPORTED_LANGUAGES:
            session["lang"] = g.lang

    def switch_lang_url(lang: str) -> str:
        """URL for the current page in another language."""
        endpoint = request.endpoint
        if endpoint and app.url_map.is_endpoint_expecting(endpoint, "lang_code"):
            args = dict(request.view_args or {})
            args.update(request.args.to_dict())
            args["lang_code"] = lang
            return url_for(endpoint, **args)
        return url_for("main.index", lang_code=lang)

    app.jinja_env.globals.update(
        t=translate_ui,
        plural=plural,
        current_lang=current_lang,
        switch_lang_url=switch_lang_url,
        supported_languages=SUPPORTED_LANGUAGES,
    )
    app.jinja_env.filters["localdate"] = format_date


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
        response.headers["Content-Language"] = current_lang()
        # HSTS only over HTTPS (production); avoid pinning local HTTP dev to TLS.
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
