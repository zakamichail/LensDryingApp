import math
from dataclasses import asdict, dataclass, field
from html import escape

from .archive import SREDA_NAME, TIP_POKRYTIYA_KOD, TIP_PROPITKI_KOD


@dataclass
class LensInput:
    h_kraya_mm: float
    d_mm: float
    r1_mm: float
    r2_mm: float
    temperatura_bazy_c: float = 22.0
    h_centr_mm: float = field(init=False)

    def __post_init__(self):
        self.h_kraya_mm = float(self.h_kraya_mm)
        self.d_mm = float(self.d_mm)
        self.r1_mm = float(self.r1_mm)
        self.r2_mm = float(self.r2_mm)
        self.temperatura_bazy_c = float(self.temperatura_bazy_c)
        self.h_centr_mm = round(calc_center_thickness(self.h_kraya_mm, self.d_mm, self.r1_mm, self.r2_mm), 3)

    @property
    def h_mm(self):
        return self.h_centr_mm


def calc_center_thickness(h_kraya_mm, d_mm, r1_mm, r2_mm):
    radius_aperture = d_mm / 2.0
    if h_kraya_mm <= 0 or d_mm <= 0:
        raise RecommendationError("Толщина по краю и диаметр линзы должны быть положительными.")
    if abs(r1_mm) <= radius_aperture or abs(r2_mm) <= radius_aperture:
        raise RecommendationError("Модуль каждого радиуса должен быть больше половины диаметра линзы.")

    def sag(r):
        # s(R) = R - sign(R) * sqrt(R^2 - (d/2)^2): стрелка сферической поверхности.
        sign = 1.0 if r >= 0 else -1.0
        return r - sign * math.sqrt(r * r - radius_aperture * radius_aperture)

    # h_c = h_edge + s(R1) - s(R2): центральная толщина линзы.
    center = h_kraya_mm + sag(r1_mm) - sag(r2_mm)
    if center <= 0:
        raise RecommendationError("Расчет не производится: центральная толщина получилась отрицательной или нулевой. Проверьте знаки и значения радиусов.")
    if center <= 0.4:
        raise RecommendationError("Расчет не производится: центральная толщина ниже технологического допуска. Проверьте знаки и значения радиусов.")
    if center > 30.0:
        raise RecommendationError("Расчетная центральная толщина слишком большая. Проверьте радиусы и диаметр.")
    return center


MODEL_BASE_TYPES = ["водная", "спиртовая", "полимерная", "фторсодержащая", "комбинированная"]
MODEL_STAGE_GROUPS = ["упрочняющее", "антибликовое", "антистатическое", "гидрофобное", "олеофобное", "антизапотевающее", "фотохромное"]
SREDA_METHOD_NAME = {1: "конвективная сушка", 2: "вакуумная сушка", 3: "инфракрасная сушка"}
FEATURES = [
    {"symbol": "λ", "name": "теплопроводность материала", "unit": "Вт/(м·К)"},
    {"symbol": "ρ", "name": "плотность материала", "unit": "кг/м3"},
    {"symbol": "c", "name": "удельная теплоемкость материала", "unit": "Дж/(кг·К)"},
    {"symbol": "α", "name": "коэффициент линейного теплового расширения", "unit": "1/К"},
    {"symbol": "Tg", "name": "температура стеклования", "unit": "°C"},
    {"symbol": "Tmax", "name": "максимально допустимая температура материала", "unit": "°C"},
    {"symbol": "a_t", "name": "температуропроводность λ/(ρc)", "unit": "м2/с"},
    {"symbol": "h_edge", "name": "толщина линзы по краю", "unit": "мм"},
    {"symbol": "h_c", "name": "расчетная центральная толщина", "unit": "мм"},
    {"symbol": "d", "name": "диаметр линзы", "unit": "мм"},
    {"symbol": "|R1|", "name": "модуль радиуса первой поверхности", "unit": "мм"},
    {"symbol": "|R2|", "name": "модуль радиуса второй поверхности", "unit": "мм"},
    {"symbol": "|R1-R2|", "name": "модуль разности радиусов", "unit": "мм"},
    {"symbol": "n", "name": "номер этапа в последовательности", "unit": ""},
    {"symbol": "N", "name": "общее количество этапов", "unit": ""},
    {"symbol": "η", "name": "динамическая вязкость пропитки", "unit": "мПа·с"},
    {"symbol": "σ", "name": "поверхностное натяжение пропитки", "unit": "мН/м"},
    {"symbol": "W0", "name": "начальное содержание летучих компонентов", "unit": "%"},
] + [
    {"symbol": "I_base(" + value + ")", "name": "признак основы пропитки: " + value, "unit": "0/1"}
    for value in MODEL_BASE_TYPES[:-1]
] + [
    {"symbol": "I_coat(" + value + ")", "name": "признак функционального типа покрытия: " + value, "unit": "0/1"}
    for value in MODEL_STAGE_GROUPS[:-1]
]

EXTERNAL_ONLY_GROUPS = {"гидрофобное", "антизапотевающее", "олеофобное", "антистатическое"}

CONFLICT_GROUP_MESSAGES = {
    "anti_fog_wetting": "Пропитки несовместимы: антизапотевающее покрытие и гидрофобное или олеофобное покрытие выполняют противоположные по физике задачи. В зависимости от нанесения одно покрытие перекрывает свойства другого.",
    "hydro_oleo_finish": "Гидрофобное и олеофобное покрытия обычно не наносят отдельными верхними слоями. Рациональнее выбрать один состав с нужным набором свойств.",
    "antistatic_covered": "Если поверх антистатического покрытия наносится другое верхнее покрытие, способность поверхности рассеивать статический заряд снижается.",
}

LAYER_ORDER = [
    "фотохромное",
    "упрочняющее",
    "антистатическое",
    "антибликовое",
    "гидрофобное",
    "олеофобное",
    "антизапотевающее",
]


def is_external_only(layer):
    return bool(getattr(layer, "external_only", False)) or getattr(layer, "stage_group", "") in EXTERNAL_ONLY_GROUPS


class RecommendationError(ValueError):
    pass


def fmt_ru(value, digits=1):
    if value is None:
        return ""
    text = f"{float(value):.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def clamp(value, low, high):
    if low > high:
        raise RecommendationError("Некорректные расчетные границы")
    return max(low, min(high, value))


def _one_hot(value, values):
    return [1.0 if value == item else 0.0 for item in values[:-1]]


def thermal_diffusivity_m2_s(material):
    # a_t = lambda / (rho * c), м2/с: температуропроводность материала.
    denominator = material.density_kg_m3 * material.heat_capacity_j_kgk
    if material.lambda_w_mk <= 0 or denominator <= 0:
        raise RecommendationError("Некорректные теплофизические свойства материала.")
    return material.lambda_w_mk / denominator


def thermal_diffusion_time_min(material, lens):
    # tau_th = L^2 / a_t, мин: характерное время выравнивания температуры по толщине.
    if lens.h_centr_mm <= 0:
        raise RecommendationError("Некорректная центральная толщина линзы.")
    length_m = lens.h_centr_mm / 1000.0
    diffusivity = thermal_diffusivity_m2_s(material)
    if diffusivity <= 0:
        raise RecommendationError("Некорректные теплофизические свойства материала.")
    return (length_m * length_m / diffusivity) / 60.0


def _feature_vector(material, lens, coating, stage_number, total_stages):
    alpha = thermal_diffusivity_m2_s(material)
    base_type = getattr(coating, "base_type", "")
    stage_group = getattr(coating, "stage_group", "")
    return [
        material.lambda_w_mk,
        material.density_kg_m3,
        material.heat_capacity_j_kgk,
        material.expansion_1_k,
        material.tg_c or 0.0,
        material.t_max_c,
        alpha,
        lens.h_kraya_mm,
        lens.h_centr_mm,
        lens.d_mm,
        abs(lens.r1_mm),
        abs(lens.r2_mm),
        abs(lens.r1_mm - lens.r2_mm),
        float(stage_number),
        float(total_stages),
        getattr(coating, "viscosity_mpa_s", 0.0),
        getattr(coating, "surface_tension_mn_m", 0.0),
        getattr(coating, "initial_solvent_pct", 0.0),
    ] + _one_hot(base_type, MODEL_BASE_TYPES) + _one_hot(stage_group, MODEL_STAGE_GROUPS)


def _row_stage_feature_vector(row, n):
    pref = f"e{n}_"
    diffusivity = row.get("lambda", 0.0) / max(row.get("plotnost", 0.0) * row.get("teploemkost", 0.0), 1e-12)
    base_code = row.get(pref + "tip_propitki_kod", 0)
    stage_code = row.get(pref + "tip_pokrytiya_kod", 0)
    base_type = {value: key for key, value in TIP_PROPITKI_KOD.items()}.get(base_code, "")
    stage_group = {value: key for key, value in TIP_POKRYTIYA_KOD.items()}.get(stage_code, "")
    return [
        row.get("lambda", 0.0),
        row.get("plotnost", 0.0),
        row.get("teploemkost", 0.0),
        row.get("alfa", 0.0),
        row.get("Tg", 0.0),
        row.get("Tmax", 0.0),
        diffusivity,
        row.get("h_kraya_mm", 0.0),
        row.get("h_centr_mm", 0.0),
        row.get("d_mm", 0.0),
        abs(row.get("r1_mm", 0.0)),
        abs(row.get("r2_mm", 0.0)),
        abs(row.get("r1_mm", 0.0) - row.get("r2_mm", 0.0)),
        float(n),
        float(row.get("kol_etapov", n)),
        row.get(pref + "eta", 0.0),
        row.get(pref + "sigma", 0.0),
        row.get(pref + "W0", 0.0),
    ] + _one_hot(base_type, MODEL_BASE_TYPES) + _one_hot(stage_group, MODEL_STAGE_GROUPS)


