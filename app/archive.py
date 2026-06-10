import csv
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median


TIP_PROPITKI_KOD = {
    "водная": 1,
    "спиртовая": 2,
    "полимерная": 3,
    "фторсодержащая": 4,
    "комбинированная": 5,
}
TIP_PROPITKI_NAME = {value: key for key, value in TIP_PROPITKI_KOD.items()}

TIP_POKRYTIYA_KOD = {
    "упрочняющее": 1,
    "антибликовое": 2,
    "антистатическое": 3,
    "гидрофобное": 4,
    "олеофобное": 5,
    "антизапотевающее": 6,
    "фотохромное": 7,
}
TIP_POKRYTIYA_NAME = {value: key for key, value in TIP_POKRYTIYA_KOD.items()}

GRUPPA_MATERIALA_KOD = {
    "стекло": 1,
    "кварц": 2,
    "полимер": 3,
}
GRUPPA_MATERIALA_NAME = {value: key for key, value in GRUPPA_MATERIALA_KOD.items()}

SREDA_KOD = {
    "сушильный шкаф": 1,
    "вакуумная камера": 2,
    "ИК-модуль": 3,
}
SREDA_NAME = {value: key for key, value in SREDA_KOD.items()}

METOD_NANESENIYA_KOD = {
    "распыление": 1,
    "погружение": 2,
    "центрифугирование": 3,
}


@dataclass
class ArchiveMaterial:
    kod: str
    name: str
    group: str
    lambda_w_mk: float
    density_kg_m3: float
    heat_capacity_j_kgk: float
    expansion_1_k: float
    tg_c: float
    t_max_c: float
    moisture_absorption_pct: float = 0.0
    heat_sensitivity: float = 0.5
    id: int | None = None

    @property
    def form_value(self):
        return f"archive:{self.kod}"

    def as_dict(self):
        return {
            "kod": self.kod,
            "name": self.name,
            "group": self.group,
            "lambda_w_mk": self.lambda_w_mk,
            "density_kg_m3": self.density_kg_m3,
            "heat_capacity_j_kgk": self.heat_capacity_j_kgk,
            "expansion_1_k": self.expansion_1_k,
            "tg_c": self.tg_c,
            "t_max_c": self.t_max_c,
            "moisture_absorption_pct": self.moisture_absorption_pct,
            "heat_sensitivity": self.heat_sensitivity,
        }


def parse_float_ru(value, default=None):
    if value is None or str(value).strip() == "":
        return default
    return float(str(value).strip().replace(" ", "").replace(",", "."))


def parse_int(value, default=0):
    if value is None or str(value).strip() == "":
        return default
    return int(float(str(value).strip().replace(",", ".")))


def _first(row, keys, default=None):
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return default


def _stage_field(row, n, names, default=None):
    prefixes = [f"e{n}_", f"e{n} "]
    candidates = []
    for prefix in prefixes:
        for name in names:
            candidates.append(prefix + name)
    return _first(row, candidates, default)


def calc_center_thickness_safe(h_kraya_mm, d_mm, r1_mm, r2_mm):
    try:
        radius_aperture = d_mm / 2.0
        if h_kraya_mm <= 0 or d_mm <= 0:
            return None
        if abs(r1_mm) <= radius_aperture or abs(r2_mm) <= radius_aperture:
            return None

        def sag(r):
            sign = 1.0 if r >= 0 else -1.0
            return r - sign * math.sqrt(r * r - radius_aperture * radius_aperture)

        center = h_kraya_mm + sag(r1_mm) - sag(r2_mm)
        if center <= 0:
            return None
        return round(center, 3)
    except (TypeError, ValueError):
        return None


