# Факты эмитента: схема узлов

Каталог `data/facts/` — факты ПАО «Совкомбанк» (тикер SVCB) на якоре: 16 файлов JSON. Все пишет сборщик
`ops/tools/build_facts.py` из листов этапа 1 (`$BANK_HANDOFF_DIR`; якорь — аргумент `--anchor`; в CI не запускается —
файлы закоммичены; §3): одиннадцать файлов ядра, срезы календаря и аналогов, три узла калибровки книги
(`credit_products`, `perimeter`, `misc_window`). Происхождение каждого числа словами — `docs/FACTS.md`; что из
фактов читает ядро — методика, приложение B. Узлы второй формы банка, которых у Совкомбанка нет (блок пакета вне
контура, нормативы группы), сохраняют имена слотов и названы ниже как форма книги второй формы; отличия формы
Совкомбанка — §3 и тесты `tests/test_facts_*.py`.

## 1. Общие правила

* **Узел.** Каждое число — узел `{"v": число, "src": …}` или `{"v": число, "calc": …}`; у узла может быть и то и
  другое. `src` — документ и место в нём: страница («с. 6») либо адрес «Лист!Ячейка» справочника аналитика
  эмитента, затем `sha256` и первые 16 знаков хэша файла. Полный хэш, путь в папке передачи, адрес и заголовок
  документа — в реестре `anchor.json → documents` (у ручных файлов — в их `sources`). `calc` — формула из узлов
  или слова о способе.
* **Квартал-разность.** Строка отчётности за квартал, которого документ отдельно не печатает (1-й квартал — из отчёта
  за полугодие, 4-й — из годового), — разность нарастающих итогов. Такой узел несёт и `src`, и `calc`: страница из
  `src` печатает уменьшаемое и вычитаемое, `calc` называет их периоды, редакцию отчёта и сами числа — «разность
  нарастающих итогов 6М2026 − 2К2026 (редакция отчёта за 6М2026): 97,6 − 53,1»; у суммы строк — «каждое слагаемое —
  разность нарастающих итогов …».
* **Нераскрытое** — `{"v": null, "calc": причина}`. Ноль пишется только там, где он раскрыт или следует из
  устройства отчётности (тогда причина — в `calc`).
* **Единицы.** Деньги — млрд ₽; акции — млн шт.; ставки, доли и нормативы — доли единицы (1 п.п. = 0,01); дивиденд на
  акцию — ₽. Всё «на акцию» — после дроблений и консолидаций, если они были (у Совкомбанка после IPO их не было:
  `split_factor` = 1); исходное значение решения — рядом (`dps_pre_split`, `split_factor`).
* **Знаки ОПУ** — как в отчётности: расходы, резервы, налог — со знаком минус. Проценты пассивных книг и взносы на
  страхование вкладов в `nii_books.json` и `dia` — величиной.
* **Базис** — поле `basis` файла: `IFRS`, `mgmt`, `mgmt↔IFRS`, `RAS→IFRS`, `mixed`. В смешанном файле
  (`capital.json`) базис есть у каждого блока и у каждого узла верхнего уровня и истории. Базисы не смешиваются:
  число банковской группы по форме Банка России не складывается с числом МСФО без моста, названного в `calc`.
* **Прибыль** (подробно — `docs/FACTS.md` §2): у Совкомбанка прибыль движка — отчётная прибыль акционеров по МСФО
  (`pnl_quarterly → ni_shareholders`, `profit_basis: "reported"`; по годам — `dividends → years`); управленческие
  значения документов — `mgmt_quarterly → op_np_exact`. У книги второй формы с пакетом вне контура прибыль движка —
  операционная, и `pnl_quarterly → reported` от неё отличается блоком пакета.
* **Оценочный узел** несёт `"estimated": true`: значение названо до выхода документа (у Совкомбанка — стоимость
  риска 2К2026: резерв по кредитам за квартал не раскрыт; нормативы банка до выхода формы 0409135). Замена оценки
  фактом — правка фактов без смены якоря.
* **Голые числа** вне узлов допустимы только в полях `year` и `split_factor`. Даты — строки ISO.
* Подписи, которые печатает витрина (`calendar → title`, `note`; `guidance → text`, `scope_note`, `event`, `note`;
  `dividends → policy.name`, `text`, `valid_until_note`, `label`; `shares → corporate_actions[].title`; `peers →
  basis`, `name`), написаны словами, даты — с годом.

## 2. Файлы

### 2.1. `anchor.json` (IFRS)

