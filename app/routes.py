import csv
from dataclasses import asdict
from datetime import datetime
from functools import wraps

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, send_file, session as flask_session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError

from .archive import count_archive_rows, get_archive_material, load_archive_rows
from .config import settings
from .database import SessionLocal
from .engine import LensInput, RecommendationError, get_by_ids, recommend_sequence
from .models import AuditLog, Impregnation, Material, ProcessRun, User

bp = Blueprint("main", __name__)

BASE_TYPES = ["водная", "спиртовая", "полимерная", "фторсодержащая", "комбинированная"]
STAGE_GROUPS = ["упрочняющее", "фотохромное", "антибликовое", "антистатическое", "гидрофобное", "олеофобное", "антизапотевающее"]
APPLICATION_METHODS = ["распыление", "погружение", "центрифугирование"]
MATERIAL_GROUPS = ["стекло", "кварц", "полимер"]


def _session():
    return SessionLocal()


def _current_user(session):
    user_id = flask_session.get("user_id")
    if not user_id:
        return None
    return session.get(User, int(user_id))


def _log_action(session, action, entity, details=""):
    user = _current_user(session)
    session.add(AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else flask_session.get("username"),
        action=action,
        entity=entity,
        details=details,
    ))


def _result_is_renderable(result):
    return (
        isinstance(result, dict)
        and isinstance(result.get("summary"), dict)
        and isinstance(result.get("linza"), dict)
        and isinstance(result.get("material"), dict)
        and isinstance(result.get("steps"), list)
    )


def _result_has_model_report(result):
    if not _result_is_renderable(result):
        return False
    steps = result.get("steps") or []
    return bool(steps) and all(isinstance(step, dict) and isinstance(step.get("model_report"), dict) for step in steps)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not flask_session.get("user_id"):
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not flask_session.get("user_id"):
            return redirect(url_for("main.login", next=request.path))
        if flask_session.get("role") != "admin":
            return "Доступ разрешен только администратору", 403
        return view(*args, **kwargs)
    return wrapped


def _to_float(raw, default):
    if raw is None or str(raw).strip() == "":
        return float(default)
    return float(str(raw).strip().replace(",", "."))


def _pct_from_raw(raw, default_pct, min_pct=0.0, max_pct=100.0, legacy_fraction=False):
    value = _to_float(raw, default_pct)
    if legacy_fraction and value <= 1.0:
        value *= 100.0
    return max(min_pct, min(max_pct, value))


def _to_int(raw, default):
    if raw is None or str(raw).strip() == "":
        return int(default)
    return int(float(str(raw).strip().replace(",", ".")))


def _to_bool(raw):
    return str(raw or "").lower() in {"1", "true", "on", "да"}


def _parse_id_list(raw_values):
    result = []
    for value in raw_values:
        if not value:
            continue
        for part in str(value).split(","):
            part = part.strip()
            if part:
                result.append(int(part))
    return result


def _reference_data(session):
    materials = session.query(Material).order_by(Material.name).all()
    impregnations = session.query(Impregnation).order_by(Impregnation.stage_group, Impregnation.name).all()
    return materials, impregnations


def _resolve_material(session, token):
    token = str(token or "").strip()
    if not token:
        raise RecommendationError("Материал не выбран.")
    if token.startswith("archive:"):
        kod = token.split(":", 1)[1]
        material = get_archive_material(settings.archive_csv_path, kod)
        if material is None:
            raise RecommendationError("Материал из архива не найден.")
        return material
    if token.startswith("db:"):
        material_id = int(token.split(":", 1)[1])
        material = session.get(Material, material_id)
    else:
        material = session.query(Material).filter(Material.kod == token).one_or_none()
        if material is None and token.isdigit():
            material = session.get(Material, int(token))
    if material is None:
        raise RecommendationError("Материал не найден в справочнике БД.")
    return material


