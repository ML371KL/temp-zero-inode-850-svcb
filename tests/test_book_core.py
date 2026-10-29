# -*- coding: utf-8 -*-
"""Книга против ядра: суждения книги, которые проверяются только прогоном ядра (поток book; MODEL §4.3–§4.13, §12). Книга —
Совкомбанка (0.1); тесты книги Т 1.0 переписаны на её форму в медленном круге (Д16).

* Модальная клетка книги — мир H × «мягкая посадка» × «средняя группа»: на ней выводятся ближний путь маржи и
  уровни года якоря (метка `tact`, без ядра: свойство вероятностей книги).
* Числа, выведенные на ядре, делают то, что говорит их правило: ключ маржи — стационарная маржа мира уровня на составе
  баланса якоря; инструменты капитала — путь книги без новых выпусков, их доля в RWA не растёт; ближний сдвиг ЧПМ
  кончается без ступени, первый прогнозный квартал печатает путь записи вывода; услуги года якоря — в диапазоне факта;
  средства клиентов года якоря растут темпом сектора; C/I после фазы роста слоя «рыночные ставки как есть» — в коридоре
  цели, модальная клетка печатает меньше. Если тесты КРАСНЫЕ на готовом ядре —
  запустить `data/assumptions/evidence/path/derive_on_engine.py` и перенести его строки в шаблон. Равенство «кредиты равны
  средствам клиентов» — проверка, а не правило: отношение печатает запись вывода.
* Цепочка отчётов «без новостей» не вымывает хвостовые режимы ниже пола (приёмочный тест решения ведущего № 2, §8 п. 4).
Пока ядро не исполняет ветви второй формы банка (схема называет их словом «не реализовано»), тесты с прогоном
пропускаются с названной причиной. Книга и факты — те, что читает ядро (`data/assumptions/assumptions.yaml`, `data/facts/`).
"""
from __future__ import annotations

import pytest

try:
    from tests import support_book as S
except ImportError:                      # прогон без pytest.ini (pythonpath = .) и без tests/__init__.py
    import support_book as S

NEAR_FREE_PERIOD = "2030Q1"              # первый квартал без ближнего сдвига ЧПМ


@pytest.fixture(scope="module")
def book() -> dict:
    return S.built_book()


@pytest.fixture(scope="module")
def modal(book):
    """(контекст прогона, модальная клетка) ядра на книге и фактах дерева; пропуск, пока ядро не готово."""
    from model import book_schema

    pending = getattr(book_schema, "pending", None)
    left = pending(book) if pending else []
    if left:
        pytest.skip(f"ядро ещё не исполняет ветви книги второй формы банка ({len(left)}): {left[0]}")
    from model.book import load_book, load_facts
    from model.cell import run_cell
    from model.grid import make_context, modal_cell

    facts = load_facts()
    core_book = load_book(facts=facts)
    ctx = make_context(core_book, facts)
    return ctx, run_cell(ctx, *modal_cell(core_book, ctx.posterior))


@pytest.mark.tact
def test_the_modal_cell_of_the_book(book):
    """Модальная клетка (INTERFACES §4.6): мир с наибольшим весом слоя «свой взгляд», режим с наибольшей вероятностью,
    сценарий капитала с наибольшей вероятностью при этом режиме — без равенств, от порядка книги не зависит. У книги
    Совкомбанка — H × «мягкая посадка» × «средняя группа» (Р12-6: мягкая посадка 0,3188 против нормализации 0,3187)."""
    j = book["joint"]
    world = max(j["world_prob"], key=j["world_prob"].get)
    regime = max(j["regime_prob"], key=j["regime_prob"].get)
    scenario = max(j["reg_prob_given_regime"][regime], key=j["reg_prob_given_regime"][regime].get)
    assert (world, regime, scenario) == ("H", "soft", "mid")
    for table in (j["world_prob"], j["regime_prob"], j["reg_prob_given_regime"][regime]):
        top = sorted(table.values())[-2:]
        assert top[1] > top[0]
    assert world == book["nii"]["transmission"]["reference_world"]            # мир отсчёта спредов — тот же