`as_of`, `period` — дата и квартал якоря; `note`; `documents[]` — реестр `{key, file, sha256, url, title}`: все
документы, на которые ссылаются `src` одиннадцати файлов сборщика. `file` — путь от корня папки передачи; сами
документы в репозиторий не кладутся.

### 2.2. `balance.json` (IFRS, на дату якоря)

| Узел | Что это |
|---|---|
| `books.<книга>` — 13 узлов | остатки книг: `auto`, `mortgage`, `cash_loans`, `cards`, `corp_loans` (с МСБ и лизингом), `securities`, `liquidity`, `retail_current`, `retail_term`, `corp_term`, `corp_current`, `wholesale`, `insurance_liab` (обязательства по операциям страхования, МСФО 17); состав — в `calc` |
| `loans_fvtpl`, `lease_gross` | справочно: кредиты по справедливой стоимости и лизинг внутри `corp_loans` |
| `allowance_ac` | резерв по кредитам и лизингу, величиной |
| `securities.{fvoci_debt, fvoci_repo, ac, ac_repo, fvtpl_bonds}` | состав книги долговых бумаг (ядро: доли бумаг через прочий совокупный доход и облигаций через прибыль) |
| `securities.{equity_fvtpl, equity_fvoci, equity_other, derivatives, floating_share_fvtpl}` | справочно: вне книги, в прочих активах |
| `liquidity.{cash, mandatory_reserves, due_from_banks}`; `liquidity.reverse_repo` | состав книги ликвидности; обратное репо — `null` с причиной (внутри двух строк) |
| `funds.{retail_current, retail_term, corp_business, sme}`; `funds.retail_brokerage` | состав книг средств клиентов; брокерские счета физлиц — справочно (в прочих обязательствах) |
| `wholesale.{banks, other_borrowed, nonfin_debt, perpetual_sub}` | состав книги оптового фондирования |
| `other_assets`, `other_liabilities` | остатком до итогов баланса; по строкам отчёта — `other_assets_parts`, `other_liabilities_parts` |
| `other_assets_fixed`, `other_assets_fixed_parts.{yandex_stake, associates}` | постоянные прочие активы (не растут с кредитами) |
| `total_assets`, `total_liabilities` | итоги отчёта о финансовом положении |
| `dividends_payable` | дивиденды к выплате: строка годового отчёта, а на промежуточную дату — расчёт по движению с начала года |
| `dividends_payable_declared[]` | `{period, amount}` — объявленные до якоря и не выплаченные к нему дивиденды закрытых кварталов прибыли; пустой список — таких нет |
| `equity.{total, at1, nci, bv_common}` и компоненты | капитал; `at1` — ноль с причиной (бессрочные займы — обязательство) |
| `prev_year_end.{as_of, loans_corporate, loans_retail}` | кредитные книги на конец прошлого года по сегменту стоимости риска |
| `iea` | процентные активы движка: кредитные книги + долговые бумаги + ликвидность |
| `history.<период>` | концы кварталов: `date`, `bv_common`, `loans`, `loans_ac_gross` (= `loans`), `loans_fvtpl` (справочно), `funds`, `iea`, `total_assets` |

### 2.3. `nii_books.json` (IFRS; квартал якоря)

`period`, `days`, `rates_carry_residual: false`; `books.<книга>.{balance_open, balance_close, balance_avg,
interest_q, rate_anchor}`, `rate_anchor = interest_q / balance_avg × 365 / days`; `interest_assets_q`,
`interest_liabilities_q`; `other_interest_net_q` — проценты вне книг; `dia_q`; `nii_q`; `iea_avg`, `nim_eng_q`;
`current_share_anchor`; `key_avg_anchor_q`.

### 2.4. `pnl_quarterly.json` (IFRS; `profit_basis: "reported"`; `quarters.<период>`)