def _material_payload_from_form():
    kod = str(request.form.get("kod") or "").strip().upper()
    name = str(request.form.get("name") or "").strip()
    group = str(request.form.get("group") or "").strip()
    if not kod or not name:
        raise RecommendationError("Код и название материала обязательны.")
    if group not in MATERIAL_GROUPS:
        raise RecommendationError("Некорректная группа материала.")
    return {
        "kod": kod,
        "name": name,
        "group": group,
        "lambda_w_mk": _to_float(request.form.get("lambda_w_mk"), 1.0),
        "density_kg_m3": _to_float(request.form.get("density_kg_m3"), 2500),
        "heat_capacity_j_kgk": _to_float(request.form.get("heat_capacity_j_kgk"), 800),
        "expansion_1_k": _to_float(request.form.get("expansion_1_k"), 0.000008),
        "tg_c": _to_float(request.form.get("tg_c"), 0),
        "t_max_c": _to_float(request.form.get("t_max_c"), 90),
        "moisture_absorption_pct": 0.0,
        "heat_sensitivity": 0.0,
    }


def _impregnation_payload_from_form():
    kod = str(request.form.get("kod") or "").strip().upper()
    name = str(request.form.get("name") or "").strip()
    base_type = str(request.form.get("base_type") or "").strip()
    stage_group = str(request.form.get("stage_group") or "").strip()
    application_method = str(request.form.get("application_method") or "").strip()
    if not kod or not name:
        raise RecommendationError("Код и название пропитки обязательны.")
    if base_type not in BASE_TYPES:
        raise RecommendationError("Некорректный тип основы пропитки.")
    if stage_group not in STAGE_GROUPS:
        raise RecommendationError("Некорректный тип функционального покрытия.")
    if application_method not in APPLICATION_METHODS:
        raise RecommendationError("Некорректный метод нанесения.")
    return {
        "kod": kod,
        "name": name,
        "base_type": base_type,
        "composition": str(request.form.get("composition") or "").strip(),
        "purpose": str(request.form.get("purpose") or "").strip(),
        "stage_group": stage_group,
        "is_final_layer": _to_bool(request.form.get("is_final_layer")),
        "external_only": _to_bool(request.form.get("external_only")),
        "application_method": application_method,
        "viscosity_mpa_s": _to_float(request.form.get("viscosity_mpa_s"), 20),
        "surface_tension_mn_m": _to_float(request.form.get("surface_tension_mn_m"), 30),
        "evaporation_rate": 0.0,
        "thermal_stability_c": _to_float(request.form.get("thermal_stability_c"), 75),
        "target_layer_thickness_um": 0.0,
        "initial_solvent_pct": _to_float(request.form.get("initial_solvent_pct"), 35),
        "overheat_sensitivity": 0.0,
        "requires_uv": _to_bool(request.form.get("requires_uv")),
    }


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)
    session = _session()
    username = str(request.form.get("username") or "").strip()
    password = str(request.form.get("password") or "")
    user = session.query(User).filter(User.username == username, User.is_active == True).one_or_none()
    if user is None or not check_password_hash(user.password_hash, password):
        return render_template("login.html", error="Неверный логин или пароль."), 400
    flask_session.clear()
    flask_session["user_id"] = user.id
    flask_session["username"] = user.username
    flask_session["employee_name"] = user.employee_name
    flask_session["role"] = user.role
    _log_action(session, "login", "users", "Вход в систему")
    session.commit()
    return redirect(request.args.get("next") or url_for("main.index"))


@bp.get("/logout")
def logout():
    session = _session()
    if flask_session.get("user_id"):
        try:
            _log_action(session, "logout", "users", "Выход из системы")
            session.commit()
        except Exception:
            session.rollback()
    flask_session.clear()
    return redirect(url_for("main.login"), code=303)


@bp.get("/")
@login_required
def index():
    session = _session()
    materials, impregnations = _reference_data(session)
    archive_count = count_archive_rows(settings.archive_csv_path)
    return render_template("index.html", materials=materials, impregnations=impregnations, archive_count=archive_count)


