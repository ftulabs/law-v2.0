"""Thai notifications and Russian resolutions/orders split into their own numbered units.

Before 2026-09-26 each reached the grader as one "(document)" or as "(passage k of N)". Texts
here are trimmed from the real instruments (pravo.gov.ru resolution No. 6 of 2023 on cross-
border transfer; FSB order No. 553; the Thai Cybersecurity Committee's threat-levels
notification; a Bank of Thailand notice kept as newline-free content_all)."""
from backend.pipeline.extraction import MAX_SNIPPET, extract_provisions
from backend.schemas import DiscoveredDoc, DocFormat, Economy, OCRMetrics


def _labels(economy, text):
    doc = DiscoveredDoc(doc_id="x", economy=economy, title="t", source_url="https://x",
                        portal="x", fmt=DocFormat.HTML)
    return [(p.article_section, p.verbatim_snippet) for p in
            extract_provisions(doc, text, OCRMetrics())]


RU_RESOLUTION = (
    "ПРАВИТЕЛЬСТВО РОССИЙСКОЙ ФЕДЕРАЦИИ\nПОСТАНОВЛЕНИЕ\nот 10 января 2023 г. № 6\n"
    "В соответствии с частью 13 статьи 12 Федерального закона\nПравительство Российской "
    "Федерации постановляет:\n"
    "1.\xa0Утвердить прилагаемые Правила принятия решения о запрещении трансграничной передачи.\n"
    "2.\xa0Настоящее постановление вступает в силу с 1 марта 2023 г.\n"
    "УТВЕРЖДЕНЫ\nпостановлением Правительства\nПРАВИЛА\nпринятия решения\n"
    "1.\xa0Настоящие Правила определяют порядок принятия решения о запрещении передачи.\n"
    "2.\xa0Решение принимается Федеральной службой по надзору в сфере связи.\n"
    "3.\xa0Представления направляются федеральными органами исполнительной власти.\n"
    "4.\xa0Для принятия решения уполномоченным органом направляется представление.\n")


def test_russian_resolution_points_and_annex_rules_are_labelled_by_scope():
    labels = [a for a, _ in _labels(Economy.RU, RU_RESOLUTION)]
    assert labels == ["Пункт 1", "Пункт 2", "Правила, пункт 1", "Правила, пункт 2",
                      "Правила, пункт 3", "Правила, пункт 4"]


def test_russian_point_snippet_keeps_its_own_number():
    snips = dict(_labels(Economy.RU, RU_RESOLUTION))
    assert snips["Правила, пункт 2"].startswith("2.")


def test_russian_numbered_annex_heading_with_no_break_space():
    text = ("ПРИКАЗЫВАЮ:\n1. Утвердить Порядок (приложение № 1).\n2. Признать утратившим силу "
            "приказ.\n3. Настоящий приказ вступает в силу.\nПриложение №\xa01\nк приказу ФСБ "
            "России\nПорядок\n1. Установка средств осуществляется субъектом КИИ.\n2. Субъект "
            "КИИ должен обеспечить.\n3. ФСБ России в течение 45 дней рассматривает.\n")
    labels = [a for a, _ in _labels(Economy.RU, text)]
    assert labels[3:] == ["Приложение № 1, пункт 1", "Приложение № 1, пункт 2",
                          "Приложение № 1, пункт 3"]


def test_an_unrecognised_restart_opens_a_new_scope_rather_than_continuing_the_count():
    body = " оператором персональных данных в информационной системе в установленном порядке.\n"
    text = ("".join(f"{n}. Утвердить положение номер {n}{body}" for n in range(1, 5))
            + "Состав сведений\n"
            + "".join(f"{n}. Сведения категории {n}{body}" for n in range(1, 4)))
    labels = [a for a, _ in _labels(Economy.RU, text)]
    assert "Пункт 5" not in labels and labels[4:] == [
        "Приложение, пункт 1", "Приложение, пункт 2", "Приложение, пункт 3"]


def test_russian_statja_snippet_no_longer_opens_on_a_dot():
    text = "\n".join(f"Статья {n}. Заголовок {n}\n1. Оператор обязан соблюдать правило {n}."
                     for n in range(1, 5))
    assert all(not s.startswith(".") for _, s in _labels(Economy.RU, text))


TH_NOTICE = (
    "ประกาศคณะกรรมการการรักษาความมั่นคงปลอดภัยไซเบอร์แห่งชาติ\n"
    "อาศัยอำนาจตามความในมาตรา ๖๐ วรรคสอง แห่งพระราชบัญญัติการรักษาความมั่นคงปลอดภัยไซเบอร์\n"
    "ข้อ ๑ ประกาศนี้เรียกว่า ประกาศคณะกรรมการ ว่าด้วยลักษณะภัยคุกคาม\n"
    "ข้อ ๒ ประกาศนี้ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศ\n"
    "ข้อมูลที่เกี่ยวข้องให้เป็นไปตามแนบท้าย\n"
    "ข้อ ๓ ให้หน่วยงานจำแนกภัยคุกคามทางไซเบอร์ตามระดับ\n"
    "ข้อ ๔ ให้ประธานกรรมการรักษาการตามประกาศนี้\n"
    "ภาคผนวก\nท้ายประกาศคณะกรรมการ\n"
    "ข้อ ๑ การจำแนกหมวดหมู่ของภัยคุกคามทางไซเบอร์\n"
    "ข้อ ๒ ตัวอย่างลักษณะภัยคุกคามทางไซเบอร์แยกตามระดับ\n")


def test_thai_notification_clauses_and_annex():
    labels = [a for a, _ in _labels(Economy.TH, TH_NOTICE)]
    assert labels == ["ข้อ ๑", "ข้อ ๒", "ข้อ ๓", "ข้อ ๔", "ภาคผนวก, ข้อ ๑", "ภาคผนวก, ข้อ ๒"]


def test_thai_data_word_is_not_a_clause_marker():
    assert not any("ข้อมูล" == a[:6] for a, _ in _labels(Economy.TH, TH_NOTICE))


def test_thai_newline_free_notice_splits_on_its_inline_sequence():
    text = ("1. เหตุผลในการออกประกาศ สถาบันการเงินใช้บริการด้านงานเทคโนโลยีสารสนเทศ พ.ศ. 2551 "
            "อัตรา 1.5 ต่อปี 2. อำนาจตามกฎหมาย อาศัยอำนาจตามความในมาตรา 47 "
            "3. ขอบเขตการบังคับใช้ ให้ใช้บังคับกับสถาบันการเงินทุกแห่ง 4. เนื้อหา 4.1 ในประกาศนี้")
    assert [a for a, _ in _labels(Economy.TH, text)] == ["ข้อ 1", "ข้อ 2", "ข้อ 3", "ข้อ 4"]


def test_a_provision_longer_than_the_snippet_cap_is_kept_whole_in_parts():
    long_body = "\n\n".join("ให้หน่วยงานแจ้งเหตุภัยคุกคามทางไซเบอร์ต่อสำนักงานภายในเวลาที่กำหนด " * 40
                            for _ in range(12))
    text = f"ข้อ ๑ ประกาศนี้เรียกว่า ก\nข้อ ๒ ใช้บังคับ ข\nข้อ ๓ {long_body}\n"
    got = _labels(Economy.TH, text)
    parts = [(a, s) for a, s in got if a.startswith("ข้อ ๓")]
    assert len(parts) >= 2 and parts[0][0].endswith(f"(part 1 of {len(parts)})")
    assert all(len(s) <= MAX_SNIPPET for _, s in parts)
    assert sum(len(s) for _, s in parts) >= len(long_body) * 0.99