def test_the_key_of_the_margin_is_the_stationary_margin_of_the_window_world(modal, book):
    """Ключ цели ЧПМ — само суждение (решение ведущего № 8, п. A1): стационарная маржа мира уровня на составе баланса
    якоря равна ключу, гейта стационарной маржи у книги нет; уровень мира-опоры передачи решатель находит сам, и он
    другой; маржа, которую печатает модальная клетка после фазы роста, — результат: кредит вытесняет ликвидные
    активы, и она выше суждения."""
    from model.grid import year_mgmt
    from model.levels import level_nim, stationary_nim

    ctx, cell = modal
    key = book["nii"]["nim_lt_target_mgmt"]
    node = level_nim(ctx)
    assert stationary_nim(ctx) is None and "nim_stationary" not in book["checks"]
    assert node["world"] == book["nii"]["transmission"]["level_world"] and node["value"] == pytest.approx(key, abs=1e-9), node
    assert node["reference_world"] == book["nii"]["transmission"]["reference_world"]
    assert node["reference_value"] != pytest.approx(key, abs=1e-4)
    values = [year_mgmt(ctx, "nim", y, cell.annual["nim"][i], lambda name, q: cell.quarters[name][q])
              for i, y in enumerate(cell.years) if y >= book["checks"]["window_backtest"]["from_year"]]
    assert sum(values) / len(values) > key


def test_the_funds_of_the_anchor_year_grow_with_the_sector(modal, book):
    """Средства клиентов года якоря (книга Совкомбанка): премия кварталов года якоря к сектору — 0 (оттока по последнему
    месячному релизу, как у книги Т, нет), средства физлиц модальной клетки в обоих прогнозных кварталах года якоря растут
    ровно темпом сектора мира с премией своего квартала."""
    ctx, cell = modal
    tl = ctx.timeline
    year = tl.anchor_year
    retail = [float(cell.quarters["funds_retail"][q]) for q in (0, 1, 2)]
    sector = float(ctx.worlds[cell.world].funds_growth["retail"][year])
    premium = book["volumes"]["funds_share_drift"]["retail"]
    assert premium[tl.period(1)] == premium[tl.period(2)] == 0.0 and str(year) not in premium
    for q in (1, 2):
        assert retail[q] / retail[q - 1] == pytest.approx(((1 + sector) * (1 + premium[tl.period(q)])) ** 0.25, rel=1e-12), q


def test_the_capital_instruments_are_the_path_of_the_book(modal, book):
    """Инструменты капитала книги Совкомбанка — путь книги без новых выпусков (добавочный и дополнительный капитал без
    прибыли, признание субординированных займов в последние пять лет линейно): ядро читает путь книги по кварталам,
    доля инструментов в RWA модальной клетки не растёт; стоимости прироста инструментов в «прочем», как у книги Т,
    нет — запись вывода её не несёт."""
    import json

    ctx, cell = modal
    tl, t2 = ctx.timeline, book["capital"]["n20"]["t2"]
    record = json.loads((S.EVIDENCE / "path" / "out" / "derive_out.json").read_text(encoding="utf-8"))
    assert "cost" not in record
    last_year = book["meta"]["last_period"][:4]
    quarters = [q for q in range(0, tl.Q + 1) if tl.period(q)[:4] != last_year]
    assert all(float(ctx.prep.t2[q]) == pytest.approx(t2[tl.period(q)], abs=1e-12) for q in quarters)
    share = [float(ctx.prep.t2[q]) / float(cell.quarters["rwa"][q]) for q in quarters]
    assert max(share[1:]) <= share[0], f"доля инструментов в RWA выше якоря: {max(share[1:]):.4f} > {share[0]:.4f}"


def test_fees_of_the_anchor_year_follow_the_fact(modal):
    """Услуги года якоря (книга Совкомбанка, Р12-1а: уровень года якоря целиком — 1П факт, 2П по правилу «середина»):
    рост услуг г/г в прогнозных кварталах года якоря — внутри диапазона факта кварталов года якоря (1К2026 +28,4 %,
    2К2026 −6,5 %), без ускорения сверх факта."""
    ctx, cell = modal
    tl, hist = ctx.timeline, ctx.prep.hist["fees"]
    facts = [float(hist[q]) / float(hist[q - 4]) - 1 for q in tl.quarters_of_year(tl.anchor_year) if q <= 0]
    growth = [float(cell.quarters["fees"][q]) / float(hist[q - 4]) - 1 for q in tl.quarters_of_year(tl.anchor_year) if q >= 1]
    assert len(facts) == 2 and len(growth) == 2
    assert all(min(facts) <= g <= max(facts) for g in growth), ([round(100 * g, 1) for g in growth], [round(100 * f, 1) for f in facts])