@bp.post("/recommend")
@login_required
def recommend():
    session = _session()
    materials, impregnations = _reference_data(session)
    try:
        material = _resolve_material(session, request.form.get("material_key"))
        lens = LensInput(
            h_kraya_mm=_to_float(request.form.get("h_kraya_mm"), 2.0),
            d_mm=_to_float(request.form.get("d_mm"), 55.0),
            r1_mm=_to_float(request.form.get("r1_mm"), 120.0),
            r2_mm=_to_float(request.form.get("r2_mm"), -120.0),
        )
        archive_raw = request.form.get("archive_weight_pct")
        if archive_raw is None:
            archive_weight_pct = _pct_from_raw(request.form.get("archive_weight"), 50.0, legacy_fraction=True)
        else:
            archive_weight_pct = _pct_from_raw(archive_raw, 50.0)
        archive_weight = archive_weight_pct / 100.0
        temperature_threshold_pct = _pct_from_raw(request.form.get("temperature_threshold_pct"), 90.0, min_pct=50.0, legacy_fraction=True)
        selected_ids = _parse_id_list(request.form.getlist("selected_layers"))
        if len(selected_ids) > 5:
            raise RecommendationError("Можно выбрать не больше пяти пропиток для одного запуска.")
        selected_layers = get_by_ids(impregnations, selected_ids)
        archive_rows = load_archive_rows(settings.archive_csv_path)
        result = recommend_sequence(material, lens, selected_layers, archive_rows=archive_rows, archive_weight=archive_weight, temperature_threshold=temperature_threshold_pct / 100.0)

        run = ProcessRun(
            batch_code=datetime.now().strftime("%Y%m%d%H%M%S"),
            material_id=getattr(material, "id", None),
            user_id=flask_session.get("user_id"),
            lens_payload=asdict(lens),
            selected_layers=selected_ids,
            calculated_sequence=result["raschetnaya_posledovatelnost"],
            recommendation=result,
            quality_status=result["summary"]["status"],
            comment="Расчет выполнен с сопоставлением по архиву запусков.",
        )
        session.add(run)
        _log_action(session, "calculate", "process_runs", "Сформирован запуск " + run.batch_code)
        session.commit()
        return render_template("result.html", result=result, run=run)
    except (ValueError, RecommendationError) as exc:
        archive_count = count_archive_rows(settings.archive_csv_path)
        return render_template("index.html", materials=materials, impregnations=impregnations, archive_count=archive_count, error=str(exc)), 400


@bp.get("/history")
@login_required
def history():
    session = _session()
    runs = session.query(ProcessRun).order_by(ProcessRun.created_at.desc()).all()
    return render_template("history.html", runs=runs)


@bp.post("/history/clear")
@login_required
def history_clear():
    session = _session()
    count = session.query(ProcessRun).count()
    session.query(ProcessRun).delete(synchronize_session=False)
    _log_action(session, "delete", "process_runs", "Очищена история запусков: " + str(count))
    session.commit()
    return redirect(url_for("main.history"))


@bp.post("/history/<int:run_id>/delete")
@login_required
def history_delete(run_id):
    session = _session()
    run = session.get(ProcessRun, run_id)
    if run is not None:
        label = run.batch_code or str(run.id)
        _log_action(session, "delete", "process_runs", "Удален запуск " + label)
        session.delete(run)
        session.commit()
    return redirect(url_for("main.history"))


@bp.get("/history/<int:run_id>")
@login_required
def history_detail(run_id):
    session = _session()
    run = session.get(ProcessRun, run_id)
    if run is None:
        return redirect(url_for("main.history"))
    result = run.recommendation or {}
    if not _result_is_renderable(result):
        return render_template("run_unavailable.html", run=run)
    return render_template("result.html", result=result, run=run)


@bp.get("/history/<int:run_id>/models")
@login_required
def history_models(run_id):
    session = _session()
    run = session.get(ProcessRun, run_id)
    if run is None:
        return redirect(url_for("main.history"))
    result = run.recommendation or {}
    if not _result_has_model_report(result):
        return render_template("run_unavailable.html", run=run)
    return render_template("model_report.html", result=result, run=run)