def _solve_linear_system(matrix, vector):
    n = len(vector)
    aug = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col]
        aug[col] = [value / div for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor:
                aug[row] = [aug[row][i] - factor * aug[col][i] for i in range(n + 1)]
    return [aug[row][-1] for row in range(n)]


def _fit_ols(samples, transform=None):
    if not samples:
        return None
    xs = [sample[0] for sample in samples]
    ys = [transform(sample[1]) if transform else sample[1] for sample in samples]
    width = len(xs[0])
    active_indices = []
    means = []
    scales = []
    for i in range(width):
        mean = sum(row[i] for row in xs) / len(xs)
        variance = sum((row[i] - mean) ** 2 for row in xs) / len(xs)
        if variance > 1e-18:
            active_indices.append(i)
            means.append(mean)
            scales.append(math.sqrt(variance))
    if len(samples) <= len(active_indices):
        return None
    zxs = [
        [1.0] + [(row[index] - means[position]) / scales[position] for position, index in enumerate(active_indices)]
        for row in xs
    ]
    p = len(active_indices) + 1
    xtx = [[0.0 for _ in range(p)] for _ in range(p)]
    xty = [0.0 for _ in range(p)]
    for row, y in zip(zxs, ys):
        for i in range(p):
            xty[i] += row[i] * y
            for j in range(p):
                xtx[i][j] += row[i] * row[j]
    # beta = (Z^T Z)^(-1) Z^T y: коэффициенты МНК для стандартизованных признаков.
    coef = _solve_linear_system(xtx, xty)
    if coef is None:
        ridge = max(sum(xtx[i][i] for i in range(p)) / max(p, 1), 1.0) * 1e-8
        for i in range(1, p):
            xtx[i][i] += ridge
        coef = _solve_linear_system(xtx, xty)
    if coef is None:
        return None
    y_mean = sum(ys) / len(ys)
    ss_total = sum((y - y_mean) ** 2 for y in ys)
    ss_res = 0.0
    for row, y in zip(zxs, ys):
        pred = sum(coef[i] * row[i] for i in range(p))
        ss_res += (y - pred) ** 2
    r2 = 1.0 - ss_res / ss_total if ss_total > 0 else 0.0
    return {
        "coef": coef,
        "indices": active_indices,
        "means": means,
        "scales": scales,
        "r2": max(0.0, min(1.0, r2)),
        "n": len(samples),
        "transform": transform,
    }


def _predict_ols(model, features, inverse=None):
    if model is None:
        return None
    indices = model.get("indices", list(range(len(model["means"]))))
    row = [1.0] + [
        (features[index] - model["means"][position]) / model["scales"][position]
        for position, index in enumerate(indices)
    ]
    value = sum(model["coef"][i] * row[i] for i in range(len(row)))
    return inverse(value) if inverse else value


def _fit_line(points):
    clean = [(float(x), float(y)) for x, y in points if x is not None and y is not None and math.isfinite(x) and math.isfinite(y)]
    if len(clean) < 2:
        return None
    x_mean = sum(x for x, _y in clean) / len(clean)
    y_mean = sum(y for _x, y in clean) / len(clean)
    ss_x = sum((x - x_mean) ** 2 for x, _y in clean)
    if ss_x <= 1e-12:
        return None
    k = sum((x - x_mean) * (y - y_mean) for x, y in clean) / ss_x
    b = y_mean - k * x_mean
    ss_total = sum((y - y_mean) ** 2 for _x, y in clean)
    ss_res = sum((y - (k * x + b)) ** 2 for x, y in clean)
    r2 = 1.0 - ss_res / ss_total if ss_total > 0 else 0.0
    return {"k": k, "b": b, "r2": max(0.0, min(1.0, r2)), "n": len(clean)}


def _pearson_r(points):
    clean = [(float(x), float(y)) for x, y in points if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(clean) < 2:
        return 0.0
    x_mean = sum(x for x, _y in clean) / len(clean)
    y_mean = sum(y for _x, y in clean) / len(clean)
    sxx = sum((x - x_mean) ** 2 for x, _y in clean)
    syy = sum((y - y_mean) ** 2 for _x, y in clean)
    if sxx <= 1e-12 or syy <= 1e-12:
        return 0.0
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in clean)
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def _predict_line(model, x):
    if not isinstance(model, dict):
        return None
    return model["k"] * float(x) + model["b"]


def _sigmoid(value):
    value = max(-60.0, min(60.0, float(value)))
    return 1.0 / (1.0 + math.exp(-value))


def _fit_logistic(points):
    clean = [
        (float(x), 1.0 if float(y) >= 0.5 else 0.0)
        for x, y in points
        if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if len(clean) < 4 or len({y for _x, y in clean}) < 2:
        return None
    x_mean = sum(x for x, _y in clean) / len(clean)
    variance = sum((x - x_mean) ** 2 for x, _y in clean) / len(clean)
    if variance <= 1e-12:
        return None
    x_scale = math.sqrt(variance)
    z_values = [(x - x_mean) / x_scale for x, _y in clean]
    y_values = [y for _x, y in clean]
    event_rate = max(1e-4, min(1.0 - 1e-4, sum(y_values) / len(y_values)))
    beta0 = math.log(event_rate / (1.0 - event_rate))
    beta1 = 0.0
    ridge = 1e-3

    for _iteration in range(40):
        g0 = 0.0
        g1 = 0.0
        a00 = 0.0
        a01 = 0.0
        a11 = ridge
        for z, y in zip(z_values, y_values):
            p = _sigmoid(beta0 + beta1 * z)
            w = max(p * (1.0 - p), 1e-6)
            error = y - p
            g0 += error
            g1 += error * z
            a00 += w
            a01 += w * z
            a11 += w * z * z
        g1 -= ridge * beta1
        det = a00 * a11 - a01 * a01
        if abs(det) <= 1e-12:
            break
        delta0 = (a11 * g0 - a01 * g1) / det
        delta1 = (-a01 * g0 + a00 * g1) / det
        delta0 = max(-2.0, min(2.0, delta0))
        delta1 = max(-2.0, min(2.0, delta1))
        beta0 += delta0
        beta1 += delta1
        if abs(delta0) + abs(delta1) < 1e-7:
            break

    k = beta1 / x_scale
    b = beta0 - beta1 * x_mean / x_scale
    loglik = 0.0
    null_loglik = 0.0
    for x, y in clean:
        p = max(1e-6, min(1.0 - 1e-6, _sigmoid(k * x + b)))
        loglik += y * math.log(p) + (1.0 - y) * math.log(1.0 - p)
        null_loglik += y * math.log(event_rate) + (1.0 - y) * math.log(1.0 - event_rate)
    r2 = 1.0 - loglik / null_loglik if null_loglik < 0 else 0.0
    return {"k": k, "b": b, "r2": max(0.0, min(1.0, r2)), "n": len(clean)}


def _model_items(models):
    for key, model in models.items():
        if key != "method":
            yield key, model


def _standard_distance(model, features):
    if not isinstance(model, dict) or "indices" not in model or not model["indices"]:
        return None
    z2 = 0.0
    for position, index in enumerate(model["indices"]):
        z = (features[index] - model["means"][position]) / model["scales"][position]
        z2 += z * z
    return math.sqrt(z2 / len(model["indices"]))


def _model_diagnostics(models, features):
    r2_values = []
    distances = []
    for _key, model in _model_items(models):
        if isinstance(model, dict) and "r2" in model:
            r2_values.append(model["r2"])
            distance = _standard_distance(model, features)
            if distance is not None:
                distances.append(distance)
    return {
        "model_quality": round(sum(r2_values) / len(r2_values), 3) if r2_values else 0.0,
        "extrapolation_index": round(sum(distances) / len(distances), 3) if distances else 0.0,
    }


def _sample_even(items, limit=1200):
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def _format_graph_number(value, step=None):
    if value is None:
        return ""
    value = float(value)
    abs_value = abs(value)
    if abs_value and (abs_value < 0.001 or abs_value >= 10_000_000):
        return f"{value:.2e}".replace(".", ",")
    if step is None:
        step = abs_value
    abs_step = abs(float(step))
    if abs_step >= 10:
        digits = 0
    elif abs_step >= 1:
        digits = 1
    elif abs_step >= 0.1:
        digits = 2
    elif abs_step >= 0.01:
        digits = 3
    else:
        digits = 4
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _nice_step(span, target_count=5):
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(target_count - 1, 1)
    power = 10 ** math.floor(math.log10(raw))
    fraction = raw / power
    if fraction <= 1:
        nice = 1
    elif fraction <= 2:
        nice = 2
    elif fraction <= 5:
        nice = 5
    else:
        nice = 10
    return nice * power


def _axis_ticks(min_value, max_value, target_count=5):
    step = _nice_step(max_value - min_value, target_count)
    start = math.ceil(min_value / step) * step
    ticks = []
    value = start
    guard = 0
    while value <= max_value + step * 0.5 and guard < 10:
        ticks.append(value)
        value += step
        guard += 1
    if not ticks:
        ticks = [min_value, max_value]
    return ticks, step


def _svg_scatter(
    title,
    x_label,
    y_label,
    points,
    selected=None,
    line_points=None,
    secondary_points=None,
    secondary_line_points=None,
    point_label="архивные наблюдения",
    line_label="расчетная зависимость",
    secondary_point_label="точки физической модели",
    secondary_line_label="физическая модель",
    selected_label="итоговый режим",
    x_bounds=None,
    y_bounds=None,
):
    width = 680
    height = 360
    left = 62
    right = 22
    title_lines = str(title).split("\n")
    legend_items = sum(bool(item) for item in [points, secondary_points, secondary_line_points, line_points, selected])
    top = max(98 + max(0, len(title_lines) - 1) * 18, 54 + max(0, len(title_lines) - 1) * 18 + legend_items * 18)
    bottom = 48
    all_points = list(points)
    if selected:
        all_points.append(selected)
    if line_points:
        all_points.extend(line_points)
    if secondary_points:
        all_points.extend(secondary_points)
    if secondary_line_points:
        all_points.extend(secondary_line_points)
    xs = [point[0] for point in all_points if point[0] is not None and math.isfinite(point[0])]
    ys = [point[1] for point in all_points if point[1] is not None and math.isfinite(point[1])]
    if not xs or not ys:
        return ""
    if x_bounds is not None:
        x_min, x_max = x_bounds
        x_min = min(x_min, min(xs))
        x_max = max(x_max, max(xs))
    else:
        x_min, x_max = min(xs), max(xs)
    if y_bounds is not None:
        y_min, y_max = y_bounds
        y_min = min(y_min, min(ys))
        y_max = max(y_max, max(ys))
    else:
        y_min, y_max = min(ys), max(ys)
    if x_min == x_max:
        x_min -= 1.0
        x_max += 1.0
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0
    if x_bounds is None:
        x_pad = (x_max - x_min) * 0.05
        x_min -= x_pad
        x_max += x_pad
    if y_bounds is None:
        y_pad = (y_max - y_min) * 0.05
        y_min -= y_pad
        y_max += y_pad

    def sx(value):
        return left + (value - x_min) / (x_max - x_min) * (width - left - right)

    def sy(value):
        return height - bottom - (value - y_min) / (y_max - y_min) * (height - top - bottom)

    x_ticks, x_step = _axis_ticks(x_min, x_max)
    y_ticks, y_step = _axis_ticks(y_min, y_max)
    grid = []
    for tick in x_ticks:
        x = sx(tick)
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" stroke="#e2e8f0" stroke-width="0.8"/>')
        grid.append(f'<line x1="{x:.1f}" y1="{height-bottom}" x2="{x:.1f}" y2="{height-bottom+4}" stroke="#334155"/>')
        grid.append(f'<text x="{x:.1f}" y="{height-bottom+17}" text-anchor="middle" font-size="10" fill="#475569">{escape(_format_graph_number(tick, x_step))}</text>')
    for tick in y_ticks:
        y = sy(tick)
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="0.8"/>')
        grid.append(f'<line x1="{left-4}" y1="{y:.1f}" x2="{left}" y2="{y:.1f}" stroke="#334155"/>')
        grid.append(f'<text x="{left-8}" y="{y+3:.1f}" text-anchor="end" font-size="10" fill="#475569">{escape(_format_graph_number(tick, y_step))}</text>')

    circles = []
    for x_value, y_value in _sample_even(points):
        circles.append(f'<circle cx="{sx(x_value):.1f}" cy="{sy(y_value):.1f}" r="2.3" fill="#64748b" opacity="0.42"/>')
    secondary_circles = []
    if secondary_points:
        for x_value, y_value in _sample_even(secondary_points):
            secondary_circles.append(f'<circle cx="{sx(x_value):.1f}" cy="{sy(y_value):.1f}" r="2.4" fill="#16a34a" opacity="0.42"/>')
    secondary_line_svg = ""
    if secondary_line_points:
        d = " ".join(
            ("M" if index == 0 else "L") + f"{sx(x_value):.1f},{sy(y_value):.1f}"
            for index, (x_value, y_value) in enumerate(secondary_line_points)
        )
        secondary_line_svg = f'<path d="{d}" fill="none" stroke="#16a34a" stroke-width="2.8" stroke-dasharray="6 4"/>'
    line_svg = ""
    if line_points:
        d = " ".join(
            ("M" if index == 0 else "L") + f"{sx(x_value):.1f},{sy(y_value):.1f}"
            for index, (x_value, y_value) in enumerate(line_points)
        )
        line_svg = f'<path d="{d}" fill="none" stroke="#1d4ed8" stroke-width="2.2"/>'
    selected_svg = ""
    if selected:
        selected_svg = f'<circle cx="{sx(selected[0]):.1f}" cy="{sy(selected[1]):.1f}" r="6" fill="#b91c1c"/>'
    legend = ""
    legend_x = left
    legend_y = 44 + max(0, len(title_lines) - 1) * 18
    if points:
        legend += f'<circle cx="{legend_x + 6}" cy="{legend_y}" r="4" fill="#64748b" opacity="0.55"/>'
        legend += f'<text x="{legend_x + 16}" y="{legend_y + 4}" font-size="12" fill="#475569">{escape(point_label)}</text>'
        legend_y += 18
    if secondary_points:
        legend += f'<circle cx="{legend_x + 6}" cy="{legend_y}" r="4" fill="#16a34a" opacity="0.65"/>'
        legend += f'<text x="{legend_x + 16}" y="{legend_y + 4}" font-size="12" fill="#475569">{escape(secondary_point_label)}</text>'
        legend_y += 18
    if secondary_line_points:
        legend += f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 24}" y2="{legend_y}" stroke="#16a34a" stroke-width="2.8" stroke-dasharray="6 4"/>'
        legend += f'<text x="{legend_x + 32}" y="{legend_y + 4}" font-size="12" fill="#475569">{escape(secondary_line_label)}</text>'
        legend_y += 18
    if line_points:
        legend += f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 24}" y2="{legend_y}" stroke="#1d4ed8" stroke-width="2.2"/>'
        legend += f'<text x="{legend_x + 32}" y="{legend_y + 4}" font-size="12" fill="#475569">{escape(line_label)}</text>'
        legend_y += 18
    if selected:
        legend += f'<circle cx="{legend_x + 6}" cy="{legend_y}" r="5" fill="#b91c1c"/>'
        legend += f'<text x="{legend_x + 18}" y="{legend_y + 4}" font-size="12" fill="#475569">{escape(selected_label)}</text>'
    title_svg = "".join(
        f'<text x="{left}" y="{22 + index * 18}" font-size="15" font-weight="700" fill="#1f2937">{escape(line)}</text>'
        for index, line in enumerate(title_lines)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>'
        + title_svg
        + legend
        +
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#334155"/>'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#334155"/>'
        f'<text x="{width/2:.1f}" y="{height-12}" text-anchor="middle" font-size="12" fill="#475569">{escape(x_label)}</text>'
        f'<text x="18" y="{height/2:.1f}" transform="rotate(-90 18 {height/2:.1f})" text-anchor="middle" font-size="12" fill="#475569">{escape(y_label)}</text>'
        + "".join(grid)
        + "".join(circles)
        + "".join(secondary_circles)
        + secondary_line_svg
        + line_svg
        + selected_svg
        + "</svg>"
    )


