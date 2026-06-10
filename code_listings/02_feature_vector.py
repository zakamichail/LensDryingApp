MODEL_BASE_TYPES = ["водная", "спиртовая", "полимерная", "фторсодержащая", "комбинированная"]
MODEL_STAGE_GROUPS = ["упрочняющее", "антибликовое", "антистатическое", "гидрофобное", "олеофобное", "антизапотевающее", "фотохромное"]

TIP_PROPITKI_KOD = {
    "водная": 1,
    "спиртовая": 2,
    "полимерная": 3,
    "фторсодержащая": 4,
    "комбинированная": 5,
}

TIP_POKRYTIYA_KOD = {
    "упрочняющее": 1,
    "антибликовое": 2,
    "антистатическое": 3,
    "гидрофобное": 4,
    "олеофобное": 5,
    "антизапотевающее": 6,
    "фотохромное": 7,
}


class RecommendationError(ValueError):
    pass


def _one_hot(value, values):
    return [1.0 if value == item else 0.0 for item in values[:-1]]


def thermal_diffusivity_m2_s(material):
    # a_t = lambda / (rho * c), м2/с: температуропроводность материала.
    denominator = material.density_kg_m3 * material.heat_capacity_j_kgk
    if material.lambda_w_mk <= 0 or denominator <= 0:
        raise RecommendationError("Некорректные теплофизические свойства материала.")
    return material.lambda_w_mk / denominator


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