@bp.get("/history/<int:run_id>/models/graph/<int:stage_number>/<graph_kind>/<graph_key>")
@login_required
def history_model_graph(run_id, stage_number, graph_kind, graph_key):
    session = _session()
    run = session.get(ProcessRun, run_id)
    if run is None:
        return redirect(url_for("main.history"))
    result = run.recommendation or {}
    step = next((item for item in result.get("steps", []) if item.get("nomer_etapa") == stage_number), None)
    if step is None:
        abort(404)
    report = step.get("model_report") or {}
    collections = {
        "calc": report.get("calculation_graphs", []),
        "pair": [graph for model in report.get("models", []) for graph in model.get("feature_graphs", [])],
    }
    graph = next((item for item in collections.get(graph_kind, []) if item.get("key") == graph_key), None)
    if graph is None:
        abort(404)
    return render_template("graph_view.html", run=run, step=step, graph=graph)


@bp.get("/reference")
@login_required
def reference():
    session = _session()
    materials, impregnations = _reference_data(session)
    return render_template("reference.html", materials=materials, impregnations=impregnations)


@bp.get("/account")
@login_required
def account_page():
    session = _session()
    user = _current_user(session)
    if user is None:
        flask_session.clear()
        return redirect(url_for("main.login"))
    return render_template("account.html", user=user, profile_error=None, password_error=None, message=None)


@bp.post("/account/profile")
@login_required
def account_profile_update():
    session = _session()
    user = _current_user(session)
    if user is None:
        flask_session.clear()
        return redirect(url_for("main.login"))
    username = str(request.form.get("username") or "").strip()
    employee_name = str(request.form.get("employee_name") or "").strip()
    password = str(request.form.get("password") or "")
    if not username or not employee_name:
        return render_template("account.html", user=user, profile_error="Логин и имя сотрудника обязательны.", password_error=None, message=None), 400
    if not check_password_hash(user.password_hash, password):
        return render_template("account.html", user=user, profile_error="Для изменения данных введите текущий пароль.", password_error=None, message=None), 400
    duplicate = session.query(User).filter(User.username == username, User.id != user.id).one_or_none()
    if duplicate is not None:
        return render_template("account.html", user=user, profile_error="Такой логин уже занят.", password_error=None, message=None), 400
    old_username = user.username
    user.username = username
    user.employee_name = employee_name
    flask_session["username"] = user.username
    flask_session["employee_name"] = user.employee_name
    _log_action(session, "update", "account", "Изменены данные аккаунта " + old_username)
    session.commit()
    return render_template("account.html", user=user, profile_error=None, password_error=None, message="Данные аккаунта обновлены.")


@bp.post("/account/password")
@login_required
def account_password_update():
    session = _session()
    user = _current_user(session)
    if user is None:
        flask_session.clear()
        return redirect(url_for("main.login"))
    old_password = str(request.form.get("old_password") or "")
    new_password = str(request.form.get("new_password") or "")
    confirm_password = str(request.form.get("confirm_password") or "")
    if not check_password_hash(user.password_hash, old_password):
        return render_template("account.html", user=user, profile_error=None, password_error="Старый пароль указан неверно.", message=None), 400
    if len(new_password) < 6:
        return render_template("account.html", user=user, profile_error=None, password_error="Новый пароль должен быть не короче 6 символов.", message=None), 400
    if new_password != confirm_password:
        return render_template("account.html", user=user, profile_error=None, password_error="Новый пароль и подтверждение не совпадают.", message=None), 400
    user.password_hash = generate_password_hash(new_password)
    _log_action(session, "update", "account", "Изменен пароль аккаунта " + user.username)
    session.commit()
    return render_template("account.html", user=user, profile_error=None, password_error=None, message="Пароль обновлен.")


@bp.get("/materials/new")
@admin_required
def material_new():
    return render_template(
        "material_form.html",
        item=None,
        action_url=url_for("main.material_create"),
        material_groups=MATERIAL_GROUPS,
        error=None,
    )


@bp.post("/materials")
@admin_required
def material_create():
    session = _session()
    try:
        payload = _material_payload_from_form()
        item = Material(**payload)
        session.add(item)
        _log_action(session, "create", "materials", "Добавлен материал " + item.kod)
        session.commit()
        return redirect(url_for("main.reference"))
    except (RecommendationError, ValueError, IntegrityError) as exc:
        session.rollback()
        return render_template(
            "material_form.html",
            item=request.form,
            action_url=url_for("main.material_create"),
            material_groups=MATERIAL_GROUPS,
            error="Не удалось сохранить материал. " + str(exc),
        ), 400