def test_the_near_path_of_the_anchor_year_is_the_path_of_the_book(modal):
    """Ближний путь маржи года якоря: упр. ЧПМ модальной клетки в первом прогнозном квартале — та, что записал вывод
    (`frozen_check.near_q3_modal_cell`, 7,465 %), и запись сошлась к цели ближнего пути листа (`near_q3` = `near_target`
    в точности записи)."""
    import json

    ctx, cell = modal
    check = json.loads((S.EVIDENCE / "path" / "out" / "derive_out.json").read_text(encoding="utf-8"))["frozen_check"]
    nim = ctx.bridge.to_mgmt_nim(float(cell.quarters["nim"][1]))
    assert nim == pytest.approx(check["near_q3_modal_cell"], abs=1e-6), round(100 * nim, 4)
    assert check["near_q3"] == pytest.approx(check["near_target"], abs=1e-6)


def test_the_near_nim_shift_ends_without_a_step(modal):
    """Ближний сдвиг ЧПМ подводит путь к марже, которую клетка печатает без сдвига: на стыке с первым свободным
    кварталом ступени нет (шаг не больше 0,15 п.п. — как между соседними кварталами ближнего пути)."""
    ctx, cell = modal
    q = ctx.timeline.index(NEAR_FREE_PERIOD)
    nim = [ctx.bridge.to_mgmt_nim(float(cell.quarters["nim"][k])) for k in (q - 1, q)]
    assert abs(nim[1] - nim[0]) <= 0.0015, f"ступень ЧПМ на стыке с {NEAR_FREE_PERIOD}: {100 * (nim[1] - nim[0]):+.2f} п.п."


def test_cost_to_income_after_the_growth_phase_is_on_target(modal, book):
    """Корни реального роста расходов выведены под цель C/I после фазы роста в ожидании слоя «рыночные ставки как
    есть» (решение ведущего № 7, п. A2): число гейта долгосрочного C/I — в коридоре цели; модальная клетка мира H
    печатает меньше цели — это результат."""
    from model.book import load_book, load_facts
    from model.grid import run_grid
    from model.levels import cir_lt_value
    from model.live import live_from_book

    facts = load_facts()
    b = load_book(facts=facts)
    node = cir_lt_value(run_grid(b, facts, live_from_book(b, facts)))
    gate = book["checks"]["cir_lt"]
    assert node["scope"] == gate["scope"] == "market_layer"
    assert abs(node["value"] - gate["target"]) <= gate["tolerance"], f"C/I упр. слоя: {100 * node['value']:.2f} %"
    assert node["modal"] < node["value"]


def test_the_no_news_chain_stops_at_the_floor(modal, book):
    """Приёмочный тест книги (решение ведущего № 2, §8 п. 4): цепочка восьми отчётов «факт = ожидание» не опускает
    вероятность ни одного режима ниже пола — доли `floor_share` базовой вероятности; сумма вероятностей — единица."""
    from model.book import load_book, load_facts
    from model.grid import run_grid
    from model.live import live_from_book
    from model.nextreport import model_expectation, open_period, with_observation

    facts = load_facts()
    b = load_book(facts=facts)
    live = live_from_book(b, facts)
    share, prior = book["joint"]["regime_update"]["floor_share"], book["joint"]["regime_prob"]
    for _ in range(8):
        period = open_period(b, facts)
        e = model_expectation(b, facts, period, live=live, run=run_grid(b, facts, live))
        b = with_observation(b, period, cor=e["cor_q_mgmt"], nim=e["nim_q_mgmt"])
        post = dict(run_grid(b, facts, live).ctx.posterior)
        assert abs(sum(post.values()) - 1) < 1e-9
        assert all(post[r] >= share * prior[r] - 1e-12 for r in prior), post
