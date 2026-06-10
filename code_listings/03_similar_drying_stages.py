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