@bp.get("/materials/<int:item_id>/edit")
@admin_required
def material_edit(item_id):
    session = _session()
    item = session.get(Material, item_id)
    if item is None:
        return redirect(url_for("main.reference"))
    return render_template(
        "material_form.html",
        item=item,
        action_url=url_for("main.material_update", item_id=item.id),
        material_groups=MATERIAL_GROUPS,
        error=None,
    )


@bp.post("/materials/<int:item_id>")
@admin_required
def material_update(item_id):
    session = _session()
    item = session.get(Material, item_id)
    if item is None:
        return redirect(url_for("main.reference"))
    try:
        payload = _material_payload_from_form()
        for key, value in payload.items():
            setattr(item, key, value)
        _log_action(session, "update", "materials", "Изменен материал " + item.kod)
        session.commit()
        return redirect(url_for("main.reference"))
    except (RecommendationError, ValueError, IntegrityError) as exc:
        session.rollback()
        return render_template(
            "material_form.html",
            item=item,
            action_url=url_for("main.material_update", item_id=item.id),
            material_groups=MATERIAL_GROUPS,
            error="Не удалось сохранить материал. " + str(exc),
        ), 400


@bp.post("/materials/<int:item_id>/delete")
@admin_required
def material_delete(item_id):
    session = _session()
    item = session.get(Material, item_id)
    if item is not None:
        try:
            _log_action(session, "delete", "materials", "Удален материал " + item.kod)
            session.delete(item)
            session.commit()
        except IntegrityError:
            session.rollback()
    return redirect(url_for("main.reference"))


@bp.get("/impregnations/new")
@admin_required
def impregnation_new():
    return render_template(
        "impregnation_form.html",
        item=None,
        action_url=url_for("main.impregnation_create"),
        base_types=BASE_TYPES,
        stage_groups=STAGE_GROUPS,
        application_methods=APPLICATION_METHODS,
        error=None,
    )


@bp.post("/impregnations")
@admin_required
def impregnation_create():
    session = _session()
    try:
        payload = _impregnation_payload_from_form()
        item = Impregnation(**payload)
        session.add(item)
        _log_action(session, "create", "impregnations", "Добавлен состав " + item.kod)
        session.commit()
        return redirect(url_for("main.reference"))
    except (RecommendationError, ValueError, IntegrityError) as exc:
        session.rollback()
        return render_template(
            "impregnation_form.html",
            item=request.form,
            action_url=url_for("main.impregnation_create"),
            base_types=BASE_TYPES,
            stage_groups=STAGE_GROUPS,
            application_methods=APPLICATION_METHODS,
            error="Не удалось сохранить запись. " + str(exc),
        ), 400


@bp.get("/impregnations/<int:item_id>/edit")
@admin_required
def impregnation_edit(item_id):
    session = _session()
    item = session.get(Impregnation, item_id)
    if item is None:
        return redirect(url_for("main.reference"))
    return render_template(
        "impregnation_form.html",
        item=item,
        action_url=url_for("main.impregnation_update", item_id=item.id),
        base_types=BASE_TYPES,
        stage_groups=STAGE_GROUPS,
        application_methods=APPLICATION_METHODS,
        error=None,
    )


@bp.post("/impregnations/<int:item_id>")
@admin_required
def impregnation_update(item_id):
    session = _session()
    item = session.get(Impregnation, item_id)
    if item is None:
        return redirect(url_for("main.reference"))
    try:
        payload = _impregnation_payload_from_form()
        for key, value in payload.items():
            setattr(item, key, value)
        _log_action(session, "update", "impregnations", "Изменен состав " + item.kod)
        session.commit()
        return redirect(url_for("main.reference"))
    except (RecommendationError, ValueError, IntegrityError) as exc:
        session.rollback()
        return render_template(
            "impregnation_form.html",
            item=item,
            action_url=url_for("main.impregnation_update", item_id=item.id),
            base_types=BASE_TYPES,
            stage_groups=STAGE_GROUPS,
            application_methods=APPLICATION_METHODS,
            error="Не удалось сохранить запись. " + str(exc),
        ), 400