Строки движка на базисе отчётной прибыли: `nii` (ЧПД движка — с финансовыми расходами страхования), `fees_net`
(с резервом по гарантиям), `insurance_net` (без финансовых расходов МСФО 17), `llp_debt_fa`, `opex` — строки отчёта;
`misc_net`, `noncore_net` (выгодные покупки; состав — `noncore_parts`), `pbt`, `tax`, `ni`, `ni_nci` — расчётные;
`ni_shareholders` — отчётная прибыль акционеров. Справочно: `dia`, `nii_form` и `ins_finance_expense` (ЧПД формы и
финансовые расходы страхования), `insurance_net_form`, `guarantee_provisions`, `at1_coupon` (купон бессрочных — через
капитал), `key_avg`, `fee_income`, `fee_expense`, `oci_fvoci`, `oci_total`, `ci_total`, `ci_shareholders`,
`fv_loans_credit` и `fvtpl_bond_reval` (`null`). Узел `investment_block` ниже — форма книги второй формы; у
Совкомбанка его нет.
`reported.{pbt, tax, ni, ni_shareholders, ni_nci}` — строки отчётности. У кварталов-разностей (§1) формула — в `calc`:
`reported.*`, `llp_debt_fa`, `opex`, `dia`, `fee_income`, `fee_expense`, `oci_fvoci`, `ci_shareholders`,
`investment_block.{reval, nonfin_interest}`.
`investment_block.{reval, dividends, debt_interest, pbt, tax, ni, nci, ni_shareholders, nonfin_interest,
adj_stake_sh, adj_interest_sh}` — исключённое из строк движка (пакет вне контура книги второй формы): `reported.x = x +
investment_block.x` (для `ni_nci` — `investment_block.nci`); `noncore_net = −investment_block.debt_interest`.

### 2.5. `capital.json` (mixed)

`n20_0.{value, as_of, estimated, pre_dividend, pre_dividend_note, min_with_buffers}` — у Совкомбанка Н1.0 банка (форма
0409135; у книги второй формы — Н20.0 банковской группы); `n1_1_bank.{value, as_of, estimated}` — Н1.2 банка (имя
слота историческое); `n1_0_bank`, `n1_1_bank_h11`, `n1_2_bank`, `n27_bank`, `n20_2` — справочно;
`bank_base_capital`, `bank_own_funds`, `bank_main_capital`, `bank_additional_capital` — капитал банка (форма 0409123);
`group_capital.{total, base, additional, supplementary}` — `null` с причиной: форма 0409805 группы не раскрывается;
`basel.{cet1, rwa, cet1_ratio, total_ratio}` — слоты ядра: капитал группы без регуляторных инструментов и вменённые
активы, взвешенные по риску; `t2_recognized` — регуляторные инструменты группы; `at1.{amount, coupon_annual,
coupon_quarter}` — нули с причиной; `fvoci_reserve`; `ofz_curve_anchor.{1, 3, 5, 10}`; `basel_ifrs.*` — Базель III
по МСФО (справочно); `instruments[]`, `instruments_total` — бессрочные субординированные займы; `history[]` —
нормативы и капитал группы по концам кварталов; `core_form_check` — сверка сборщика: нормативы якоря формой ядра
на ключах листа калибровки капитала (ядро блок не читает). При оценке до выхода формы у слотов — `estimated: true`
и блок `estimate.{bank_value, spread, spread_as_of}`.

### 2.6. `shares.json` (IFRS; млн шт. после дробления)

`issued_total`, `issued_ordinary`, `treasury_ordinary`, `outstanding_total`, `outstanding_ordinary`;
`depositary_block` — акции без голосов и выплат (в делитель входят); `economic_treasury` — ноль с причиной;
`voting`, `motivation_program`, `par_value`; `by_ticker`; `corporate_actions[]` — `{date, kind, title, src}`, у
дробления — `factor` и `first_trade_date`, у выпуска — `shares_before`, `shares_after`.

### 2.7. `dividends.json` (IFRS)

`policy.{name, doc, doc_title, sha256, approved, approved_by, frequency, cap, threshold, valid_until,
valid_until_note, text, src}` — `cap` 0,30; `threshold` и `valid_until` — `null` с причиной; `doc_title` — название
документа политики словами: его, а не имя файла `doc`, выпуск несёт в `dividends.policy.doc`. `history[]` — одна строка на решение собрания:
`year`, `period` (квартал прибыли), `label`, `dps`, `dps_pre_split`, `split_factor`, `recommended_date`,
`decided_date`, `decided_by`, `record_date`, `last_buy_date`, `ex_date`, `pay_date`, `pay_deadline_others`,
`settlement`, `pool_declared`, `sources[]` (строки «вид: …», виды `manual` и `news`, у каждого решения оба).
`pay_date` — срок выплаты номинальным держателям по решению собрания (10 рабочих дней после реестра),
`pay_deadline_others` — срок прочим лицам реестра (25 рабочих дней); источник обоих — рекомендация совета директоров
или протокол собрания. День фактической выплаты в фактах не хранится: колонка «Дата выплаты» файла эмитента «История
дивидендных выплат» — другая величина (`docs/FACTS.md` §4.6).
`years.<год>.{ni_shareholders, complete, through}` — отчётная прибыль акционеров для проверки потолка политики.
`register_seed[]` — решения с экс-датой позже якоря: поля записи реестра и `status`. `dates_rule`,
`broker_check` — словами; `snapshot` — день снимка листа решений.

