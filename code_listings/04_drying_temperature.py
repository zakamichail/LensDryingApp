class RecommendationError(ValueError):
    pass


def clamp(value, low, high):
    if low > high:
        raise RecommendationError("Некорректные расчетные границы")
    return max(low, min(high, value))


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


def target_drying_temperature(temp_limit, temp_floor, start_temp_c, temperature_threshold):
    # Tсуш = Kпор * min(Tmax материала, Tg материала, Tmax выбранных слоев).
    target = temperature_threshold * temp_limit
    return clamp(max(target, temp_floor, start_temp_c), start_temp_c, temp_limit)