@bp.post("/impregnations/<int:item_id>/delete")
@admin_required
def impregnation_delete(item_id):
    session = _session()
    item = session.get(Impregnation, item_id)
    if item is not None:
        _log_action(session, "delete", "impregnations", "Удален состав " + item.kod)
        session.delete(item)
        session.commit()
    return redirect(url_for("main.reference"))


@bp.get("/users")
@admin_required
def users_page():
    session = _session()
    users = session.query(User).order_by(User.created_at.desc()).all()
    return render_template("users.html", users=users)


@bp.get("/users/new")
@admin_required
def user_new():
    return render_template("user_form.html", item=None, error=None)


@bp.post("/users")
@admin_required
def user_create():
    session = _session()
    username = str(request.form.get("username") or "").strip()
    employee_name = str(request.form.get("employee_name") or "").strip()
    password = str(request.form.get("password") or "")
    role = str(request.form.get("role") or "technologist")
    if not username or not employee_name or not password:
        return render_template("user_form.html", item=request.form, error="Логин, пароль и имя сотрудника обязательны."), 400
    if role not in {"admin", "technologist"}:
        return render_template("user_form.html", item=request.form, error="Некорректный тип аккаунта."), 400
    try:
        user = User(username=username, employee_name=employee_name, role=role, password_hash=generate_password_hash(password), is_active=True)
        session.add(user)
        _log_action(session, "create", "users", "Добавлен пользователь " + username)
        session.commit()
        return redirect(url_for("main.users_page"))
    except IntegrityError as exc:
        session.rollback()
        return render_template("user_form.html", item=request.form, error="Не удалось создать пользователя. " + str(exc)), 400


@bp.post("/users/<int:user_id>/delete")
@admin_required
def user_delete(user_id):
    session = _session()
    user = session.get(User, user_id)
    if user is not None and user.id != flask_session.get("user_id"):
        user.is_active = False
        _log_action(session, "deactivate", "users", "Отключен пользователь " + user.username)
        session.commit()
    return redirect(url_for("main.users_page"))


@bp.get("/audit")
@admin_required
def audit_page():
    session = _session()
    logs = session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template("audit.html", logs=logs)


@bp.get("/api/reference")
@login_required
def api_reference():
    session = _session()
    materials, impregnations = _reference_data(session)
    return jsonify({
        "materials": [m.as_dict() for m in materials],
        "impregnations": [i.as_dict() for i in impregnations],
    })