### 2.8. `guidance.json` (mgmt)

`year`, `as_of`; `items.{op_np_growth, dps_growth, roe_target}` — узлы с `kind`, `text`, `date`, `event`, `scope`,
у точки — `tol`, у пункта с оговоркой — `scope_note`; `items.{roe, nim, cor_max, cir}` — `null` с причиной;
`history[]` — `{date, key, value, event, note}`.

### 2.9. `mgmt_quarterly.json` (mgmt)

`quarters.<период>`: напечатанное в документах квартала — без суффикса, точное значение справочника аналитика — с
суффиксом `_exact`: `nim`, `cor`, `cir`, `roe`, `op_np`, `op_equity`, `roe_shareholders`, `roe_reported`,
`cost_of_funding`, `clients_total`, `clients_active`; только точное — `cor_cards`, `cor_cash`, `cor_auto`,
`cor_mortgage`, `cor_sme`, `cor_corp`, `cor_lease`; только напечатанное — `asset_yield`.
`annual.<год>.{nim, cor, cir, roe}`.
`history_gaps[] = {period, basis, reason}` — частичные провалы раскрытия отчётной истории выпуска: `period` — квартал
или диапазон `ГГГГQn–ГГГГQn`, `basis` — `mgmt` (у квартала напечатана только часть метрик `nim`, `cor`, `cir`, `roe`)
или `ifrs` (до первого конца квартала истории баланса не считаются капитал, ROE и стоимость риска по МСФО; до первой
формы с нормативами группы нет Н20.0), `reason` — словами для экрана: какая метрика пуста и почему. Список пишет
сборщик из пустых узлов кварталов и из первых кварталов истории баланса и капитала; квартал, у которого базис пуст
целиком, называет сама сборка выпуска.

### 2.10. `bridge_mgmt_ifrs.json` (mgmt↔IFRS)

`window`, `direction`; для `cor`, `nim`, `cir` — `method: "additive"`, `window`, `value`, `sd`, `n`, `definition`,
`history[] = {period, mgmt, engine, gap}`; `to_engine(v) = v + value`. У `nim` в истории ещё `engine_x4`, `gap_x4`
(без ряби счёта дней; по ним `value`). У `cor` знаменатель моста — параметр сборщика: сумма кредитных книг (знаменатель
движка; на нём мост и калибруется) либо кредиты по амортизированной стоимости с лизингом без кредитов по справедливой
стоимости (определение листа калибровки, справочно); история несёт оба варианта
(`engine`, `gap` — выбранный; `engine_books`, `gap_books` — на сумме книг, знаменателе движка), значения обоих — узлы
`value_ac_only` и `value_books`.

### 2.11. `bridge_ras_ifrs.json` (RAS→IFRS)

`quarters[] = {period, ras_ni, ifrs_ni_sh, ratio, src}` — справочный ряд; `by_quarter.{1…4}` — `null` с причиной
(моста прибыли нет). `nii.{definition, method: "prev_quarter", window, quarters[], value, n, sd, by_quarter}` — мост
ЧПД по форме 0409102. `iea` — определение процентных активов по форме 0409101 (`codes`, `codes_required`); `value` —
`null`. `cor` — `null` с причиной.

### 2.12. `calendar.json` (вручную)

`as_of`, `horizon`, `note`, `sources[]`, `events[] = {id, kind, date, title, covers, confirmed, precision, src}` и
необязательные `estimated`, `earliest`, `latest`, `in_book`, `note`. Виды: `ifrs`, `databook`,
`dividend_decision`, `record`, `form805`, `ops_release`, `cbr_rate`, `cbr_forecast`, `call_option`, `deal`,
`regulation`. Событие с `estimated: true` несёт `confirmed: false`, `precision: "window"`, `earliest`, `latest`.

### 2.13. `peers.json` (вручную)

`as_of`, `basis`, `subject_ticker`, `note`, `sources[]`, `banks[] = {ticker, name, basis, bv_date, ni_ltm_period,
bv, bv_prev, ni_ltm, roe_ltm, shares_outstanding, shares_issued, dps_ltm, capital_ratio {name, value, as_of},
src}`. Строки эмитента в файле нет: её собирает выпуск из фактов. `src` строки банка уходит в выпуск (источник
строки таблицы аналогов, без хвостов sha256), поэтому в нём название документа словами, страница и `sha256` с первыми
16 знаками хэша по каждому документу — без имени файла; без хвостов строка не длиннее 120 знаков. У узлов внутри
строки `src` — как у прочих фактов.