def _model_coefficients(model):
    rows = [{
        "term": "b0",
        "symbol": "b0",
        "meaning": "свободный член регрессионной модели; расчетное значение при средних стандартизованных признаках",
        "unit": "",
        "mean": None,
        "scale": None,
        "coef": round(model["coef"][0], 6),
    }]
    for offset, feature_index in enumerate(model["indices"], start=1):
        feature = FEATURES[feature_index]
        rows.append({
            "term": "z(" + feature["symbol"] + ")",
            "symbol": feature["symbol"],
            "meaning": feature["name"],
            "unit": feature["unit"],
            "mean": round(model["means"][offset - 1], 6),
            "scale": round(model["scales"][offset - 1], 6),
            "coef": round(model["coef"][offset], 6),
        })
    return rows


def _model_equation(model, key, name, unit):
    terms = ["y* = " + fmt_ru(model["coef"][0], 6)]
    for offset, feature_index in enumerate(model["indices"], start=1):
        feature = FEATURES[feature_index]
        coef = model["coef"][offset]
        sign = " + " if coef >= 0 else " - "
        terms.append(sign + fmt_ru(abs(coef), 6) + "·z(" + feature["symbol"] + ")")
    linear = "".join(terms)
    if key == "time":
        return linear + "; τ = exp(y*)"
    if key == "risk":
        return linear + "; p = min(1, max(0, y*))"
    if key.startswith("method_"):
        return linear + "; P = min(1, max(0, y*))"
    return linear + "; " + name + (", " + unit if unit else "") + " = y*"


def _formula_lines(key, name, unit):
    base = [
        "z(x) = (x - среднее x в архиве) / стандартное отклонение (СКО) x в архиве",
        "коэффициенты b_j рассчитаны методом наименьших квадратов по архивным этапам",
        "линейная часть: y* = b0 + Σ bj · z(xj)",
    ]
    if key == "time":
        return base + ["модель времени: ln(τ) = y*", "время сушки: τ = exp(y*)"]
    if key == "risk":
        return base + ["риск дефекта: p = min(1, max(0, y*))", "статус этапа задается верхней границей допуска p_high и границей p_border"]
    if key.startswith("method_"):
        return base + ["оценка принадлежности оборудованию: P = min(1, max(0, y*))", "выбирается оборудование с максимальной оценкой P"]
    return base + [name + (", " + unit if unit else "") + ": y = y*"]


TARGET_META = {
    "temperature": {"symbol": "Tсуш", "name": "температура сушки", "unit": "°C"},
    "time": {"symbol": "τ", "name": "время сушки", "unit": "мин"},
    "pressure": {"symbol": "p", "name": "давление в вакуумной камере", "unit": "Па"},
    "air_speed": {"symbol": "Vвозд", "name": "скорость воздушного потока", "unit": "м/с"},
    "humidity": {"symbol": "φ", "name": "относительная влажность среды", "unit": "%"},
    "residual": {"symbol": "Wост", "name": "остаток летучих компонентов", "unit": "%"},
    "delta_t": {"symbol": "ΔT", "name": "температурный перепад", "unit": "°C"},
    "risk": {"symbol": "p деф", "name": "вероятность дефекта", "unit": "доля"},
}

def _variable_label(symbol, name, unit="", include_unit=True):
    text = symbol + " — " + name
    if include_unit and unit:
        text += ", " + unit
    return text


def _target_label(key, fallback_name, fallback_unit, include_unit=True):
    meta = TARGET_META.get(key, {"symbol": fallback_name, "name": fallback_name.lower(), "unit": fallback_unit})
    return _variable_label(meta["symbol"], meta["name"], meta["unit"], include_unit=include_unit)


def _simple_model_equation(model):
    sign = " + " if model["b"] >= 0 else " - "
    if model.get("kind") == "arrhenius_time":
        return "τ = exp(" + fmt_ru(model["k"], 6) + "·(1 / T_K)" + sign + fmt_ru(abs(model["b"]), 6) + ")"
    if model.get("kind") == "exponential_decay":
        return model["y_symbol"] + " = exp(" + fmt_ru(model["k"], 6) + "·" + model["x_symbol"] + sign + fmt_ru(abs(model["b"]), 6) + ")"
    if model.get("kind") == "clapeyron_pressure":
        return "p = exp(" + fmt_ru(model["k"], 6) + "·(1 / T_K)" + sign + fmt_ru(abs(model["b"]), 6) + ")"
    if model.get("kind") == "logistic":
        linear = fmt_ru(model["k"], 6) + "·" + model["x_symbol"] + sign + fmt_ru(abs(model["b"]), 6)
        return "p деф = 1 / (1 + exp(-(" + linear + ")))"
    return model["y_symbol"] + " = " + fmt_ru(model["k"], 6) + "·" + model["x_symbol"] + sign + fmt_ru(abs(model["b"]), 6)