@bp.post("/api/recommend")
@login_required
def api_recommend():
    session = _session()
    payload = request.get_json(force=True)
    try:
        material = _resolve_material(session, payload.get("material_key") or payload.get("material_id"))
        impregnations = session.query(Impregnation).all()
        lens = LensInput(**payload["linza"])
        selected_ids = [int(x) for x in payload.get("selected_layers", [])]
        if len(selected_ids) > 5:
            raise RecommendationError("Можно выбрать не больше пяти пропиток для одного запуска.")
        selected_layers = get_by_ids(impregnations, selected_ids)
        archive_rows = load_archive_rows(settings.archive_csv_path)
        if "archive_weight_pct" in payload:
            archive_weight_pct = _pct_from_raw(payload.get("archive_weight_pct"), 50.0)
        else:
            archive_weight_pct = _pct_from_raw(payload.get("archive_weight"), 50.0, legacy_fraction=True)
        archive_weight = archive_weight_pct / 100.0
        raw_threshold = payload.get("temperature_threshold_pct", payload.get("temperature_threshold", 90.0))
        temperature_threshold_pct = _pct_from_raw(raw_threshold, 90.0, min_pct=50.0, legacy_fraction=True)
        result = recommend_sequence(material, lens, selected_layers, archive_rows=archive_rows, archive_weight=archive_weight, temperature_threshold=temperature_threshold_pct / 100.0)
        _log_action(session, "calculate", "api", "Сформирован запуск через API")
        session.commit()
    except (TypeError, ValueError, RecommendationError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@bp.get("/dataset")
@login_required
def dataset_page():
    preview = []
    csv_path = settings.archive_csv_path
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for idx, row in enumerate(reader):
                preview.append(row)
                if idx >= 4:
                    break
    return render_template(
        "dataset.html",
        preview=preview,
        csv_exists=csv_path.exists(),
        csv_path=csv_path.name,
        row_count=count_archive_rows(csv_path),
    )


@bp.post("/dataset/upload")
@admin_required
def dataset_upload():
    file = request.files.get("csv_file")
    if file is None or file.filename == "":
        return render_template(
            "dataset.html",
            preview=[],
            csv_exists=settings.archive_csv_path.exists(),
            csv_path=settings.archive_csv_path.name,
            row_count=count_archive_rows(settings.archive_csv_path),
            error="CSV-файл не выбран.",
        ), 400
    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".csv"):
        return render_template(
            "dataset.html",
            preview=[],
            csv_exists=settings.archive_csv_path.exists(),
            csv_path=settings.archive_csv_path.name,
            row_count=count_archive_rows(settings.archive_csv_path),
            error="Можно загрузить только CSV-файл.",
        ), 400
    file.save(settings.archive_csv_path)
    try:
        load_archive_rows(settings.archive_csv_path)
    except Exception as exc:
        return render_template(
            "dataset.html",
            preview=[],
            csv_exists=settings.archive_csv_path.exists(),
            csv_path=settings.archive_csv_path.name,
            row_count=count_archive_rows(settings.archive_csv_path),
            error="Файл сохранен, но не прошел проверку структуры: " + str(exc),
        ), 400
    session = _session()
    _log_action(session, "upload", "archive_csv", "Загружен архив запусков " + filename)
    session.commit()
    return redirect(url_for("main.dataset_page"))



ARCHIVE_HEADERS = [
    "kod_zapuska", "godnaya_partiya", "kol_etapov", "material_kod", "gruppa_materiala_kod", "lambda", "rho", "c", "alpha", "Tg", "Tmax", "h kraya mm", "d mm", "R1 mm", "R2 mm",
]
for _n in range(1, 6):
    ARCHIVE_HEADERS.extend([
        f"e{_n}_pokrytie_kod", f"e{_n}_tip_pokrytiya_kod", f"e{_n}_tip_propitki_kod", f"e{_n}_sostav_kod", f"e{_n}_metod_naneseniya_kod", f"e{_n}_sreda_kod",
        f"e{_n}_eta", f"e{_n}_sigma", f"e{_n}_W0", f"e{_n}_t суш", f"e{_n}_tau суш", f"e{_n}_p суш Па", f"e{_n}_v суш", f"e{_n}_fi суш", f"e{_n}_W ост", f"e{_n}_delta T", f"e{_n}_delta L", f"e{_n}_defekt_kod",
    ])

TIP_PROPITKI_TO_KOD = {"водная": 1, "спиртовая": 2, "полимерная": 3, "фторсодержащая": 4, "комбинированная": 5}
TIP_POKRYTIYA_TO_KOD = {"упрочняющее": 1, "антибликовое": 2, "антистатическое": 3, "гидрофобное": 4, "олеофобное": 5, "антизапотевающее": 6, "фотохромное": 7}
GRUPPA_MATERIALA_TO_KOD = {"стекло": 1, "кварц": 2, "полимер": 3}
SREDA_TO_KOD = {"сушильный шкаф": 1, "вакуумная камера": 2, "ИК-модуль": 3}
METOD_NANESENIYA_TO_KOD = {"распыление": 1, "погружение": 2, "центрифугирование": 3}


