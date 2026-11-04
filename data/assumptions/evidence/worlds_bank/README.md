# worlds_bank — банковская надстройка миров (A-M3, MODEL §3.1, прил. B)

`build_overlay.py` собирает `data/assumptions/worlds_bank.json` из листа надстройки этапа 1
(`inputs/bank_overlay_draft.yaml` — копия листа, имена локальных папок заменены относительными путями; `--sync` обновляет
копию из `$BANK_HANDOFF_DIR`, `--check` — сверка). Хэш файла вписывает в книгу `build_assumptions.py`
(`worlds.overlay.sha256`); ядро сверяет файл с этим хэшем.

Рост сектора у банков семейства один, поэтому файл обязан совпасть с надстройкой банков версии миров бит в бит
(хэш — `overlay_sha256` в `data/assumptions/worlds_state.json`) — скрипт предупреждает, если это не так. Лист этапа 1 несёт готовые пути по мирам; скрипт их не
пересчитывает, а проверяет: мир N — середины диапазонов базового сценария «Основных направлений денежно-кредитной
политики» (документ и страница — поле `source` и текст `recipe` файла `worlds_bank.json` версии) и прогноза Банка России по балансам («Банковский
сектор. II кв. 2026», PDF-с. 20) для «прочей розницы» 2026–2027 годов; 2028–2029 — (население − w·ИЖК)/(1 − w),
w = 0,5806; миры H и M — реальный рост базы при инфляции своего мира (g_W = (1 + g_N)(1 + π_W)/(1 + π_N) − 1);
средства физлиц и бизнеса — денежная масса М2; годы 2026–2029, дальше ядро сводит рост к g_T мира к `volumes.lt_from`
(2033).

| Мир | Кредиты бизнесу 2026 / 27 / 28 / 29 | Ипотека | Прочая розница | Средства (М2) |
|---|---|---|---|---|
| N | <!--~bank:worlds.N.credit_growth.corporate.2026 p1-->10,5<!--~--> / <!--~bank:worlds.N.credit_growth.corporate.2027 p1-->8,5<!--~--> / <!--~bank:worlds.N.credit_growth.corporate.2028 p1-->10,5<!--~--> / <!--~bank:worlds.N.credit_growth.corporate.2029 p1-->10,5<!--~--> % | <!--~bank:worlds.N.credit_growth.mortgage.2026 p1-->7,5<!--~--> / <!--~bank:worlds.N.credit_growth.mortgage.2027 p1-->7,5<!--~--> / <!--~bank:worlds.N.credit_growth.mortgage.2028 p1-->12,5<!--~--> / <!--~bank:worlds.N.credit_growth.mortgage.2029 p1-->12,5<!--~--> | <!--~bank:worlds.N.credit_growth.retail_other.2026 p1-->6,0<!--~--> / <!--~bank:worlds.N.credit_growth.retail_other.2027 p1-->5,5<!--~--> / <!--~bank:worlds.N.credit_growth.retail_other.2028 p1-->7,7<!--~--> / <!--~bank:worlds.N.credit_growth.retail_other.2029 p1-->7,7<!--~--> | <!--~bank:worlds.N.funds_growth.retail.2026 p1-->11,5<!--~--> / <!--~bank:worlds.N.funds_growth.retail.2027 p1-->7,5<!--~--> / <!--~bank:worlds.N.funds_growth.retail.2028 p1-->9,5<!--~--> / <!--~bank:worlds.N.funds_growth.retail.2029 p1-->9,5<!--~--> |
| H | <!--~bank:worlds.H.credit_growth.corporate.2026 p1-->10,5<!--~--> / <!--~bank:worlds.H.credit_growth.corporate.2027 p1-->10,2<!--~--> / <!--~bank:worlds.H.credit_growth.corporate.2028 p1-->13,4<!--~--> / <!--~bank:worlds.H.credit_growth.corporate.2029 p1-->13,2<!--~--> | <!--~bank:worlds.H.credit_growth.mortgage.2026 p1-->7,5<!--~--> / <!--~bank:worlds.H.credit_growth.mortgage.2027 p1-->9,2<!--~--> / <!--~bank:worlds.H.credit_growth.mortgage.2028 p1-->15,4<!--~--> / <!--~bank:worlds.H.credit_growth.mortgage.2029 p1-->15,3<!--~--> | <!--~bank:worlds.H.credit_growth.retail_other.2026 p1-->6,0<!--~--> / <!--~bank:worlds.H.credit_growth.retail_other.2027 p1-->7,2<!--~--> / <!--~bank:worlds.H.credit_growth.retail_other.2028 p1-->10,5<!--~--> / <!--~bank:worlds.H.credit_growth.retail_other.2029 p1-->10,4<!--~--> | <!--~bank:worlds.H.funds_growth.retail.2026 p1-->11,5<!--~--> / <!--~bank:worlds.H.funds_growth.retail.2027 p1-->9,2<!--~--> / <!--~bank:worlds.H.funds_growth.retail.2028 p1-->12,3<!--~--> / <!--~bank:worlds.H.funds_growth.retail.2029 p1-->12,2<!--~--> |
| M | <!--~bank:worlds.M.credit_growth.corporate.2026 p1-->10,5<!--~--> / <!--~bank:worlds.M.credit_growth.corporate.2027 p1-->8,5<!--~--> / <!--~bank:worlds.M.credit_growth.corporate.2028 p1-->13,7<!--~--> / <!--~bank:worlds.M.credit_growth.corporate.2029 p1-->16,9<!--~--> | <!--~bank:worlds.M.credit_growth.mortgage.2026 p1-->7,5<!--~--> / <!--~bank:worlds.M.credit_growth.mortgage.2027 p1-->7,5<!--~--> / <!--~bank:worlds.M.credit_growth.mortgage.2028 p1-->15,8<!--~--> / <!--~bank:worlds.M.credit_growth.mortgage.2029 p1-->19,0<!--~--> | <!--~bank:worlds.M.credit_growth.retail_other.2026 p1-->6,0<!--~--> / <!--~bank:worlds.M.credit_growth.retail_other.2027 p1-->5,5<!--~--> / <!--~bank:worlds.M.credit_growth.retail_other.2028 p1-->10,9<!--~--> / <!--~bank:worlds.M.credit_growth.retail_other.2029 p1-->14,0<!--~--> | <!--~bank:worlds.M.funds_growth.retail.2026 p1-->11,5<!--~--> / <!--~bank:worlds.M.funds_growth.retail.2027 p1-->7,5<!--~--> / <!--~bank:worlds.M.funds_growth.retail.2028 p1-->12,7<!--~--> / <!--~bank:worlds.M.funds_growth.retail.2029 p1-->15,9<!--~--> |

Премии роста банка к сектору в надстройку не входят — это ключи книги (`volumes.loan_share_drift`, `funds_share_drift`;
текст книги, A-G1 и A-G2). Блоки истории премий листа надстройки (`t_premium`, `funds`) — общие для банков семейства
поля листа; числа премий Совкомбанка — лист калибровки ЧПД этапа 1 (`calib-nii`, `volumes.py`). Ряд сектора «прочая
розница» — необеспеченные потребительские кредиты без автокредитов; у Совкомбанка автокредиты — своя книга (`auto`),
она растёт с сектором «прочая розница».