def _simple_model_coefficients(model):
    return [
        {
            "term": "b",
            "symbol": "b",
            "meaning": "свободный член уравнения",
            "unit": "",
            "coef": round(model["b"], 6),
        },
        {
            "term": "k",
            "symbol": "k",
            "meaning": "коэффициент наклона",
            "unit": "",
            "coef": round(model["k"], 6),
        },
    ]


def _selected_y_text(model):
    selected = model.get("selected")
    if not selected or selected[1] is None:
        return ""
    value = float(selected[1])
    symbol = model.get("y_symbol", "Y")
    unit = model.get("unit", "")
    if model.get("key") == "pressure" or unit == "Па":
        return symbol + " = " + fmt_ru(value / 1000.0, 2) + " кПа"
    if unit == "доля":
        return symbol + " = " + fmt_ru(value, 3)
    if unit:
        return symbol + " = " + fmt_ru(value, 2) + " " + unit
    return symbol + " = " + fmt_ru(value, 3)


def _simple_model_report(model):
    points = model.get("points", [])
    line_points = model.get("line_points", [])
    selected = model.get("selected")
    correlation = round(model.get("correlation", _pearson_r(points)), 3)
    selected_y_text = _selected_y_text(model)
    unit = model.get("unit", "")
    if unit == "доля" and model.get("key") != "risk":
        unit = ""
    graph = _svg_scatter(
        model["x_label_short"] + "\n" + model["y_label_short"],
        model["x_label"],
        model["y_label"],
        points,
        selected=selected,
        line_points=line_points,
        secondary_line_points=model.get("secondary_line_points"),
        point_label=model.get("point_label", "удачные похожие запуски"),
        line_label="регрессия",
        secondary_line_label=model.get("secondary_line_label", "физическая модель"),
        selected_label="итоговый режим",
        x_bounds=model.get("x_bounds"),
        y_bounds=model.get("y_bounds"),
    )
    return {
        "key": model["key"],
        "name": model["name"],
        "unit": unit,
        "r2": round(model.get("r2", 0.0), 3),
        "correlation": correlation,
        "selected_y_text": selected_y_text,
        "n": model.get("n", 0),
        "coefficients": _simple_model_coefficients(model),
        "equation": _simple_model_equation(model),
        "equation_label": "Формула регрессии",
        "feature_graphs": [{
            "key": model["key"],
            "name": model["x_label_short"] + " / " + model["y_label_short"],
            "feature": model["x_label_short"] + "\n" + model["y_label_short"],
            "graph": graph,
            "equation": _simple_model_equation(model),
            "equation_label": "Формула регрессии",
            "r2": round(model.get("r2", 0.0), 3),
            "correlation": correlation,
            "selected_y_text": selected_y_text,
            "n": model.get("n", 0),
        }],
    }


def build_stage_model_report(models, features, material, lens, step_calc):
    reports = [_simple_model_report(model) for model in step_calc.get("stage_models", [])]

    t_room = step_calc["temperatura_starta_c"]
    t_dry = step_calc["temperatura_sush_c"]
    t_ramp = step_calc["vremya_razgona_min"]
    t_hold = step_calc["vremya_vyderzhki_min"]
    t_cool = step_calc["vremya_ohlazhdeniya_min"]
    t_total = step_calc["polnoe_vremya_etapa_min"]
    profile = [
        (0.0, t_room),
        (t_ramp, t_dry),
        (t_ramp + t_hold, t_dry),
        (t_total, step_calc["temperatura_posle_ohlazhdeniya_c"]),
    ]
    temp_profile = _svg_scatter(
        "Температурная программа этапа",
        "τ — время от начала этапа, мин",
        "T — температура линзы, °C",
        [],
        selected=None,
        line_points=profile,
        point_label="",
        line_label="температурная программа",
        selected_label="",
    )

    correlation_values = [abs(model.get("correlation", 0.0)) for model in step_calc.get("stage_models", []) if model.get("n", 0) > 1]
    diagnostics = {
        "model_quality": round(sum(correlation_values) / len(correlation_values), 3) if correlation_values else 0.0,
        "extrapolation_index": step_calc.get("arhiv_stat", {}).get("extrapolation_index", 0.0),
    }
    return {
        "diagnostics": diagnostics,
        "models": reports,
        "calculation_graphs": [
            {"key": "temperature_program", "name": "Температурная программа", "graph": temp_profile},
        ],
    }


def _percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    return values[lower] * (upper - position) + values[upper] * (position - lower)


def _status_thresholds(predictions, labels):
    # p_low и p_high выбираются минимизацией порядковой ошибки по фактическому браку архива.
    paired = sorted((round(pred, 4), label) for pred, label in zip(predictions, labels))
    candidates = sorted(set(pred for pred, _label in paired))
    if len(candidates) < 2:
        value = candidates[0] if candidates else 0.0
        return value, value

    prefix_defects = [0.0]
    prefix_goods = [0.0]
    for _pred, label in paired:
        prefix_defects.append(prefix_defects[-1] + (1.0 if label else 0.0))
        prefix_goods.append(prefix_goods[-1] + (0.0 if label else 1.0))

    first_index = {}
    last_index = {}
    for index, (pred, _label) in enumerate(paired):
        first_index.setdefault(pred, index)
        last_index[pred] = index

    total = len(paired)
    best = None
    for low_index, low in enumerate(candidates[:-1]):
        low_end = last_index[low]
        low_loss = 2.0 * prefix_defects[low_end + 1]
        for high in candidates[low_index + 1:]:
            high_start = first_index[high]
            middle_count = max(0, high_start - low_end - 1)
            high_goods = prefix_goods[total] - prefix_goods[high_start]
            loss = low_loss + middle_count + 2.0 * high_goods
            if best is None or loss < best[0]:
                best = (loss, low, high)
    if best is None:
        return min(candidates), max(candidates)
    low, high = best[1], best[2]
    if high - low < 0.05:
        values = [pred for pred, _label in paired]
        low = _percentile(values, 0.40)
        high = _percentile(values, 0.75)
    return low, high


def build_archive_models(rows):
    records = []
    for row in rows or []:
        row_good = row.get("godnaya_partiya", 0) == 1
        material_limits = [row.get("Tmax", 0.0)]
        if row.get("Tg", 0.0) and row.get("Tg", 0.0) > 0:
            material_limits.append(row.get("Tg"))
        material_temperature_limit = min(value for value in material_limits if value and value > 0) if any(value and value > 0 for value in material_limits) else None
        for n in range(1, 6):
            pref = f"e{n}_"
            if row.get("kol_etapov", 0) < n or not row.get(pref + "pokrytie_kod"):
                continue
            features = _row_stage_feature_vector(row, n)
            stage_defect_code = row.get(pref + "defekt_kod", 0)
            stage_temperature = row.get(pref + "t_sush")
            physical_ok = (
                stage_temperature is None
                or material_temperature_limit is None
                or stage_temperature <= material_temperature_limit + 1e-6
            )
            stage_success = row_good and stage_defect_code == 0 and physical_ok
            if not physical_ok:
                risk_defect = None
            elif stage_defect_code == 2:
                risk_defect = None
            elif stage_defect_code != 0:
                risk_defect = 1.0
            elif row_good:
                risk_defect = 0.0
            else:
                risk_defect = None
            records.append({
                "features": features,
                "coating": row.get(pref + "pokrytie_kod"),
                "stage_group_code": row.get(pref + "tip_pokrytiya_kod", 0),
                "base_code": row.get(pref + "tip_propitki_kod", 0),
                "method_code": row.get(pref + "sreda_kod", 1),
                "defect": risk_defect,
                "success": stage_success,
                "row_good": row_good,
                "stage_defect_code": stage_defect_code,
                "physical_ok": physical_ok,
                "material_temperature_limit_c": material_temperature_limit,
                "t_sush": row.get(pref + "t_sush"),
                "tau_sush": row.get(pref + "tau_sush"),
                "p_sush_pa": row.get(pref + "p_sush_pa"),
                "v_sush": row.get(pref + "v_sush"),
                "fi_sush": row.get(pref + "fi_sush"),
                "w_ost": row.get(pref + "w_ost"),
                "delta_t": row.get(pref + "delta_t"),
            })
    success_records = [record for record in records if record.get("success")]
    risk_records = [record for record in records if record.get("defect") is not None and record.get("physical_ok")]
    if not risk_records:
        risk_records = records
    method_records = success_records or risk_records or records
    def samples(field):
        return [(record["features"], record[field]) for record in success_records if record.get(field) is not None]
    models = {
        "records": records,
        "method": {
            code: _fit_ols([(record["features"], 1.0 if record["method_code"] == code else 0.0) for record in method_records])
            for code in sorted(SREDA_NAME)
        },
        "temperature": _fit_ols(samples("t_sush")),
        "time": _fit_ols(samples("tau_sush"), transform=lambda value: math.log(max(value, 1e-6))),
        "pressure": _fit_ols(samples("p_sush_pa")),
        "air_speed": _fit_ols(samples("v_sush")),
        "humidity": _fit_ols(samples("fi_sush")),
        "residual": _fit_ols(samples("w_ost")),
        "delta_t": _fit_ols(samples("delta_t")),
        "risk": _fit_ols([(record["features"], record["defect"]) for record in risk_records]),
    }
    if models["risk"]:
        preds = [max(0.0, min(1.0, _predict_ols(models["risk"], record["features"]))) for record in risk_records]
        labels = [record["defect"] for record in risk_records]
        models["risk_thresholds"] = _status_thresholds(preds, labels)
    else:
        defect_rate = sum(record["defect"] for record in risk_records) / len(risk_records) if risk_records else 0.0
        models["risk_thresholds"] = (defect_rate, defect_rate)
    return models


_ARCHIVE_MODELS_CACHE = {}