def _csv_ru(value, digits=None):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if digits is None:
        text = str(value)
    else:
        text = f"{float(value):.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _result_to_archive_row(run):
    result = run.recommendation or {}
    material = result.get("material", {})
    lens = result.get("linza", {})
    row = {header: "" for header in ARCHIVE_HEADERS}
    row.update({
        "kod_zapuska": run.batch_code or str(run.id),
        "godnaya_partiya": "неизвестно",
        "kol_etapov": result.get("summary", {}).get("kolichestvo_etapov", len(result.get("steps", []))),
        "material_kod": material.get("kod", "неизвестно"),
        "gruppa_materiala_kod": GRUPPA_MATERIALA_TO_KOD.get(material.get("group", ""), "неизвестно"),
        "lambda": _csv_ru(material.get("lambda_w_mk"), 4),
        "rho": _csv_ru(material.get("density_kg_m3"), 1),
        "c": _csv_ru(material.get("heat_capacity_j_kgk"), 1),
        "alpha": _csv_ru(material.get("expansion_1_k"), 8),
        "Tg": _csv_ru(material.get("tg_c"), 1),
        "Tmax": _csv_ru(material.get("t_max_c"), 1),
        "h kraya mm": _csv_ru(lens.get("h_kraya_mm"), 3),
        "d mm": _csv_ru(lens.get("d_mm"), 2),
        "R1 mm": _csv_ru(lens.get("r1_mm"), 2),
        "R2 mm": _csv_ru(lens.get("r2_mm"), 2),
    })
    for step in result.get("steps", [])[:5]:
        n = step.get("nomer_etapa")
        pref = f"e{n}_"
        row[pref + "pokrytie_kod"] = step.get("pokrytie_kod", "неизвестно")
        row[pref + "tip_pokrytiya_kod"] = TIP_POKRYTIYA_TO_KOD.get(step.get("tip_pokrytiya", ""), "неизвестно")
        row[pref + "tip_propitki_kod"] = TIP_PROPITKI_TO_KOD.get(step.get("tip_propitki", ""), "неизвестно")
        row[pref + "sostav_kod"] = step.get("pokrytie_kod", "неизвестно")
        row[pref + "metod_naneseniya_kod"] = METOD_NANESENIYA_TO_KOD.get(step.get("metod_naneseniya", ""), "неизвестно")
        row[pref + "sreda_kod"] = SREDA_TO_KOD.get(step.get("sreda_sushki", ""), "неизвестно")
        row[pref + "eta"] = _csv_ru(step.get("eta_mpa_s"), 2)
        row[pref + "sigma"] = _csv_ru(step.get("sigma_mn_m"), 2)
        row[pref + "W0"] = _csv_ru(step.get("w0_pct"), 2)
        row[pref + "t суш"] = _csv_ru(step.get("temperatura_sush_c"), 1)
        row[pref + "tau суш"] = _csv_ru(step.get("polnoe_vremya_etapa_min") or step.get("vremya_vyderzhki_min"), 1)
        row[pref + "p суш Па"] = _csv_ru(step.get("davlenie_sush_pa"), 0)
        row[pref + "v суш"] = _csv_ru(step.get("skorost_vozduha_ms"), 2)
        row[pref + "fi суш"] = _csv_ru(step.get("vlazhnost_sredy_pct"), 1)
        row[pref + "W ост"] = _csv_ru(step.get("w_ost_pct"), 2)
        row[pref + "delta T"] = _csv_ru(step.get("delta_t_c"), 2)
        row[pref + "delta L"] = _csv_ru(step.get("delta_l_mkm"), 3)
        row[pref + "defekt_kod"] = "неизвестно"
    return row


@bp.get("/history/<int:run_id>/dataset.csv")
@login_required
def run_dataset_download(run_id):
    session = _session()
    run = session.get(ProcessRun, run_id)
    if run is None:
        return "Расчет не найден", 404
    _log_action(session, "download", "process_run_csv", "Скачан запуск " + (run.batch_code or str(run.id)))
    session.commit()
    row = _result_to_archive_row(run)
    lines = [";".join(ARCHIVE_HEADERS), ";".join(str(row.get(header, "")) for header in ARCHIVE_HEADERS)]
    body = "\ufeff" + "\n".join(lines) + "\n"
    filename = (run.batch_code or str(run_id)) + ".csv"
    return Response(
        body,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=" + filename},
    )

@bp.get("/dataset/download")
@admin_required
def dataset_download():
    csv_path = settings.archive_csv_path
    if not csv_path.exists():
        return "CSV-файл не найден", 404
    session = _session()
    _log_action(session, "download", "archive_csv", "Скачан архив запусков")
    session.commit()
    return send_file(csv_path, as_attachment=True, download_name=csv_path.name)