### 2.14. `misc_window.json` (IFRS; узел калибровки)

Ряд «прочего» книги (решения ведущего Совкомбанка № 7, Р7-1): `quarters.<период>` 2023К1–2026К2 — `sec` (бумаги и
валюта), `fvr` (переоценка облигаций ССПУ в полную дюрацию, середина прочтений ОФЗ 1 и 3 лет), `other_core` (прочее без
разовых и резерва по гарантиям), `deflator` (к ценам якоря) и их произведения `*_real`, `fvtpl` (строка ССПУ квартала —
решения № 8, Р8-2); `slope.R`, `slope.y2023_2026` — оценки наклона прохождения переоценки в отчётную строку (МНК с
константой): с круга 8 — регрессия СТРОКИ ССПУ (`fvtpl`) на `fvr` (Р8-2); прежние оценки на всей строке «бумаги и валюта»
(круг 7) — `slope_sec_line`, справочно. Пишут листы `svcb-850-handoff/stage1/round7/r7_1_misc_slope.py` (ряд) и
`svcb-850-handoff/stage1/round8/r8_book.py` (пункт misc: `fvtpl` и `slope`); сборщик собирает узел из этих листов на своём
якоре; читают правила класса 6 (`class_checks.yaml`) формулой; ядро файл не читает.

### 2.15. `credit_products.json` (МСФО и справочник банка; узел калибровки)

Стоимость риска по пяти кредитным книгам (решения ведущего Совкомбанка № 3, Р3 и Р11): `quarters.<период>` 4К2018 —
квартал якоря (`gross_end`, `charge`, `cor_books`, `total`, `on_anchor`, `intensity`; квартал якоря — МСФО за период
минус справочник прошлого квартала), `years_ifrs`, `windows_ifrs` (лист Б7), `intensity.<окно>` (справочник, МСФО,
середина), `m7_readings`, `anchor_weights` (доли книг якоря). Собирает сборщик из справочника банка (лист COR) и листов
кругов 2–3 на своём якоре; на другом якоре переносит как есть. Читают правила класса 6; ядро не читает.

### 2.16. `perimeter.json` (IFRS; узел калибровки)

Ряд поправок периметра окна R к периметру якоря (решения ведущего № 4, Р4-3; № 5, Р5-2): `entities`, `events`,
`groups` (связки: концы и центр — середина концов), `rows[]` (строка ОПУ, лицо, квартал, `centre` — узел, `low`,
`high`), `aux`. Сборщик считает ряд правилом листа круга 5 (`stage1/round5/perimeter_series.py`) и сверяет с листом
строка в строку; на другом якоре переносит как есть. Читает лист вывода книги; ядро не читает.

## 3. Якорь и параметры сборщика

`BANK_HANDOFF_DIR=<папка передачи> python -B ops/tools/build_facts.py [--check] [--anchor <период>] [--out <каталог>]
[--report <файл>]`; `--plan` — перечень недостающих строк листов для якоря `--anchor` и шаги дня отчёта; `--forms
<перепись> [<вторая>]` — тождества переписи форм-сканов ОПУ и ОФП и сверка двух переписей; `--expected <файл отчёта>
--out <каталог> [--facts <каталог>]` — сухой прогон перезаякоривания (§4). Сборщик пишет все 16 файлов: календарь и
аналоги — из листов `calendar.csv` и `peers.csv`, узлы калибровки — на своём якоре. Из якоря выводятся: дата, конец
прошлого квартала и года, нарастающий итог (`6M2026`), ряд кварталов ОПУ с `PNL_FIRST`, документ отчёта
(`2026Q2_ifrs_fs.pdf`, у четвёртого квартала — `FY…`), дата форм банка (первое число после квартала), окна истории
капитала.

Таблицы состава: книги (`LOANS`, `ASSET_BOOKS`, `LIAB_BOOKS` — 13 книг; состав остатка — лист книг, проценты —
`INTEREST_LINES`, вне книг — `INTEREST_OUTSIDE`), строки ОПУ движка (`PNL_SLOTS`, `PNL_SUM`; состав слота — лист
`pnl_composition.csv`), прочие активы (`OTHER_ASSETS`, `OTHER_ASSETS_FIXED`), строки капитала (`EQUITY_LINES`),
политика (`POLICY`). Числа якоря, которых в листах нет, — `SHEET_GAPS` (с документом и страницей; сборщик сначала ищет
строку `balance_anchor.csv` с тем же именем), `ALLOWANCE_BOOKS`, `GUARANTEES` (страница — по текстовому слою отчёта);
слова якоря с числами вне листов — `ANCHOR_WORDS` (на другом якоре — общие слова).

