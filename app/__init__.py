from flask import Flask, render_template, session

from .config import settings
from .database import SessionLocal, init_db
from .seed import seed_reference_data


def ru_num(value, digits=1):
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def ru_sci(value):
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.2e}".replace(".", ",")


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key
    app.jinja_env.filters["ru"] = ru_num
    app.jinja_env.filters["rusci"] = ru_sci

    init_db()
    seed_reference_data()

    from .routes import bp

    app.register_blueprint(bp)

    @app.context_processor
    def inject_user():
        return {
            "current_user": {
                "id": session.get("user_id"),
                "username": session.get("username"),
                "employee_name": session.get("employee_name"),
                "role": session.get("role"),
                "is_admin": session.get("role") == "admin",
            }
        }

    @app.teardown_appcontext
    def remove_session(exception=None):
        SessionLocal.remove()

    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            "error.html",
            title="Страница не найдена",
            heading="Страница не найдена",
            message="Такого адреса в приложении нет или запись была удалена.",
            status_code=404,
        ), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template(
            "error.html",
            title="Ошибка приложения",
            heading="Ошибка приложения",
            message="Страница не открылась из-за внутренней ошибки. Вернитесь назад или откройте историю расчетов.",
            status_code=500,
        ), 500

    return app
