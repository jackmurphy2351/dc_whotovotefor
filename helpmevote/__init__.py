import os

from flask import Flask

from .config import config
from .data_loader import load_all_content


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

    return app