def load_archive_rows(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for raw in reader:
            row = dict(raw)
            row["godnaya_partiya"] = parse_int(_first(row, ["godnaya_partiya", "годная партия"], 0), 0)
            row["kol_etapov"] = parse_int(_first(row, ["kol_etapov", "kol etapov", "кол этапов"], 0), 0)
            row["gruppa_materiala_kod"] = parse_int(_first(row, ["gruppa_materiala_kod", "gruppa materiala kod"], 0), 0)
            row["gruppa_materiala"] = GRUPPA_MATERIALA_NAME.get(row["gruppa_materiala_kod"], row.get("gruppa_materiala", "материал"))
            row["material_kod"] = _first(row, ["material_kod", "material kod", "код материала"], "")
            numeric_aliases = {
                "lambda": ["lambda", "λ"],
                "plotnost": ["plotnost", "rho", "ρ"],
                "teploemkost": ["teploemkost", "c"],
                "alfa": ["alfa", "alpha", "α"],
                "Tg": ["Tg", "tg"],
                "Tmax": ["Tmax", "tmax"],
            }
            for key, aliases in numeric_aliases.items():
                row[key] = parse_float_ru(_first(row, aliases), 0.0)
            row["h_kraya_mm"] = parse_float_ru(_first(row, ["h kraya mm", "h_kraya_mm", "h_mm"], 0.0), 0.0)
            row["d_mm"] = parse_float_ru(_first(row, ["d mm", "d_mm"], 0.0), 0.0)
            row["r1_mm"] = parse_float_ru(_first(row, ["R1 mm", "r1_mm", "R1"], 0.0), 0.0)
            row["r2_mm"] = parse_float_ru(_first(row, ["R2 mm", "r2_mm", "R2"], 0.0), 0.0)
            row["h_centr_mm"] = calc_center_thickness_safe(row["h_kraya_mm"], row["d_mm"], row["r1_mm"], row["r2_mm"])
            if row["h_centr_mm"] is None:
                continue
            for n in range(1, 6):
                pref = f"e{n}_"
                coating_kod = _stage_field(row, n, ["pokrytie_kod", "pokrytie kod"], "")
                if not coating_kod:
                    continue
                row[pref + "pokrytie_kod"] = coating_kod
                row[pref + "sostav_kod"] = _stage_field(row, n, ["sostav_kod", "sostav kod"], coating_kod)
                int_fields = {
                    "tip_pokrytiya_kod": ["tip_pokrytiya_kod", "tip pokrytiya kod"],
                    "tip_propitki_kod": ["tip_propitki_kod", "tip propitki kod"],
                    "metod_naneseniya_kod": ["metod_naneseniya_kod", "metod naneseniya kod"],
                    "sreda_kod": ["sreda_kod", "sreda kod"],
                    "defekt_kod": ["defekt_kod", "defekt kod"],
                }
                for key, aliases in int_fields.items():
                    row[pref + key] = parse_int(_stage_field(row, n, aliases), 0)
                float_fields = {
                    "eta": ["eta", "η"],
                    "sigma": ["sigma", "σ"],
                    "W0": ["W0", "W 0"],
                    "t_sush": ["t суш"],
                    "tau_sush": ["tau суш"],
                    "p_sush_pa": ["p суш Па"],
                    "v_sush": ["v суш"],
                    "fi_sush": ["fi суш"],
                    "w_ost": ["W ост"],
                    "delta_t": ["delta T"],
                    "delta_l": ["delta L"],
                }
                for key, aliases in float_fields.items():
                    row[pref + key] = parse_float_ru(_stage_field(row, n, aliases), None)
            rows.append(row)
    return rows


def count_archive_rows(path: Path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        return sum(1 for _ in reader)


def archive_materials(path: Path, exclude_codes=None):
    exclude_codes = set(exclude_codes or [])
    rows = load_archive_rows(path)
    grouped = {}
    for row in rows:
        kod = row.get("material_kod")
        if not kod or kod in exclude_codes:
            continue
        grouped.setdefault(kod, []).append(row)
    materials = []
    for kod, items in grouped.items():
        def med(field):
            values = [x[field] for x in items if x.get(field) is not None]
            return float(median(values)) if values else 0.0
        group_values = [x.get("gruppa_materiala") for x in items if x.get("gruppa_materiala")]
        group = max(set(group_values), key=group_values.count) if group_values else "материал"
        materials.append(ArchiveMaterial(
            kod=kod,
            name=kod + " из архива",
            group=group,
            lambda_w_mk=med("lambda"),
            density_kg_m3=med("plotnost"),
            heat_capacity_j_kgk=med("teploemkost"),
            expansion_1_k=med("alfa"),
            tg_c=med("Tg"),
            t_max_c=med("Tmax"),
            heat_sensitivity=0.0,
        ))
    return sorted(materials, key=lambda item: item.kod)


def get_archive_material(path: Path, kod: str):
    for material in archive_materials(path):
        if material.kod == kod:
            return material
    return None
