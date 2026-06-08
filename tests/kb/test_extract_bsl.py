from pathlib import Path

from packages.kb.indexer.extract_bsl import extract_bsl_procedures

SAMPLE = """#Область СлужебныеПроцедурыИФункции

Процедура ТестоваяПроцедура(Параметр) Экспорт
    // комментарий
    А = 1;
КонецПроцедуры

Функция ВычислитьСумму(А, Б)
    Возврат А + Б;
КонецФункции

#КонецОбласти
"""


def test_extract_procedures(tmp_path: Path):
    path = tmp_path / "Module.bsl"
    path.write_text(SAMPLE, encoding="utf-8")
    procedures = extract_bsl_procedures(str(path))
    assert len(procedures) == 2
    assert procedures[0].name == "ТестоваяПроцедура"
    assert procedures[0].is_export is True
    assert procedures[0].region == "СлужебныеПроцедурыИФункции"
    assert procedures[1].name == "ВычислитьСумму"
    assert procedures[1].is_export is False
