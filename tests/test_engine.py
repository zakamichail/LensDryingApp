from app.archive import load_archive_rows
from app.config import settings
from app.engine import LensInput, recommend_sequence
from app.seed import seed_reference_data
from app.database import SessionLocal, init_db
from app.models import Impregnation, Material


def test_recommendation_uses_archive_and_applies_method_fields():
    init_db()
    seed_reference_data()
    session = SessionLocal()
    try:
        material = session.query(Material).filter(Material.kod == "MITSUI_MR8").one()
        hard = session.query(Impregnation).filter(Impregnation.kod == "TEST_HARD_01").one()
        ar = session.query(Impregnation).filter(Impregnation.kod == "TEST_AR_01").one()
        final = session.query(Impregnation).filter(Impregnation.kod == "TEST_OLEO_01").one()
        lens = LensInput(h_kraya_mm=2.0, d_mm=62, r1_mm=120, r2_mm=-120)
        archive_rows = load_archive_rows(settings.archive_csv_path)
        result = recommend_sequence(material, lens, [final, hard, ar], archive_rows=archive_rows)
        assert result["linza"]["h_centr_mm"] > result["linza"]["h_kraya_mm"]
        assert result["steps"][0]["arhiv_stat"]["found"] > 0
        assert "comparison_mode" in result["steps"][1]["arhiv_stat"]
        assert result["summary"]["kolichestvo_etapov"] == 3
        assert result["summary"]["sum_polnoe_vremya_min"] > result["summary"]["sum_vyderzhka_min"]
        assert any(step["trebuet_uf_otverzhdenie"] for step in result["steps"])
        for step in result["steps"]:
            assert step["vremya_razgona_min"] >= 0
            assert step["skorost_razgona_c_min"] > 0
            if step["temperatura_sush_c"] > step["temperatura_starta_c"]:
                assert step["vremya_razgona_min"] > 0
            assert step["vremya_ohlazhdeniya_min"] >= 0
            assert step["skorost_ohlazhdeniya_c_min"] > 0
            assert step["polnoe_vremya_etapa_min"] >= step["vremya_vyderzhki_min"]
            assert step["temperatura_starta_c"] == 22.0
            assert step["temperatura_posle_ohlazhdeniya_c"] == 22.0
            assert step["model_stat"]["n"] > 0
            assert step["model_stat"]["r2"]
            assert step["model_report"]["models"]
            assert step["model_report"]["calculation_graphs"]
            assert "tolshina_sloya_mkm" not in step
            drying_items = [item for item in step["profile"] if item["operation"] == "Сушка"]
            ramp_items = [item for item in step["profile"] if item["operation"] == "Нагрев"]
            cooling_items = [item for item in step["profile"] if item["operation"] in {"Отпуск перед следующим этапом", "Финальное охлаждение"}]
            assert drying_items
            assert ramp_items
            assert cooling_items
            assert drying_items[0]["description"].startswith("Выполнить: ")
            assert "Ориентировочное время нагрева" in ramp_items[0]["description"]
            assert "скоростью не выше" in cooling_items[0]["description"]
            assert "Толщина слоя" not in step["profile"][0]["description"]
            if step["trebuet_uf_otverzhdenie"]:
                assert step["metod_sushki"].startswith("комбинированная сушка")
                assert any(item["operation"] == "УФ-отверждение" for item in step["profile"])
                assert all("основной доли растворителя" not in item["description"] for item in step["profile"])
            method = step["bazovyi_metod_sushki"]
            if method == "вакуумная сушка":
                assert step["davlenie_sush_pa"] is not None
                assert step["skorost_vozduha_ms"] is None
            if method == "конвективная сушка":
                assert step["davlenie_sush_pa"] is None
                assert step["skorost_vozduha_ms"] is not None
            if method == "инфракрасная сушка":
                assert step["davlenie_sush_pa"] is None
                assert step["skorost_vozduha_ms"] is None
    finally:
        session.close()


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