| Параметр | Значение | Что это |
|---|---|---|
| `PNL_FIRST` | 2023Q1 | первый квартал ОПУ (МСФО 17 и нынешний учёт ССПУ) |
| `BRIDGE_HISTORY_FIRST` | 2024Q1 | первый квартал истории мостов упр. ↔ движок |
| `CAPITAL_HISTORY_FIRST` | 2025Q1 | первый квартал истории нормативов банка |
| `HORIZON_YEARS` | 10 | `last_period` — четвёртый квартал года якоря + 10 |
| `SNAPSHOT` | 21.10.2026 / 20.10.2026 | срез листов этапа 1 и дата оценки книги |
| `CP_ANCHOR`, `PERIM_ANCHOR`, `MISC_ANCHOR` | 2026Q2 | якорь узлов калибровки книги |

## 4. Файл отчёта квартала (`quarter-report/1`)

`--report <файл>` пишет вход `ops/tools/reanchor.py --facts`: `balance.{books (13), loans_fvtpl, fvoci, fvtpl_bonds,
allowance, other_assets, other_assets_fixed, other_liabilities, dividends_payable, dividends_payable_year (при остатке
к выплате), dividends_payable_declared[], bv_common, fvoci_reserve, at1, nci}`; `interest.<книга>` (у книги
`insurance_liab` — финансовые расходы страхования); `dia`; `pnl` — строки движка отчётного базиса; `capital.{n20_0
(Н1.0 банка), n20_pre_dividend, n1_1_bank (Н1.2 банка), basel_cet1, basel_rwa, bank_base_capital, t2, estimated}`;
`market.{ofz_curve, key_avg}`; `mgmt.{nim, cor, cir}` — расчёт по определению банка (`_exact`); `shares`;
`dividend_decisions[]` — решения, принятые в квартале якоря.

`--expected <файл>` строит из фактов якоря и отчёта следующего квартала факты нового якоря — в `--out`, не в
`data/facts`: узлы якоря — числа отчёта (`src` — файл отчёта и sha256), строки внутри книг — долями прежнего якоря,
ставки книг активов несут остаток ЧПД (`rates_carry_residual: true`), окна мостов продлены кварталом, решения
отчёта — строками истории дивидендов, справочное, чего модель не ведёт, — `null` с причиной; календарь, аналоги и узлы
калибровки переносятся без изменений.

## 5. Тождества (тесты фактов)

1. `Σ books активов − allowance_ac + other_assets = total_assets`; `Σ books пассивов + other_liabilities +
   dividends_payable + equity.total = total_assets`; `0 ≤ other_assets_fixed ≤ other_assets`;
   `other_assets_fixed = Σ other_assets_fixed_parts`; `Σ dividends_payable_declared ≤ dividends_payable`.
2. `prev_year_end.loans_corporate + loans_retail = history.<конец прошлого года>.loans`.
3. `Σ процентов активных книг − Σ пассивных − dia_q + other_interest_net_q = nii_q`.
4. `pbt = nii + llp_debt_fa + fees_net + insurance_net + noncore_net + opex + misc_net`; `ni = pbt + tax`;
   `ni_shareholders = ni − ni_nci`; `reported = строки движка + investment_block`; `|debt_interest| ≤
   nonfin_interest`.
5. Прибыль движка квартала якоря, сумма за последний полный год и за год якоря нарастающим итогом равны
   прибыли акционеров эмитента (у Совкомбанка — отчётной; у книги второй формы — операционной).
6. Нормативы якоря формой ядра на ключах листа капитала равны нормативам формы (у Совкомбанка — 0409135 банка; у
   книги второй формы — 0409805 группы; `core_form_check`).
7. Дивиденды: `dps × split_factor = dps_pre_split`; `pool_declared = dps × issued_total`; дата реестра — через
   10–20 дней после решения; у записи стартового реестра есть строка истории с тем же периодом.
8. Мосты: `value` — среднее `gap` (у ЧПМ — `gap_x4`) по своему окну; `engine` и `engine_books` воспроизводятся из
   `pnl_quarterly` и `balance.history`.
