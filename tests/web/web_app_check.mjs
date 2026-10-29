// Поведение витрины web/app.js без браузера: скрипт грузится в node:vm с заглушкой DOM
// (tests/web/dom_stub.mjs). Выпуск — две формы генератора tests/web/make_sample.py: общая форма
// tests/web/payload-generic.json (разделы 1–9) и форма панели tests/fixtures/payload-sample.json
// (раздел 10); для частных случаев — их копии с правками. Запускает tests/test_web_node.py; печатает
// JSON с итогами, код выхода 1 — если хоть одна проверка не прошла.
import { SAMPLE_TEXT, GENERIC_TEXT, SCREEN_NAMES, makePage as page0, visibleText, countTag, findNode, squash } from "./dom_stub.mjs";

// Разделы 1–9 — общий каркас на общей форме выпуска (две категории акций, годовая выплата, релиз РСБУ);
// раздел 10 — форма панели: карточки по узлам, слова общей формы не печатаются; раздел 11 — узлы волны № 6.
const sample = () => JSON.parse(GENERIC_TEXT);
const panel = () => JSON.parse(SAMPLE_TEXT);
const makePage = (opts = {}) => page0({ payload: GENERIC_TEXT, ...opts });
const [MAIN, SECOND] = sample().meta.company.tickers;

const checks = [];
const check = (name, cond, detail) => checks.push({ name, ok: !!cond, detail: cond ? undefined : detail });

const rejections = [];
process.on("unhandledRejection", (reason) => rejections.push(String((reason && reason.stack) || reason)));
const settle = () => new Promise((resolve) => setTimeout(resolve, 20));
const BAD_TEXT = /NaN|undefined|\[object Object\]|Infinity/;
// Часы страницы — день после публикации фикстуры: выпуск свежий.
const FRESH = Date.parse("2026-10-01T09:00:00+03:00");

// Подсказки узлов графика — WeakMap самой витрины.
const tipsOf = (page, root, tag) => {
  const out = [];
  const walk = (n) => {
    if (!n || n.nodeType !== 1) return;
    if (n.tagName === tag) { page.ctx.__n = n; const t = page.get("TIPS.get(globalThis.__n)"); if (t) out.push(t); }
    n.children.forEach(walk);
  };
  walk(root);
  return out;
};
const cardOf = (page, title) => findNode(page.app, (n) => n.tagName === "SECTION" && n.children.some((c) => squash(visibleText(c)).startsWith(title)));

/* ── 1. адрес: битый, старый или чужой хэш ── */

{
  const page = makePage();
  const cases = [["#overview", "overview"], ["#book", "book"], ["#%62ook", "book"], ["", "overview"], ["#nope", "overview"], ["#capital", "capital"],
    ["#debt", "capital"], ["#money", "capital"], ["#value", "overview"], ["#priced", "market"],
    ["#overview?utm_source=tg", "overview"], ["#%E0%A4%A", "overview"], ["#%", "overview"], ["#100%", "overview"], ["#%FF", "overview"]];
  for (const [hash, want] of cases) {
    page.url.hash = hash;
    let got, error = null;
    try { got = page.get("screenFromHash()"); } catch (e) { error = String(e); }
    check(`screenFromHash ${JSON.stringify(hash)} → ${want}`, !error && got === want, error || got);
  }
}

for (const [hash, want] of [["#%E0%A4%A", "overview"], ["#debt", "capital"], ["#money", "capital"], ["#value", "overview"]]) {
  const page = makePage({ href: `https://example.pages.dev/${hash}`, now: FRESH });
  const before = rejections.length;
  await page.boot();
  await settle();
  check(`старт с ${hash}: экран ${want}, адрес #${want}`, page.get("CURRENT") === want && page.url.hash === `#${want}`, [page.get("CURRENT"), page.url.hash]);
  check(`старт с ${hash}: без исключений`, !page.bootError && rejections.length === before && !page.errors.length, [page.bootError, page.errors.slice(0, 2)]);
}

{
  const page = makePage({ href: "https://example.pages.dev/#book", now: FRESH });
  await page.boot();
  await settle();
  let error = null;
  try { page.hashchange("#%E0%A4%A"); } catch (e) { error = String(e); }
  check("битый хэш после загрузки: «Оценка», адрес #overview, без исключения", !error && page.get("CURRENT") === "overview" && page.url.hash === "#overview", [error, page.url.hash]);
  page.hashchange("#debt");
  check("старый адрес #debt после загрузки ведёт на #capital", page.get("CURRENT") === "capital" && page.url.hash === "#capital", [page.get("CURRENT"), page.url.hash]);
  check("заголовок вкладки — экран и имя эмитента из выпуска", page.document.title === `capital · ${sample().meta.company.name} — справедливая стоимость`, page.document.title);
}

/* ── 2. все экраны фикстуры в ширине карточки и телефона ── */

for (const width of [640, 343]) {
  const page = makePage({ width, now: FRESH });
  await page.boot();
  await settle();
  for (const name of SCREEN_NAMES) {
    page.hashchange(`#${name}`);
    const text = page.text();
    check(`экран ${name} (${width} px): без ошибок`, page.get("CURRENT") === name && !page.errors.length && !/не отрисовал/.test(text),
      page.errors.slice(0, 2).concat(text.match(/.{0,80}не отрисовал.{0,120}/) || []));
    check(`экран ${name} (${width} px): графики нарисованы`, countTag(page.app, "SVG") > 0, countTag(page.app, "SVG"));
    const bad = text.match(new RegExp(`.{0,60}(${BAD_TEXT.source}).{0,40}`));
    check(`экран ${name} (${width} px): нет NaN/undefined в тексте`, !bad, bad && bad[0]);
    page.errors.length = 0;
  }
  check(`пояс плашек пуст на свежем выпуске (${width} px)`, !/Выпуску \d/.test(page.text()), page.text().slice(0, 200));
}

/* ── 3. ползунок λ: шаг — сетка выпуска, пересчёт — правило книги ── */

{
  const d = sample();
  const head = d.fair_value.headline;
  const page = makePage({ now: FRESH });
  await page.boot();
  await settle();
  const slider = findNode(page.app, (n) => n.tagName === "INPUT" && n.attrs.id === "lambda");
  check("ползунок λ есть на «Оценке»", !!slider, null);
  check("шаг ползунка = lambda_step выпуска", slider && slider.attrs.step === String(head.lambda_step), slider && slider.attrs.step);
  check("сетка by_lambda — 21 шаг с шагом lambda_step", head.by_lambda.length === 21
    && head.by_lambda.every((r, i) => Math.abs(r.lambda - i * head.lambda_step) < 1e-9), head.by_lambda.map((r) => r.lambda));
  page.ctx.__h = head;
  let worst = 0, printed = 0;
  for (const row of head.by_lambda) {
    page.ctx.__lam = row.lambda === head.own_macro_confidence ? row.lambda + 1e-12 : row.lambda;
    const hl = page.get("headlineAt(globalThis.__h, globalThis.__lam)");
    worst = Math.max(worst, Math.abs(hl.median - row.median), Math.abs(hl.band80[0] - row.p10), Math.abs(hl.band80[1] - row.p90),
      Math.abs(hl.band50[0] - row.p25), Math.abs(hl.band50[1] - row.p75));
    if (Math.abs(hl.printed_median - page.get(`roundHalfUp(${row.median} / ${head.print_step}) * ${head.print_step}`)) > 1e-9) printed += 1;
  }
  check("правило λ фронта воспроизводит строки by_lambda (квантили до 0,006 ₽)", worst <= 0.006, worst);
  check("печать при λ ≠ книги — половиной вверх к print_step", printed === 0, printed);
  check("половина вверх: 372,5 → 375, 367,5 → 370, 372,49 → 370", page.get("[372.5, 367.5, 372.49].map((v) => roundHalfUp(v / 5) * 5).join()") === "375,370,370",
    page.get("[372.5, 367.5, 372.49].map((v) => roundHalfUp(v / 5) * 5).join()"));
  const headline = () => squash(visibleText(findNode(page.app, (n) => n.attrs.id === "fv-headline")));
  const upside = () => squash(visibleText(findNode(page.app, (n) => n.attrs.id === "fv-upside")));
  check("при λ книги — печатаемая медиана выпуска", headline().includes(page.get(`fmt.num(${head.printed_median})`)), headline());
  for (const v of ["0", "1"]) {
    slider.value = v;
    slider.dispatch("input");
    page.paint();
    const row = head.by_lambda.find((r) => Math.abs(r.lambda - Number(v)) < 1e-9);
    const want = page.get(`fmt.num(roundHalfUp(${row.median} / ${head.print_step}) * ${head.print_step})`);
    check(`λ = ${v}: заголовок — печать медианы строки by_lambda`, headline().includes(want), [headline(), want]);
    check(`λ = ${v}: потенциал — строка by_lambda`, upside().includes(squash(page.get(`fmt.signedPct(${row.upside[MAIN]}, 0)`))), upside());
    check(`λ = ${v}: без ошибок`, !page.errors.length, page.errors.slice(0, 2));
  }
  const reset = findNode(page.app, (n) => n.attrs.class === "lambda-reset");
  reset.dispatch("click");
  check("кнопка «вернуть λ книги» возвращает числа выпуска", page.get("LAMBDA") === null && headline().includes(page.get(`fmt.num(${head.printed_median})`)), headline());
}

/* ── 4. выпуск без необязательных полей и без блоков ── */

function stripOptional(d) {
  delete d.market.brokers.history;
  delete d.capital.observed;
  delete d.capital.anchor.n10_bank;
  delete d.regimes.reference_class;
  delete d.guidance.strategy;
  delete d.checks.control_model;
  delete d.fair_value.jump_guard.note_valid_until;
  delete d.dividends.next_expected.last_buy_date;
  d.changes.vs_previous = null;
  for (const r of d.market.peers.rows) delete r.reason;
  return d;
}
const variants = [
  ["без необязательных полей", stripOptional(sample())],
  ["без нау-каста, индикаторов, истории оценки", (() => { const d = sample(); d.nowcast = {}; d.indicators = {}; d.valuation_history = {}; d.history = {}; return d; })()],
  ["без суждений и обратного расчёта", (() => { const d = sample(); d.judgements = {}; d.reverse_dcf = {}; d.fair_value.headline.contributions = []; return d; })()],
  ["быстрая сборка без прогонов", (() => { const d = sample(); d.meta.fast = true; d.fair_value.headline.low_draws = []; d.fair_value.headline.high_draws = []; return d; })()],
];
for (const [name, d] of variants) {
  const page = makePage({ payload: JSON.stringify(d), now: FRESH, width: 343 });
  await page.boot();
  await settle();
  for (const s of SCREEN_NAMES) {
    page.hashchange(`#${s}`);
    const text = page.text();
    check(`${name}: экран ${s} без ошибок`, !page.bootError && !page.errors.length && !/не отрисовал/.test(text),
      [page.bootError, page.errors.slice(0, 2), (text.match(/.{0,80}не отрисовал.{0,160}/) || [])[0]]);
    const bad = text.match(new RegExp(`.{0,60}(${BAD_TEXT.source}).{0,40}`));
    check(`${name}: экран ${s} без NaN/undefined`, !bad, bad && bad[0]);
    page.errors.length = 0;
  }
}

/* ── 5. пояс плашек и ярлык выпуска ── */

{
  const d = sample();
  const stale = makePage({ now: Date.parse("2026-10-10T12:00:00+03:00") });
  await stale.boot();
  await settle();
  check("выпуск старше 96 ч — плашка и красный ярлык", /Выпуску 9 дней/.test(stale.text()) && stale.get('document.querySelector("#release-chip").dataset.state') === "stale",
    [stale.text().slice(0, 200), stale.get('document.querySelector("#release-chip").dataset.state')]);
  const fresh = makePage({ now: FRESH });
  await fresh.boot();
  await settle();
  check("свежий выпуск — зелёный ярлык с временем МСК", fresh.get('document.querySelector("#release-chip").dataset.state') === "ok" && /МСК/.test(squash(visibleText(fresh.chipText))),
    squash(visibleText(fresh.chipText)));
  check("подвал — имя и тикеры из выпуска", squash(fresh.colophon.textContent).includes(`${d.meta.company.name} (${d.meta.company.tickers.join(" · ")})`), fresh.colophon.textContent);

  d.checks.flags.find((f) => f.name === "report_fact").raised = true;
  d.checks.flags.find((f) => f.name === "report_fact").detail = "МСФО за 9 месяцев 2026 г. вышло 2026-10-28; квартал в книге открыт";
  d.next_report.closing.published = true;
  d.checks.flags.find((f) => f.name === "price_fallback").raised = true;
  d.live.degraded_flag = true;
  d.live.degraded = [`цена ${SECOND} не принята: торги не велись`];
  d.dividends.register.push({ year: 2026, dps: 20.5, amount: 463.0, record_date: "2026-10-06", last_buy_date: "2026-10-05", ex_date: "2026-10-06",
    pay_date: "2026-10-20", status: "declared", in_bridge: true, sources: ["синтетика"] });
  const page = makePage({ payload: JSON.stringify(d), now: FRESH });
  await page.boot();
  await settle();
  const text = page.text();
  check("флаг report_fact — плашка с датой по-русски", text.includes("Вышла МСФО, факт не внесён.") && text.includes("28.10.2026"), text.slice(0, 600));
  check("флаг price_fallback и деградация входов — плашки", text.includes("Живая цена не принята.") && text.includes("Часть входов не свежая."), text.slice(0, 600));
  check("последний день покупки в ближайшие 7 дней — плашка", /Последний день покупки скоро: дивиденд 20,50 ₽ за 2026 — 05\.10\.2026, через 5 дней/.test(text), text.slice(0, 900));
  check("МСФО вышло — вместо отсчёта «Отчёт вышел»", text.includes("Отчёт вышел") && text.includes("факт ещё не внесён в модель"), text.slice(0, 900));
  check("жёлтый ярлык при деградации", page.get('document.querySelector("#release-chip").dataset.state') === "warn", page.get('document.querySelector("#release-chip").dataset.state'));

  // Закрытый первый квартал книги: до отчёта — справка и зелёный ярлык (обычное состояние между концом квартала и
  // отчётом); отчёт вышел — плашка флага вместо справки; книга отстала больше чем на квартал — тревога.
  const closedPage = async (patch) => {
    const s = sample();
    s.meta.book_first_period_closed = true;
    patch(s);
    const p = makePage({ payload: JSON.stringify(s), now: FRESH });
    await p.boot();
    await settle();
    return [p.text(), p.get('document.querySelector("#release-chip").dataset.state'), s];
  };
  const [waitText, waitChip, waitSample] = await closedPage(() => {});
  const due = waitSample.calendar.next_fact.date.split("-").reverse().join("\\.");       // дата отчёта образца выпуска — как на экране
  check("первый квартал книги закрыт, отчёта ещё нет — справка с датой отчёта, ярлык зелёный",
    waitSample.calendar.next_fact.covers === waitSample.meta.first_period
    && new RegExp(`закрыт по календарю, отчёт за него ожидается (≈\\s)?${due}: до отчёта оценка считается на фактах .{3,24} и прогнозе книги\\.`).test(waitText)
    && !waitText.includes("а факты и книга прежние") && waitChip === "ok", [waitText.slice(0, 500), waitChip]);
  const [outText, outChip] = await closedPage((s) => { s.checks.flags.find((f) => f.name === "report_fact").raised = true; });
  check("первый квартал закрыт, отчёт вышел — плашка флага без справки, ярлык жёлтый",
    outText.includes("Вышла МСФО, факт не внесён.") && !outText.includes("закрыт по календарю") && outChip === "warn", [outText.slice(0, 500), outChip]);
  const [lateText, lateChip] = await closedPage((s) => { s.meta.periods_closed = 2; });
  check("книга отстала больше чем на квартал — тревога и жёлтый ярлык",
    lateText.includes("закрыт по календарю, а факты и книга прежние") && lateChip === "warn", [lateText.slice(0, 500), lateChip]);

  // Сворачивание плашек: нажатие сворачивает в ярлык и разворачивает обратно; свёрнутое живёт при смене экрана и
  // после перезагрузки (хранилище браузера), пока текст плашки тот же; «выпуск устарел» не сворачивается.
  const store = () => { const data = {}; return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); } }; };
  const banner = (p, word) => findNode(p.app, (n) => /(^| )banner( |$)/.test(n.attrs.class || "") && squash(n.textContent).includes(word));
  const isFolded = (n) => n.classList.contains("is-folded");
  const withBanners = () => {
    const s = sample();
    s.meta.book_first_period_closed = true;
    s.checks.flags.find((f) => f.name === "price_fallback").raised = true;
    return s;
  };
  const open = async (opts) => { const p = makePage({ now: FRESH, ...opts }); await p.boot(); await settle(); return p; };
  const shelf = store();
  const first = await open({ payload: JSON.stringify(withBanners()), storage: shelf });
  let closed = banner(first, "закрыт по календарю");
  check("плашка — кнопка: развёрнута, с подсказкой и фокусом с клавиатуры",
    closed && closed.getAttribute("role") === "button" && closed.getAttribute("aria-expanded") === "true" && closed.getAttribute("tabindex") === "0"
    && !isFolded(closed), closed && closed.attrs);
  closed.dispatch("click");
  check("нажатие сворачивает плашку: класс, признак, полный текст — подсказкой, текст в узле цел",
    isFolded(closed) && closed.getAttribute("aria-expanded") === "false" && closed.title.startsWith("Первый прогнозный") && first.text().includes("закрыт по календарю")
    && !isFolded(banner(first, "Живая цена не принята")), [closed.attrs, closed.title]);
  first.hashchange("#model");
  check("свёрнутая плашка остаётся свёрнутой на другом экране", isFolded(banner(first, "закрыт по календарю")) && !isFolded(banner(first, "Живая цена не принята")));
  const again = await open({ payload: JSON.stringify(withBanners()), storage: shelf });
  check("после перезагрузки свёрнутое помнит браузер", isFolded(banner(again, "закрыт по календарю")) && !isFolded(banner(again, "Живая цена не принята")), shelf.data);
  banner(again, "закрыт по календарю").dispatch("keydown", { key: "Tab" });
  check("посторонняя клавиша плашку не трогает", isFolded(banner(again, "закрыт по календарю")));
  banner(again, "закрыт по календарю").dispatch("keydown", { key: "Enter" });
  check("Enter разворачивает; хранилище пусто", !isFolded(banner(again, "закрыт по календарю")) && shelf.data["tzi-banners"] === "[]", shelf.data);
  banner(again, "закрыт по календарю").dispatch("click");
  const changed = withBanners();
  changed.meta.first_period = "2026Q4";
  changed.calendar.next_fact.covers = "2026Q4";
  const next = await open({ payload: JSON.stringify(changed), storage: shelf });
  check("текст плашки изменился — она приходит развёрнутой", banner(next, "закрыт по календарю") && !isFolded(banner(next, "закрыт по календарю")), shelf.data);
  banner(next, "Живая цена не принята").dispatch("click");
  check("ключ исчезнувшей плашки не копится в хранилище", JSON.parse(shelf.data["tzi-banners"]).length === 1, shelf.data);
  const bare = await open({ payload: JSON.stringify(withBanners()) });
  banner(bare, "закрыт по календарю").dispatch("click");
  check("без хранилища сворачивание работает до перезагрузки", isFolded(banner(bare, "закрыт по календарю")) && !bare.errors.length, bare.errors);
  const old = makePage({ now: Date.parse("2026-10-10T12:00:00+03:00") });
  await old.boot();
  await settle();
  const staleBanner = banner(old, "Выпуску 9 дней");
  staleBanner.dispatch("click");
  check("«выпуск устарел» не сворачивается", staleBanner.getAttribute("role") === "status" && !isFolded(staleBanner) && !staleBanner.hasAttribute("aria-expanded"), staleBanner.attrs);
  const buyDay = (today) => {
    const s = sample();
    s.meta.valuation_date = today;
    s.dividends.register.push({ year: 2026, dps: 20.5, amount: 463.0, record_date: "2026-10-06", last_buy_date: "2026-10-05", ex_date: "2026-10-06",
      pay_date: "2026-10-20", status: "declared", in_bridge: true, sources: ["синтетика"] });
    return JSON.stringify(s);
  };
  const days = store();
  const d5 = await open({ payload: buyDay("2026-09-30"), storage: days });
  banner(d5, "Последний день покупки скоро").dispatch("click");
  const d4 = await open({ payload: buyDay("2026-10-01"), storage: days });
  const d0 = await open({ payload: buyDay("2026-10-05"), storage: days });
  check("последний день покупки: свёрнутая не разворачивается назавтра, только в сам последний день",
    isFolded(banner(d4, "Последний день покупки скоро")) && /сегодня/.test(banner(d0, "Последний день покупки скоро").textContent)
    && !isFolded(banner(d0, "Последний день покупки скоро")), [days.data, d4.text().slice(0, 300), d0.text().slice(0, 300)]);
}

/* ── 6. волна W1: подписи, дивиденд, пары передачи, доли, эталоны, гайденс ── */

