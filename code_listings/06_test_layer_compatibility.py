from app.archive import load_archive_rows
from app.config import settings
from app.database import SessionLocal, init_db
from app.engine import LensInput, recommend_sequence
from app.models import Impregnation, Material
from app.seed import seed_reference_data


def test_external_only_conflict_is_reported():
    init_db()
    seed_reference_data()
    session = SessionLocal()
    try:
        material = session.query(Material).filter(Material.kod == "MITSUI_MR8").one()
        anti_fog = session.query(Impregnation).filter(Impregnation.stage_group == "антизапотевающее").first()
        hydro = session.query(Impregnation).filter(Impregnation.stage_group == "гидрофобное").first()
        lens = LensInput(h_kraya_mm=2.0, d_mm=62, r1_mm=120, r2_mm=-120)
        archive_rows = load_archive_rows(settings.archive_csv_path)
        result = recommend_sequence(material, lens, [anti_fog, hydro], archive_rows=archive_rows)
        warnings = result["summary"]["preduprezhdeniya_sovmestimosti"]
        assert warnings
        assert result["summary"]["status"] == "требуется проверка технологом"
        assert any("Пропитки несовместимы" in warning for warning in warnings)
        assert any("Переход основы требует проверки" in warning or "Неблагоприятное перекрытие" in warning for warning in warnings)
        assert result["steps"][0]["tolko_vneshniy_sloy"] is True
    finally:
        session.close()