def _archive_rows_signature(rows):
    total = 1469598103934665603
    for row in rows or []:
        parts = [
            row.get("kod_zapuska", ""),
            row.get("godnaya_partiya", ""),
            row.get("kol_etapov", ""),
            row.get("material_kod", ""),
        ]
        for n in range(1, 6):
            pref = f"e{n}_"
            parts.extend([
                row.get(pref + "pokrytie_kod", ""),
                row.get(pref + "defekt_kod", ""),
                row.get(pref + "t_sush", ""),
                row.get(pref + "tau_sush", ""),
            ])
        text = "|".join(str(part) for part in parts)
        for char in text:
            total ^= ord(char)
            total = (total * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return len(rows or []), total


def archive_models_for_rows(rows):
    signature = _archive_rows_signature(rows)
    cached = _ARCHIVE_MODELS_CACHE.get(signature)
    if cached is not None:
        return cached
    models = build_archive_models(rows)
    if len(_ARCHIVE_MODELS_CACHE) >= 3:
        _ARCHIVE_MODELS_CACHE.clear()
    _ARCHIVE_MODELS_CACHE[signature] = models
    return models


def _model_r2_map(models):
    values = {}
    for key, model in _model_items(models):
        if isinstance(model, dict) and "r2" in model:
            values[key] = round(model["r2"], 3)
    return values


def _archive_record_allowed(record, temp_limit=None):
    if not record.get("physical_ok", True):
        return False
    if temp_limit is None:
        return True
    temp = record.get("t_sush")
    return temp is None or temp <= temp_limit + 1e-6


def similar_stage_records(records, coating, temp_limit=None):
    pool = [record for record in records if _archive_record_allowed(record, temp_limit)]
    if not pool:
        pool = [record for record in records if record.get("physical_ok", True)]
    exact = [record for record in pool if record["coating"] == coating.kod]
    group = [
        record for record in pool
        if record["stage_group_code"] == TIP_POKRYTIYA_KOD.get(coating.stage_group)
        and record["base_code"] == TIP_PROPITKI_KOD.get(coating.base_type)
    ]
    selected = exact or group or pool
    mode = "тот же состав" if exact else "тот же тип покрытия и основы" if group else "общая регрессионная выборка"
    good = [record for record in selected if record.get("success")]
    return selected, good, mode


def target_drying_temperature(temp_limit, temp_floor, start_temp_c, temperature_threshold):
    # Tсуш = Kпор * min(Tmax материала, Tg материала, Tmax выбранных слоев).
    target = temperature_threshold * temp_limit
    return clamp(max(target, temp_floor, start_temp_c), start_temp_c, temp_limit)


def _evaporation_energy_j_mol(coating):
    base = getattr(coating, "base_type", "")
    if base == "водная":
        return 40650.0
    if base == "спиртовая":
        return 38560.0
    if base == "фторсодержащая":
        return 30000.0
    if base == "комбинированная":
        return 0.5 * (40650.0 + 38560.0)
    return 42000.0


def _physical_reference_time_min(material, lens, coating):
    tau_th = thermal_diffusion_time_min(material, lens)
    solvent_load = max(getattr(coating, "initial_solvent_pct", 0.0), 1.0)
    evaporation_rate = max(getattr(coating, "evaporation_rate", 0.0), 0.05)
    return max(5.0, tau_th + solvent_load / evaporation_rate)


def _physical_time_at_temp(temp_c, anchor_temp_c, anchor_time_min, coating):
    gas_constant = 8.314462618
    energy = _evaporation_energy_j_mol(coating)
    temp_k = temp_c + 273.15
    anchor_k = anchor_temp_c + 273.15
    return max(1.0, anchor_time_min * math.exp((energy / gas_constant) * (1.0 / temp_k - 1.0 / anchor_k)))


def _median(values):
    clean = sorted(value for value in values if value is not None and math.isfinite(value))
    if not clean:
        return None
    return _percentile(clean, 0.5)


def _temperature_time_points(records):
    return [
        (record.get("t_sush"), record.get("tau_sush"))
        for record in records
        if record.get("t_sush") is not None and record.get("tau_sush") is not None
    ]


def _physical_point_count(archive_count, archive_weight):
    archive_weight = clamp(float(archive_weight), 0.0, 1.0)
    if archive_weight >= 1.0:
        return 0
    if archive_weight <= 0.0:
        return max(60, archive_count)
    return int(round(archive_count * (1.0 - archive_weight) / archive_weight))


def _fit_time_model(material, lens, coating, records, temp_c, temp_min, temp_max, archive_weight):
    archive_points = _temperature_time_points(records)
    physics_anchor_temp = max(temp_min, min(temp_max, 60.0))
    physics_anchor_time = _physical_reference_time_min(material, lens, coating)

    physics_count = _physical_point_count(len(archive_points), archive_weight)
    physics_points = []
    if physics_count:
        steps = max(physics_count - 1, 1)
        for index in range(physics_count):
            t = temp_min + (temp_max - temp_min) * index / steps
            physics_points.append((t, _physical_time_at_temp(t, physics_anchor_temp, physics_anchor_time, coating)))

    physics_curve_points = []
    for index in range(80):
        t = temp_min + (temp_max - temp_min) * index / 79.0
        physics_curve_points.append((t, _physical_time_at_temp(t, physics_anchor_temp, physics_anchor_time, coating)))

    if archive_weight <= 0:
        regression_points = physics_points
    elif archive_weight >= 1:
        regression_points = archive_points
    else:
        regression_points = archive_points + physics_points
    if len(regression_points) < 2:
        raise RecommendationError("Недостаточно удачных похожих запусков для температурно-временной регрессии.")

    transformed = [(1.0 / (t + 273.15), math.log(max(tau, 1e-6))) for t, tau in regression_points]
    line = _fit_line(transformed)
    if line is None:
        raise RecommendationError("Температурно-временная регрессия не построена.")
    tau = math.exp(_predict_line(line, 1.0 / (temp_c + 273.15)))

    line_points = []
    for index in range(80):
        t = temp_min + (temp_max - temp_min) * index / 79.0
        line_points.append((t, math.exp(_predict_line(line, 1.0 / (t + 273.15)))))

    return tau, {
        "key": "time",
        "kind": "arrhenius_time",
        "name": "Время сушки",
        "unit": "мин",
        "x_symbol": "1/T_K",
        "x_label": "Tсуш — температура сушки, °C",
        "x_label_short": "Tсуш — температура сушки",
        "y_symbol": "τ",
        "y_label": "τ — время сушки, мин",
        "y_label_short": "τ — время сушки",
        "k": line["k"],
        "b": line["b"],
        "r2": line["r2"],
        "correlation": _pearson_r(archive_points),
        "n": len(regression_points),
        "points": archive_points,
        "line_points": line_points,
        "secondary_line_points": physics_curve_points,
        "selected": (temp_c, tau),
        "point_label": "удачные похожие запуски",
        "secondary_line_label": "физическая модель",
        "archive_points": len(archive_points),
        "physics_points": len(physics_points),
    }


def _fit_stage_line_model(key, name, unit, x_symbol, x_name, x_unit, y_symbol, records, x_getter, y_field, selected_x, point_label="удачные похожие запуски"):
    points = []
    for record in records:
        y_value = record.get(y_field)
        if y_value is None:
            continue
        x_value = x_getter(record)
        if x_value is not None and math.isfinite(x_value) and math.isfinite(y_value):
            points.append((x_value, y_value))
    line = _fit_line(points)
    if line is None:
        return None, None
    selected_y = _predict_line(line, selected_x)
    x_values = [x for x, _y in points] + [selected_x]
    x_min, x_max = min(x_values), max(x_values)
    if x_min == x_max:
        x_min -= 1.0
        x_max += 1.0
    line_points = [
        (x_min + (x_max - x_min) * index / 60.0, _predict_line(line, x_min + (x_max - x_min) * index / 60.0))
        for index in range(61)
    ]
    model = {
        "key": key,
        "kind": "linear",
        "name": name,
        "unit": unit,
        "x_symbol": x_symbol,
        "x_label": _variable_label(x_symbol, x_name, x_unit),
        "x_label_short": _variable_label(x_symbol, x_name, "", include_unit=False),
        "y_symbol": y_symbol,
        "y_label": _target_label(key, name, unit),
        "y_label_short": _target_label(key, name, unit, include_unit=False),
        "k": line["k"],
        "b": line["b"],
        "r2": line["r2"],
        "correlation": _pearson_r(points),
        "n": line["n"],
        "points": points,
        "line_points": line_points,
        "selected": (selected_x, selected_y),
        "point_label": point_label,
    }
    return selected_y, model


def _line_graph_points(points, selected_x, predictor, count=61):
    x_values = [x for x, _y in points] + [selected_x]
    x_min, x_max = min(x_values), max(x_values)
    if x_min == x_max:
        x_min -= 1.0
        x_max += 1.0
    return [
        (x_min + (x_max - x_min) * index / (count - 1), predictor(x_min + (x_max - x_min) * index / (count - 1)))
        for index in range(count)
    ]


def _fit_stage_exponential_model(key, name, unit, x_symbol, x_name, x_unit, y_symbol, records, x_getter, y_field, selected_x, point_label="удачные похожие запуски"):
    points = []
    transformed = []
    for record in records:
        y_value = record.get(y_field)
        if y_value is None or y_value <= 0:
            continue
        x_value = x_getter(record)
        if x_value is not None and math.isfinite(x_value) and math.isfinite(y_value):
            points.append((x_value, y_value))
            transformed.append((x_value, math.log(max(y_value, 1e-6))))
    line = _fit_line(transformed)
    if line is None:
        return None, None
    selected_y = math.exp(_predict_line(line, selected_x))
    line_points = _line_graph_points(points, selected_x, lambda value: math.exp(_predict_line(line, value)))
    model = {
        "key": key,
        "kind": "exponential_decay",
        "name": name,
        "unit": unit,
        "x_symbol": x_symbol,
        "x_label": _variable_label(x_symbol, x_name, x_unit),
        "x_label_short": _variable_label(x_symbol, x_name, "", include_unit=False),
        "y_symbol": y_symbol,
        "y_label": _target_label(key, name, unit),
        "y_label_short": _target_label(key, name, unit, include_unit=False),
        "k": line["k"],
        "b": line["b"],
        "r2": line["r2"],
        "correlation": _pearson_r(points),
        "n": line["n"],
        "points": points,
        "line_points": line_points,
        "selected": (selected_x, selected_y),
        "point_label": point_label,
    }
    return selected_y, model


def _fit_stage_clapeyron_model(key, name, unit, records, selected_temp_c, point_label="удачные похожие запуски"):
    points = []
    transformed = []
    for record in records:
        temp_c = record.get("t_sush")
        pressure = record.get("p_sush_pa")
        if temp_c is None or pressure is None or pressure <= 0:
            continue
        if math.isfinite(temp_c) and math.isfinite(pressure):
            points.append((temp_c, pressure))
            transformed.append((1.0 / (temp_c + 273.15), math.log(max(pressure, 1e-6))))
    line = _fit_line(transformed)
    if line is None:
        return None, None
    selected_y = math.exp(_predict_line(line, 1.0 / (selected_temp_c + 273.15)))
    line_points = _line_graph_points(
        points,
        selected_temp_c,
        lambda value: math.exp(_predict_line(line, 1.0 / (value + 273.15))),
    )
    model = {
        "key": key,
        "kind": "clapeyron_pressure",
        "name": name,
        "unit": unit,
        "x_symbol": "1/T_K",
        "x_label": "Tсуш — температура сушки, °C",
        "x_label_short": "Tсуш — температура сушки",
        "y_symbol": "p",
        "y_label": _target_label(key, name, unit),
        "y_label_short": _target_label(key, name, unit, include_unit=False),
        "k": line["k"],
        "b": line["b"],
        "r2": line["r2"],
        "correlation": _pearson_r(points),
        "n": line["n"],
        "points": points,
        "line_points": line_points,
        "selected": (selected_temp_c, selected_y),
        "point_label": point_label,
    }
    return selected_y, model


def _fit_stage_logistic_model(key, name, unit, x_symbol, x_name, x_unit, y_symbol, records, x_getter, y_field, selected_x, point_label="похожие архивные этапы"):
    points = []
    for record in records:
        y_value = record.get(y_field)
        if y_value is None:
            continue
        x_value = x_getter(record)
        if x_value is not None and math.isfinite(x_value) and math.isfinite(y_value):
            points.append((x_value, 1.0 if y_value >= 0.5 else 0.0))
    model_line = _fit_logistic(points)
    if model_line is None:
        return None, None
    selected_y = _sigmoid(model_line["k"] * selected_x + model_line["b"])
    line_points = _line_graph_points(points, selected_x, lambda value: _sigmoid(model_line["k"] * value + model_line["b"]))
    predictions = [_sigmoid(model_line["k"] * x + model_line["b"]) for x, _y in points]
    labels = [y for _x, y in points]
    model = {
        "key": key,
        "kind": "logistic",
        "name": name,
        "unit": unit,
        "x_symbol": x_symbol,
        "x_label": _variable_label(x_symbol, x_name, x_unit),
        "x_label_short": _variable_label(x_symbol, x_name, "", include_unit=False),
        "y_symbol": y_symbol,
        "y_label": _target_label(key, name, unit),
        "y_label_short": _target_label(key, name, unit, include_unit=False),
        "k": model_line["k"],
        "b": model_line["b"],
        "r2": model_line["r2"],
        "correlation": _pearson_r(points),
        "n": model_line["n"],
        "points": points,
        "line_points": line_points,
        "thresholds": _status_thresholds(predictions, labels),
        "y_bounds": (0.0, 1.0),
        "selected": (selected_x, selected_y),
        "point_label": point_label,
    }
    return selected_y, model


def predict_stage_values(models, features, material, lens, coating, temp_limit, temp_floor, start_temp_c, selected_records, good_records, archive_weight, temperature_threshold):
    records = models.get("records", [])
    if not records:
        raise RecommendationError("Архив не содержит этапов для построения регрессионной модели.")
    selected_records = selected_records or [record for record in records if _archive_record_allowed(record, temp_limit)]
    if not selected_records:
        selected_records = records
    good_records = good_records or [record for record in selected_records if record.get("success")]
    if not good_records:
        raise RecommendationError("Недостаточно успешных похожих запусков для построения расчетных регрессий.")
    regression_records = good_records

    method_scores = {}
    for code in sorted(SREDA_NAME):
        score = _predict_ols(models.get("method", {}).get(code), features)
        if score is None:
            raise RecommendationError("Не построена регрессионная модель выбора оборудования: " + SREDA_NAME[code] + ".")
        method_scores[code] = max(0.0, min(1.0, score))
    method_code = max(method_scores, key=lambda code: method_scores[code])
    method = SREDA_METHOD_NAME[method_code]
    environment = SREDA_NAME[method_code]

    temp = target_drying_temperature(temp_limit, temp_floor, start_temp_c, temperature_threshold)
    archive_temps = [record.get("t_sush") for record in regression_records if record.get("t_sush") is not None]
    if archive_temps:
        temp_min = max(start_temp_c + 1.0, min(archive_temps), 22.0)
        temp_max = min(temp_limit, max(archive_temps))
    else:
        temp_min = max(start_temp_c + 1.0, temp - 8.0)
        temp_max = min(temp_limit, temp + 8.0)
    if temp_max <= temp_min:
        temp_min = max(start_temp_c + 1.0, temp - 8.0)
        temp_max = min(temp_limit, temp + 8.0)
    temp_min = min(temp_min, temp)
    temp_max = max(temp_max, temp)
    if temp_max <= temp_min:
        temp_min = temp - 1.0
        temp_max = temp + 1.0

    program_time_min, time_model = _fit_time_model(
        material,
        lens,
        coating,
        regression_records,
        temp,
        temp_min,
        temp_max,
        archive_weight,
    )
    program_time_min = max(0.0, program_time_min)

    stage_models = [time_model]

    residual, residual_model = _fit_stage_exponential_model(
        "residual",
        "Остаток летучих компонентов",
        "%",
        "Tсуш",
        "температура сушки",
        "°C",
        "Wост",
        regression_records,
        lambda record: record.get("t_sush"),
        "w_ost",
        temp,
    )
    if residual_model:
        stage_models.append(residual_model)
    if residual is None:
        raise RecommendationError("Недостаточно удачных похожих запусков для регрессии остатка летучих компонентов.")
    residual = max(0.0, residual)

    delta_t, delta_model = _fit_stage_line_model(
        "delta_t",
        "Температурный перепад",
        "°C",
        "Tсуш",
        "температура сушки",
        "°C",
        "ΔT",
        regression_records,
        lambda record: record.get("t_sush"),
        "delta_t",
        temp,
    )
    if delta_model:
        stage_models.append(delta_model)
    if delta_t is None:
        raise RecommendationError("Недостаточно удачных похожих запусков для регрессии температурного перепада.")
    delta_t = max(0.0, delta_t)

    pressure_pa = None
    air_speed = None
    humidity_pct = None
    if method_code == 2:
        vacuum_records = [record for record in regression_records if record.get("method_code") == 2 and record.get("p_sush_pa") is not None]
        pressure_pa, pressure_model = _fit_stage_clapeyron_model(
            "pressure",
            "Давление в вакуумной камере",
            "Па",
            vacuum_records,
            temp,
        )
        if pressure_model:
            stage_models.append(pressure_model)
        if pressure_pa is None:
            raise RecommendationError("Регрессионная модель выбрала вакуумную сушку, но похожие удачные запуски не содержат давления.")
        pressure_pa = max(0.0, pressure_pa)
    elif method_code == 1:
        conv_records = [record for record in regression_records if record.get("method_code") == 1]
        air_speed, air_model = _fit_stage_line_model(
            "air_speed",
            "Скорость воздушного потока",
            "м/с",
            "Tсуш",
            "температура сушки",
            "°C",
            "Vвозд",
            conv_records,
            lambda record: record.get("t_sush"),
            "v_sush",
            temp,
        )
        humidity_pct, humidity_model = _fit_stage_line_model(
            "humidity",
            "Относительная влажность среды",
            "%",
            "Tсуш",
            "температура сушки",
            "°C",
            "φ",
            conv_records,
            lambda record: record.get("t_sush"),
            "fi_sush",
            temp,
        )
        if air_model:
            stage_models.append(air_model)
        if humidity_model:
            stage_models.append(humidity_model)
        if air_speed is None or humidity_pct is None:
            raise RecommendationError("Регрессионная модель выбрала конвективную сушку, но похожие удачные запуски не содержат скорости воздуха или влажности.")
        air_speed = max(0.0, air_speed)
        humidity_pct = max(0.0, min(100.0, humidity_pct))

    risk, risk_model = _fit_stage_logistic_model(
        "risk",
        "Вероятность дефекта",
        "доля",
        "Tсуш",
        "температура сушки",
        "°C",
        "p деф",
        selected_records,
        lambda record: record.get("t_sush"),
        "defect",
        temp,
        point_label="похожие архивные этапы",
    )
    if risk_model:
        stage_models.append(risk_model)
    if risk is None:
        raise RecommendationError("Недостаточно похожих запусков для регрессии риска.")
    risk = max(0.0, min(1.0, risk))
    risk_thresholds = risk_model.get("thresholds") if risk_model else models.get("risk_thresholds", (0.0, 0.0))
    return {
        "metod_sushki": method,
        "sreda_sushki": environment,
        "temperatura_sush_c": temp,
        "vremya_programmy_min": program_time_min,
        "davlenie_sush_pa": pressure_pa,
        "skorost_vozduha_ms": air_speed,
        "vlazhnost_sredy_pct": humidity_pct,
        "w_ost_pct": residual,
        "delta_t_c": delta_t,
        "risk": risk,
        "risk_thresholds": risk_thresholds,
        "model_n": len(regression_records),
        "model_r2": _model_r2_map(models),
        "stage_models": stage_models,
    }


def archive_stage_stat(models, features, coating, temp_limit=None):
    records = models.get("records", [])
    if not records:
        return {"found": 0, "good": 0, "defect_rate": 0.0, "model_quality": 0.0, "extrapolation_index": 0.0, "comparison_mode": "архив пуст"}
    selected, good, mode = similar_stage_records(records, coating, temp_limit)
    defect_labels = [record["defect"] for record in selected if record.get("defect") is not None]
    defect_count = sum(defect_labels)
    diagnostics = _model_diagnostics(models, features)
    return {
        "found": len(selected),
        "good": len(good),
        "same_material_good": 0,
        "same_stack_good": 0,
        "defect_rate": round(defect_count / len(defect_labels), 3) if defect_labels else 0.0,
        "model_quality": diagnostics["model_quality"],
        "extrapolation_index": diagnostics["extrapolation_index"],
        "comparison_mode": mode,
    }


def _layer_temperature_need(layer):
    return layer.thermal_stability_c


def _layer_rank(layer):
    try:
        return LAYER_ORDER.index(layer.stage_group)
    except ValueError:
        return len(LAYER_ORDER)


def ordered_layers(selected_layers):
    unique = {}
    for layer in selected_layers:
        unique[layer.id] = layer
    layers = list(unique.values())
    layers.sort(key=lambda item: (_layer_rank(item), -_layer_temperature_need(item), item.name))
    return layers[:5]


def temperature_limit_candidates(material, current_layer, prior_layers):
    candidates = [
        (material.t_max_c, "Tmax материала: " + material.name),
        (current_layer.thermal_stability_c, "Tmax текущего состава: " + current_layer.name),
    ]
    if material.tg_c is not None and material.tg_c > 0:
        candidates.append((material.tg_c, "Tg материала: " + material.name))

    for layer in prior_layers:
        candidates.append((layer.thermal_stability_c, "Tmax уже нанесенного слоя: " + layer.name))
    return candidates


def effective_temperature_limit(material, current_layer, prior_layers, stage_index):
    candidates = [value for value, _label in temperature_limit_candidates(material, current_layer, prior_layers)]
    return max(22.0, min(candidates))


def temperature_limit_source(material, current_layer, prior_layers):
    value, label = min(temperature_limit_candidates(material, current_layer, prior_layers), key=lambda item: item[0])
    return round(max(22.0, value), 1), label


def process_temperature_floor(coating, start_temp_c):
    group_floor = {
        "упрочняющее": 42.0,
        "фотохромное": 40.0,
        "антибликовое": 36.0,
        "антистатическое": 34.0,
        "гидрофобное": 34.0,
        "олеофобное": 34.0,
        "антизапотевающее": 34.0,
    }.get(coating.stage_group, 34.0)
    solvent_floor = start_temp_c + 8.0 + 0.04 * max(getattr(coating, "initial_solvent_pct", 0.0), 0.0)
    if coating.requires_uv:
        solvent_floor += 2.0
    return max(group_floor, solvent_floor)


def estimate_ramp_rate(temp_c, start_temp_c, material, lens, allowed_delta_t_c):
    ramp_time = estimate_ramp_time(temp_c, start_temp_c, material, lens, allowed_delta_t_c)
    if ramp_time <= 0:
        return 0.0
    return (temp_c - start_temp_c) / ramp_time


def estimate_ramp_time(temp_c, start_temp_c, material, lens, allowed_delta_t_c):
    if temp_c <= start_temp_c:
        return 0.0
    if allowed_delta_t_c <= 0:
        raise RecommendationError("Архивная модель дала недопустимый температурный перепад.")
    # t = tau_th * DeltaT_surface / DeltaT_allowed.
    return thermal_diffusion_time_min(material, lens) * (temp_c - start_temp_c) / allowed_delta_t_c


def estimate_cooling_rate(temp_c, target_temp_c, material, lens, allowed_delta_t_c):
    cooling_time = estimate_cooling_time(temp_c, target_temp_c, material, lens, allowed_delta_t_c)
    if cooling_time <= 0:
        return 0.0
    return (temp_c - target_temp_c) / cooling_time


def estimate_cooling_time(temp_c, target_temp_c, material, lens, allowed_delta_t_c):
    if temp_c <= target_temp_c:
        return 0.0
    if allowed_delta_t_c <= 0:
        raise RecommendationError("Архивная модель дала недопустимый температурный перепад.")
    # t = tau_th * DeltaT_surface / DeltaT_allowed.
    return thermal_diffusion_time_min(material, lens) * (temp_c - target_temp_c) / allowed_delta_t_c


def estimate_delta_l_um(material, lens, delta_t_c):
    # DeltaL = alpha * d * DeltaT, результат переведен из мм в мкм.
    return material.expansion_1_k * lens.d_mm * delta_t_c * 1000.0


def transition_text(coating):
    if coating.application_method == "погружение":
        return "После извлечения из ванны убрать избыток состава с кромки, контролировать отсутствие потеков и непрокрытых зон."
    if coating.application_method == "распыление":
        return "После распыления перенести линзу в зону сушки без сильного встречного потока, контролировать равномерность аэрозольного слоя."
    if coating.application_method == "центрифугирование":
        return "После остановки вращения проверить отсутствие радиальных полос и скопления состава у края линзы."
    return "Проверить равномерность нанесенного слоя перед сушкой."


def drying_description(method, temp_c, time_min, pressure_pa, speed_ms, humidity_pct, requires_uv=False):
    method_display = method
    if requires_uv:
        method_display = "комбинированная сушка: " + method + " + УФ-отверждение"
    base = (
        "Выполнить: " + method_display + ". "
        + "Температура сушки " + fmt_ru(temp_c, 1) + " °C. "
        + "Время выдержки " + fmt_ru(time_min, 1) + " мин."
    )
    if method == "вакуумная сушка":
        return base + " Давление в рабочей камере " + fmt_ru(pressure_pa, 0) + " Па."
    if method == "конвективная сушка":
        return (
            base
            + " Скорость воздушного потока " + fmt_ru(speed_ms, 2) + " м/с. "
            + "Оптимальная относительная влажность среды " + fmt_ru(humidity_pct, 1) + " %."
        )
    return base + " Контролировать равномерность поверхностного нагрева без задания давления и скорости воздушного потока."


def build_profile(
    coating,
    temp_c,
    time_min,
    ramp_rate_c_min,
    ramp_time_min,
    cooling_rate_c_min,
    cooling_time_min,
    cooling_target_c,
    total_time_min,
    method,
    pressure_pa,
    speed_ms,
    humidity_pct,
    is_final,
):
    profile = [
        {
            "operation": "Нанесение покрытия",
            "description": "Нанести " + coating.name + ", метод нанесения: " + coating.application_method + ".",
        },
        {
            "operation": "Контроль слоя перед сушкой",
            "description": transition_text(coating),
        },
        {
            "operation": "Нагрев",
            "description": "Плавно вывести оборудование на " + fmt_ru(temp_c, 1) + " °C. Скорость нагрева не выше " + fmt_ru(ramp_rate_c_min, 2) + " °C/мин. Ориентировочное время нагрева " + fmt_ru(ramp_time_min, 1) + " мин.",
        },
        {
            "operation": "Сушка",
            "description": drying_description(method, temp_c, time_min, pressure_pa, speed_ms, humidity_pct, coating.requires_uv),
        },
    ]
    if coating.requires_uv:
        profile.append(
            {
                "operation": "УФ-отверждение",
                "description": "После тепловой выдержки выполнить УФ-отверждение по карте состава.",
            }
        )
    cooling_name = "Финальное охлаждение" if is_final else "Отпуск перед следующим этапом"
    profile.append({
        "operation": cooling_name,
        "description": "Охлаждение вести со скоростью не выше "
        + fmt_ru(cooling_rate_c_min, 2)
        + " °C/мин. При расчетном охлаждении до "
        + fmt_ru(cooling_target_c, 1)
        + " °C полное время сушки "
        + fmt_ru(total_time_min, 1)
        + " мин.",
    })
    return profile


def round_or_none(value, digits):
    if value is None:
        return None
    return round(value, digits)


def base_components(layer):
    if getattr(layer, "base_type", "") != "комбинированная":
        return {getattr(layer, "base_type", "")}
    text = (getattr(layer, "composition", "") or "").lower()
    result = set()
    if "вод" in text:
        result.add("водная")
    if "спирт" in text or "этанол" in text or "изопропанол" in text or "гликол" in text or "органическ" in text:
        result.add("спиртовая")
    if "акрил" in text or "уретан" in text or "полимер" in text or "смол" in text:
        result.add("полимерная")
    if "фтор" in text or "pfpe" in text:
        result.add("фторсодержащая")
    return result or {"комбинированная"}


def base_transition_warnings(layers):
    warnings = []
    for lower, upper in zip(layers, layers[1:]):
        lower_components = base_components(lower)
        upper_components = base_components(upper)
        low_energy_lower = "фторсодержащая" in lower_components or lower.stage_group in {"гидрофобное", "олеофобное"}
        if low_energy_lower:
            warnings.append(
                "Неблагоприятное перекрытие слоев: поверх низкоэнергетического слоя "
                + lower.name
                + " наносится "
                + upper.name
                + ". Возможны плохое смачивание и слабая адгезия; поведение структуры без отдельной пробы неизвестно."
            )
        if "водная" in lower_components and "спиртовая" in upper_components:
            warnings.append(
                "Переход основы требует проверки: спиртовая система "
                + upper.name
                + " наносится поверх водного слоя "
                + lower.name
                + ". При неполной фиксации нижнего слоя возможны набухание, размывание или изменение адгезии."
            )
        if "спиртовая" in lower_components and "водная" in upper_components:
            warnings.append(
                "Переход основы требует проверки: водная система "
                + upper.name
                + " наносится поверх спиртового слоя "
                + lower.name
                + ". После полной сушки это может быть допустимо, но без подтверждения возможны проблемы смачивания и адгезии."
            )
    return warnings


def compatibility_warnings(layers):
    warnings = []
    external_layers = [layer for layer in layers if is_external_only(layer)]
    external_groups = sorted({layer.stage_group for layer in external_layers})

    finish_layers = [layer for layer in external_layers if layer.stage_group != "антистатическое"]
    if len(finish_layers) > 1:
        names = ", ".join(layer.name for layer in finish_layers)
        warnings.append(
            "Выбрано несколько покрытий, которые должны оставаться верхним слоем: "
            + names
            + ". При последовательном нанесении верхнее покрытие перекрывает свойства нижнего."
        )

    duplicate_groups = []
    by_group = {}
    for layer in external_layers:
        by_group.setdefault(layer.stage_group, []).append(layer.name)
    for group, names in by_group.items():
        if len(names) > 1:
            duplicate_groups.append(group + " (" + str(len(names)) + " состава)")
    if duplicate_groups:
        warnings.append(
            "Выбрано несколько составов одного типа: "
            + ", ".join(sorted(duplicate_groups))
            + ". Обычно оставляют один состав данного типа."
        )

    if "антизапотевающее" in external_groups and ({"гидрофобное", "олеофобное"} & set(external_groups)):
        warnings.append(CONFLICT_GROUP_MESSAGES["anti_fog_wetting"])

    if "гидрофобное" in external_groups and "олеофобное" in external_groups:
        warnings.append(CONFLICT_GROUP_MESSAGES["hydro_oleo_finish"])

    antistatic_positions = [index for index, layer in enumerate(layers) if layer.stage_group == "антистатическое"]
    if antistatic_positions:
        first_antistatic = min(antistatic_positions)
        covered_by_finish = any(is_external_only(layer) and layer.stage_group != "антистатическое" for layer in layers[first_antistatic + 1:])
        if covered_by_finish:
            warnings.append(CONFLICT_GROUP_MESSAGES["antistatic_covered"])

    warnings.extend(base_transition_warnings(layers))
    return warnings


def recommend_sequence(material, lens, selected_layers, archive_rows=None, archive_weight=0.5, temperature_threshold=0.9):
    if not selected_layers:
        raise RecommendationError("Не выбрано ни одно покрытие.")
    if len(selected_layers) > 5:
        raise RecommendationError("За один расчет допускается не более пяти покрытий.")
    if lens.h_kraya_mm <= 0 or lens.d_mm <= 0:
        raise RecommendationError("Толщина по краю и диаметр линзы должны быть положительными.")
    archive_weight = clamp(float(archive_weight), 0.0, 1.0)
    temperature_threshold = clamp(float(temperature_threshold), 0.5, 1.0)

    requested_layers = ordered_layers(selected_layers)
    global_warnings = compatibility_warnings(requested_layers)
    prior_layers = []
    steps = []
    archive_rows = archive_rows or []
    archive_models = archive_models_for_rows(archive_rows)

    for i, coating in enumerate(requested_layers, start=1):
        stage_index = len(prior_layers) + 1
        is_final = i == len(requested_layers)
        start_temp_c = lens.temperatura_bazy_c
        cooling_target_c = lens.temperatura_bazy_c

        temp_limit = effective_temperature_limit(material, coating, prior_layers, stage_index)
        _limit_value, temp_limit_source = temperature_limit_source(material, coating, prior_layers)
        features = _feature_vector(material, lens, coating, stage_index, len(requested_layers))
        temp_floor = process_temperature_floor(coating, start_temp_c)
        if temp_floor > temp_limit:
            raise RecommendationError("Для состава " + coating.name + " расчетный минимум температуры выше допустимого температурного предела материала или предыдущего слоя.")
        selected_records, good_records, _mode = similar_stage_records(archive_models.get("records", []), coating, temp_limit)
        values = predict_stage_values(
            archive_models,
            features,
            material,
            lens,
            coating,
            temp_limit,
            temp_floor,
            start_temp_c,
            selected_records,
            good_records,
            archive_weight,
            temperature_threshold,
        )
        archive_stat = archive_stage_stat(archive_models, features, coating, temp_limit)

        method = values["metod_sushki"]
        method_display = method
        if coating.requires_uv:
            method_display = "комбинированная сушка: " + method + " + УФ-отверждение"
        environment = values["sreda_sushki"]
        temp_c = values["temperatura_sush_c"]
        temp_c = clamp(temp_c, start_temp_c, temp_limit)
        program_time_min = values["vremya_programmy_min"]
        pressure_pa = values["davlenie_sush_pa"]
        air_speed = values["skorost_vozduha_ms"]
        rel_humidity = values["vlazhnost_sredy_pct"]
        residual = values["w_ost_pct"]
        max_external_delta = max(temp_c - start_temp_c, temp_c - cooling_target_c, 0.0)
        delta_t = min(max(values["delta_t_c"], 0.0), max_external_delta) if max_external_delta > 0 else 0.0
        allowed_delta_t = delta_t if delta_t > 0 else max_external_delta
        ramp_rate = estimate_ramp_rate(temp_c, start_temp_c, material, lens, allowed_delta_t)
        ramp_time = estimate_ramp_time(temp_c, start_temp_c, material, lens, allowed_delta_t)
        delta_l = estimate_delta_l_um(material, lens, delta_t)
        cooling_rate = estimate_cooling_rate(temp_c, cooling_target_c, material, lens, allowed_delta_t)
        cooling_time = estimate_cooling_time(temp_c, cooling_target_c, material, lens, allowed_delta_t)
        time_min = max(0.0, program_time_min)
        total_stage_time = time_min + ramp_time + cooling_time

        risk = round(values["risk"], 3)
        risk_low, risk_high = values.get("risk_thresholds") or archive_models.get("risk_thresholds", (0.0, 0.0))
        risk_gap = max(risk_high - risk_low, 0.08)
        risk_border = min(1.0, risk_high + risk_gap)
        if risk <= risk_high:
            status = "допустимый"
        elif risk <= risk_border:
            status = "требует контроля"
        else:
            status = "на границе допуска"
        warnings = []
        if archive_stat.get("found", 0) == 0:
            warnings.append("Архивная регрессионная модель не получила обучающих строк для данного этапа.")
        elif archive_stat.get("defect_rate", 0.0) > risk_high:
            warnings.append("В похожих архивных запусках повышен брак.")
        step = {
            "nomer_etapa": i,
            "pokrytie": coating.name,
            "pokrytie_kod": coating.kod,
            "tip_pokrytiya": coating.stage_group,
            "tip_propitki": coating.base_type,
            "tip_propitki_otobrazhenie": getattr(coating, "base_display", coating.base_type),
            "sostav": coating.composition,
            "naznachenie": coating.purpose,
            "metod_naneseniya": coating.application_method,
            "tolko_vneshniy_sloy": is_external_only(coating),
            "metod_sushki": method_display,
            "bazovyi_metod_sushki": method,
            "trebuet_uf_otverzhdenie": bool(coating.requires_uv),
            "sreda_sushki": environment,
            "temperatura_starta_c": round(start_temp_c, 1),
            "temperatura_sush_c": round(temp_c, 1),
            "vremya_vyderzhki_min": round(time_min, 1),
            "skorost_razgona_c_min": round(ramp_rate, 2),
            "vremya_razgona_min": round(ramp_time, 1),
            "temperatura_posle_ohlazhdeniya_c": round(cooling_target_c, 1),
            "skorost_ohlazhdeniya_c_min": round(cooling_rate, 2),
            "vremya_ohlazhdeniya_min": round(cooling_time, 1),
            "polnoe_vremya_etapa_min": round(total_stage_time, 1),
            "davlenie_sush_pa": round_or_none(pressure_pa, 0),
            "skorost_vozduha_ms": round_or_none(air_speed, 2),
            "vlazhnost_sredy_pct": round_or_none(rel_humidity, 1),
            "w0_pct": coating.initial_solvent_pct,
            "w_ost_pct": round(residual, 2),
            "eta_mpa_s": coating.viscosity_mpa_s,
            "sigma_mn_m": coating.surface_tension_mn_m,
            "delta_t_c": round(delta_t, 2),
            "delta_l_mkm": round(delta_l, 3),
            "temperaturnyi_predel_c": round(temp_limit, 1),
            "koeffitsient_poroga_temperatury_pct": round(temperature_threshold * 100.0, 1),
            "istochnik_temperaturnogo_predela": temp_limit_source,
            "ocenka_riska": risk,
            "status": status,
            "warnings": warnings,
            "stage_models": values["stage_models"],
            "model_stat": {
                "risk_low": round(risk_low, 3),
                "risk_high": round(risk_high, 3),
                "risk_border": round(risk_border, 3),
                "r2": values["model_r2"],
                "n": values["model_n"],
                "model_quality": archive_stat.get("model_quality", 0.0),
                "extrapolation_index": archive_stat.get("extrapolation_index", 0.0),
            },
            "profile": build_profile(
                coating,
                temp_c,
                time_min,
                ramp_rate,
                ramp_time,
                cooling_rate,
                cooling_time,
                cooling_target_c,
                total_stage_time,
                method,
                pressure_pa,
                air_speed,
                rel_humidity,
                is_final,
            ),
            "arhiv_stat": archive_stat or {"found": 0, "good": 0, "defect_rate": 0.0, "model_quality": 0.0, "extrapolation_index": 0.0},
        }
        step["model_report"] = build_stage_model_report(archive_models, features, material, lens, step)
        step.pop("stage_models", None)
        steps.append(step)
        prior_layers.append(coating)

    total_hold_time = round(sum(step["vremya_vyderzhki_min"] for step in steps), 1)
    total_time = round(sum(step["polnoe_vremya_etapa_min"] for step in steps), 1)
    max_temp = max(step["temperatura_sush_c"] for step in steps)
    overall_risk = round(max(step["ocenka_riska"] for step in steps), 3)
    all_steps_allowed = all(step["status"] == "допустимый" for step in steps)

    lens_dict = asdict(lens)
    return {
        "material": material.as_dict(),
        "linza": lens_dict,
        "vybrannye_pokrytiya": [layer.name for layer in selected_layers],
        "raschetnaya_posledovatelnost": [layer.name for layer in requested_layers],
        "steps": steps,
        "summary": {
            "kolichestvo_etapov": len(steps),
            "sum_vyderzhka_min": total_hold_time,
            "sum_polnoe_vremya_min": total_time,
            "max_temperatura_c": round(max_temp, 1),
            "obschaya_ocenka_riska": overall_risk,
            "status": "допустимо" if all_steps_allowed and not global_warnings else "требуется проверка технологом",
            "preduprezhdeniya_sovmestimosti": global_warnings,
        },
    }


def get_by_ids(items, ids):
    lookup = {item.id: item for item in items}
    result = []
    for item_id in ids:
        if item_id in lookup:
            result.append(lookup[item_id])
    return result