{
  const d = sample();
  const page = makePage({ now: FRESH });
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const rub = (v) => squash(page.get(`fmt.rub(${v}, 2)`));
  const nx = d.dividends.next_expected;
  let text = at("overview");
  check("W1: ближайший дивиденд — DPS политики с риском отмены", text.includes(rub(nx.dps)) && text.includes(`DPS по политике · риск отмены ${Math.round(nx.p_cancel * 100)} %`), text.slice(0, 1600));
  check("W1: среднее по клеткам — второй строкой", text.includes(`в среднем по клеткам ${rub(nx.dps_mean)}`), text.slice(0, 1600));
  check("№ 1: доли меньше 1 % — «< 1 %» без порядка; все оси в полосе — строки «вне полосы» нет", text.includes("Вклад < 1 %:") && !text.includes("Вне полосы"), text.match(/.{0,200}Вклад <.{0,300}/));
  text = at("model");
  const pair = d.nii.transmission.pairs[0];
  check("W1: парные передачи вместо одного числа", text.includes(`${pair.from} → ${pair.to}`) && text.includes("в коридоре") && !text.includes("ROE-эквивалент передачи"), text.match(/.{0,200}Передача по парам.{0,300}/));
  check("W1: ближний сдвиг ЧПМ — отдельной строкой", text.includes("Ближний сдвиг ЧПМ, общий для режимов и миров"), null);
  check("W1: гайденс по виду строки (пол Н20.0 — «≥»)", text.includes("≥ 13,3 %") && text.includes("≤ 1,4 %"), text.match(/.{0,100}Гайденс.{0,400}/));
  text = at("report");
  check("W1: названия эталонов — из выпуска, не ключи", text.includes(d.nowcast.retro.titles.ras_bridge) && !/\bras_bridge\b|\bprev_quarter\b|same_quarter_last_year/.test(text), text.match(/.{0,300}Эталоны на истории.{0,400}/));
  check("W1: дата решения о допуске — по-русски", text.includes("не раньше 28.10.2027") && !text.includes("2027-10-28"), text.match(/.{0,80}не раньше.{0,40}/));
  const t90 = findNode(page.app, (n) => n.tagName === "BUTTON" && n.textContent === "T-90");
  check("W1: ретро — переключатель горизонта", !!t90, null);
  if (t90) { t90.dispatch("click"); page.paint(); check("W1: горизонт T-90 рисуется без ошибок", !page.errors.length && !/не отрисовал/.test(page.text()), page.errors.slice(0, 2)); }
  text = at("capital");
  check("W1: Н1.0 и Н1.2 — подписями capital.titles", text.includes(`${d.capital.titles.n1_0} —`) && text.includes(`${d.capital.titles.n1_2} —`), text.match(/.{0,120}в оценку не входит.{0,20}/));
  check("W1: условие капитала — подписью норматива, не ключом", text.includes(`Условие капитала: ${d.capital.titles.n20} после выплаты`) && !text.includes("n20_0"), text.match(/.{0,40}Условие капитала.{0,80}/));
  check("W1: реестр — два источника", text.includes("T-Invest + Интерфакс") && text.includes("два источника"), text.match(/.{0,80}Источники.{0,200}/));
  check("W1: ввод избытка ε — линейно за ramp_years", text.includes(`ввод линейно за ${d.dividends.policy.excess.ramp_years} года`), text.match(/.{0,80}Выплата избытка.{0,80}/));
  check("W1: C/I по годам — упр. базис", text.includes("C/I упр."), null);
  check("имя норматива в тексте выпуска — не дробь («Н20.0», не «Н20,0»)", text.includes("Н20.0 после выплаты") && !/Н\d+,\d/.test(text), text.match(/.{0,40}Н\d+[.,]\d.{0,40}/));
  text = at("book");
  check("№ 1: все оси книги в полосе — «вне полосы» у суждений нет", !/вне полосы/i.test(squash(visibleText(cardOf(page, "Суждения книги по цене ошибки")))), text.match(/.{0,80}не полосы.{0,80}/));
  check("W1: клетки сработавшего гейта — словами выпуска", text.includes("Клетки (первые 10 из 22)") && text.includes(`${d.worlds.rows.N.name} · ${d.regimes.rows.soft.title} · ${d.capital.scenarios.schedule.title}`), text.match(/.{0,60}Клетки.{0,200}/));
  check("W1: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));
}

{
  const d = sample();
  d.nii.transmission.pairs[1].value = 0.31;
  d.nii.transmission.pairs[1].inside = false;
  d.checks.flags.find((f) => f.name === "ni_jump").raised = true;
  d.checks.flags.find((f) => f.name === "ni_jump").detail = "2027Q1: +31 % г/г при ключевой 14 → 14 %";
  d.live.degraded_flag = true;
  d.live.degraded = ["cbr: ставки вкладов: https://example.org/statistics/avg/?From=27.08.2025&To=01.10.2026: HTTP 403"];
  d.next_report = { ...d.next_report, status: "not_computed", reason: "быстрая сборка", cor_table: [], nim_table: [] };
  d.reverse_dcf.rows[0] = { ...d.reverse_dcf.rows[0], status: "not_computed", solved: null, reason: "быстрая сборка" };
  const page = makePage({ payload: JSON.stringify(d), now: FRESH, width: 343 });
  await page.boot();
  await settle();
  let text = page.text();
  check("W1: флаг ni_jump — плашка с подробностью", text.includes("Прибыль квартала г/г прыгает при неизменной ключевой.") && text.includes("+31 %"), text.slice(0, 900));
  check("W1: причина деградации — без адреса запроса", text.includes("example.org: HTTP 403") && !text.includes("From=27"), text.slice(0, 900));
  page.hashchange("#model");
  check("W1: пара вне коридора — отметкой", page.text().includes("вне коридора"), null);
  page.hashchange("#report");
  check("W1: «что даст отчёт» в быстрой сборке — причина", page.text().includes("Таблицы не считались: быстрая сборка."), page.text().match(/.{0,80}Что даст отчёт.{0,120}/));
  page.hashchange("#market");
  check("W1: ось обратного расчёта без поиска — «не считалось»", page.text().includes("не считалось"), null);
  check("W1: частные случаи без ошибок", !page.errors.length && !/не отрисовал/.test(page.text()), page.errors.slice(0, 2));
}

/* ── 7. волна W2 (AUDIT-1): печать по П§2, слова вместо кодов ── */

{
  const d = sample();
  const page = makePage({ now: FRESH });
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const ru = (t) => squash(page.get(`ruText(${JSON.stringify(t)})`));

  // № 61: ruText — дроби с запятой, версии и ссылки как есть
  for (const [src, want] of [["рост 1.5 %", "рост 1,5 %"], ["книга 1.1", "книга 1.1"], ["книга 1.1 → 1.2; факты те же", "книга 1.1 → 1.2; факты те же"],
    ["book-1.6", "book-1.6"], ["М§4.11 и DESIGN §3.3", "М§4.11 и DESIGN §3.3"], ["(М§14.4)", "(М§14.4)"], ["п. 6.4: срок 3 года", "п. 6.4: срок 3 года"],
    ["Н20.0 не ниже 13.30%", "Н20.0 не ниже 13,30 %"], ["уравнение ni-1.0", "уравнение ni-1.0"], ["эмпирика 0.056–0.085", "эмпирика 0,056–0,085"],
    ["2026-10-28 и 28.10.2026", "28.10.2026 и 28.10.2026"], ["Форма 0409102 за 2026M09", "Форма 0409102 за сентябрь 2026"], ["версия 1.2.3", "версия 1.2.3"],
    ["CoR 1.42 % против 1.4 %", "CoR 1,42 % против 1,4 %"], ["сдвиг -0.5 п.п.", "сдвиг −0,5 п.п."]]) {
    check(`№ 61: ruText «${src}» → «${want}»`, ru(src) === want, ru(src));
  }

  let text = at("overview");
  const head = d.fair_value.headline;
  check("№ 63: число осей полосы — строки суждений in_band", text.includes(`${head.draws / 1000 | 0} 000 прогонов по ${d.judgements.rows.filter((j) => j.in_band).length} суждениям книги`), text.match(/.{0,40}прогонов по.{0,60}/));
  check("№ 65: «точка выше медианы» — оси с наибольшим сдвигом положения, в рублях с пометкой", /Сильнее всего прогоны вниз от точки уводят ЧПМ сквозь цикл \(−3,2 ₽\) и CoR сквозь цикл \(−2,0 ₽\) — вклад в «среднее прогонов − точка», первый порядок\./.test(text), text.match(/.{0,60}Точка выше медианы.{0,260}/));
  check("№ 66: запас норматива — до порога дивидендной политики", text.includes(`запас ${d.capital.titles.n20} до порога дивидендной политики`) && !text.includes("до требования"), text.match(/.{0,40}запас Н.{0,80}/));
  check("№ 67: DPS по прибыли с нау-кастом подписан", text.includes("DPS за 2026 с нау-кастом, интервал"), text.match(/.{0,40}DPS за 2026.{0,60}/));
  check("№ 68: капитализация и капитал — числами", text.includes(`(капитализация ${squash(page.get(`fmt.num(${d.market.cap}, 0)`))} минус капитал ${squash(page.get(`fmt.num(${d.fair_value.bank_first_line.bv_v}, 0)`))})`), text.match(/.{0,40}капитализация.{0,60}/));
  const ni = d.next_report.expectation.ni, eq = d.next_report.neutral.cor.ni_equivalent;
  check("№ 16: эквивалент — уровень ЧП квартала рядом с ожиданием, не чувствительность", text.includes(`при ней прибыль квартала ≈ ${squash(page.get(`fmt.bn(${eq}, 1)`))} (ожидание модели — ${squash(page.get(`fmt.num(${ni}, 1)`))})`)
    && !/прибыли квартала на 0,1/.test(text), text.match(/.{0,80}при ней.{0,120}/));
  check("№ 22: наклон — местный, рядом размах реакции", text.includes("у нейтрального значения — около 6,7 ₽ на 0,1 п.п., дальше реакция упирается в предел сдвига режимов: от −19,9 до +14,6 ₽"), text.match(/.{0,40}около.{0,160}/));
  check("№ 28: пояснение строки разложения; прогулки по ключам нет", text.includes("входит в строку «Суждения книги»") && !text.includes("Крупнейшие ключи книги"), text.match(/.{0,80}Суждения книги.{0,200}/));
  // № 64: подпись «сейчас …» не закрывает точки мини-графика CoR
  const teaser = cardOf(page, "Ближайший отчёт");
  const svg = findNode(teaser, (n) => n.tagName === "SVG" && (n.attrs["aria-label"] || "").startsWith("Медиана в зависимости"));
  const now = findNode(svg, (n) => n.tagName === "TEXT" && n.textContent.startsWith("сейчас"));
  const dots = [];
  const walk = (n) => { if (n.nodeType === 1) { if (n.tagName === "CIRCLE") dots.push([+n.attrs.cx, +n.attrs.cy]); n.children.forEach(walk); } };
  walk(svg);
  const box = now && { x0: +now.attrs.x, x1: +now.attrs.x + now.textContent.length * 7, y0: +now.attrs.y - 13, y1: +now.attrs.y + 3 };
  check("№ 64: подпись «сейчас» не закрывает точки графика", !!now && dots.length > 5 && !dots.some(([cx, cy]) => cx > box.x0 - 4 && cx < box.x1 + 4 && cy > box.y0 - 4 && cy < box.y1 + 4), [box, dots.slice(0, 3)]);

  text = at("market");
  check("№ 27: оговорка метода обратного расчёта", text.includes("решения разных строк не перемножаются") && text.includes("Строки решаются по одной"), null);
  check("№ 64: «недостижимо» — один раз на строку", !/недостижимо\s+недостижимо/.test(text) && text.includes("недостижимо"), text.match(/.{0,60}недостижимо.{0,60}/));
  const subject = d.market.peers.rows[0];
  check("№ 64: аналоги — дата отчётности из строки, снимок — отдельно", text.includes(`отчётность на ${page.get(`fmt.date("${subject.bv_date}")`)}; снимок аналогов ${page.get(`fmt.date("${d.market.peers.as_of}")`)}`)
    && text.includes("отчётность на 31.03.2026"), text.match(/.{0,40}Банки-аналоги.{0,160}/));

  text = at("model");
  check("№ 17: строки сектора — подписью, «лучше сектора» не сравнивается", text.includes("прогноз сектора; лучше сектора") && text.includes("не сравнивается")
    && text.includes("прогноз сектора; в соответствии с сектором") && text.includes("в прогнозе сектора") && text.includes("гейт их не берёт"), text.match(/.{0,60}Рост кредитов.{0,300}/));
  check("№ 62: базисы — словами (норматив ЦБ, прогноз сектора)", text.includes("норматив ЦБ") && !/\bregulatory\b|\bsector\b/.test(text), text.match(/.{0,40}regulatory|sector.{0,40}/));
  check("№ 64: «Смесь заголовка» — без повтора в скобках; слои в ней названы так же, как в карточке слоёв", text.includes(`${page.get("upperFirst")(d.layers.headline_mix.title)}; строки — % средних активов`)
    && d.layers.headline_mix.title !== d.paths.mix.title && !/Смесь заголовка \(смесь/.test(text), text.match(/.{0,80}средних активов.{0,40}/));
  check("№ 62: «п.п..» нет", !/п\.п\.\./.test(text), text.match(/.{0,60}п\.п\.\..{0,20}/));
  check("В8: сдвиг спредов активов и пассивов, эффективный LT-спред с полом", text.includes("сдвиг LT-спредов σ0: активы / пассивы; на активах — 80 % сдвига") && text.includes("−0,11 / +0,03 п.п.")
    && text.includes("+0,63 / +0,55 / +0,51") && text.includes("пол спреда 0,50 п.п.") && text.includes("опора — ОФЗ 1 г.") && !/ofz_/.test(text), text.match(/.{0,60}Корпоративные кредиты.{0,200}/));
  check("№ 14: флаги клеток — «урезан капиталом» и «отменена» раздельно", text.includes("дивиденд урезан капиталом") && text.includes("решения года кризиса отменены") && !text.includes("рост урезан капиталом"), null);

  text = at("report");
  check("№ 60: дата месячной плитки — период словами", text.includes("август 2026 · РСБУ банка") && !/\d{4}M\d{2}/.test(text), text.match(/.{0,60}Чистая прибыль, месяц.{0,120}/));
  check("№ 64: «15 рядов» — по числу", text.includes(`${d.indicators.tiles.length} рядов`), text.match(/.{0,20}Опережающие индикаторы.{0,60}/));
  check("№ 44: консенсус — «у отчёта»", text.includes("Консенсус у отчёта (за день до выхода)"), text.match(/.{0,200}Эталоны на истории.{0,500}/));
  const t90 = findNode(page.app, (n) => n.tagName === "BUTTON" && n.textContent === "T-90");
  t90.dispatch("click");
  page.paint();
  check("№ 44: на горизонте T-90 консенсуса нет", !squash(visibleText(cardOf(page, "Эталоны на истории"))).includes("онсенсус"), squash(visibleText(cardOf(page, "Эталоны на истории"))).slice(0, 600));
  const nim = findNode(page.app, (n) => n.tagName === "BUTTON" && n.textContent === "ЧПМ" && n.parentNode.attrs["aria-label"] === "Показатель отчёта");
  nim.dispatch("click");
  page.paint();
  text = page.text();
  check("№ 19: ЧПМ режимы не учит, пока ожидания равны; второе наблюдаемое — не наблюдалось", text.includes("Ожидания ЧПМ у режимов равны: такой факт вероятностей режимов не меняет")
    && text.includes("второй показатель в ней считается ненаблюдавшимся"), text.match(/.{0,60}Ожидания ЧПМ.{0,200}/));
  check("№ 16: нейтральная ЧПМ — уровень ЧП = ожиданию", text.includes(`Нейтральная ЧПМ 3 кв. 2026 (упр.) — 5,97 %`) && text.includes(`при ней прибыль квартала ≈ ${squash(page.get(`fmt.bn(${ni}, 1)`))} (ожидание модели`), text.match(/.{0,40}Нейтральная ЧПМ.{0,300}/));

  text = at("capital");
  check("№ 66: «Капитал на дату» — порог политики и регуляторный пол года", text.includes("порог дивидендной политики — требование года") && text.includes("запас до порога дивидендной политики")
    && text.includes("регуляторный пол года (ожидание по сценариям)"), text.match(/.{0,200}запас до.{0,160}/));
  check("№ 33, № 97: срок политики — датой; запись о сроке — предложением, без приставки «Срок:»", text.includes("действует по 05.12.2026") && text.includes("П. 6.4 Положения: срок — 3 года")
    && !text.includes("Срок: п.") && !text.includes("действует по —"), text.match(/.{0,80}действует по.{0,60}/));
  check("№ 62: коды политики — словами", text.includes("База — прибыль группы по МСФО, приходящаяся на акционеров; делитель — размещённые акции обеих категорий; округление — до копейки вверх; нехватка капитала — остаток сверх требований")
    && text.includes("догоняющая выплата — да") && !/\b[a-z]+_[a-z_]+\b|\btrue\b/.test(text), text.match(/.{0,40}База —.{0,300}/));
  check("№ 59: капитальный разрыв — число клеток и клетки словами", d.capital.capital_gap.cells === 4 && text.includes(`(4 клетки: ${d.worlds.rows.H.name} · ${d.regimes.rows.crisis.title} · ${d.capital.scenarios.upper.title}; ${d.worlds.rows.H.name} · ${d.regimes.rows.crisis.title} · ${d.capital.scenarios.strict.title}; ${d.worlds.rows.M.name} · `), text.match(/.{0,40}Капитальный разрыв.{0,200}/));
  const annual = cardOf(page, "По годам");
  check("reintegrate: таблица «По годам» — плотная (влезает в карточку на 1280)", !!findNode(annual, (n) => n.tagName === "TABLE" && /\bdense\b/.test(n.attrs.class || "")), null);
  const table = findNode(page.app, (n) => n.tagName === "BUTTON" && n.textContent === "Таблица" && squash(visibleText(cardOf(page, "Дивиденды по году прибыли"))).length > 0 && cardOf(page, "Дивиденды по году прибыли").contains(n));
  table.dispatch("click");
  check("№ 14: дивиденды по годам — «урезано капиталом» и «без выплаты» раздельно", page.text().includes("Урезано капиталом") && page.text().includes("Без выплаты"), null);

  text = at("book");
  const cm = squash(visibleText(cardOf(page, "Сверка с контрольной моделью")));
  check("№ 15: относительная разность — в процентах", cm.includes("−0,27 %") && cm.includes("3,0 %"), cm.slice(0, 700));
  check("№ 15: абсолютная разность — в единицах строки (|diff| > 1 — не проценты)", cm.includes("−30,0 млрд ₽") && cm.includes("584,5 млрд ₽") && !/2 997|58 448/.test(cm), cm.slice(0, 1200));
  check("№ 15: доли — в п.п., малые допуски — степенью, пол допуска — «или»", cm.includes("−0,03 п.п.") && cm.includes("0,30 п.п.") && cm.includes("1·10⁻⁶") && cm.includes("10,0 % или 44,3 млрд ₽") && cm.includes("или 2,05 ₽"), cm.slice(0, 1500));
  check("№ 58: источник суждения — словами книги", text.includes("линия 5,4 % + 0,037 × ключевая сквозь цикл") && text.includes("книга 1.3, ось „Кризис: сдвиг ЧПМ 2027“") && !/valuation\.uncertainty/.test(text), null);
  check("№ 1: сдвиг положения оси — столбцом", text.includes("Сдвиг положения, ₽") && text.includes("−3,2"), text.match(/.{0,40}Сдвиг положения.{0,200}/));
  check("№ 68: строка фактов — период словами", text.includes("Факты якоря") && text.includes("2 кв. 2026") && !/2026Q2/.test(text), text.match(/.{0,40}Факты якоря.{0,80}/));
  check("reintegrate: κ — число, не проценты", /κ: CoR к реальной ставке сверх мира N 0,05 0 … 0,15/.test(text), text.match(/.{0,20}κ: CoR.{0,80}/));
  check("№ 61: версия книги на экране — «1.3», не «1,3»", text.includes("книга 1.3") && !/1,3, ось|книга 1,\d/.test(text), text.match(/.{0,40}книга 1[.,]\d.{0,40}/));
  check("W2: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));
}

{
  // Частные случаи W2: ось вне полосы, требование ≠ порогу политики, срок политики не задан, разные ожидания ЧПМ,
  // наклон у ожидания, метка клетки и код периода в тексте ядра, одна P(ниже рынка) у двух тикеров.
  const d = sample();
  const j = d.judgements.rows.find((r) => r.id === "epsilon");
  Object.assign(j, { in_band: false, share: null, rank_corr: null });
  d.fair_value.headline.contributions = d.fair_value.headline.contributions.filter((c) => c.judgement_key !== "epsilon");
  d.judgements.off_band_shift = { rub: j.mean_shift, limit: 2.5, axes: 1 };
  d.capital.anchor.req20_now = 0.113;
  d.dividends.policy.valid_until = null;
  d.dividends.policy.valid_until_note = "срок действия в Положении не указан";
  d.next_report.expectation.by_regime[0].nim_mgmt = 0.0602;
  d.next_report.slope.at_cor = "expectation";
  d.next_report.nim_table = d.next_report.nim_table.slice(0, 4);
  d.checks.flags.find((f) => f.name === "ni_jump").raised = true;
  d.checks.flags.find((f) => f.name === "ni_jump").detail = "H/norm/schedule 2027Q2: ЧП г/г +25% при ключевой 14.62% → 14.00%";
  for (const row of [d.fair_value.headline, ...d.fair_value.headline.by_lambda]) { row.p_below_market = 0.035; row.p_below_by_ticker = { [MAIN]: 0.035, [SECOND]: 0.035 }; }
  d.fair_value.headline.by_lambda[20].p_below_market = 0.001;
  d.fair_value.headline.by_lambda[20].p_below_by_ticker = { [MAIN]: 0.001, [SECOND]: 0.001 };
  const page = makePage({ payload: JSON.stringify(d), now: FRESH });
  await page.boot();
  await settle();
  let text = page.text();
  check("reintegrate: плашка ni_jump — клетка и квартал словами", text.includes(`${d.worlds.rows.H.name} · ${d.regimes.rows.norm.title} · ${d.capital.scenarios.schedule.title} 2 кв. 2027: ЧП г/г +25 % при ключевой 14,62 % → 14,00 %`) && !/H\/norm|2027Q2/.test(text), text.slice(0, 500));
  check("№ 1: ось вне полосы — той же мерой, что правило (сдвиг заголовка и порог)", text.includes(`Вне полосы (их фиксация сдвигает заголовок на ${squash(page.get(`fmt.signedRub(${j.mean_shift}, 1)`))} при пороге 2,5 ₽): выплата избытка ε с 2030.`), text.match(/.{0,40}Вне полосы.{0,200}/));
  check("№ 63: одна вероятность — одна печать у обоих тикеров", text.includes("4 %вероятность") && text.includes(`${SECOND}: 4 %`) && !text.includes(`${SECOND}: 3,5 %`), text.match(/.{0,20}вероятность, что.{0,220}/));
  check("№ 66: требование не равно порогу политики — «минимум с надбавками + запас»", text.includes("до требования (минимум с надбавками + запас)"), text.match(/.{0,40}запас Н.{0,80}/));
  check("№ 22: наклон снят в ожидании — так и сказано", text.includes("у ожидания — около 6,7 ₽ на 0,1 п.п."), text.match(/.{0,40}около.{0,80}/));
  const slider = findNode(page.app, (n) => n.tagName === "INPUT" && n.attrs.id === "lambda");
  slider.value = "1";
  slider.dispatch("input");
  page.paint();
  text = page.text();
  check("№ 63: меньше 1 % — два знака у обоих тикеров", text.includes("0,10 %вероятность") && text.includes(`${SECOND}: 0,10 %`), text.match(/.{0,20}вероятность, что.{0,220}/));
  check("№ 65: при λ ≠ книги — пометка приближения", text.includes("первый порядок, при λ книги."), text.match(/.{0,60}первый порядок.{0,40}/));
  page.hashchange("#report");
  const nim = findNode(page.app, (n) => n.tagName === "BUTTON" && n.textContent === "ЧПМ" && n.parentNode.attrs["aria-label"] === "Показатель отчёта");
  nim.dispatch("click");
  page.paint();
  text = page.text();
  check("№ 19: ожидания ЧПМ режимов разные — подписи о равенстве нет", !text.includes("Ожидания ЧПМ у режимов равны"), null);
  const impact = cardOf(page, "Что даст отчёт");
  const titles = tipsOf(page, impact, "CIRCLE").map((t) => t.title);
  check("№ 20: ось графика накрывает эталоны и нау-каст за краем таблицы", titles.includes("гайденс года") && titles.includes("прошлый отчётный квартал"), titles);
  page.hashchange("#capital");
  text = squash(visibleText(cardOf(page, "Дивидендная политика")));
  check("№ 33: срок политики не задан — причина словами, не «действует по —»", text.includes("срок действия в Положении не указан") && !text.includes("действует по"), text.match(/.{0,60}Дивидендная политика.{0,160}/));
  page.hashchange("#book");
  text = page.text();
  check("№ 1: «вне полосы» на «Допущениях» с мерой сдвига", text.includes("вне полосы") && text.includes("Вне полосы — 1: их фиксация сдвигает заголовок"), text.match(/.{0,60}Вне полосы.{0,160}/));
  check("W2: частные случаи без ошибок", !page.errors.length && !/не отрисовал/.test(page.text()), page.errors.slice(0, 2));
}

/* ── 8. волна W3 (AUDIT-2): тексты, диапазоны, легенды, нули и провалы, новые поля П§2 ── */

// Запись легенды ↔ нарисованный элемент той же карточки: цвет ключа — заливка или обводка, пунктирный ключ — пунктирная линия,
// сплошной ключ-линия — линия без пунктира, ключ-точка — кружок; у HTML-полос — класс полосы.
const KEY_COLORS = { "key-model": ["var(--model)"], "key-model2": ["var(--model)"], "key-market": ["var(--market)"], "key-market2": ["var(--market)"], "key-third": ["var(--third)"], "key-third2": ["var(--third)"],
  "key-ink": ["var(--ink)"], "key-neg": ["var(--neg)"], "key-neg2": ["var(--neg)"], "key-neg3": ["var(--neg)"], "key-neutral": ["var(--series-neutral)"],
  "key-b80": ["var(--model-wash-1)", "var(--model-wash-2)"], "key-b50": ["var(--model-wash-2)", "var(--model-wash-3)"], "key-dash": ["var(--ink-2)"],
  "key-band": ["var(--market-wash)"], "key-diamond": ["var(--ink)"] };
const DASHED_KEYS = new Set(["key-model2", "key-market2", "key-third2", "key-neg2", "key-neg3", "key-dash"]);
const BAR_CLASS = { "key-neg": "is-down", "key-model": "is-up" };
function legendOrphans(page) {
  const out = [];
  const cards = [];
  const collect = (n) => { if (n.nodeType !== 1) return; if (n.tagName === "SECTION") cards.push(n); n.children.forEach(collect); };
  collect(page.app);
  for (const card of cards) {
    const keys = [], marks = [];
    const walk = (n, inLegend) => {
      if (n.nodeType !== 1 || n.hidden) return;
      const cl = (n.attrs.class || "").split(" ");
      if (n.tagName === "I" && inLegend && cl.includes("key")) keys.push({ cl, name: squash(visibleText(n.parentNode)) });
      else if (["PATH", "LINE", "CIRCLE", "RECT", "POLYLINE"].includes(n.tagName) || cl.includes("bt-bar")) marks.push(n);
      n.children.forEach((c) => walk(c, inLegend || cl.includes("legend")));
    };
    walk(card, false);
    for (const { cl, name } of keys) {
      const key = cl.find((c) => KEY_COLORS[c]);
      if (!key) { out.push(`${name}: ключ без цвета (${cl.join(" ")})`); continue; }
      const dashed = DASHED_KEYS.has(key), solidLine = cl.includes("key-line") && !dashed, dot = cl.includes("key-dot");
      const hit = marks.some((m) => {
        if ((m.attrs.class || "").split(" ").includes("bt-bar")) return !!BAR_CLASS[key] && m.attrs.class.split(" ").includes(BAR_CLASS[key]);
        const colour = KEY_COLORS[key].includes(m.attrs.stroke) || KEY_COLORS[key].includes(m.attrs.fill);
        if (!colour) return false;
        if (dot) return m.tagName === "CIRCLE" && KEY_COLORS[key].includes(m.attrs.fill);
        if (dashed) return !!m.attrs["stroke-dasharray"] && KEY_COLORS[key].includes(m.attrs.stroke);
        if (solidLine) return !m.attrs["stroke-dasharray"] && KEY_COLORS[key].includes(m.attrs.stroke);
        return true;
      });
      if (!hit) out.push(`${squash(visibleText(card)).slice(0, 40)}: «${name}» (${key})`);
    }
  }
  return out;
}
const svgTexts = (root) => { const out = []; const walk = (n) => { if (n.nodeType === 1) { if (n.tagName === "TEXT") out.push(n.textContent); n.children.forEach(walk); } }; walk(root); return out; };
const countNodes = (root, pred) => { let k = 0; const walk = (n) => { if (n.nodeType === 1) { if (pred(n)) k += 1; n.children.forEach(walk); } }; walk(root); return k; };
const legendOf = (card) => { const out = []; const walk = (n) => { if (n.nodeType === 1) { if ((n.attrs.class || "").split(" ").includes("legend")) out.push(squash(visibleText(n))); n.children.forEach(walk); } }; walk(card); return out.join(" | "); };
const press = (page, label, group) => {
  const b = findNode(page.app, (n) => n.tagName === "BUTTON" && n.textContent === label && (!group || n.parentNode.attrs["aria-label"] === group));
  if (b) { b.dispatch("click"); page.paint(); }
  return !!b;
};

{
  const d = sample();
  const page = makePage({ now: FRESH });
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const orphans = [];
  for (const name of SCREEN_NAMES) { at(name); orphans.push(...legendOrphans(page).map((x) => `${name}: ${x}`)); }
  check("№ 103: каждая запись легенды соответствует нарисованному элементу своей карточки", orphans.length === 0, orphans.slice(0, 8));

  let text = at("overview");
  const bfl = d.fair_value.bank_first_line;
  const whole = (v) => squash(page.get(`fmt.signedRub(${v})`));
  check("№ 81: чувствительности языка банка — целые рубли", text.includes(`0,1 п.п. CoR — ${whole(bfl.rub_per_01pp_cor)}, 0,1 п.п. ЧПМ — ${whole(bfl.rub_per_01pp_nim)}.`)
    && text.includes(`Цена 1 п.п. долгосрочного ROE${squash(page.get(`fmt.num(${bfl.rub_per_1pp_roe})`))}₽ на акцию`) && !text.includes("запаса капитала"), text.match(/.{0,40}Цена 1 п\.п\. ROE.{0,200}/));
  check("В17: истекающее объяснение гейта — плашка, не тревога", text.includes("Срок объяснения проверки истекает. «Путь года вне гайденса» — объяснение действует по 28.10.2026.")
    && page.get('document.querySelector("#release-chip").dataset.state') === "ok", text.slice(0, 300));
  check("№ 100: дата формы ЦБ — окном оценки, не точной датой", text.includes("≈ 24 окт.") && text.includes("окно 24 окт.–26 окт.") && !/(?<!≈ )24 окт\.через/.test(text), text.match(/.{0,60}Форма 0409102.{0,80}/));
  check("№ 82: год нау-каста — на слое смеси заголовка", text.includes("прибыль 2026: факт + ожидание модели с поправкой нау-каста") && /DPS за 2026 с нау-кастом, интервал \d+,\d–\d+,\d ₽/.test(text), text.match(/.{0,60}DPS за 2026.{0,80}/));

  text = at("market");
  check("№ 101, §4.3: строка обратного расчёта без оси — без диапазона «0 % … 0 %»", text.includes("книга 0 % · оси с диапазоном в книге нет") && !/0 % … 0 %/.test(text), text.match(/.{0,40}Регуляторный сценарий.{0,160}/));
  check("№ 101: торнадо — у оси-словаря ключ с наибольшим ходом, а не название типа", text.includes(`${d.regimes.rows.crisis.title} 10,0 → 25,0 % · …`) && !text.includes("словарь долей"), text.match(/.{0,60}Вероятности режимов.{0,160}/));
  check("№ 103: ключ «медиана модели» — пунктирный, как линия", !!findNode(cardOf(page, "Цена акций за 12 месяцев"), (n) => n.tagName === "I" && /key-model2/.test(n.attrs.class || "")), null);

  text = at("model");
  check("№ 102: базы терминала названы; «оценка капитала», а не «стоимость капитала V0»", text.includes("PV терминала RI") && text.includes("Доля терминала DDM") && !text.includes("Стоимость капитала V0"), text.match(/.{0,60}PV терминала.{0,80}/));
  check("№ 102: пересмотры гайденса — только смены значения", text.includes("Пересмотры гайденса · 3") && text.includes("29.04.2026 — ЧПМ: 5,90 % → 6,20 % (МСФО 1К26 (29.04.2026))")
    && !/Пересмотры гайденса · 32/.test(text), text.match(/.{0,20}Пересмотры гайденса.{0,300}/));
  const books = cardOf(page, "Книги ЧПД и передача ставки");
  const tips = [];
  const walkTh = (n) => { if (n.nodeType === 1) { if (n.tagName === "SPAN" && n.parentNode.tagName === "TH") { page.ctx.__n = n; tips.push(page.get("TIPS.get(globalThis.__n)")); } n.children.forEach(walkTh); } };
  walkTh(books);
  check("№ 102: подсказки к ρ и β", tips.some((x) => /доля разрыва ставки книги к цели/.test(x || "")) && tips.some((x) => /передача ставки опоры книги в стоимость пассива/.test(x || "")), tips);
  const bt = squash(visibleText(books));
  check("№ 103: плитки с «—» нет — причина строкой", !/—\s*раскрытая чувствительность/.test(bt) && bt.includes("Раскрытой чувствительности ЧПД к ±100 б.п. нет: не раскрыто в фактах книги."), bt.match(/.{0,80}аскрыт.{0,160}/));
  check("В12: сжатие φ — по сторонам баланса, кредитная маржа миров", bt.includes("0,290 / 0,179") && bt.includes("на кредитных книгах — 60 % сжатия φ = 0,484") && bt.includes("Кредитная маржа, п.п.") && bt.includes("3,12")
    && !bt.includes("рост кредита стоимость разрушает"), bt.match(/.{0,40}сжатие φ.{0,200}/));
  check("В15: пол вероятности режима — в подписи фильтра", text.includes("вероятность режима после наблюдений — не ниже 33 % книжной"), text.match(/.{0,60}Фильтр читает.{0,160}/));
  check("reintegrate: запись миров — версия записи семейства, не имя репозитория", text.includes("Миры: запись семейства 850, версия 1.6, кривые 18.09.2026.") && !/worlds-850|book-1\.6/.test(text), text.match(/.{0,40}Цена мира — оценка.{0,160}/));

  text = at("report");
  check("№ 73: «Уравнение словами», без номера версии", text.includes("Уравнение словами") && !/Уравнение [a-z]/.test(text), text.match(/.{0,30}Уравнение.{0,60}/));
  const now = cardOf(page, "Нау-каст");
  check("№ 103: эталоны полосы нау-каста — из журнала, в пределах оси", legendOf(now).includes("эталоны") && tipsOf(page, now, "CIRCLE").some((x) => /Эталон: РСБУ квартала/.test(x.title))
    && !tipsOf(page, now, "CIRCLE").some((x) => /год назад/.test(x.title)), [legendOf(now), tipsOf(page, now, "CIRCLE").map((x) => x.title)]);
  press(page, "CoR квартала", "Цель нау-каста");
  check("№ 103: нет интервала — нет и записи легенды", !legendOf(cardOf(page, "Нау-каст")).includes("интервал нау-каста") && legendOf(cardOf(page, "Нау-каст")).includes("ожидание модели"), legendOf(cardOf(page, "Нау-каст")));
  const impact = cardOf(page, "Что даст отчёт");
  check("№ 103: точка прогноза на «Что даст отчёт» — и без интервала", tipsOf(page, impact, "CIRCLE").some((x) => x.title === "Нау-каст квартала") && legendOf(impact).includes("нау-каст")
    && !legendOf(impact).includes("интервал нау-каста") && svgTexts(impact).some((x) => /^нау-каст 1,25 %/.test(squash(x))), [legendOf(impact), svgTexts(impact).slice(-3)]);
  check("№ 82: год — на одном слое; DPS без нау-каста — на прибыли смеси заголовка", text.includes("DPS политики на прибыли смеси заголовка (без нау-каста)")
    && text.includes("Открытый квартал: смесь заголовка и отклонение нау-каста") && Math.abs(d.nowcast.year.dps - d.nowcast.year.dps_model - d.nowcast.quarter.by_target.ni_q.deviation * 500 / d.meta.shares.issued_mln) < 2e-4,
  text.match(/.{0,60}DPS политики.{0,80}/));
  const tiles = squash(visibleText(cardOf(page, "Опережающие индикаторы")));
  check("№ 98: плитки — в единицах кодов П§0.2; нормативы банка — «норматив ЦБ»", /Собственные средства банка, форма 0409123 \d \d{3} млрд ₽/.test(tiles) && /Н1\.0 банка\d+,\d\d %август 2026 · норматив ЦБ/.test(tiles) && /Медиана целей брокеров \d+,\d\d ₽/.test(tiles)
    && /Чистая прибыль, месяц\d+,\d млрд ₽/.test(tiles), tiles.slice(0, 600));
  check("№ 100: событие формы ЦБ в календаре — окном", squash(visibleText(cardOf(page, "События"))).includes("окно 24 окт.–26 окт."), null);

  text = at("capital");
  const path = cardOf(page, "Путь нормативов");
  check("№ 103: полы нормативов — свои ключи и подписи", legendOf(path).includes(`пол ${d.capital.titles.n20}`) && legendOf(path).includes(`пол ${d.capital.titles.n11}`)
    && !!findNode(path, (n) => n.tagName === "I" && /key-neg2/.test(n.attrs.class || "")) && !!findNode(path, (n) => n.tagName === "I" && /key-neg3/.test(n.attrs.class || ""))
    && countNodes(path, (n) => n.tagName === "PATH" && n.attrs.stroke === "var(--neg)" && n.attrs["stroke-dasharray"] === "1 4") === 1, legendOf(path));
  const wide = makePage({ now: FRESH, width: 1100 });
  await wide.boot();
  await settle();
  wide.hashchange("#capital");
  const hist = cardOf(wide, "Дивиденды по году прибыли");
  const zero = d.dividends.history.find((r) => r.dps === 0), small = d.dividends.history.find((r) => r.dps > 0 && r.dps < 1);
  check("№ 105: нулевой дивиденд — подпись «0» и цель подсказки; меньше рубля — с копейками", svgTexts(hist).includes("0") && svgTexts(hist).includes(squash(page.get(`fmt.num(${small.dps}, 2)`)))
    && tipsOf(wide, hist, "RECT").some((x) => x.title === `${zero.year}: факт` && /0,00/.test(squash(x.rows[0][1]))), [zero, small, svgTexts(hist).slice(0, 12)]);
  check("№ 83: «По годам» — столбцы FVC и разовых статей", squash(visibleText(cardOf(page, "По годам"))).includes("FVC") && squash(visibleText(cardOf(page, "По годам"))).includes("Разовые")
    && squash(visibleText(cardOf(page, "По годам"))).includes("−60"), null);
  check("№ 97: заголовок ступени политики — с пробелом перед процентом", !/\d%/.test(text), text.match(/.{0,30}\d%.{0,30}/));

  text = at("book");
  check("№ 97: после многоточия точки нет", !/…\./.test(text), text.match(/.{0,40}…\..{0,20}/));
  check("reintegrate: «Миры: запись семейства 850, версия 1.6»", text.includes("Миры: запись семейства 850, версия 1.6 от 21.09.2026, sha256") && !/worlds-850/.test(text), text.match(/.{0,20}Миры:.{0,120}/));
  press(page, `Показать все ${d.judgements.rows.length}`);
  text = page.text();
  check("№ 101: диапазон оси-словаря — пары концов по ключам", text.includes(`${d.worlds.rows.N.name} 25,0 → 40,0 % · ${d.worlds.rows.H.name} 50,0 → 45,0 % · ${d.worlds.rows.M.name} 25,0 → 15,0 %`)
    && text.includes(`${d.regimes.rows.crisis.title} 10,0 → 25,0 %`) && !text.includes("словарь долей"), text.match(/.{0,40}Веса миров.{0,300}/));
  check("№ 99: срок — в годах; κ — числом", /Срок подтягивания FVOCI 4 года 2,5 года … 6 лет/.test(text) && /κ: CoR к реальной ставке сверх мира N 0,05 0 … 0,15/.test(text), text.match(/.{0,20}Срок подтягивания.{0,80}/));
  check("№ 97: сообщение гейта — предложением с заглавной", text.includes("Путь 2026 года вне гайденса (рост комиссий: 1,2 % против гайденса 0,0 %).") && text.includes("Норматив ниже пола в 4 клетках."), text.match(/.{0,40}вне гайденса \(.{0,80}/));
  check("№ 73: малое число инварианта — как допуск, без e-нотации", text.includes("1,8·10⁻¹²") && !/\de-\d/.test(text), text.match(/.{0,60}относительная разность.{0,40}/));
  const history = cardOf(page, "Отчётная история");
  check("№ 84: линия упр. метрик — по непрерывным участкам, через нераскрытое не идёт", countNodes(history, (n) => n.tagName === "PATH" && n.attrs.stroke === "var(--model)") === 2
    && countNodes(history, (n) => n.tagName === "PATH" && n.attrs.stroke === "var(--neg)" && !n.attrs["stroke-dasharray"]) === 2, countNodes(history, (n) => n.tagName === "PATH"));
  check("№ 84: провалы раскрытия — по базисам", squash(visibleText(history)).includes("Провалы раскрытия: МСФО группы, 1 кв. 2021–4 кв. 2022 — потоков МСФО квартала в фактах нет; упр., 4 кв. 2021–4 кв. 2022 — управленческие метрики квартала не раскрывались."),
    squash(visibleText(history)).slice(-260));
  check("W3: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));
}

{
  // Частные случаи W3: нет ошибки года, срок политики истёк, вход по форме ЦБ, отрицательная кредитная маржа, ось-словарь без конца,
  // раскрытая чувствительность есть, одиночная точка линии, текст ядра без типографики.
  const d = sample();
  d.nowcast.year.ni_year_se = null;
  d.nowcast.year.dps_interval = null;
  d.checks.flags.find((f) => f.name === "policy_expired").raised = true;
  d.calendar.next_ras.enters_via = "form102";
  d.calendar.next_ras.date = d.calendar.next_ras.form102_date_est;
  d.nii.transmission.loan_margin.M = -0.0031;
  d.nii.disclosed = { nii_per_100bp: 18.0, src: "годовой отчёт" };
  delete d.judgements.rows.find((r) => r.id === "regime_prob").high.crisis;
  d.dividends.ladder[0].title = "Доля 50% прибыли";
  d.dividends.ladder[0].condition = "Н20.0 после выплаты не ниже 13.30%";
  d.history.quarters[3].ifrs.cor = 0.011;
  d.guidance.revisions = d.guidance.revisions.filter((r) => r.date === "2025-12-10");
  d.worlds.source.origin = "прежняя запись";
  const page = makePage({ payload: JSON.stringify(d), now: FRESH });
  await page.boot();
  await settle();
  let text = page.text();
  check("№ 82: ошибки года нет — «интервал не оценён», без NaN", text.includes("DPS за 2026 с нау-кастом, интервал не оценён") && !BAD_TEXT.test(text), text.match(/.{0,40}DPS за 2026.{0,80}/));
  check("В17: срок политики истёк — плашка", text.includes("Срок дивидендной политики истёк: действует прежняя до новой."), text.slice(0, 400));
  page.hashchange("#report");
  text = page.text();
  check("№ 82: водопад года без ошибки — словами", text.includes("ошибка года не оценена") && text.includes("интервал не оценён") && !BAD_TEXT.test(text), text.match(/.{0,60}Прибыль акционерам 2026.{0,80}/));
  check("№ 100: вход нау-каста по форме ЦБ — окном дат", text.includes("Раньше МСФО: ≈ 24.10.2026–26.10.2026 — РСБУ банка за сентябрь 2026 (по форме 0409102, дата — оценка)"), text.match(/.{0,20}Раньше МСФО.{0,160}/));
  page.hashchange("#model");
  text = page.text();
  check("В12: отрицательная кредитная маржа мира — с пояснением", text.includes("−0,31") && text.includes("где она отрицательна, рост кредита стоимость разрушает"), text.match(/.{0,60}Кредитная маржа.{0,200}/));
  check("№ 103: раскрытая чувствительность есть — плиткой", text.includes("18 млрд ₽ раскрытая чувствительность ЧПД к ±100 б.п.") && !text.includes("Раскрытой чувствительности"), null);
  check("№ 102: значение гайденса не менялось — так и сказано", text.includes("Гайденс года с 10.12.2025 не пересматривался.") && !text.includes("Пересмотры гайденса"), text.match(/.{0,40}Гайденс года с.{0,60}/));
  check("reintegrate: запись миров без версии — без имени источника", text.includes("Миры: запись семейства 850, кривые") && !text.includes("прежняя запись"), text.match(/.{0,20}Миры:.{0,80}/));
  page.hashchange("#capital");
  text = page.text();
  check("В17: срок политики истёк — в карточке политики", text.includes("срок истёк 05.12.2026: до новой политики действует прежняя") && !text.includes("действует по 05.12.2026"), text.match(/.{0,80}срок истёк.{0,60}/));
  check("№ 97: текст ступени политики — с пробелом и запятой в процентах", text.includes("Доля 50 % прибыли") && text.includes("не ниже 13,30 %"), text.match(/.{0,20}Доля 50.{0,80}/));
  page.hashchange("#book");
  press(page, `Показать все ${d.judgements.rows.length}`);
  text = page.text();
  check("№ 101: у оси-словаря нет конца — «—»", text.includes(`${d.regimes.rows.crisis.title} 10,0 % → —`), text.match(/.{0,80}Кризис 10,0.{0,40}/));
  check("№ 84: одиночная точка линии без маркеров — точкой", countNodes(cardOf(page, "Отчётная история"), (n) => n.tagName === "CIRCLE" && n.attrs.fill === "var(--neg)" && n.attrs.r === "2.5") === 1, null);
  check("W3: частные случаи без ошибок", !page.errors.length && !/не отрисовал/.test(page.text()), page.errors.slice(0, 2));
}

/* ── 8б. печать по проверке W3 (решение P7): падеж после дробного, счётчики проверок, сверка по виду допуска, источник истории дивидендов ── */

{
  const d = sample();
  const page = makePage({ now: FRESH });
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const years = (v) => squash(page.get(`formatByUnit(${v}, "years")`));
  check("P7: после дробного числа — «года»; после целого — по числу", years(1.6) === "1,6 года" && years(2.4) === "2,4 года" && years(0.5) === "0,5 года"
    && years(1) === "1 год" && years(2) === "2 года" && years(5) === "5 лет" && years(11) === "11 лет" && years(21) === "21 год" && years(4.96) === "5,0 года",
  [1.6, 2.4, 0.5, 1, 2, 5, 11, 21, 4.96].map(years));
  check("P7: слово после числа — по напечатанному числу", page.get('plural(2.4, ["день", "дня", "дней"])') === "дня" && page.get('plural(4.6, ["день", "дня", "дней"])') === "дней"
    && page.get('plural(4.6, ["день", "дня", "дней"], 1)') === "дня" && squash(page.get("fmt.days(21)")) === "21 день", null);

  let text = at("book");
  check("P7: счётчики проверок согласованы с числом", text.includes("0 нарушенных инвариантов из 14 2 сработавших гейта из 19 1 поднятый флаг"), text.match(/.{0,20}нарушенн.{0,120}/));
  check("P7: число клеток гейта — словом в падеже числа, без «кл.»", text.includes("22 клетки · 61,0 % массы · ожидалось 40,0–80,0 %") && text.includes("4 клетки · ") && !/\d кл\./.test(text), text.match(/.{0,30}массы.{0,60}/));
  const cm = squash(visibleText(cardOf(page, "Сверка с контрольной моделью")));
  check("P7: сверка — сдвиг доли в п.п. и в столбцах уровня; допуск — в единице строки", cm.includes("передача: сдвиг спредов активов σ0 −0,11 п.п. −0,11 п.п. 0 п.п. 0,0001 п.п. в допуске"), cm.slice(0, 900));
  check("P7: сверка — разность мельче знаков допуска печатается нулём, без степени десяти", cm.includes("кредитная маржа стационара, мир M 0,58 п.п. 0,58 п.п. 0 п.п. 0,0001 п.п. в допуске") && !/10⁻¹⁷/.test(cm), cm.slice(0, 900));
  check("P7: сверка — уровень доли в %, её разность и допуск в п.п.; число — степенью, деньги — млрд ₽ и ₽", cm.includes("14,89 % 14,86 % −0,03 п.п. 0,30 п.п.") && cm.includes("0,0600 0,0600 0 1·10⁻⁶")
    && cm.includes("−30,0 млрд ₽ 584,5 млрд ₽") && cm.includes("10,0 % или 2,05 ₽") && cm.includes("коммит 5f1c0d9;"), cm.slice(0, 1500));
  check("P7: сверка — правило печати названо в подзаголовке", cm.includes("Разность и допуск — по виду допуска: относительные — в процентах, абсолютные — в единице строки (доли и сдвиги — в п.п.); разность мельче знаков допуска — ноль."), cm.slice(0, 400));

  text = at("capital");
  const hist = squash(visibleText(cardOf(page, "Дивиденды по году прибыли")));
  check("P7: источник истории дивидендов — словами выпуска, годы с одним источником — одной записью",
    hist.includes("Источники факта: 2013–2020, 2022–2025 — решение годового общего собрания акционеров (раскрытие эмитента); сверено с брокерским календарём дивидендов; 2021 — годовое общее собрание акционеров решило дивиденды не выплачивать (раскрытие эмитента)."),
    hist.slice(-400));
  check("P7: мост норматива назван расчётом модели", text.includes("расчёт модели на смеси заголовка, включая уровень на дату якоря"), text.match(/.{0,40}Мост .{0,160}/));
  text = at("book");
  check("P7: узел кривой — срок словом по числу", text.includes("сдвиг узла 5 лет к книге") && text.includes("сдвиг узла 10 лет к книге"), text.match(/.{0,20}сдвиг узла.{0,40}/));
  check("P7: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));
}

{
  // Частные случаи: счётчики на 1 и 2; гейт, сравнивающий миры целиком; строки сверки вне допуска с малой разностью;
  // один источник истории дивидендов и свой у каждого года; дробный срок на оси и в политике.
  const d = sample();
  d.checks.invariants_broken = 1;
  d.checks.flags.forEach((f) => { f.raised = ["explanation_expiring", "ni_jump"].includes(f.name); });
  const worlds = d.checks.gates.find((g) => g.name === "roe_k_homogeneity");
  Object.assign(worlds, { fired: true, mass: 1.0, cells: 0, cell_list: [], status: "explained", expected_mass: 1.0, valid_until: "2026-11-30",
    message: "разрыв между мирами 5,24 п.п. при пределе 5 п.п.", explanation: "Разрыв — цена раздельного сжатия спреда; объяснён до пересмотра книги." });
  d.checks.gates.find((g) => g.name === "capital_gap").fired = false;
  d.checks.gates.find((g) => g.name === "guidance_gap").fired = false;
  // Несработавший гейт с сообщением: в нём хвост прогонов полосы, которого в печатаемой сетке нет (М§10).
  d.checks.gates.find((g) => g.name === "roe_gt_g").message = "ROE терминала не выше роста в 0 клетках; в полосе — в 367 из 2 000 прогонов (масса таких клеток в среднем по всем прогонам — 0,64 %)";
  const noisy = d.checks.control_model.rows.find((r) => r.what.startsWith("кредитная маржа"));
  Object.assign(noisy, { control: noisy.core + 3e-6, diff: 3e-6, diff_rel: 3e-6 / noisy.core, ok: false });
  const number = d.checks.control_model.rows.find((r) => r.unit === "number");
  Object.assign(number, { control: number.core + 2e-5, diff: 2e-5, diff_rel: 2e-5 / number.core, ok: false });
  d.dividends.history.forEach((h) => { h.src = "решения годовых общих собраний акционеров (раскрытие эмитента)"; });
  d.judgements.rows.find((j) => j.id === "fvoci_maturity").low = 1.6;
  d.dividends.policy.excess.ramp_years = 2.5;
  d.live.curve.shift_bp = { 1: 4, 2: -3 };
  const page = makePage({ payload: JSON.stringify(d), now: FRESH });
  await page.boot();
  await settle();
  page.hashchange("#book");
  press(page, `Показать все ${d.judgements.rows.length}`);
  let text = page.text();
  check("P7: счётчики на 1 и 2 — «1 нарушенный инвариант», «1 сработавший гейт», «2 поднятых флага»", text.includes("1 нарушенный инвариант из 14 1 сработавший гейт из 19 2 поднятых флага"), text.match(/.{0,20}нарушенн.{0,120}/));
  check("P7: гейт, сравнивающий миры целиком, — масса без счёта клеток", text.includes(`${worlds.title}100,0 % массы · ожидалось 100,0 %`) && !/0 клеток ·|\d кл\./.test(text), text.match(/.{0,60}100,0 % массы.{0,60}/));
  const quietGates = squash(visibleText(cardOf(page, "Проверки")));
  check("аудит 02.10: сообщение несработавшего гейта печатается у его коридора — предложением",
    quietGates.includes("ROE'_T > g_T ROE терминала не выше роста в 0 клетках; в полосе — в 367 из 2 000 прогонов (масса таких клеток в среднем по всем прогонам — 0,64 %)."), quietGates.match(/.{0,40}ROE терминала не выше роста.{0,200}/));
  const cm = squash(visibleText(cardOf(page, "Сверка с контрольной моделью")));
  check("P7: сверка — строка вне допуска разность не прячет", cm.includes("+0,0003 п.п. 0,0001 п.п. вне допуска") && cm.includes("2·10⁻⁵ 1·10⁻⁶ вне допуска") && cm.includes("вне допуска — 2."), cm.slice(0, 900));
  check("P7: дробный срок на оси — «1,6 года»", /Срок подтягивания FVOCI 4 года 1,6 года … 6 лет/.test(text), text.match(/.{0,20}Срок подтягивания.{0,80}/));
  check("P7: узел кривой 1 год и 2 года", text.includes("сдвиг узла 1 год к книге") && text.includes("сдвиг узла 2 года к книге"), text.match(/.{0,20}сдвиг узла.{0,40}/));
  page.hashchange("#capital");
  text = page.text();
  check("P7: один источник истории дивидендов — одной строкой", squash(visibleText(cardOf(page, "Дивиденды по году прибыли"))).endsWith("Источник факта: решения годовых общих собраний акционеров (раскрытие эмитента)."), text.match(/.{0,40}Источники? факта.{0,160}/));
  check("P7: дробный срок ввода избытка — «за 2,5 года»", text.includes("ввод линейно за 2,5 года"), text.match(/.{0,40}ввод линейно.{0,40}/));

  const many = sample();
  many.dividends.history.forEach((h) => { h.src = h.dps ? `решение годового общего собрания акционеров ${h.year + 1} года (раскрытие эмитента)` : null; });
  const wide = makePage({ payload: JSON.stringify(many), now: FRESH });
  await wide.boot();
  await settle();
  wide.hashchange("#capital");
  const card = squash(visibleText(cardOf(wide, "Дивиденды по году прибыли")));
  check("P7: у каждого года свой источник — списком по годам; год без источника не печатается", card.includes("Источники факта по годам · 12") && card.includes("2025решение годового общего собрания акционеров 2026 года (раскрытие эмитента)")
    && !card.includes("2021решение"), card.slice(-300));
  check("P7: частные случаи без ошибок", !page.errors.length && !wide.errors.length && !/не отрисовал/.test(page.text() + wide.text()), page.errors.concat(wide.errors).slice(0, 2));
}

/* ── 10. форма панели: карточки по узлам, слова общей формы — по данным (DASHBOARD §2, §3) ── */

// Мост трёх прибылей и месячная таблица релиза — карточки формы Т, мёртвые для формы Совкомбанка: сняты с витрины (узлы в образце есть, карточек нет).
const T_ONLY_CARDS = ["Три прибыли: мост", "Операционные результаты и формы ЦБ по месяцам"];
const PANEL_CARDS = ["Пределы и срок", "Путь ROE и роста капитала к терминалу",
  "Рост, на который хватает капитала", "Цена правила", "Квартальные DPS", "Число акций и события"];
// Слова общей формы: на форме панели их нет ни на одном экране.
const GENERIC_WORDS = ["обеих категорий", "сквозь цикл", "Купон AT1", "AT1 / T2", "РСБУ банка по месяцам", "Месяцы РСБУ банка", "РСБУ банка за", "попадёт в нау-каст", "оценка квартала по РСБУ", "сезонный мост",
  "Проверка формулы на истории", "порог дивидендной политики", "порог политики", "Условие капитала", "ГОСА", "Банки-аналоги", "Капитал банка оценивается"];
// Часы страницы — день после публикации формы панели.
const FRESH_P = Date.parse("2026-10-08T09:00:00+03:00");
const pagePanel = (opts = {}) => page0({ payload: SAMPLE_TEXT, now: FRESH_P, ...opts });
const allText = (page) => SCREEN_NAMES.map((name) => { page.hashchange(`#${name}`); return page.text(); });
const titles = (page) => { const out = []; const walk = (n) => { if (n.nodeType === 1) { if (n.tagName === "H2") out.push(squash(visibleText(n))); n.children.forEach(walk); } }; walk(page.app); return out; };
const hasCard = (page, title) => titles(page).some((t) => t.startsWith(title));
const plain = (node) => squash(visibleText(node)).replace(/­/g, "");
// Кнопка переключателя с подсказкой-долей («Жёсткий 26 %»): по началу подписи.
const pressLike = (page, label, group) => {
  const b = findNode(page.app, (n) => n.tagName === "BUTTON" && n.textContent.startsWith(label) && n.parentNode.attrs["aria-label"] === group);
  if (b) { b.dispatch("click"); page.paint(); }
  return !!b;
};
// Выпуск формы панели без её необязательных узлов (П§2, поля «?» панели).
function stripPanel(d) {
  for (const k of ["divisor_mln", "divisor_basis", "divisor_label", "depositary_block_mln", "economic_treasury_mln", "corporate_actions"]) delete d.meta.shares[k];
  delete d.meta.basis_labels;
  delete d.history.ltm.roe_issuer;
  delete d.history.three_profits;
  delete d.paths.fade;
  delete d.nowcast.ops;
  d.nowcast.retro = {};                     // блока ретро-проверки нет (сборка без индикаторов): карточки нет, заглушки нет
  for (const k of ["requirement", "growth", "rule_price"]) delete d.capital[k];
  delete d.capital.anchor.estimated;
  delete d.dividends.model_quarters;
  delete d.dividends.cap_check;
  delete d.fair_value.bank_first_line.rub_per_1pp_buffer;
  d.reverse_dcf.bank_rows = d.reverse_dcf.bank_rows.slice(0, 3);
  d.checks.flags = d.checks.flags.filter((f) => !["deal_pending", "capital_estimated"].includes(f.name));
  for (const list of [d.dividends.register, d.dividends.history, d.market.ex_dividend, d.fair_value.bridge.rows]) for (const r of list) { delete r.period; delete r.label; }
  for (const k of ["period", "label", "yield_period"]) delete d.dividends.next_expected[k];
  return d;
}

{
  const d = panel();
  const t1 = MAIN, one = d.meta.company.tickers;
  check("панель: в фикстуре одна категория акций и схема двери", one.length === 1 && d.schema === "svcb-v1" && t1 !== one[0], [one, d.schema]);
  for (const width of [640, 343]) {
    const page = pagePanel({ width });
    await page.boot();
    await settle();
    for (const name of SCREEN_NAMES) {
      page.hashchange(`#${name}`);
      const text = page.text();
      const bad = text.match(new RegExp(`.{0,60}(${BAD_TEXT.source}|не отрисовал).{0,60}`));
      check(`панель: экран ${name} (${width} px) без ошибок и NaN`, page.get("CURRENT") === name && !page.errors.length && !bad && countTag(page.app, "SVG") > 0, page.errors.slice(0, 2).concat(bad ? bad[0] : []));
      page.errors.length = 0;
    }
  }

  const page = pagePanel();
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const screens = allText(page);
  const seen = SCREEN_NAMES.flatMap((name) => { at(name); return titles(page); });
  check("панель: все карточки панели нарисованы", PANEL_CARDS.every((t) => seen.some((x) => x.startsWith(t))), PANEL_CARDS.filter((t) => !seen.some((x) => x.startsWith(t))));
  const words = GENERIC_WORDS.filter((w) => screens.some((t) => t.includes(w)));
  check("панель: слов общей формы нет ни на одном экране", words.length === 0, words.map((w) => `${w}: ${(screens.find((t) => t.includes(w)).match(new RegExp(`.{0,50}${w}.{0,30}`)) || [])[0]}`));
  check("панель: «нет блока» и пустых заглушек на месте узлов нет", !screens.some((t) => /В этом выпуске нет блока|нет данных/.test(t)), screens.map((t) => (t.match(/.{0,60}нет блока.{0,40}/) || [])[0]).filter(Boolean));
  const orphans = [];
  for (const name of SCREEN_NAMES) { at(name); orphans.push(...legendOrphans(page).map((x) => `${name}: ${x}`)); }
  check("панель: каждая запись легенды соответствует нарисованному элементу", orphans.length === 0, orphans.slice(0, 8));

  // «Оценка»: одна категория, делитель, подписи базиса, дивиденд по периоду
  let text = at("overview");
  const hero = findNode(page.app, (n) => n.attrs.class === "card hero-chart");
  check("панель: одна линия рынка — без пунктира второй категории и без тикера в подписях", !findNode(hero, (n) => n.tagName === "I" && /key-market2/.test(n.attrs.class || ""))
    && countNodes(hero, (n) => n.tagName === "LINE" && n.attrs.stroke === "var(--market)") === 1 && text.includes("к цене +") && !text.includes(`к ${one[0]} `) && text.includes("ниже рыночной цены —"),
  text.match(/.{0,30}рыночной цены.{0,40}/));
  check("панель: бровь экрана называет тикер из выпуска", text.includes(`Справедливая стоимость акции · ${one[0]} · 07.10.2026`), text.match(/Справедливая стоимость.{0,40}/));
  const L = d.meta.basis_labels;
  check("панель: паспорт — ROE эмитента, запас Н20.1 до требования, квартальный DPS и реестр с отсчётом", text.includes("ROE эмитента за 12 мес.") && text.includes(`запас ${d.capital.titles.n11} до его требования, оценка`)
    && text.includes("DPS за полугодие 2026 года (объявлен); реестр 12.10.2026, через 5 дней") && text.includes("дивдоходность: четыре ближайших квартала, без объявления — по политике")
    && text.includes(`+1,2 п.п. запас ${d.capital.titles.n20} до требования с глиссадой (3К’26), оценка; до требования года — +1,7 п.п.`), text.match(/.{0,40}ROE эмитента.{0,400}/));
  check("панель: подписи базиса прибыли, ROE и делителя — строкой паспорта", text.includes(`Прибыль в P/E и ROE — ${L.profit}; ROE — ${L.roe}; ROE эмитента — ${d.history.ltm.roe_issuer.label}; на акцию — ${L.divisor}.`), text.match(/Прибыль в P\/E.{0,300}/));
  check("панель: цена запаса капитала и ROE термином книги — плиткой", text.includes("Цена 1 п.п. ROE после фазы роста") && !text.includes("олгосрочн") && /1 п\.п\. запаса капитала — −\d+ ₽/.test(text), text.match(/.{0,40}запаса капитала.{0,40}/));
  check("панель: вменённый ROE — заголовком строки выпуска, срок — словом", text.includes("Рынку нужен вменённый ROE после фазы роста 16,7 % против 19,5 % книги. В цене — 2 года избыточной доходности."), text.match(/Рынку нужен.{0,160}/));
  check("панель: отсчёт — заголовок события месячного релиза, оценочные даты с «≈» и окном", text.includes("≈ 16дней — операционные результаты за сентябрь 2026 года (≈ 23.10.2026)")
    && text.includes("≈ 43дня — МСФО за 3 кв. 2026 (≈ 19.11.2026, окно 3 нояб.–30 нояб.)") && text.includes("два ритма: месячный релиз и формы ЦБ и квартальная МСФО группы"), text.match(/.{0,20}дней — .{0,200}/));
  check("панель: дивиденд — периодом словами выпуска, доходность квартальной выплаты, реестр с отсчётом", text.includes("Дивиденд за полугодие 2026 года") && text.includes("доходность квартальной выплаты к цене")
    && text.includes("дата реестра, через 5 дней") && text.includes("За полугодие 2026 года") && text.includes("За первый квартал 2026 года"), text.match(/Дивиденд за.{0,300}/));
  check("панель: события — оценочная дата «≈» и окно, у точной даты «≈» нет", text.includes("≈ 23 окт.≈ через 16 дней") && text.includes("12 окт.через 5 дней") && text.includes("окно 21 окт.–27 окт."), text.match(/События.{0,400}/));
  check("панель: «Как читать» — делитель и базис прибыли подписями выпуска, без слов о двух категориях",
    text.includes(`на 2 682,7 млн: ${L.divisor}. База — МСФО группы; прибыль — ${L.profit}.`) && !text.includes("Одна справедливая стоимость на обе"), text.match(/.{0,80}млн: .{0,200}/));
  check("панель: флаги сделки и оценки нормативов — плашки; ярлык выпуска не желтеет", text.includes("Объявлена сделка, в книге её нет. Закрытие сделки") && text.includes("Нормативы якоря — оценка до выхода формы. Форма 0409805 на 30.06.2026 ещё не вышла.")
    && page.get('document.querySelector("#release-chip").dataset.state') === "ok", text.slice(0, 500));
  check("панель: последний день покупки скоро — период словами записи", text.includes("Последний день покупки скоро: дивиденд 4,70 ₽ за полугодие 2026 года — 09.10.2026, через 2 дня."), text.slice(0, 900));
  check("панель: события недели — решение о дивиденде и сделка", text.includes("События недели: 01.10.2026 — решение собрания о дивиденде за полугодие 2026 года (4,70 ₽ на акцию); 01.10.2026 — объявлена покупка доли"), text.slice(0, 1100));

  // «Что в цене»: пределы и срок, цена за год
  text = at("market");
  const limits = cardOf(page, "Пределы и срок");
  check("панель: пределы — обе границы, цена и точка на одной шкале, срок — крупно", svgTexts(limits).some((x) => squash(x).startsWith("капитал без премии 262 ₽")) && svgTexts(limits).some((x) => squash(x).startsWith("без опережающего роста 305 ₽"))
    && squash(visibleText(limits)).includes("2 года избыточной доходности в цене") && countNodes(limits, (n) => n.tagName === "RECT" && n.attrs.fill === "var(--model)") === d.reverse_dcf.bank_rows[5].by_year.length,
  [svgTexts(limits), squash(visibleText(limits)).slice(0, 300)]);
  const price = cardOf(page, "Цена акции за 12 месяцев");
  const marks = tipsOf(page, price, "LINE");
  check("панель: цена за год — экс-даты по периодам и отметка дробления", marks.filter((t) => t.title === "Экс-дата дивиденда").length === d.market.ex_dividend.length
    && marks.some((t) => t.rows.some((r) => r[0] === "решение" && r[1] === "за 2025 год")) && marks.some((t) => t.note === "цены до этой даты пересчитаны" && t.title === "Дробление акций 1 к 10")
    && legendOf(price).includes("дробление") && squash(visibleText(price)).includes(`Прибыль — ${L.profit}.`), [marks.map((t) => t.title), legendOf(price)]);
  check("панель: аналоги — нейтральный заголовок, у строки эмитента подпись базиса", text.includes("Аналоги на одной базе") && !text.includes("Банки-аналоги") && text.includes(d.market.peers.rows[0].basis), text.match(/Аналоги.{0,300}/));
  check("панель: язык банка — термин книги из заголовка строки и подпись базиса ROE", text.includes("вменённый ROE после фазы роста: нужен рынку / в книге") && text.includes("ROE после фазы роста / стоимость капитала (λ книги)")
    && squash(visibleText(cardOf(page, "Капитал: модель против рынка"))).includes(`ROE — ${L.roe}.`), text.match(/.{0,60}нужен рынку \/ в книге.{0,120}/));

  // «Расчёт»: путь к терминалу, три прибыли, гайденс, сетка
  text = at("model");
  const fade = cardOf(page, "Путь ROE и роста капитала к терминалу");
  check("панель: путь к терминалу — три линии и угасание", countNodes(fade, (n) => n.tagName === "PATH") === 3 && squash(visibleText(fade)).includes("20,6 → 19,5 % ROE терминала на капитале без избытка: до угасания → после")
    && squash(visibleText(fade)).includes("0,50 множитель угасания избыточной доходности") && squash(visibleText(fade)).includes(`ROE — ${L.roe}.`), squash(visibleText(fade)).slice(0, 500));
  check("панель: мост трёх прибылей формы Т не рисуется и при узле выпуска", !!d.history.three_profits && !hasCard(page, "Три прибыли: мост"), titles(page));
  check("панель: гайденс — пол «≥», строка без числа и «не сравнивается»; слова стратегии нет", text.includes("≥ 20,0 %") && text.includes("эмитент числа не называет") && text.includes("не сравнивается")
    && text.includes("Гайденс 2026 против пути модели") && !text.includes("и стратегия") && text.includes("Пересмотры гайденса · 1"), text.match(/Гайденс 2026.{0,500}/));
  check("панель: сетка — флаг урезанного роста, невязка доли прироста — в подсказке", text.includes("◔ рост урезан капиталом") && tipsOf(page, cardOf(page, "Сетка:"), "TD").some((t) => /доля прироста найдена с невязкой/.test(t.note || "")), null);
  check("панель: «Расчёт» — капитал группы, делитель словами выпуска", text.includes("Капитал группы оценивается напрямую") && text.includes(`на 2 682,7 млн: ${L.divisor}; точка`), text.match(/.{0,60}млн: .{0,80}/));
  check("панель: дерево ROE — нейтральные заголовки и подпись базиса", text.includes("Услуги и комиссии") && text.includes("Доход пакета") && !text.includes("Непрофильный"), null);

  // «Ближайший отчёт»: месячная таблица панели, нау-каст без РСБУ
  text = at("report");
  check("панель: месячная таблица релиза формы Т не рисуется и при узле выпуска", !!d.nowcast.ops && !hasCard(page, "Операционные результаты и формы ЦБ по месяцам"), titles(page));
  check("панель: карточки РСБУ общей формы нет", !hasCard(page, "Месяцы РСБУ") && text.includes("месячный релиз эмитента и формы ЦБ — наблюдение"), titles(page));
  const now = squash(visibleText(cardOf(page, "Нау-каст")));
  check("панель: нау-каст — прогноз равен ожиданию модели, без оценки по РСБУ и моста", now.includes("цель — квартал МСФО; к цене не подключён") && !now.includes("входы —") && now.includes(`ожидание модели, слой «${d.layers.analytical.title}» (упр.)`)
    && now.includes("нау-каст ± 3,4 млрд ₽"), now.slice(0, 500));
  press(page, "Стоимость риска квартала", "Цель нау-каста");
  check("панель: нау-каст без ошибки — «ожидание модели», без «—»", squash(visibleText(cardOf(page, "Нау-каст"))).includes("нау-каст: ожидание модели"), squash(visibleText(cardOf(page, "Нау-каст"))).slice(0, 400));
  check("панель: окно формы 0409102 — оценкой, без слов о РСБУ", text.includes("Форма 0409102 за сентябрь 2026 — ≈ 24.10.2026–26.10.2026 (дата — оценка)") && !text.includes("РСБУ банка за"), text.match(/Форма 0409102 за.{0,160}/));
  check("панель: год → DPS без купона; квартальная политика словами окна базы", text.includes("сумма решений за кварталы прибыли года, база решения — средняя прибыль 4 последних кварталов, на размещённые акции")
    && text.includes("проверка капитала") && text.includes(`Прибыль — ${L.profit}.`), text.match(/Прибыль 2026 → .{0,400}/));
  const tiles = squash(visibleText(cardOf(page, "Опережающие индикаторы")));
  check("панель: плитки — клиенты числом, примечание плитки строкой", /Клиенты всего, млн56,1август 2026 · упр\./.test(tiles), tiles.slice(0, 300));
  press(page, "Таблица");
  check("панель: календарь — сделка вне книги и право отзыва", squash(visibleText(cardOf(page, "События"))).includes("в книге нет") && squash(visibleText(cardOf(page, "События"))).includes("Право отзыва бессрочного субординированного займа"), null);

  // «Капитал и дивиденды»
  text = at("capital");
  const kp = squash(visibleText(cardOf(page, "Капитал на")));
  check("панель: капитал на дату — оценка до выхода формы, без бессрочных инструментов и нормативов банка", kp.startsWith("Капитал на 30.06.2026 — оценка до выхода формы") && kp.includes("регуляторные инструменты капитала")
    && kp.includes(`${d.capital.titles.n11_observed} на 31.03.2026: 10,42 %. Последнее наблюдение`) && !kp.includes(d.capital.titles.n1_0) && kp.includes(`на 2 682,7 млн: ${L.divisor}`)
    && kp.includes("требование года: минимум с надбавками + запас"), kp.slice(0, 900));
  const path = cardOf(page, "Путь нормативов");
  check("панель: требование с глиссадой — ступенями по кварталам, без точек кварталов и порога политики", legendOf(path).includes("требование с глиссадой") && legendOf(path).includes("требование без глиссады")
    && legendOf(path).includes(`${d.capital.titles.n11} с прибылью периода`) && countNodes(path, (n) => n.tagName === "PATH" && / H[\d.]+ V/.test(n.attrs.d || "")) === 3
    && squash(visibleText(path)).includes("по 0,25 п.п. за квартал за 4 кв. до ступени") && !squash(visibleText(path)).includes("полые точки"), [legendOf(path), squash(visibleText(path)).slice(0, 300)]);
  const growth = () => cardOf(page, "Рост, на который хватает капитала");
  const pairs = d.capital.growth.potential.filter((v) => v !== null).length;
  check("панель: рост — пары столбцов, доля урезанного, вероятность урезания, порядок словами", countNodes(growth(), (n) => n.tagName === "RECT" && n.attrs.fill === "var(--series-neutral)") === pairs
    && svgTexts(growth()).some((x) => squash(x) === "−1,8 %") && squash(visibleText(growth())).includes("54 % наибольшая вероятность урезания роста — в 2028 году")
    && squash(visibleText(growth())).includes("При нехватке капитала первым уступает рост портфеля; дивиденд снижается только при нулевом росте."), [svgTexts(growth()).slice(0, 14), squash(visibleText(growth())).slice(0, 300)]);
  pressLike(page, d.capital.scenarios.strict.title, "Сценарий капитала");
  check("панель: переключатель сценария меняет рост и требование", squash(visibleText(growth())).startsWith(`Рост, на который хватает капитала: ${d.capital.scenarios.strict.title}`) && svgTexts(growth()).some((x) => squash(x) === "−3,8 %")
    && !page.errors.length, [svgTexts(growth()).slice(0, 14), page.errors.slice(0, 1)]);
  press(page, "Ожидание", "Сценарий капитала");
  const rule = cardOf(page, "Цена правила");
  check("панель: цена правила — три замыкания, замыкание книги отмечено", countNodes(rule, (n) => n.tagName === "TR") === 4 && (squash(visibleText(rule)).match(/в книге/g) || []).length === 1
    && squash(visibleText(rule)).includes("Без ограничения роста капиталом 372,4 ₽ +11,6 ₽ +9,9 ₽ 18,6 %"), squash(visibleText(rule)));
  // книга с записью сухого перевывода развилок (М§14.5): разности с точкой и медианой книги, медианы в рублях нет; без цены — причина
  const RP = d.capital.rule_price.rows, rp = squash(visibleText(rule));
  check("панель: цена правила (запись сухого перевывода) — разности с точкой и медианой книги, строка без цены — с причиной", rp.includes("К точке книги") && rp.includes("К медиане книги")
    && !rp.includes("Медиана") && rp.includes(`${RP[2].title}${RP[2].why} — без цены — —`) && rp.includes("малая полоса на общих случайных числах"), rp.slice(0, 400));
  const pol = squash(visibleText(cardOf(page, "Дивидендная политика")));
  check("панель: политика — потолок и периодичность, проверка потолка вместо формулы до копейки", pol.includes("до 30 %Выплата по политике —") && pol.includes("Проверка потолка выплат") && pol.includes("2025 40,0 174,4 22,9 % 30 % в пределах")
    && pol.includes("год не завершён") && pol.includes(`База — ${L.profit}, средняя за 4 последних квартала; решения — ежеквартально; делитель — размещённые акции; нехватка капитала — остаток сверх требований; потолок — до 30 % прибыли года.`)
    && pol.includes("догоняющая выплата — нет") && pol.includes("срок действия в Положении не ограничен"), pol.slice(0, 1200));
  const nextCard = squash(visibleText(cardOf(page, "Следующая выплата")));
  check("панель: следующая выплата — период, отсчёты, капитал без порога, источники из выпуска", nextCard.startsWith("Следующая выплата: за полугодие 2026 года") && nextCard.includes("последний день покупки, через 2 дня")
    && nextCard.includes("дата реестра, через 5 дней") && nextCard.includes(`Капитал: ожидаемый ${d.capital.titles.n20} в квартале вычета этой выплаты —`) && nextCard.includes("документ эмитента + T-Invest")
    && nextCard.includes("Реестр сборщиков (документы эмитента, брокерский календарь) и факты книги") && nextCard.includes("01.10.2026"), nextCard.slice(0, 900));
  const qd = cardOf(page, "Квартальные DPS");
  const mq = d.dividends.model_quarters.filter((q) => !q.declared).length;
  check("панель: квартальные DPS — факт (решённые кварталы — один раз) и модель с усами и отметкой политики", countNodes(qd, (n) => n.tagName === "LINE" && n.attrs.stroke === "var(--ink)") === mq
    && countNodes(qd, (n) => n.tagName === "RECT" && n.attrs.fill === "var(--market)") === d.dividends.history.length && d.dividends.register.every((r) => d.dividends.history.some((h) => h.period === r.period))
    && tipsOf(page, qd, "RECT").some((t) => t.title === "За 2025 год: решение собрания" && t.rows.some((r) => r[0] === "объявлено до дробления" && squash(r[1]) === "45,00 ₽"))
    && tipsOf(page, qd, "RECT").some((t) => squash(t.title) === "3 кв. 2026: модель" && t.rows.some((r) => r[0] === "решение" && squash(r[1]) === "4 кв. 2026")), tipsOf(page, qd, "RECT").map((t) => t.title).slice(0, 12));
  const hist = cardOf(page, "Дивиденды по году прибыли");
  check("панель: дивиденды по годам — факт суммой кварталов, год без решения за 4-й квартал не рисуется", tipsOf(page, hist, "RECT").filter((t) => / факт$/.test(t.title)).map((t) => t.title).join() === "2025: факт"
    && squash(visibleText(hist)).includes("сумма кварталов года") && squash(visibleText(hist)).includes("Источники факта по годам · 8"), [tipsOf(page, hist, "RECT").map((t) => t.title), squash(visibleText(hist)).slice(-300)]);
  const sh = squash(visibleText(cardOf(page, "Число акций и события")));
  check("панель: число акций — делитель с подписью, депозитарный блок, события", sh.includes(`2 682,7 делитель: ${L.divisor}`) && sh.includes("132,8 собственные акции") && sh.includes("на счёте депозитарных программ")
    && sh.includes("15.04.2026 дробление Дробление акций 1 к 10 1 к 10") && sh.includes("дивиденд уходит из капитала по акциям в обращении"), sh.slice(0, 900));
  const bridge = squash(visibleText(cardOf(page, "Мост капитала")));
  check("панель: мост капитала — строки реестра по периодам, ₽ на акцию делителя", bridge.includes(`₽ на акцию (${L.divisor})`) && bridge.includes("за полугодие 2026 года: 4,70 ₽") && bridge.includes("за первый квартал 2026 года: 4,60 ₽"), bridge.slice(0, 600));
  check("панель: «По годам» — без пустого столбца FVC, с подписью базиса", !squash(visibleText(cardOf(page, "По годам"))).includes("FVC") && squash(visibleText(cardOf(page, "По годам"))).includes("C/I упр.")
    && squash(visibleText(cardOf(page, "По годам"))).includes(`Прибыль — ${L.profit}. ROE — ${L.roe}.`), null);

  // «Допущения»
  text = at("book");
  check("панель: «Допущения» — цена правила ссылкой, оценка нормативов в свежести, подписи базиса тремя строками", text.includes("Цена правила — оценка при трёх замыканиях капитала: «Капитал и дивиденды» →")
    && /Нормативы якоря\s*оценка до выхода формы группы/.test(text) && text.includes(`Прибыль — ${L.profit}. ROE — ${L.roe}. На акцию — ${L.divisor}.`), text.match(/.{0,40}Цена правила.{0,120}/));
  check("панель: счётчики проверок — знаменатель по длине списка выпуска", text.includes(`4 сработавших гейта из ${d.checks.gates.length}`) && d.checks.gates.length === 28 && text.includes("3 поднятых флага") && text.includes("Объявлена сделка, в книге её нет"), text.match(/.{0,20}нарушенн.{0,140}/));
  const hc = cardOf(page, "Отчётная история");
  press(page, "Таблица");
  check("панель: история — ROE эмитента столбцом, базис подписью", legendOf(hc).length > 0 && squash(visibleText(cardOf(page, "Отчётная история"))).includes(`Прибыль — ${L.profit}. ROE — ${L.roe}.`), null);
  check("панель: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));
}

{
  // Форма панели без её необязательных узлов и общая форма: ни одной карточки панели и ни одной заглушки на их месте.
  for (const [name, payload, now] of [["панель без узлов", JSON.stringify(stripPanel(panel())), FRESH_P], ["общая форма", GENERIC_TEXT, FRESH]]) {
    const page = page0({ payload, now });
    await page.boot();
    await settle();
    const seen = [], texts = [];
    for (const s of SCREEN_NAMES) { page.hashchange(`#${s}`); seen.push(...titles(page)); texts.push(page.text()); }
    const drawn = PANEL_CARDS.filter((t) => seen.some((x) => x.startsWith(t)));
    const bad = texts.join(" ").match(new RegExp(`.{0,60}(${BAD_TEXT.source}|не отрисовал|нет данных).{0,60}`));
    check(`${name}: карточек панели нет, заглушек на их месте нет, экраны живы`, drawn.length === 0 && !bad && !page.errors.length && !page.bootError, [drawn, bad && bad[0], page.errors.slice(0, 2)]);
    if (name === "панель без узлов") check("панель без блока ретро-проверки: карточки «Эталоны на истории» нет, заглушки нет", !seen.some((t) => t.startsWith("Эталоны на истории"))
      && !texts.join(" ").includes("ретро-проверка эталонов"), seen.filter((t) => t.startsWith("Эталоны")));
    if (name === "общая форма") {
      const all = texts.join(" ");
      check("общая форма: слова общей формы печатаются там, где данные их оправдывают", ["обеих категорий", "Купон AT1 после налога", "Месяцы РСБУ банка", "Проверка формулы на истории", "порог дивидендной политики", "AT1 / T2",
        "оценка квартала по РСБУ", "РСБУ за сентябрь 2026 попадёт в нау-каст"].every((w) => all.includes(w)), null);
    } else {
      const all = texts.join(" ");
      check("панель без узлов: делитель — акции в обращении, запись дивиденда — по году", all.includes("млн акций в обращении") && all.includes("Дивиденд за 2026") && all.includes("полые точки — первые кварталы смеси"), all.match(/.{0,40}млн акций.{0,40}/));
    }
  }
  // Частные случаи панели: норматив фактом, сделка в книге, недостижимый срок, «в цене 0 лет», ближайшая выплата по политике, год без решения.
  const d = panel();
  d.capital.anchor.estimated = false;
  d.checks.flags = d.checks.flags.filter((f) => f.name !== "capital_estimated");
  const years = d.reverse_dcf.bank_rows.find((r) => r.key === "excess_return_years");
  Object.assign(years, { implied: null, status: "unreachable" });
  Object.assign(d.dividends.next_expected, { period: "2026Q3", label: null, status: "model", dps: 5.02, dps_policy: 5.02, dps_mean: 4.94, dps_p10: 4.1, dps_p90: 5.1, p_cancel: 0.02,
    record_date: null, record_date_est: "2027-01-11", record_date_note: "по прошлым решениям: через две недели после собрания", last_buy_date: null });
  d.history.annual.find((a) => a.year === 2025).dps = null;
  let page = pagePanel({ payload: JSON.stringify(d) });
  await page.boot();
  await settle();
  let text = page.text();
  check("панель: норматив фактом — пометки и плашки оценки нет", !text.includes("оценка до выхода формы") && !/до его требования, оценка/.test(text) && text.includes("до его требования"), text.match(/.{0,40}до его требования.{0,30}/));
  check("панель: срок недостижим — словами", text.includes("В цене — больше избыточной доходности, чем даёт модель вместе с терминалом."), text.match(/В цене — .{0,100}/));
  check("панель: ближайшая выплата по политике — период подписью, риск отмены", text.includes("Дивиденд за 3 кв. 2026") && text.includes("DPS по политике · риск отмены 2 %") && text.includes("ожидаемая дата реестра")
    && text.includes("DPS за 3 кв. 2026 (по политике); реестр ≈ 11.01.2027"), text.match(/Дивиденд за.{0,300}/));
  page.hashchange("#market");
  check("панель: недостижимый срок — крупно словом", squash(visibleText(cardOf(page, "Пределы и срок"))).includes("недостижимо избыточной доходности в цене"), squash(visibleText(cardOf(page, "Пределы и срок"))).slice(0, 400));
  page.hashchange("#capital");
  check("панель: год без решения за четвёртый квартал — факта года нет, карточка жива", !tipsOf(page, cardOf(page, "Дивиденды по году прибыли"), "RECT").some((t) => / факт$/.test(t.title)) && !page.errors.length, page.errors.slice(0, 2));
  Object.assign(years, { implied: 0, status: "solved", market_excess: -29.4 });
  page = pagePanel({ payload: JSON.stringify(d) });
  await page.boot();
  await settle();
  check("панель: капитализация не выше капитала — «в цене 0 лет»", page.text().includes("В цене — 0 лет избыточной доходности: капитализация не выше капитала."), page.text().match(/В цене — .{0,100}/));
}

/* ── 11. узлы волны № 6: термины книги, печатаемая маржа, связка, гейты знака, база суммы дивиденда, строка против требования ── */

{
  const d = panel();
  const page = pagePanel();
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const T = d.meta.terms, n11 = d.capital.titles.n11, worldM = d.worlds.rows.M.name, worldH = d.worlds.rows.H.name;
  // Книга с ключом уровня: ключ цели и есть суждение — рядом с осью стоят слова о нём, второго числа нет.
  const printed = `суждение книги — стационарная маржа мира «${worldM}» на составе баланса якоря`;

  // «Оценка»
  let text = at("overview");
  check("№ 6: запас второго норматива — число выпуска, в подсказке — норматив и требование", text.includes(`+3,1 п.п. запас ${n11} до его требования, оценка`)
    && tipsOf(page, findNode(page.app, (n) => n.attrs.id === "passport"), "DIV").some((t) => t.title === n11 && squash(t.rows[0].join(" ")) === "на отчётную дату 10,60 %" && squash(t.rows[1].join(" ")) === "требование года 7,50 %"),
  text.match(/.{0,30}до его требования.{0,30}/));
  check("№ 6: «ROE после фазы роста» — термин книги из словаря выпуска", text.includes(`Цена 1 п.п. ${T.roe_lt}`) && text.includes(`${T.roe_lt} 1`) && !text.includes("олгосрочн"), text.match(/Цена 1 п\.п\..{0,160}/));
  check("№ 8: строка обратного расчёта по ключу цели маржи — суждение названо словами, решение и значение книги — числа самой строки",
    squash(visibleText(cardOf(page, "Что заложено в цену"))).includes(`${printed} 10,47 %книга 11,1 % · в диапазоне книги`) && !text.includes("ключ цели"), squash(visibleText(cardOf(page, "Что заложено в цену"))).slice(0, 400));

  // «Что в цене»
  text = at("market");
  const rev = () => squash(visibleText(cardOf(page, "Обратный расчёт по осям книги")));
  check("№ 8: обратный расчёт — у строки маржи суждение словами и уровни смеси при корне; у прочих строк подписи нет",
    rev().includes(`книга 11,1 % · диапазон 10,3 % … 11,6 %${printed}смесь заголовка при нём печатает ЧПМ 9,87 %, CoR 5,60 %, C/I 49,6 %`)
    && (rev().match(/стационарная маржа мира/g) || []).length === 1, rev().slice(0, 500));
  check("№ 6: корень на краю отрезка поиска — «недостижимо» с причиной словами выпуска", rev().includes("недостижимокорень на краю отрезка поиска") && !rev().includes("4,31 %"), rev().match(/Запас менеджмента.{0,200}/));
  press(page, "Таблица");
  check("№ 8: таблица обратного расчёта — суждение о марже под именем оси", rev().includes(`ЧПМ после фазы роста (при рыночных ставках, на балансе якоря)${printed} 10,47 % 11,1 % 10,3 % … 11,6 %`), rev().slice(0, 500));
  press(page, "График");
  const price = cardOf(page, "Цена акции за 12 месяцев");
  check("№ 6: дивдоходность за 12 месяцев — четыре последних объявленных квартала из узла дивидендов", squash(visibleText(price)).includes("6,4 % дивдоходность за 12 мес.: объявленные кварталы прибыли 3К’25–2К’26")
    && Math.abs(d.dividends.yield_ltm[d.meta.company.main_ticker] - 17.4 / d.market.price) < 1e-6 && d.dividends.yield_ltm_periods.length === 4, squash(visibleText(price)).slice(-400));
  check("№ 6: отметка дробления — с коэффициентом числом", tipsOf(page, price, "LINE").some((t) => t.note === "цены до этой даты пересчитаны" && t.rows.some((r) => r[0] === "коэффициент" && r[1] === "1 к 10")),
    tipsOf(page, price, "LINE").map((t) => t.rows));
  const tornado = squash(visibleText(cardOf(page, "Цена по одному суждению")));
  check("№ 6: связка в «торнадо» — именем оси и концами первого пути", tornado.includes("Гибкость расходов и услуг к портфелю") && tornado.includes("0,3 … 0,7"), tornado.slice(0, 600));

  // «Расчёт»
  text = at("model");
  press(page, "Ещё 7 карточек");
  const trans = () => squash(visibleText(cardOf(page, "Книги ЧПД и передача ставки")));
  check("№ 8: ЧПМ после фазы роста — суждение и выведенный уровень мира-опоры рядом, оба мира именами выпуска", trans().includes(`11,10 / 11,31 % ЧПМ ${T.lt_level}, упр.: суждение книги — `
    + `стационарная маржа мира «${worldM}» на составе баланса якоря / выведенный из неё уровень мира-опоры «${worldH}»; ключ в движке — 10,98 %`), trans().slice(0, 700));
  const tree = cardOf(page, "Дерево ROE");
  check("№ 6: строка вне основного бизнеса — термином книги: в шапке без скобок, целиком — в подсказке", squash(visibleText(tree)).includes("Доход пакета") && !squash(visibleText(tree)).includes("возврат процентов")
    && tipsOf(page, tree, "SPAN").includes("Доход пакета (возврат процентов по долгу под него)") && !text.includes("Вне осн. бизнеса"), tipsOf(page, tree, "SPAN"));
  const sc = squash(visibleText(cardOf(page, "Регуляторные сценарии капитала")));
  check("№ 6: объяснение гейта знака стресса — в карточке сценариев капитала", sc.includes(`Гейт «${d.checks.gates.find((g) => g.name === "stress_sign").title}»`), sc.slice(-300));

  // «Капитал и дивиденды»
  text = at("capital");
  const kp = squash(visibleText(cardOf(page, "Капитал на")));
  check("№ 6: капитал на дату — запас второго норматива рядом с требованием", kp.includes(`${n11} на 30.06.2026; требование 7,50 %, запас +3,10 п.п.`), kp.match(/.{0,40}требование 7.{0,60}/));
  const path = () => cardOf(page, "Путь нормативов");
  const R = d.capital.requirement;
  check("№ 6: с требованием сравнивается второй норматив с прибылью периода; отчётный — пунктиром и справочно", legendOf(path()).includes(`${n11} с прибылью периода`) && legendOf(path()).includes(`${n11} отчётный — справочно`)
    && squash(visibleText(path())).includes(`${n11}: ${R.notes.n11_star}; ${R.notes.n11}.`) && R.mix.n11.some((v, i) => v < R.mix.req11_glide[i] && R.mix.n11_star[i] > R.mix.req11_glide[i]),
  [legendOf(path()), squash(visibleText(path())).slice(-500)]);
  const keyOf = (name) => { let cls = null; const walk = (n) => { if (n.nodeType !== 1) return; if (n.tagName === "SPAN" && squash(visibleText(n)) === name) { const i = n.children.find((c) => c.tagName === "I"); if (i) cls = i.attrs.class; } n.children.forEach(walk); }; walk(path()); return cls; };
  check("№ 6: в легенде норматив с прибылью периода — сплошной ключ, отчётный — пунктирный", /key-third$/.test(keyOf(`${n11} с прибылью периода`) || "") && /key-third2$/.test(keyOf(`${n11} отчётный — справочно`) || ""),
    [keyOf(`${n11} с прибылью периода`), keyOf(`${n11} отчётный — справочно`)]);
  press(page, "Таблица");
  const yearRow = squash(visibleText(path())).match(/2027 [^А-Яа-я]{0,120}/);
  check("№ 6: таблица пути нормативов — второй норматив с прибылью периода рядом с требованием с глиссадой, отчётный — последним столбцом",
    squash(visibleText(path())).includes(`${n11} с прибылью периода Требование ${n11} с глиссадой ${n11} отчётный — справочно`)
    && squash(visibleText(path())).includes(squash([R.years_mix.n11_star[1], R.years_mix.req11_glide[1], d.capital.mix.n11[1]].map((v) => page.get(`fmt.pct(${v}, 2)`)).join(" "))), yearRow);
  press(page, "График");
  pressLike(page, d.capital.scenarios.strict.title, "Сценарий капитала");
  check("№ 6: у сценария годового ряда с прибылью периода нет — таблица без его столбцов, экран жив", !page.errors.length && legendOf(path()).includes(`${n11} с прибылью периода`), page.errors.slice(0, 2));
  press(page, "Ожидание", "Сценарий капитала");
  const growth = squash(visibleText(cardOf(page, "Рост, на который хватает капитала")));
  check("№ 6: объяснение гейта знака объёмных эффектов — в карточке роста", growth.includes(`Гейт «${d.checks.gates.find((g) => g.name === "volume_sign").title}»`), growth.slice(-300));
  const rule = squash(visibleText(cardOf(page, "Цена правила")));
  check("№ 6: строки «цены правила» — подписями выпуска", d.capital.rule_price.rows.every((r) => rule.includes(r.title)), rule);
  const bridge = squash(visibleText(cardOf(page, "Мост капитала")));
  const nextCard = squash(visibleText(cardOf(page, "Следующая выплата")));
  const L = d.meta.basis_labels;
  check("№ 6: сумма дивиденда — с базой: мост — на акции в обращении, реестр — на все размещённые", bridge.includes("Сумма, млрд ₽") && bridge.includes(`Сумма дивиденда — ${L.dividend_outstanding}. Мост не несёт`)
    && nextCard.includes("Сумма, млрд ₽") && nextCard.includes(`Сумма дивиденда — ${L.dividend_issued}. `) && !nextCard.includes("Пул, млрд"), [bridge.slice(-260), nextCard.slice(-360)]);
  const sh = squash(visibleText(cardOf(page, "Число акций и события")));
  check("№ 6: коэффициент дробления — числом выпуска", typeof d.meta.shares.corporate_actions[1].factor === "number" && sh.includes("Дробление акций 1 к 10 1 к 10"), sh.slice(-300));

  // «Допущения»
  text = at("book");
  const judg = () => squash(visibleText(cardOf(page, "Суждения книги по цене ошибки")));
  check("№ 8: суждение о марже — ключ цели и есть суждение: слова о нём без второго числа, диапазон — самого суждения", judg().includes(`ЧПМ после фазы роста 11,1 %${printed} 10,3 % … 11,6 %`)
    && !judg().includes("ключа цели"), judg().slice(0, 500));
  const flex = d.judgements.rows.find((r) => r.kind === "bundle");
  check("№ 6: связка — именем оси, значением и концами первого пути, без имён ключей книги", judg().includes(`${flex.name} 0,5связка: чисел книги — ${flex.paths.length}, к своим концам идут вместе; в строке — первое 0,3 … 0,7`)
    && flex.book === flex.ends.book[flex.paths[0]] && flex.low === flex.ends.low[flex.paths[0]] && !/volume_link|real_growth|\[object/.test(SCREEN_NAMES.map(at).join(" ")), judg().match(/Гибкость.{0,200}/));
  at("overview");
  const drivers = cardOf(page, "Что определяет полосу");
  check("№ 6: связка во вкладах в полосу — именем оси; в подсказке — диапазон первого пути", tipsOf(page, drivers, "DIV").some((t) => t.title === flex.name && t.rows.some((r) => r[0] === "диапазон книги" && r[1] === "0,3 … 0,7")),
    tipsOf(page, drivers, "DIV").map((t) => t.title));
  text = at("book");
  const gates = squash(visibleText(cardOf(page, "Проверки")));
  const G = Object.fromEntries(d.checks.gates.map((g) => [g.name, g]));
  check("№ 6: гейты знака — в общем списке: заголовок, масса, срок, сообщение и объяснение", ["volume_sign", "stress_sign"].every((k) => gates.includes(G[k].title) && gates.includes(G[k].explanation))
    && (gates.match(/Объяснение действует по 31\.03\.2027 включительно/g) || []).length >= 3 && gates.includes("меняет точку на −6,40 ₽ (372,40 → 366,00 ₽)")
    && gates.includes(`${G.volume_sign.title}100,0 % массы`) && gates.includes(`${G.stress_sign.title}2 клетки · 2,7 % массы`), gates.slice(0, 900));
  check("№ 6: метки клеток в сообщении и списке гейта — словами выпуска", gates.includes(`${worldM} · ${d.regimes.rows.downturn.title} · ${d.capital.scenarios.strict.title} против ${worldM} · ${d.regimes.rows.downturn.title} · ${d.capital.scenarios.schedule.title}`)
    && !/[NHM]\/(soft|norm|downturn|crisis)\//.test(gates), gates.match(/.{0,80}против M.{0,80}/));
  findNode(page.app, (n) => n.tagName === "SUMMARY" && n.textContent.startsWith("Коридоры несработавших гейтов")).parentNode.attrs.open = "";
  const quiet = squash(visibleText(cardOf(page, "Проверки")));
  check("№ 8: несработавший гейт окна фактов — коридор и сообщение: маржа слоя рядом с наибольшим кварталом окна", quiet.includes(G.window_backtest.title) && quiet.includes(G.window_backtest.corridor.text)
    && quiet.includes("ЧПМ 10,05 % при наибольшем квартале окна фактов 9,98 % и доле кредитов в процентных активах 71,2 % — гейтом не сверяется.") && !G.nim_stationary,
  quiet.match(/.{0,60}вне окна фактов.{0,500}/));
  check("№ 6: слово отношения расходов к доходам в заголовке гейта и на экранах — одно", gates.includes("C/I года вне коридора") && !SCREEN_NAMES.map(at).join(" ").includes("CIR"), null);
  check("№ 6: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));
}

{
  // Слова — из выпуска: термин, подпись базы и строка «цены правила» меняются вместе с ним; без узлов волны экраны прежние.
  const d = panel();
  Object.assign(d.meta.terms, { cir: "Расходы/доходы", roe_lt: "ROE зрелого бизнеса", stake: "вложение вне основного бизнеса", noncore: "доход вложения" });
  d.meta.basis_labels.dividend_issued = "на размещённые акции — метка";
  d.capital.rule_price.rows[0].title = "Замыкание без ограничения — метка";
  d.meta.shares.corporate_actions[1].factor = { v: 10, src: "узел-факта" };
  let page = pagePanel({ payload: JSON.stringify(d) });
  await page.boot();
  await settle();
  let all = allText(page).join(" ");
  check("№ 6: термины, подпись базы суммы и строка «цены правила» — из выпуска, не из кода", all.includes("Расходы/доходы упр.") && !all.includes("C/I упр.") && all.includes("Цена 1 п.п. ROE зрелого бизнеса")
    && all.includes("Доход вложения") && all.includes("Сумма дивиденда — на размещённые акции — метка.")
    && all.includes("Замыкание без ограничения — метка"), all.match(/.{0,40}метка.{0,40}/g));
  check("№ 6: коэффициент не числом — прочерк, а не содержимое узла", !all.includes("1 к [object") && !all.includes("узел-факта") && all.includes("Дробление акций 1 к 10 —") && !page.errors.length, all.match(/.{0,40}Дробление акций.{0,60}/));

  const bare = panel();
  delete bare.meta.terms;
  for (const k of ["dividend_issued", "dividend_outstanding"]) delete bare.meta.basis_labels[k];
  delete bare.capital.anchor.n11_headroom;
  for (const k of ["compare", "notes"]) delete bare.capital.requirement[k];
  delete bare.capital.requirement.years_mix.n11_star;
  for (const k of ["amount_basis", "yield_ltm_periods"]) delete bare.dividends[k];
  delete bare.fair_value.bridge.amount_basis;
  delete bare.nii.transmission.level;
  for (const k of ["levels", "modal_cell"]) delete bare.paths[k];
  delete bare.book.reference_variants;
  delete bare.reverse_dcf.refine_rows;
  for (const k of ["book_version", "valuation_date", "n_rows", "n_bad", "all_ok"]) delete bare.checks.control_model[k];
  for (const k of ["req20_glide_next", "req20_glide_period", "n20_headroom_glide"]) delete bare.capital.anchor[k];
  for (const r of bare.reverse_dcf.rows) for (const k of ["stationary_book", "stationary_solved", "levels_solved", "reason", "gap_basis"]) delete r[k];
  for (const k of ["volume_sign", "stress_sign", "funds_cost_to_key"]) delete bare.checks[k];
  bare.checks.gates = bare.checks.gates.filter((g) => !["nim_stationary", "window_backtest", "funds_cost_to_key", "volume_sign", "stress_sign"].includes(g.name));
  bare.judgements.rows = bare.judgements.rows.filter((r) => r.kind !== "bundle");
  page = pagePanel({ payload: JSON.stringify(bare) });
  await page.boot();
  await settle();
  all = allText(page).join(" ");
  const bad = all.match(new RegExp(`.{0,60}(${BAD_TEXT.source}|не отрисовал).{0,60}`));
  check("№ 6: выпуск без узлов волны — родовые слова и прежние подписи, экраны живы", !bad && !page.errors.length && all.includes("Цена 1 п.п. долгосрочного ROE") && all.includes("C/I упр.") && all.includes("Вне осн. бизнеса")
    && all.includes(`${bare.capital.titles.n11} против требования, оценка`) && !all.includes("Сумма дивиденда —") && !all.includes("стационарная маржа") && !all.includes("ключ цели;") && !all.includes("На чём стоит заголовок") && !all.includes("Цена правил и развилок")
    && !/диапазона\s?оценка по подвыборке/.test(all) && !all.includes("Окно фактов") && all.includes("13 строк, вне допуска — 0.") && !all.includes("сводка на книге")
    && !all.includes("с глиссадой к концу") && all.includes("дивиденды за 12 мес. к цене")
    && !all.includes("отчётный — справочно"), [bad && bad[0], page.errors.slice(0, 2)]);
  page.hashchange("#capital");
  check("№ 6: без строки против требования — прежняя легенда пути нормативов", legendOf(cardOf(page, "Путь нормативов")).includes(`${bare.capital.titles.n11} с прибылью периода`)
    && !legendOf(cardOf(page, "Путь нормативов")).includes("отчётный"), legendOf(cardOf(page, "Путь нормативов")));
}

/* ── 12. на чём стоит заголовок: суждение о марже и уровни, цена правил, требование с глиссадой, подписи по находкам проверки ── */

{
  const d = panel();
  const page = pagePanel();
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const worldM = d.worlds.rows.M.name, worldH = d.worlds.rows.H.name, n20 = d.capital.titles.n20, n11 = d.capital.titles.n11, L = d.paths.levels, mc = d.paths.modal_cell;
  const pct = (v, k) => squash(page.get(`fmt.pct(${v}, ${k})`));
  // Кнопка «Таблица» / «График» своей карточки.
  const pressIn = (card, label) => { const b = findNode(card, (n) => n.tagName === "BUTTON" && n.textContent === label); if (b) { b.dispatch("click"); page.paint(); } return !!b; };

  // «Оценка»
  let text = at("overview");
  const lv = () => cardOf(page, "На чём стоит заголовок");
  const lvText = () => squash(visibleText(lv()));
  check("уровни: суждение о марже — стационарная маржа мира уровня; уровень мира-опоры — выведенным числом, оба мира именами выпуска", lvText().includes(`Суждение книги о марже — стационарная маржа при ставках мира «${worldM}» на составе баланса якоря, упр.: 11,10 %; `
    + `уровень мира-опоры «${worldH}» выведен из неё — 11,31 %.`) && lvText().startsWith(`На чём стоит заголовок: уровни ${d.meta.terms.lt_level}`) && !lvText().includes("ключ цели"), lvText().slice(0, 400));
  check("уровни: четыре строки выпуска с долей кредитов; смесь заголовка названа строкой, на которой стоит оценка", L.order.every((k) => lvText().includes(
    `${L.rows[k].title} ` + [pct(L.rows[k].nim, 2), pct(L.rows[k].cor, 2), pct(L.rows[k].cir, 1), pct(L.rows[k].loans_share, 1)].join(" ")))
    && lvText().includes(`средние за ${L.from_year}–${L.to_year} годы, упр. базис; кредиты — доля в процентных активах`) && lvText().includes("C/I Кредиты")
    && lvText().includes("Оценка стоит на строке «смесь заголовка»: клетки под вероятностями точки."), lvText().slice(400, 1100));
  check("уровни: модальная клетка — именами выпуска (мир, режим, сценарий), с весом в слое и в смеси и ценой клетки", lvText().includes(`${L.rows.modal_cell.title} — ${worldH} · ${d.regimes.rows.norm.title} · ${d.capital.scenarios.mid.title}: `
    + `вес ${pct(mc.p_analytical, 1)} в слое «${d.layers.analytical.title}» и ${pct(mc.p_point, 1)} в смеси; цена клетки ${squash(page.get(`fmt.rub(${mc.price})`))}.`), lvText().slice(600, 1100));
  check("уровни: путь прибыли смеси рядом с путём модальной клетки, ссылка на путь смеси по годам", legendOf(lv()) === "смесь заголовкамодальная клетка"
    && countNodes(lv(), (n) => n.tagName === "PATH" && n.attrs.stroke === "var(--model)" && !n.attrs["stroke-dasharray"]) === 1
    && countNodes(lv(), (n) => n.tagName === "PATH" && n.attrs.stroke === "var(--third)" && !!n.attrs["stroke-dasharray"]) === 1
    && tipsOf(page, lv(), "CIRCLE").some((t) => t.title === "модальная клетка: ’27" && squash(t.rows[0][1]) === squash(page.get(`fmt.bn(${mc.ni_sh[1]}, 0)`)))
    && !!findNode(lv(), (n) => n.tagName === "A" && n.attrs.href === "#capital" && n.textContent === "Путь смеси по годам"), [legendOf(lv()), tipsOf(page, lv(), "CIRCLE").slice(0, 2)]);
  const passTips = tipsOf(page, findNode(page.app, (n) => n.attrs.id === "passport"), "DIV");
  check("A13: паспорт — запас до требования с глиссадой и до требования года; в подсказке — оба требования", text.includes(`+1,2 п.п. запас ${n20} до требования с глиссадой (3К’26), оценка; до требования года — +1,7 п.п.`)
    && passTips.some((t) => t.title === n20 && t.rows.some((r) => r[0] === "требование с глиссадой" && squash(r[1]) === "11,51 %") && t.rows.some((r) => squash(r[1]) === "11,00 %")), passTips.map((t) => t.rows));
  check("A15: DPS года на первом экране — «по политике» и ожидание по клеткам", text.includes("19,64 ₽ DPS за 2026 по политике, интервал 19,5–19,8 ₽ожидание по клеткам — 18,81 ₽: урезано капиталом в 3 % массы, без выплаты — 0 %")
    && text.includes("дивдоходность: четыре ближайших квартала, без объявления — по политике") && text.includes("прибыль 2026: факт + ожидание модели"), text.match(/.{0,40}DPS за 2026.{0,120}/));

  // «Что в цене»
  text = at("market");
  const tornado = squash(visibleText(cardOf(page, "Цена по одному суждению")));
  check("A17: диапазон оси маржи — самого суждения, без оговорки о ключе; премия средств клиентов — концами первого пути связки", tornado.includes("10,3 % … 11,6 %") && !tornado.includes("ключ цели")
    && tornado.includes("Премия роста средств клиентов с 2027 года") && tornado.includes("−5,0 п.п. … +5,0 п.п."), tornado.slice(0, 500));
  const price = squash(visibleText(cardOf(page, "Цена акции за 12 месяцев")));
  check("A55: цена оценки — «последняя сделка» со временем, ряд — закрытия основной сессии", price.includes("последняя сделка · 07.10.2026 18:49 МСК") && price.includes("дневные закрытия основной сессии")
    && !price.includes("цена · 07.10.2026"), price.match(/.{0,30}07\.10\.2026.{0,60}/));

  // «Расчёт»
  text = at("model");
  press(page, "Ещё 7 карточек");
  const guide = squash(visibleText(cardOf(page, "Гайденс 2026")));
  check("A16: цель ROE эмитента — «не сравнивается», без модели и массы; пустого столбца «нужно в остатке года» нет", guide.includes("Цель ROE эмитента (к операционному капиталу)упр. 30,0 % 27,40 % — не сравнивается —")
    && !guide.includes("Нужно в остатке года") && d.guidance.items.every((r) => r.required_rest === null), guide.slice(0, 700));
  text = page.text();
  check("A52: служебных обозначений на «Расчёте» нет — подписи словами и терминами выпуска", !/A-P2u|k_T|g_T|ROE._T|CoR LT|ЧПМ LT/.test(text) && text.includes("после наблюдений кварталов")
    && text.includes(`После наблюдений CoR ${d.meta.terms.lt_level} Сдвиг ЧПМ ${d.meta.terms.lt_level}`)
    && text.includes(`Вес: ${d.layers.analytical.title.toLowerCase()} Вес: ${d.layers.market_implied.title.toLowerCase()} Стоимость капитала Рост терминала Цена мира`) && !text.includes("Свой вес")
    && tipsOf(page, cardOf(page, "Сетка:"), "TD").every((t) => t.rows.some((r) => r[0] === `${d.meta.terms.roe_lt} / стоимость капитала`)), text.match(/.{0,60}(A-P2u|k_T|g_T|CoR LT).{0,60}/));
  const gov = cardOf(page, "Дисконт за управление");
  check("A54: основания каналов дисконта — во всю ширину под водопадом, а не в колонке названий", squash(visibleText(gov)).includes(`Основания каналов · ${d.governance.components.length}`)
    && d.governance.components.every((c) => squash(visibleText(gov)).includes(`${c.name}: ${squash(page.get(`ruText(${JSON.stringify(c.basis)})`))}`))
    && !findNode(gov, (n) => (n.attrs.class || "") === "wf-name" && !!findNode(n, (h) => (h.attrs.class || "") === "hint")), squash(visibleText(gov)).slice(0, 500));
  const trans = squash(visibleText(cardOf(page, "Книги ЧПД и передача ставки")));
  check("уровни: «Расчёт» — суждение о марже и выведенный уровень мира-опоры одной плиткой", trans.includes("11,10 / 11,31 %") && trans.includes(`суждение книги — стационарная маржа мира «${worldM}» на составе баланса якоря`), trans.slice(0, 600));

  // «Ближайший отчёт»
  text = at("report");
  check("A49: прибыль квартала подписана одним базисом — базисом цели выпуска; слой ожидания назван", text.includes("Факт отчётных кварталов (упр.)") && !text.includes("Факт отчётных кварталов (МСФО группы)")
    && text.includes(`ожидание модели, слой «${d.layers.analytical.title}» (упр.)`), text.match(/.{0,20}Факт отчётных.{0,60}/));
  check("A15: карточка года — DPS по политике и ожидание по клеткам рядом", text.includes("19,64 ₽ DPS по политике: 26 % базы на 2 682,7 млн акций; интервал 19,48–19,80 ₽ожидание по клеткам — 18,81 ₽: урезано капиталом в 3 % массы, без выплаты — 0 %"),
    text.match(/.{0,20}DPS по политике.{0,160}/));
  press(page, "Ещё 6 карточек");
  const retro = () => cardOf(page, "Эталоны на истории");
  check("A49: ретро — базис цели и подпись прибыли; главный эталон с историей — в легенде", squash(visibleText(retro())).includes("прибыль квартала (упр.)") && squash(visibleText(retro())).includes(`Прибыль — ${d.meta.basis_labels.profit}.`)
    && legendOf(retro()).includes("главный эталон:"), squash(visibleText(retro())).slice(0, 300));

  // «Капитал и дивиденды»
  text = at("capital");
  const kp = squash(visibleText(cardOf(page, "Капитал на")));
  check("A13: капитал на дату — требование с глиссадой и запас до него рядом с требованием года", kp.includes("11,51 % требование с глиссадой к концу 3 кв. 2026: с ним сравнивает норматив правило роста")
    && kp.includes("+1,20 п.п. запас до требования с глиссадой к концу 3 кв. 2026") && kp.includes("+1,71 п.п. запас до требования (минимум с надбавками + запас)"), kp.slice(0, 700));
  const path = () => cardOf(page, "Путь нормативов");
  const R = d.capital.requirement;
  check("A13: годовой путь — против требования с глиссадой; требование года — тонкой линией; Н20.1 с прибылью периода — основной линией", legendOf(path()).includes(`требование ${n20} с глиссадой`)
    && legendOf(path()).includes("требование года, без глиссады") && legendOf(path()).startsWith(`${n20}${n11} с прибылью периода${n11} отчётный — справочно`)
    && R.years_mix.req20_glide.some((v, i) => v > d.capital.mix.req20[i]), legendOf(path()));
  pressIn(path(), "Таблица");
  check("A13: таблица пути — требование с глиссадой рядом с нормативом, требование года — отдельным столбцом", squash(visibleText(path())).includes(`Год ${n20} Требование с глиссадой Требование года Пол`)
    && squash(visibleText(path())).includes([R.years_mix.req20_glide[1], d.capital.mix.req20[1], d.capital.mix.floor20[1]].map((v) => pct(v, 2)).join(" ")), squash(visibleText(path())).match(/Год .{0,260}/));
  pressIn(path(), "График");
  const growth = () => squash(visibleText(cardOf(page, "Рост, на который хватает капитала")));
  check("A14: плитки роста — экстремумы рядов, а не год якоря; нулевой плитки навёрстывания нет", growth().includes("54 % наибольшая вероятность урезания роста — в 2028 году")
    && growth().includes("48 % наименьшая доля прироста за квартал — в 2028 году") && growth().includes("12,6 % урезано на конец 2036 г.") && !growth().includes("навёрстано за год")
    && !/урезания роста — в 2026 году/.test(growth()) && typeof d.capital.growth.potential[0] === "number", growth().slice(300, 800));
  pressLike(page, d.capital.scenarios.strict.title, "Сценарий капитала");
  check("A14: у сценария плитки вероятности и доли прироста названы плитками смеси; доля урезанного — сценария", growth().includes("в 2028 году (смесь заголовка)")
    && growth().includes(`${pct(d.capital.growth.by_scenario.strict.cut_share[10], 1)} урезано на конец 2036 г.`) && !legendOf(path()).includes(`требование ${n20} с глиссадой`), growth().slice(300, 800));
  press(page, "Ожидание", "Сценарий капитала");
  const next = cardOf(page, "Следующая выплата");
  check("A48: плашка источников — по их счёту", squash(visibleText(next)).includes("документ эмитента + T-Invest + Интерфакс3 источника") && squash(visibleText(next)).includes("документ эмитента + T-Investдва источника"),
    squash(visibleText(next)).match(/.{0,60}Источники.{0,100}/g));
  const qd = () => cardOf(page, "Квартальные DPS");
  pressIn(qd(), "Таблица");
  check("A48, A15, A33: у решённых кварталов — DPS политики, дата решения и срок выплаты «до» из выпуска; отмена квартала — столбцом", squash(visibleText(qd())).includes("2 кв. 2026решение собрания 4,70 ₽ 4,76 ₽ — — 01.10.2026 до 26.10.2026")
    && squash(visibleText(qd())).includes("1 кв. 2026решение собрания 4,60 ₽ 4,55 ₽ — — 30.07.2026 до 24.08.2026") && squash(visibleText(qd())).includes("По политике P10–P90 Без выплаты Решение Выплата")
    && squash(visibleText(qd())).includes("4 кв. 2026модель 4,57 ₽ 5,31 ₽ 0,00–5,42 15 %"), squash(visibleText(qd())).match(/2 кв\. 2026.{0,200}/));
  pressIn(cardOf(page, "Дивиденды по году прибыли"), "Таблица");
  check("A15: строка года — «без выплаты» за весь год; отмена квартала — в квартальной таблице", squash(visibleText(cardOf(page, "Дивиденды по году прибыли")))
    .includes("без выплаты за весь год — отмена решения за отдельный квартал видна в «Квартальных DPS»"), null);
  check("A52: терминал в «По годам» — словами", squash(visibleText(cardOf(page, "По годам"))).includes("Терминал: ROE 19,5 %, стоимость капитала 18,1 %, рост 7,4 %"), squash(visibleText(cardOf(page, "По годам"))).slice(-400));

  // «Допущения»
  text = at("book");
  const lb = cardOf(page, "На чём стоит заголовок");
  check("уровни на «Допущениях» — та же таблица без графика, со ссылкой на путь смеси", countTag(lb, "SVG") === 0 && countNodes(lb, (n) => n.tagName === "TR") === L.order.length + 1
    && !!findNode(lb, (n) => n.tagName === "A" && n.attrs.href === "#capital"), squash(visibleText(lb)).slice(0, 200));
  const vr = cardOf(page, "Цена правил и развилок");
  const V = d.book.reference_variants;
  const notesOf = (r) => [r.note, r.why, r.mark, r.median_mark].filter(Boolean).join("");
  const vrow = (r) => (r.d_point === null ? `${r.title}${notesOf(r)} — без цены —`
    : `${r.title}${notesOf(r)} ${squash(page.get(`fmt.rub(${r.point}, 1)`))} ${squash(page.get(`fmt.signedRub(${r.d_point}, 1)`))} ${squash(page.get(`fmt.signedRub(${r.d_median}, 1)`))}`);
  check("цена правил и развилок (запись сухого перевывода) — строки выпуска: точка, разности с точкой и медианой книги, строка без цены с причиной, база разностей в подвале",
    countNodes(vr, (n) => n.tagName === "TR") === V.rows.length + 1 && V.rows.some((r) => r.d_point === null) && V.rows.some((r) => r.median_mark)
    && V.rows.every((r) => squash(visibleText(vr)).includes(vrow(r))) && squash(visibleText(vr)).includes("К медиане книги")
    && squash(visibleText(vr)).includes(`На цене и дате книги точка — ${squash(page.get(`fmt.rub(${V.point}, 2)`))}; в выпуске варианты не пересчитываются.`)
    && squash(visibleText(vr)).includes(`${V.basis.charAt(0).toUpperCase()}${V.basis.slice(1)}.`) && squash(visibleText(vr)).includes("−118,6 ₽"), squash(visibleText(vr)).slice(0, 500));
  const judg = squash(visibleText(cardOf(page, "Суждения книги по цене ошибки")));
  const prem = d.judgements.rows.find((r) => r.id === "funds_premium");
  check("A17: центр премии роста средств клиентов виден — уровень первого пути связки, а не «без сдвига»", prem.kind === "bundle" && prem.book === 0
    && judg.includes(`${prem.name} 0,0 п.п.связка: чисел книги — ${prem.paths.length}, к своим концам идут вместе; в строке — первое −5,0 п.п. … +5,0 п.п.`), judg.match(/Премия роста средств.{0,200}/));
  const phone = pagePanel({ width: 343 });
  await phone.boot();
  await settle();
  phone.hashchange("#book");
  const moreBtn = findNode(phone.app, (n) => n.tagName === "BUTTON" && n.textContent === "Ещё 2 карточки");
  check("A54: сверка с контрольной моделью и отчётная история на «Допущениях» — под «ещё 2 карточки»", !!moreBtn && !!findNode(moreBtn.parentNode, (n) => n.tagName === "H2" && n.textContent.startsWith("Сверка с контрольной моделью")), null);
  phone.hashchange("#capital");
  check("A14: на узком экране подпись доли урезанного — короче, а не пропуск", svgTexts(cardOf(phone, "Рост, на который хватает капитала")).some((x) => squash(x) === "−2")
    && svgTexts(cardOf(phone, "Рост, на который хватает капитала")).some((x) => squash(x) === "−13"), svgTexts(cardOf(phone, "Рост, на который хватает капитала")).slice(0, 24));
  check("финальная волна: экраны без ошибок", !page.errors.length && !phone.errors.length, page.errors.concat(phone.errors).slice(0, 2));
}

{
  // Частные случаи: ключ цели решён вне диапазона книги; гайденс без смен; наблюдение равно якорю; навёрстывание включено; главный эталон без истории.
  const d = panel();
  const row = d.reverse_dcf.rows.find((r) => r.paths.includes("nii.nim_lt_target_mgmt"));
  Object.assign(row, { solved: 0.1183, delta: 0.0073, in_range: false, stationary_solved: 0.1183 });
  Object.assign(d.reverse_dcf.rows.at(-1), { kind: "shift", unit: "pp", book: 0, solved: 0.0236, delta: 0.0236, in_range: false, status: "solved" });   // последняя строка «вне диапазона» — в п.п.
  d.guidance.revisions.forEach((r) => { if (r.key === "op_np_growth") r.value = 0.2; });
  Object.assign(d.capital.observed, { n1_1: d.capital.anchor.n11_bank.value, as_of: d.capital.anchor.n11_bank.as_of });
  Object.assign(d.capital.growth, { catch_up_rate: 0.25, catch_up: d.capital.growth.years.map((y, i) => (i === 4 ? 27.4 : 0)) });
  for (const h of [d.nowcast.retro, ...Object.values(d.nowcast.retro.by_horizon)]) { h.main = "model"; h.titles.model = "ожидание модели без индикаторов"; }
  const page = pagePanel({ payload: JSON.stringify(d) });
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  let text = at("overview");
  const teaser = squash(visibleText(cardOf(page, "Что заложено в цену")));
  check("ключ цели — суждение, решён вне диапазона книги: в строке «вне диапазона» — одно число, без оговорки о ключе", teaser.includes("Вне диапазона книги: ЧПМ после фазы роста 11,83 %; ") && !teaser.includes("ключ цели"),
    teaser.match(/Вне диапазона книги.{0,200}/));
  check("строка «вне диапазона» кончается одной точкой и тогда, когда последнее значение — в п.п.", teaser.endsWith("п.п.") && !teaser.includes("п.п.."),
    teaser.match(/Вне диапазона книги.{0,400}/));
  text = at("model");
  check("A47: гайденс без смен — дата, с которой он стоит в нынешнем составе, а не первая запись цели без года", text.includes("Гайденс года с 19.02.2026 не пересматривался.") && !text.includes("28.11.2024")
    && d.guidance.revisions.some((r) => r.date === "2024-11-28"), text.match(/.{0,40}Гайденс года с.{0,60}/));
  text = at("report");
  press(page, "Ещё 6 карточек");
  const retro = cardOf(page, "Эталоны на истории");
  check("A49: главный эталон без истории — в легенде его нет, сказано словами", legendOf(retro) === "факт" && squash(visibleText(retro)).includes("У главного эталона (ожидание модели без индикаторов) истории ещё нет: зачёт начнётся с первого события.")
    && legendOrphans(page).length === 0, [legendOf(retro), legendOrphans(page)]);
  text = at("capital");
  const kp = squash(visibleText(cardOf(page, "Капитал на")));
  check("A46: наблюдение формы, равное плитке якоря, второй строкой не печатается", !kp.includes("Последнее наблюдение") && kp.includes(`${d.capital.titles.n11} на 30.06.2026`), kp.slice(-300));
  check("A14: навёрстывание включено — плитка «навёрстано» есть", squash(visibleText(cardOf(page, "Рост, на который хватает капитала"))).includes("27,4 млрд ₽ навёрстано за год, наибольшее"), null);
  check("частные случаи финальной волны: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));

  // Быстрая сборка: цена на краях суждений не считалась — так и сказано, заглушки «нет блока» нет.
  const f = panel();
  f.meta.fast = true;
  for (const j of f.judgements.rows) Object.assign(j, { price_low: null, price_high: null, swing: null, mean_shift: null, status: "not_computed", reason: "быстрая сборка: поиски не считались" });
  const fast = pagePanel({ payload: JSON.stringify(f) });
  await fast.boot();
  await settle();
  fast.hashchange("#market");
  check("быстрая сборка: «Цена по одному суждению» — «не считалась», а не «нет блока»", fast.text().includes("В быстрой сборке цена на краях суждений не считалась.") && !fast.text().includes("В этом выпуске нет блока")
    && !fast.errors.length, fast.text().match(/Цена по одному суждению.{0,120}/));

  // Книга с целью печатаемой маржи (узел `nim_lt_printed`, поля `printed_*`) — прежние подписи рядом с ключом цели.
  const p = panel();
  delete p.nii.transmission.level;
  Object.assign(p.nii.transmission, { nim_lt_target_mgmt: 0.1075, target_eng: 0.1063, nim_lt_printed: { value: 0.1111, target: 0.111, tolerance: 0.001, from_year: 2030, to_year: 2036, cell: "H/norm/mid" } });
  const r = p.reverse_dcf.rows.find((x) => x.paths.includes("nii.nim_lt_target_mgmt"));
  for (const k of ["stationary_book", "stationary_solved", "levels_solved"]) delete r[k];
  Object.assign(r, { printed_book: 0.1111, printed_solved: 0.0994 });
  const old = pagePanel({ payload: JSON.stringify(p) });
  await old.boot();
  await settle();
  const all = allText(old).join(" ");
  check("книга с целью печатаемой маржи: рядом с ключом цели — маржа модальной клетки, слов о стационарной марже нет", all.includes("ключ цели; модальная клетка печатает 11,11 %, при нужном рынку значении — 9,94 %")
    && all.includes(`10,75 / 11,11 % ЧПМ ${p.meta.terms.lt_level}, упр.: ключ цели / печатает модальная клетка (${p.worlds.rows.H.name} · ${p.regimes.rows.norm.title} · ${p.capital.scenarios.mid.title}) в среднем за 2030–2036 годы`)
    && !all.includes("стационарная маржа") && all.includes("Уровни клеток и слоёв — результат") && !old.errors.length, [all.match(/.{0,40}модальная клетка печатает.{0,80}/), old.errors.slice(0, 1)]);
}

/* ── 13. ключ уровня маржи, окно фактов под таблицей уровней, базы «пределов», имена миров и слоёв, подписи по находкам проверки ── */

{
  const d = panel();
  const page = pagePanel();
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const text = (card) => squash(visibleText(card));
  const L = d.paths.levels, W = L.window, V = d.book.reference_variants, R = d.reverse_dcf, cm = d.checks.control_model;
  const rub = (v, k = 0) => squash(page.get(`fmt.rub(${v}, ${k})`)), signed = (v) => squash(page.get(`fmt.signedRub(${v})`));
  const WINDOW_LINE = "Окно фактов, от наименьшего квартала до наибольшего: ЧПМ 9,12…9,98 % (среднее 9,61 %); CoR 4,69…6,65 % (среднее 5,64 %); C/I 46,0…48,3 % (среднее 47,0 %); "
    + "кредиты — 63,6 % в среднем за окно, 67,7 % на дату якоря.";
  const ABOVE = " ЧПМ всех строк выше наибольшего квартала окна";
  const WHY = ": состав баланса у них другой — кредитов в процентных активах больше, чем в окне и на якоре.";

  // «Оценка»
  let all = at("overview");
  const lv = () => text(cardOf(page, "На чём стоит заголовок"));
  check("окно фактов: под таблицей уровней — строка подузла `levels.window` числами выпуска", lv().includes(WINDOW_LINE) && Math.min(...L.order.map((k) => L.rows[k].nim)) > W.nim.max
    && countNodes(cardOf(page, "На чём стоит заголовок"), (n) => n.tagName === "TR") === L.order.length + 1, lv().slice(700, 1400));
  check("окно фактов: фраза «маржа выше окна» — по числам выпуска, с причиной в составе баланса", lv().includes(WINDOW_LINE + ABOVE + WHY)
    && Math.min(...L.order.map((k) => L.rows[k].loans_share)) > Math.max(W.loans_share.window, W.loans_share.anchor), lv().slice(900, 1500));
  check("имена миров: в названии клетки — имя мира из выпуска, буквы без имени на «Оценке» нет", lv().includes(`${d.worlds.rows.H.name} · ${d.regimes.rows.norm.title} · ${d.capital.scenarios.mid.title}`)
    && !/(?:^|[\s(«—])[NHM] · /.test(all), all.match(/.{0,40}[NHM] · .{0,60}/));

  // «Что в цене»
  all = at("market");
  const limits = cardOf(page, "Пределы и срок");
  const bank = Object.fromEntries(R.bank_rows.map((r) => [r.key, r]));
  const marks = svgTexts(limits).map(squash);
  check("пределы: обе границы подписаны разностью с точкой из выпуска; медианы полосы на шкале нет", marks.includes(`капитал без премии ${rub(bank.book_value_per_share.implied)} (${signed(bank.book_value_per_share.delta)})`)
    && marks.includes(`без опережающего роста ${rub(bank.value_without_excess_growth.implied)} (${signed(bank.value_without_excess_growth.delta)})`)
    && marks.includes(`точка ${rub(d.fair_value.central)}`) && marks.includes(`цена ${rub(d.market.price)}`) && !marks.some((m) => m.startsWith("медиана")), marks);
  check("пределы: база названа — точка при значениях книги, а не медиана полосы", text(limits).includes("Обе границы считаны от точки при значениях книги, а не от медианы полосы; в скобках — разность с точкой.")
    && Math.abs(bank.value_without_excess_growth.delta - (bank.value_without_excess_growth.implied - d.fair_value.central)) < 0.006, text(limits).slice(0, 400));
  const rev = () => cardOf(page, "Обратный расчёт по осям книги");
  const loose = R.rows.filter((r) => r.status === "solved" && !R.refine_rows.includes(r.key));
  check("обратный расчёт: решение строки вне списка уточнения подписано «оценка по подвыборке»; у названных строк подписи нет", loose.length === 4 && R.refine_rows.length === 2
    && countNodes(rev(), (n) => (n.attrs.class || "") === "b" && n.textContent === "оценка по подвыборке") === loose.length
    && loose.every((r) => r.gap_basis === "subsample") && R.rows.filter((r) => R.refine_rows.includes(r.key)).every((r) => r.gap_basis === "full"), text(rev()).slice(0, 600));
  const tableButton = findNode(rev(), (n) => n.tagName === "BUTTON" && n.textContent === "Таблица");
  tableButton.dispatch("click");
  page.paint();
  check("обратный расчёт: в таблице — та же подпись под плашкой строки", (text(rev()).match(/диапазонаоценка по подвыборке/g) || []).length === loose.length
    && text(rev()).includes("10,47 % 11,1 % 10,3 % … 11,6 % 0,00 в диапазоне книги Сдвиг"), text(rev()).slice(400, 1200));
  tableButton.dispatch("click");
  page.paint();

  // «Расчёт»
  all = at("model");
  press(page, "Ещё 7 карточек");
  const fade = text(cardOf(page, "Путь ROE и роста капитала к терминалу"));
  check("путь к терминалу: линии — средние по клеткам; знак разности линий — не знак прироста стоимости; ROE терминала — на капитале без избытка", fade.includes("Линии — средние по клеткам под вероятностями точки. "
    + "Остаточный доход считается в каждой клетке по её ставкам, поэтому знак разности линий — не знак прироста стоимости: накопленный приведённый доход по годам — на экране «Что в цене». За горизонтом избыток доходности угасает.")
    && fade.includes("ROE терминала на капитале без избытка: до угасания → после") && !fade.includes("пока ROE выше стоимости капитала"), fade.slice(0, 500));
  const regimes = text(cardOf(page, "Режимы доходности и кредитного цикла"));
  check("режимы: мир, в котором стоят уровни режимов, назван именем выпуска; ожидание подписано — по ключам режимов книги, а не уровень слоя", regimes.includes("(движок). "
    + `Пути и уровни CoR режимов стоят при ставках мира «${d.worlds.rows[d.regimes.reference_world].name}»: в других мирах их сдвигает разность реальных ставок. `
    + "Это ожидание по ключам режимов книги, а не уровень слоя: уровни, которые печатают клетки и слои, — на экране «Оценка»."), regimes.match(/Ожидание:.{0,400}/));
  const worlds = text(cardOf(page, "Миры ставок"));
  check("имена слоёв: веса миров подписаны слоями выпуска, своих слов для слоёв нет", worlds.includes(`Вес: ${d.layers.analytical.title.toLowerCase()} Вес: ${d.layers.market_implied.title.toLowerCase()}`)
    && !/Свой вес|Вменённый /.test(worlds), worlds.slice(0, 600));

  // «Ближайший отчёт»
  all = at("report");
  press(page, "Ещё 6 карточек");
  check("допуск нау-каста: у выпуска со слоем индикаторов — счёт событий", text(cardOf(page, "До отчёта")).includes("Засчитано 0 из 4; первое засчитываемое — 3 кв. 2026") && text(cardOf(page, "До отчёта")).includes("копим события"), null);

  // «Капитал и дивиденды»
  all = at("capital");
  check("A33: в реестре выплат срок выплаты подписан «Выплата до»", text(cardOf(page, "Следующая выплата")).includes("Последний день покупки Реестр Выплата до"), text(cardOf(page, "Следующая выплата")).slice(-500));

  // «Допущения»
  all = at("book");
  const vr = cardOf(page, "Цена правил и развилок");
  const order = [];
  const walk = (n) => { if (n.nodeType !== 1) return; if (n.tagName === "TD" && (n.attrs.class || "").includes("name")) order.push(squash(visibleText(n))); n.children.forEach(walk); };
  walk(vr);
  check("цена правил и развилок: строки — в порядке выпуска, по убыванию модуля цены; главная развилка первой, с подписью строки", order.length === V.rows.length
    && V.rows.every((r, i) => order[i] === `${r.title}${[r.note, r.why, r.mark, r.median_mark].filter(Boolean).join("")}`)
    && V.rows.every((r, i) => !i || V.rows[i - 1].d_point === null ? r.d_point === null || !i : r.d_point === null || Math.abs(V.rows[i - 1].d_point) >= Math.abs(r.d_point))
    && V.rows[0].id === "window_in_modal_cell" && !!V.rows[0].note && !!findNode(vr, (n) => (n.attrs.class || "") === "hint" && squash(n.textContent) === V.rows[0].note), order.slice(0, 3));
  press(page, "Ещё 2 карточки");
  const control = text(cardOf(page, "Сверка с контрольной моделью"));
  check("сверка: числа сводки — на книге, её цене и дате; день счёта — отдельно; на экране — выдержка из всех строк", control.includes(`годовая модель, написанная отдельно; сводка на книге ${cm.book_version}, `
    + `на её цене и дате (06.10.2026); посчитана 07.10.2026, коммит 7a1c0d9; на экране ${cm.rows.length} строк из 9 842, вне допуска во всей сводке — 0. Разность и допуск — по виду допуска`), control.slice(0, 400));
  check("решения № 8: экраны без ошибок", !page.errors.length, page.errors.slice(0, 2));

  // 375 px: подписи событий на графике цены — короткие, вертикаль начинается от строки своей подписи и чужих не перечёркивает.
  // Ширина знака в заглушке — 7 px; подпись занимает [x, x + 7·длина], строка — 16 px.
  const crossings = (card, minLength = 60) => {
    const lines = [], labels = [];
    const scan = (n) => {
      if (n.nodeType !== 1) return;
      if (n.tagName === "LINE" && n.attrs.x1 === n.attrs.x2 && +n.attrs.y1 <= +n.attrs.y2 - minLength && n.attrs.class !== "gridline") lines.push({ x: +n.attrs.x1, top: +n.attrs.y1, bottom: +n.attrs.y2 });
      if (n.tagName === "TEXT" && (n.attrs.class || "") === "halo label") { const w = n.textContent.length * 7, x0 = +n.attrs.x - (n.attrs["text-anchor"] === "end" ? w : 0); labels.push({ x0, x1: x0 + w, y: +n.attrs.y, text: n.textContent }); }
      n.children.forEach(scan);
    };
    scan(card);
    return { lines, labels, hits: labels.flatMap((t) => lines.filter((v) => v.x > t.x0 - 1 && v.x < t.x1 + 1 && v.top < t.y + 3 && v.bottom > t.y - 11).map((v) => `${t.text} × ${v.x}`)) };
  };
  for (const [width, short] of [[343, true], [309, true], [640, false]]) {
    const p = pagePanel({ width });
    await p.boot();
    await settle();
    p.hashchange("#market");
    const got = crossings(cardOf(p, "Цена акции за 12 месяцев"));
    const dividends = got.labels.filter((t) => /\d,\d\d\s?₽$/.test(squash(t.text)));
    const median = got.labels.filter((t) => squash(t.text) === (short ? "350 ₽" : "медиана модели 350 ₽"));
    check(`график цены, ширина ${width}: подписи событий и медианы ${short ? "короткие — сумма и коэффициент, слова в легенде" : "полные"}; ни одна вертикаль не идёт через подпись`,
      got.hits.length === 0 && median.length === 1 && dividends.length === d.market.ex_dividend.length && dividends.every((t) => t.text.startsWith("дивиденд ") !== short)
      && got.labels.some((t) => squash(t.text) === (short ? "1 к 10" : "дробление акций 1 к 10")) && got.lines.length >= dividends.length + 1
      && new Set(got.lines.map((v) => v.top)).size === new Set(dividends.concat(got.labels.filter((t) => /1 к 10/.test(t.text))).map((t) => t.y)).size, [got.hits, got.labels, got.lines]);
    // Гантели «Капитал: модель против рынка»: опорная вертикаль P/B = 1 — отрезками у строк, мимо подписей строк.
    // У фикстуры P/B = 1 попадает на подпись рыночного P/B: отрезок стоит только под ней.
    const bars = crossings(cardOf(p, "Капитал: модель против рынка"), 10);
    const names = bars.labels.filter((t) => t.x0 === 8);
    check(`гантели P/B, ширина ${width}: опорная вертикаль — отрезок у каждой строки; ни подписи строк, ни подписи значений не перечёркнуты`, bars.hits.length === 0 && names.length >= 2
      && bars.lines.length === names.length && bars.lines.every((v, i) => v.top > names[i].y + 20 && v.bottom - v.top === 12), [bars.hits, bars.lines, names]);
  }
  {
    // Рыночный P/B ниже единицы: вертикаль P/B = 1 идёт между точками гантели — отрезком во всю строку, мимо подписи строки над ней.
    const low = panel();
    low.fair_value.bank_first_line.market_pb = 0.82;
    const p = pagePanel({ payload: JSON.stringify(low), width: 343 });
    await p.boot();
    await settle();
    p.hashchange("#market");
    const bars = crossings(cardOf(p, "Капитал: модель против рынка"), 10);
    const names = bars.labels.filter((t) => t.x0 === 8);
    check("гантели P/B: вертикаль между точками — отрезок во всю строку, под подписью строки, которую пересекла бы сплошная линия", bars.hits.length === 0 && bars.lines.length === names.length
      && bars.lines.every((v, i) => v.top > names[i].y && v.bottom - v.top === 30) && bars.lines.some((v, i) => v.x > names[i].x0 && v.x < names[i].x1), [bars.hits, bars.lines, names]);
  }
}

{
  // Частные случаи окна фактов, допуска нау-каста, подвыборки и сверки: слова выбирают числа и узлы выпуска.
  const open = async (edit, hash) => { const d = panel(); edit(d); const p = pagePanel({ payload: JSON.stringify(d) }); await p.boot(); await settle(); if (hash) p.hashchange(`#${hash}`); return p; };
  const lvOf = (p) => squash(visibleText(cardOf(p, "На чём стоит заголовок")));
  let p = await open((d) => { d.paths.levels.window.nim.max = 0.1006; });
  check("окно фактов: строка уровней не выше наибольшего квартала окна — фразы о марже нет, строка окна остаётся", lvOf(p).includes("ЧПМ 9,12…10,06 % (среднее 9,61 %)") && !lvOf(p).includes("ЧПМ всех строк"), lvOf(p).slice(800, 1400));
  p = await open((d) => { d.paths.levels.window.loans_share.anchor = 0.72; });
  check("окно фактов: доля кредитов якоря не ниже строк — маржа выше окна печатается без причины", lvOf(p).includes("72,0 % на дату якоря. ЧПМ всех строк выше наибольшего квартала окна. ") && !lvOf(p).includes("состав баланса у них другой"), lvOf(p).slice(800, 1400));
  p = await open((d) => { Object.assign(d.paths.levels.window, { nim: { min: null, max: null, mean: null }, loans_share: { window: null, anchor: 0.677 } }); for (const k of ["cor", "cir"]) d.paths.levels.window[k].mean = null; });
  check("окно фактов: чего книга не называет, того в строке нет — ни прочерков, ни «null»", lvOf(p).includes("Окно фактов, от наименьшего квартала до наибольшего: CoR 4,69…6,65 %; C/I 46,0…48,3 %; кредиты — 67,7 % на дату якоря. Модальная клетка")
    && !/null|NaN|— %|ЧПМ всех строк/.test(lvOf(p)) && !p.errors.length, [lvOf(p).slice(800, 1400), p.errors.slice(0, 1)]);
  p = await open((d) => { delete d.paths.levels.window; });
  check("окно фактов: без подузла строки под таблицей нет, карточка прежняя", !lvOf(p).includes("Окно фактов") && lvOf(p).includes("Модальная клетка — ") && !p.errors.length, lvOf(p).slice(600, 1000));

  // Путь фондирования под годовой таблицей смеси и мир уровней режимов: числа и имена — из выпуска.
  {
    const d = panel(), F = d.paths.funding, pc = (v) => squash(`${(v * 100).toFixed(1).replace(".", ",")} %`);
    const annualOf = (q) => squash(visibleText(cardOf(q, "По годам: смесь заголовка")));
    p = await open(() => {}, "capital");
    const i = F.years.indexOf(2030), row = `${F.years[i]}${pc(F.mix.loans_to_funds[i])}${pc(F.modal_cell.loans_to_funds[i])}${pc(F.mix.wholesale_share[i])}${pc(F.modal_cell.wholesale_share[i])}`;
    check("путь фондирования: под годовой таблицей — кредиты к средствам клиентов и доля оптового фондирования смеси и модальной клетки, якорь — строкой над таблицей (не подписью таблицы: подпись широкой таблицы на узком экране обрезается)",
      annualOf(p).replace(/\s/g, "").includes(row.replace(/\s/g, "")) && annualOf(p).includes(`Чем закрыт рост кредитов. На дату якоря кредиты к средствам клиентов — ${pc(F.anchor.loans_to_funds)}, доля оптового фондирования — ${pc(F.anchor.wholesale_share)}; модальная клетка — `
        + `${d.worlds.rows.H.name} · `) && annualOf(p).includes("Кредиты к средствам клиентов: смесь") && !findNode(cardOf(p, "По годам: смесь заголовка"), (n) => n.tagName === "CAPTION") && !p.errors.length, [row, annualOf(p).slice(-900), p.errors.slice(0, 1)]);
    p = await open((x) => { x.paths.funding.modal_cell.wholesale_share[i] = null; x.paths.funding.anchor.wholesale_share = null; }, "capital");
    check("путь фондирования: числа, которого нет, нет и на экране — прочерк, без «null» и NaN", !/null|NaN/.test(annualOf(p)) && annualOf(p).includes("Кредиты к средствам клиентов: смесь") && !p.errors.length, annualOf(p).slice(-600));
    p = await open((x) => { delete x.paths.funding; }, "capital");
    check("путь фондирования: без узла таблицы нет, карточка прежняя", !annualOf(p).includes("Кредиты к средствам клиентов") && annualOf(p).includes("Терминал: ROE") && !p.errors.length, annualOf(p).slice(-300));
    p = await open((x) => { delete x.regimes.reference_world; }, "model");
    const rg = squash(visibleText(cardOf(p, "Режимы доходности и кредитного цикла")));
    check("режимы: без мира-опоры в выпуске фразы о мире нет", !rg.includes("стоят при ставках мира") && rg.includes("(движок). Это ожидание по ключам режимов книги") && !p.errors.length, rg.match(/Ожидание:.{0,300}/));
  }

  const ABSENT = "Выпуск собран на цене и дате книги, без слоя индикаторов: счёта событий допуска в нём нет";
  const empty = { rule: null, status: "collecting", events_needed: null, events_scored: null, mse_ratio: null, first_event: null, earliest_decision: null };
  p = await open((d) => { d.nowcast.absent = ABSENT; d.nowcast.admission = { ...empty }; }, "report");
  let report = squash(visibleText(cardOf(p, "До отчёта")));
  check("допуск нау-каста: выпуск без слоя индикаторов — слова выпуска вместо счёта событий, без прочерков и плашки состояния", report.includes(`Допуск нау-каста к цене ${ABSENT}.`)
    && !/Засчитано|— из|копим события/.test(report) && !p.errors.length, report.slice(-300));
  p = await open((d) => { d.nowcast.admission = { ...empty }; }, "report");
  report = squash(visibleText(cardOf(p, "До отчёта")));
  check("допуск нау-каста: без счёта и без слов выпуска — «нет блока», а не «— из 0»", report.includes("В этом выпуске нет блока «допуск нау-каста».") && !/Засчитано|— из/.test(report), report.slice(-300));

  p = await open((d) => { const r = d.reverse_dcf.rows.find((x) => x.key === "erp"); Object.assign(r, { solved: 0.0601, delta: 0.0044, in_range: true }); });
  const teaser = squash(visibleText(cardOf(p, "Что заложено в цену")));
  check("обратный расчёт на «Оценке»: строка «в диапазоне книги» вне списка уточнения — с оговоркой «оценка по подвыборке»; у названных строк оговорки нет", teaser.includes("6,01 %книга 5,57 % · в диапазоне книги · оценка по подвыборке")
    && teaser.includes("книга 11,1 % · в диапазоне книги") && !teaser.includes("книга 11,1 % · в диапазоне книги · оценка") && (teaser.match(/оценка по подвыборке/g) || []).length === 1, teaser.slice(0, 700));
  p = await open((d) => { delete d.reverse_dcf.refine_rows; }, "market");
  check("обратный расчёт: без списка уточнения (книга уточняет все строки) подписи «оценка по подвыборке» нет", countNodes(cardOf(p, "Обратный расчёт по осям книги"), (n) => n.textContent === "оценка по подвыборке") === 0, null);

  p = await open((d) => { delete d.checks.control_model.valuation_date; d.checks.control_model.n_bad = 3; }, "book");
  press(p, "Ещё 2 карточки");
  const control = squash(visibleText(cardOf(p, "Сверка с контрольной моделью")));
  check("сверка: без даты чисел сводки — книга и день счёта; счёт строк вне допуска — всей сводки", control.includes("сводка на книге 1.1, на её цене и дате; посчитана 07.10.2026") && control.includes("из 9 842, вне допуска во всей сводке — 3."), control.slice(0, 300));
  p = await open((d) => { for (const r of d.reverse_dcf.bank_rows) delete r.by_year; }, "model");
  const fade = squash(visibleText(cardOf(p, "Путь ROE и роста капитала к терминалу")));
  check("путь к терминалу: без накопленного дохода по годам в выпуске ссылки на него нет", fade.includes("не знак прироста стоимости. За горизонтом избыток доходности угасает.") && !fade.includes("«Что в цене»"), fade.slice(0, 400));
}

{
  // Книга с гейтом стационарной маржи (узел `nim_stationary`, ключа уровня нет): ключ цели — уровень мира-опоры,
  // суждение о марже стоит рядом с ним числом — на книге и при нужном рынку значении; диапазон оси подписан диапазоном ключа.
  const g = panel();
  const worldM = g.worlds.rows.M.name;
  delete g.nii.transmission.level;
  Object.assign(g.nii.transmission, { nim_lt_target_mgmt: 0.1075, target_eng: 0.1063, nim_stationary: { world: "M", value: 0.111, target: 0.111, tolerance: 0.0005 } });
  const row = g.reverse_dcf.rows.find((r) => r.paths.includes("nii.nim_lt_target_mgmt"));
  Object.assign(row, { book: 0.1075, range: [0.0955, 0.1165], solved: 0.0962, delta: -0.0113, stationary_book: 0.111, stationary_solved: 0.0997 });
  Object.assign(g.judgements.rows.find((r) => r.id === "nim_lt"), { book: 0.1075, low: 0.0955, high: 0.1165 });
  const printed = `ключ цели; стационарная маржа мира «${worldM}» — 11,10 %`;
  let page = pagePanel({ payload: JSON.stringify(g) });
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  at("overview");
  const lv = squash(visibleText(cardOf(page, "На чём стоит заголовок")));
  check("книга с гейтом стационарной маржи: суждение — с целью и допуском, ключ цели — уровень мира-опоры рядом", lv.includes(`Суждение книги о марже — стационарная маржа при ставках мира «${worldM}» на составе баланса якоря, упр.: 11,10 % `
    + "(цель 11,10 % ± 0,05 п.п.); ключ цели — уровень мира-опоры — 10,75 %."), lv.slice(0, 400));
  check("книга с гейтом стационарной маржи: строка обратного расчёта — суждение о марже на книге и при корне",
    squash(visibleText(cardOf(page, "Что заложено в цену"))).includes(`${printed}, при нужном рынку значении — 9,97 %`), squash(visibleText(cardOf(page, "Что заложено в цену"))).slice(0, 400));
  at("market");
  const rev = squash(visibleText(cardOf(page, "Обратный расчёт по осям книги")));
  check("книга с гейтом стационарной маржи: обратный расчёт — оба числа у строки маржи и уровни смеси при корне",
    rev.includes(`книга 10,75 % · диапазон 9,55 % … 11,65 %${printed}, при нужном рынку значении — 9,97 %смесь заголовка при нём печатает ЧПМ 9,87 %, CoR 5,60 %, C/I 49,6 %`), rev.slice(0, 500));
  check("книга с гейтом стационарной маржи: диапазон оси в «торнадо» подписан диапазоном ключа", squash(visibleText(cardOf(page, "Цена по одному суждению"))).includes("ключ цели: 9,55 % … 11,65 %"), null);
  at("model");
  press(page, "Ещё 7 карточек");
  const trans = squash(visibleText(cardOf(page, "Книги ЧПД и передача ставки")));
  check("книга с гейтом стационарной маржи: «Расчёт» — ключ цели и суждение одной плиткой, с целью и допуском", trans.includes(`10,75 / 11,10 % ЧПМ ${g.meta.terms.lt_level}, упр.: ключ цели — уровень мира-опоры / суждение книги — `
    + `стационарная маржа мира «${worldM}» на составе баланса якоря; цель 11,10 % ± 0,05 п.п.; ключ в движке — 10,63 %`), trans.slice(0, 700));
  at("book");
  const judg = squash(visibleText(cardOf(page, "Суждения книги по цене ошибки")));
  check("книга с гейтом стационарной маржи: строка суждения — ключ и суждение рядом; диапазон подписан диапазоном ключа", judg.includes(`ЧПМ после фазы роста 10,75 %${printed}диапазон — тоже ключа цели 9,55 % … 11,65 %`)
    && !page.errors.length, [judg.slice(0, 500), page.errors.slice(0, 1)]);

  Object.assign(row, { solved: 0.1183, delta: 0.0108, in_range: false, stationary_solved: 0.1218 });
  page = pagePanel({ payload: JSON.stringify(g) });
  await page.boot();
  await settle();
  const teaser = squash(visibleText(cardOf(page, "Что заложено в цену")));
  check("книга с гейтом стационарной маржи: ключ решён вне диапазона — в строке «вне диапазона» ключ и суждение о марже при нём",
    teaser.includes(`Вне диапазона книги: ЧПМ после фазы роста 11,83 % (ключ цели; стационарная маржа мира «${worldM}» — 12,18 %)`), teaser.match(/Вне диапазона книги.{0,200}/));
}

/* ── 14. форма Совкомбанка: шаг печати 0,1 ₽, годовой плательщик, выкуп акций дочкой, жетон DPS, формы ЦБ без релиза ── */

{
  const g = panel();
  const h = g.fair_value.headline;
  Object.assign(h, { print_step: 0.1, printed_median: 16.5, printed_band80: [12.5, 19.9], printed_band50: [14.5, 17.7], printed_point: 17.2 });
  g.dividends.policy.frequency = "annual";
  // ближайшая выплата годового плательщика без объявления: главная цифра — ожидание модели по клеткам, DPS политики рядом
  const ne = g.dividends.next_expected;
  Object.assign(ne, { status: "model", label: "за 2026 год", dps: 0.2975, dps_mean: 0.2975, dps_policy: 0.8509, dps_p10: 0, dps_p90: 0.35, p_cancel: 0.15,
    record_date: null, last_buy_date: null, record_date_est: "2027-07-13", record_date_note: "оценка по календарю событий", yield: { T: 0.02944 },
    condition: { ...ne.condition, p_limited: 0.85 } });
  delete ne.period;
  delete ne.yield_period;
  g.meta.shares.dividend_eligible_mln = 2675.9;
  g.dividends.buyback = { title: "выкуп акций дочкой", price_rule: "world_forward", price_book: 10.105, closed: [{ period: "2026Q3", price: 10.0557 }],
    first_period: "2026Q3", last_period: "2028Q4", shares_start_mln: 2549.9, amount: 29.0, shares_bought_mln: 247.8, price: 11.7, divisor_after_mln: 2302.1,
    years: [{ year: 2026, amount: 5.0, price: 10.19, shares_bought_mln: 49.1, shares_end_mln: 2500.8 }, { year: 2027, amount: 12.0, price: 11.23, shares_bought_mln: 106.8, shares_end_mln: 2394.0 }],
    by_world: { N: { price: 11.56, divisor_after_mln: 2301.0 }, H: { price: 11.72, divisor_after_mln: 2302.5 }, M: { price: 11.74, divisor_after_mln: 2303.1 } } };
  g.dividends.token = { min_dps: 0.35, years: [{ year: 2026, min_dps: 0.35, p_token: 0.85, dps: 0.2975 }, { year: 2031, min_dps: 0.35, p_token: 0, dps: 2.6 }] };
  // год прибыли 2026: ожидание модели по клеткам 0,30 ₽ при DPS политики 0,85 ₽ (капитал урезал выплату в 85 % массы)
  Object.assign(g.dividends.model.find((r) => r.year === g.nowcast.year.year), { dps: 0.2975, dps_p10: 0, dps_p90: 0.35, dps_policy: 0.8509, p_cut: 0.85, p_zero: 0.15 });
  Object.assign(g.calendar.next_ras, { release_date: null, release_confirmed: false, enters_via: "form102", date: "2026-10-24" });
  g.calendar.events = g.calendar.events.filter((e) => e.kind !== "ops_release");
  const page = pagePanel({ payload: JSON.stringify(g) });
  await page.boot();
  await settle();
  const at = (name) => { page.hashchange(`#${name}`); return page.text(); };
  const over = at("overview");
  check("форма Совкомбанка: заголовок и полосы — с шагом печати 0,1 ₽", over.includes("≈16,5₽") && over.includes("12,5–19,9 ₽") && over.includes("14,5–17,7 ₽")
    && squash(visibleText(cardOf(page, "Точка при значениях книги"))).includes("17,2"), over.slice(0, 400));
  check("форма Совкомбанка: два ритма — формы ЦБ банка за месяц, без месячного релиза", over.includes("два ритма: формы ЦБ банка за месяц и квартальная МСФО группы")
    && over.includes("форма 0409102 банка за сентябрь 2026") && !over.includes("РСБУ за сентябрь"), over.match(/.{0,80}два ритма.{0,160}/));
  const cap = at("capital");
  const bb = squash(visibleText(cardOf(page, "Выкуп акций дочкой")));
  check("форма Совкомбанка: выкуп акций дочкой — сумма, цена, куплено, делитель после выкупа, по годам и мирам",
    bb.includes("29 млрд ₽ сумма выкупа") && bb.includes("11,70 ₽ средняя цена покупок") && bb.includes("2 302,1 акций в обращении после выкупа, млн (было 2 549,9)")
    && bb.includes("от 10,105 ₽") && bb.includes("3 кв. 2026 — 10,0557 ₽") && bb.includes(g.worlds.rows.N.name), bb.slice(0, 600));
  const tok = squash(visibleText(cardOf(page, "Жетон DPS")));
  check("форма Совкомбанка: жетон DPS — минимум и годы, где он связывает", tok.startsWith("Жетон DPS: 0,35 ₽") && tok.includes("2026 0,30 ₽ 85 %") && !tok.includes("2031"), tok);
  check("форма Совкомбанка: годовой плательщик — без «Квартальных DPS»; делитель дивиденда — акции с правом на дивиденд",
    !cap.includes("Квартальные DPS") && cap.includes("на 2 675,9 млн акций с правом на дивиденд") && cap.includes("решения — раз в год"), cap.match(/.{0,80}с правом на дивиденд.{0,80}/));
  check("форма Совкомбанка: ближайшая выплата годового плательщика — ожидание модели в паспорте и тизере, P10–P90 при нём, DPS политики — с долей среза",
    over.includes("дивдоходность вперёд (ожидание модели)") && over.includes("(ожидание модели); реестр")
    && over.includes("0,30 ₽ ожидание модели · риск отмены 15 %P10–P90 0,00–0,35 ₽; по политике 0,85 ₽: капитал урезал выплату в 85 % массы"),
    over.match(/.{0,160}по политике 0,85.{0,120}/));
  const pay = squash(visibleText(cardOf(page, "Следующая выплата")));
  check("форма Совкомбанка: карточка ближайшей выплаты — P10–P90 при ожидании модели, DPS политики без интервала",
    pay.includes("0,30 ₽ ожидание модели · риск отмены 15 %P10–P90 0,00–0,35 ₽ 0,85 ₽ DPS политики без среза капиталом 15 % риск отмены")
    && (pay.match(/P10–P90/g) || []).length === 1, pay.slice(0, 400));
  at("overview");
  const teaser = squash(visibleText(cardOf(page, "Ближайший отчёт")));
  const POLICY_LINE = "по политике 0,85 ₽ — при запасе капитала; капитал урезал выплату в 85 % массы, без выплаты — 15 %";
  check("форма Совкомбанка: «Ближайший отчёт» — главная цифра DPS года — ожидание модели, DPS по политике второй строкой с условием",
    teaser.includes(`0,30 ₽ DPS за ${g.nowcast.year.year} — ожидание модели, P10–P90 0,00–0,35 ₽${POLICY_LINE}`) && !teaser.includes("по политике, интервал"), teaser.slice(0, 400));
  const rep = at("report");
  const yc = squash(visibleText(cardOf(page, `Прибыль ${g.nowcast.year.year} → дивиденд`)));
  check("форма Совкомбанка: карточка года — первая цифра DPS — ожидание модели по клеткам, DPS по политике — следом",
    yc.includes(`0,30 ₽ DPS за ${g.nowcast.year.year} — ожидание модели по клеткам, P10–P90 0,00–0,35 ₽${POLICY_LINE}`)
    && yc.indexOf("ожидание модели по клеткам") < yc.indexOf("DPS по политике:") && !yc.includes("ожидание по клеткам —"), yc.slice(0, 500));
  check("форма Совкомбанка: без ошибок витрины", !page.errors.length && !BAD_TEXT.test(over + cap + rep), page.errors.slice(0, 2));
  // годовой календарь модели (узла `model_quarters` нет) при годовой частоте политики: без объявления — DPS политики
  const g2 = JSON.parse(JSON.stringify(g));
  delete g2.dividends.model_quarters;
  g2.dividends.next_expected.dps = 0.8509;
  const page2 = pagePanel({ payload: JSON.stringify(g2) });
  await page2.boot();
  await settle();
  page2.hashchange("#capital");
  page2.text();
  const pay2 = squash(visibleText(cardOf(page2, "Следующая выплата")));
  check("годовой календарь модели: ближайшая выплата без объявления — DPS по политике, а не «ожидание модели»",
    pay2.includes("0,85 ₽ DPS по политике · риск отмены 15 %") && !pay2.includes("ожидание модели") && !page2.errors.length, pay2.slice(0, 300));
}

/* ── 9. отказы двери ── */

for (const [status, body, title] of [[503, '{"error":"not published yet"}', "Выпуск ещё не опубликован"], [503, '{"error":"upstream unavailable"}', "Источник данных временно недоступен"],
  [403, '{"error":"user-agent required"}', "Данные недоступны"], [200, "<html>", "Ответ не разобрался как JSON"]]) {
  const page = makePage({ status, payload: body, now: FRESH });
  await page.boot();
  await settle();
  check(`дверь ${status} ${body.slice(0, 30)} → «${title}»`, page.text().includes(title) && !page.bootError, page.text().slice(0, 200));
}

const failed = checks.filter((c) => !c.ok);
console.log(JSON.stringify({ total: checks.length, failed, unhandled: rejections.slice(0, 3) }, null, 1));
process.exitCode = failed.length || rejections.length ? 1 : 0;
