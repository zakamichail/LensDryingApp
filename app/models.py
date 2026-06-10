from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True)
    kod = Column(String(40), unique=True, nullable=False)
    name = Column(String(80), unique=True, nullable=False)
    group = Column(String(32), nullable=False)
    lambda_w_mk = Column(Float, nullable=False)
    density_kg_m3 = Column(Float, nullable=False)
    heat_capacity_j_kgk = Column(Float, nullable=False)
    expansion_1_k = Column(Float, nullable=False)
    tg_c = Column(Float, nullable=True)
    t_max_c = Column(Float, nullable=False)
    moisture_absorption_pct = Column(Float, default=0.0)
    heat_sensitivity = Column(Float, default=0.5)

    @property
    def form_value(self):
        return self.kod

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


class Impregnation(Base):
    __tablename__ = "impregnations"

    id = Column(Integer, primary_key=True)
    kod = Column(String(40), unique=True, nullable=False)
    name = Column(String(120), unique=True, nullable=False)
    base_type = Column(String(40), nullable=False)
    composition = Column(String(320), nullable=False)
    purpose = Column(String(220), nullable=False)
    stage_group = Column(String(80), nullable=False)
    is_final_layer = Column(Boolean, default=False)
    external_only = Column(Boolean, default=False)
    application_method = Column(String(120), nullable=False)
    viscosity_mpa_s = Column(Float, nullable=False)
    surface_tension_mn_m = Column(Float, nullable=False)
    evaporation_rate = Column(Float, nullable=False)
    thermal_stability_c = Column(Float, nullable=False)
    target_layer_thickness_um = Column(Float, nullable=False)
    initial_solvent_pct = Column(Float, nullable=False)
    overheat_sensitivity = Column(Float, default=0.3)
    requires_uv = Column(Boolean, default=False)

    @property
    def base_display(self):
        if self.base_type != "комбинированная":
            return self.base_type
        text = (self.composition or "").lower()
        parts = []
        if "вод" in text:
            parts.append("водная")
        if "спирт" in text or "этанол" in text or "изопропанол" in text or "ipa" in text or "гликол" in text or "органическ" in text:
            parts.append("спиртовая")
        if "акрил" in text or "уретан" in text or "полимер" in text or "смол" in text:
            parts.append("полимерная")
        if "фтор" in text or "pfpe" in text or "фторполимер" in text:
            parts.append("фторсодержащая")
        if not parts:
            parts.append("несколько технологических основ")
        return "комбинированная (" + ", ".join(dict.fromkeys(parts)) + ")"

    def as_dict(self):
        return {
            "kod": self.kod,
            "name": self.name,
            "base_type": self.base_type,
            "base_display": self.base_display,
            "composition": self.composition,
            "purpose": self.purpose,
            "stage_group": self.stage_group,
            "is_final_layer": self.is_final_layer,
            "external_only": self.external_only,
            "application_method": self.application_method,
            "viscosity_mpa_s": self.viscosity_mpa_s,
            "surface_tension_mn_m": self.surface_tension_mn_m,
            "evaporation_rate": self.evaporation_rate,
            "thermal_stability_c": self.thermal_stability_c,
            "target_layer_thickness_um": self.target_layer_thickness_um,
            "initial_solvent_pct": self.initial_solvent_pct,
            "overheat_sensitivity": self.overheat_sensitivity,
            "requires_uv": self.requires_uv,
        }


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    employee_name = Column(String(140), nullable=False)
    role = Column(String(32), nullable=False, default="technologist")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User")
    username = Column(String(80), nullable=True)
    action = Column(String(80), nullable=False)
    entity = Column(String(80), nullable=False)
    details = Column(Text, nullable=True)


class ProcessRun(Base):
    __tablename__ = "process_runs"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    batch_code = Column(String(80), default="")
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    material = relationship("Material")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User")
    lens_payload = Column(JSON, nullable=False)
    selected_layers = Column(JSON, nullable=False)
    calculated_sequence = Column(JSON, nullable=False)
    recommendation = Column(JSON, nullable=False)
    quality_status = Column(String(80), default="recommended")
    comment = Column(Text, nullable=True)
