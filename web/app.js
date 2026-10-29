/* Модель 850 — витрина выпуска (контракт — поле `schema`). Правила держат tests/test_web_*.py и tests/web/*.mjs:
 * числа и слова эмитента — только из выпуска `/api/model` (имя `d` — только выпуск, литералов эмитента нет);
 * единственный пересчёт — ползунок λ по прогонам заголовка, прочее при λ ≠ книги — строки `by_lambda`;
 * карточка панели рисуется по своему узлу выпуска, слово общей формы — по данным; упавший экран не роняет остальные. */
"use strict";

const API = "/api/model";
// Дверь ждёт источник 8 с и отдаёт копию; витрина ждёт дверь не дольше этого.
const API_TIMEOUT_MS = 20000;
const STALE_HOURS = 96;
const SVG_NS = "http://www.w3.org/2000/svg";
const SW = "stroke-width";
// Цвета рядов — переменные темы.
const MODEL = "var(--model)", THIRD = "var(--third)", MARKET = "var(--market)", INK = "var(--ink)", NEG = "var(--neg)", INK2 = "var(--ink-2)", GREY = "var(--series-neutral)", SURF = "var(--surface)";

let DATA = null;          // выпуск
let LAMBDA = null;        // null — λ книги
let CURRENT = "overview";
let RUB_DIGITS = 0;      // знаков у рублей на акцию по умолчанию — по шагу печати выпуска (0,1 ₽ → один; 1 и 5 ₽ — ни одного)

/* ── DOM ── */

function el(tag, attrs, ...kids) {
	const node = document.createElement(tag);
	setAttrs(node, attrs);
	append(node, kids);
	return node;
}

function sv(tag, attrs, ...kids) {
	const node = document.createElementNS(SVG_NS, tag);
	setAttrs(node, attrs);
	append(node, kids);
	return node;
}

function setAttrs(node, attrs) {
	if (!attrs) return;
	for (const [key, value] of Object.entries(attrs)) {
		if (value === null || value === undefined || value === false) continue;
		if (key === "text") node.textContent = value;
		else if (key === "on") for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn);
		else if (key === "tip") setTip(node, value);
		else node.setAttribute(key, value === true ? "" : String(value));
	}
}

function append(node, kids) {
	for (const kid of kids.flat(Infinity)) {
		if (kid === null || kid === undefined || kid === false || kid === "") continue;
		node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
	}
}

function fill(node, ...kids) { node.replaceChildren(); append(node, kids); }

const $ = (selector, root = document) => root.querySelector(selector);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const cls = (...names) => names.filter(Boolean).join(" ") || null;
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : {});
const list = (x) => (Array.isArray(x) ? x : []);

function sentence(t) { return /[.!?…]$/.test(t) ? t : t + "."; }
function upperFirst(t) { const s = String(t); return s.charAt(0).toUpperCase() + s.slice(1); }
// Строка выпуска — предложением: заглавная буква и точка.
function phrase(t) { return sentence(upperFirst(ruText(t))); }
function lowerFirst(t) {
	const s = String(t);
	const word = s.split(/[\s(,:]/)[0];
	return s.length > 1 && !/[A-ZА-ЯЁ]/.test(word.slice(1)) && s[1] !== s[1].toUpperCase() ? s[0].toLowerCase() + s.slice(1) : s;
}
// Слово после числа — по напечатанному числу: с дробной частью — «1,6 года».
function plural(n, [one, few, many], digits = 0) {
	if (digits > 0) return few;
	const a = Math.abs(Math.round(n)) % 100, b = a % 10;
	return a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many;
}
const YEAR_WORDS = ["год", "года", "лет"];
function yearsText(v) { const k = exactDigits(v, 1); return fmt.num(v, k) + NBSP + plural(v, YEAR_WORDS, k); }

/* ── числа и даты по-русски ── */

const NBSP = String.fromCharCode(0x00a0);
const THIN = String.fromCharCode(0x202f);
const MINUS = String.fromCharCode(0x2212);
const SPACES = new RegExp(`[${NBSP}${THIN} ]`, "g");
const FORMATS = new Map();

function numberFormat(digits) {
	if (!FORMATS.has(digits)) {
		FORMATS.set(digits, new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: true }));
	}
	return FORMATS.get(digits);
}

const MSK = "Europe/Moscow";
const TIME_FORMAT = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: MSK });
const DAY_MSK = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: MSK });
const MONTHS_SHORT = ["янв.", "февр.", "марта", "апр.", "мая", "июня", "июля", "авг.", "сент.", "окт.", "нояб.", "дек."];
const MONTHS_AXIS = ["янв", "февр", "март", "апр", "май", "июнь", "июль", "авг", "сент", "окт", "нояб", "дек"];
const MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"];

function parseDay(iso) {
	if (typeof iso !== "string") return null;
	const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
	if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
	if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(iso)) return null;
	const t = Date.parse(iso);
	return Number.isNaN(t) ? null : new Date(t);
}

function mskDay(iso) {
	const t = parseDay(iso);
	return t ? DAY_MSK.format(t) : null;
}

function daysBetween(fromIso, toIso) {
	const a = parseDay(fromIso), b = parseDay(toIso);
	if (!a || !b) return null;
	const utc = (x) => Date.UTC(x.getFullYear(), x.getMonth(), x.getDate());
	return Math.round((utc(b) - utc(a)) / 864e5);
}

const fmt = {
	num(x, digits = 0) {
		if (!isNum(x)) return "—";
		const k = 10 ** digits;
		const rounded = Math.round(x * k) / k;
		return numberFormat(digits).format(rounded === 0 ? 0 : rounded).replace(/-/g, MINUS).replace(SPACES, THIN);
	},
	signed(x, digits = 0) {
		if (!isNum(x)) return "—";
		const out = fmt.num(x, digits);
		return x > 0 && out !== fmt.num(0, digits) ? "+" + out : out;
	},
	rub(x, digits = RUB_DIGITS) { return isNum(x) ? fmt.num(x, digits) + THIN + "₽" : "—"; },
	signedRub(x, digits = RUB_DIGITS) { return isNum(x) ? fmt.signed(x, digits) + THIN + "₽" : "—"; },
	bn(x, digits = 1) { return isNum(x) ? fmt.num(x, digits) + NBSP + "млрд" + NBSP + "₽" : "—"; },
	signedBn(x, digits = 1) { return isNum(x) ? fmt.signed(x, digits) + NBSP + "млрд" + NBSP + "₽" : "—"; },
	pct(share, digits = 1) { return isNum(share) ? fmt.num(share * 100, digits) + THIN + "%" : "—"; },
	signedPct(share, digits = 1) { return isNum(share) ? fmt.signed(share * 100, digits) + THIN + "%" : "—"; },
	pp(share, digits = 2) { return isNum(share) ? fmt.signed(share * 100, digits) + NBSP + "п.п." : "—"; },
	bp(points, digits = 0) { return isNum(points) ? fmt.signed(points, digits) + NBSP + "б.п." : "—"; },
	x(multiple, digits = 2) { return isNum(multiple) ? fmt.num(multiple, digits) + "×" : "—"; },
	// Переменная дня здесь не `d`: `d.` — только выпуск.
	date(iso) {
		const day = parseDay(iso);
		return day ? `${String(day.getDate()).padStart(2, "0")}.${String(day.getMonth() + 1).padStart(2, "0")}.${day.getFullYear()}` : "—";
	},
	dateShort(iso) { const day = parseDay(iso); return day ? `${day.getDate()}${NBSP}${MONTHS_SHORT[day.getMonth()]}` : "—"; },
	time(iso) { const day = parseDay(iso); return day ? `${TIME_FORMAT.format(day)}${NBSP}МСК` : "—"; },
	stamp(iso) { return parseDay(iso) ? `${fmt.date(mskDay(iso))} ${fmt.time(iso)}` : "—"; },
	days(n) { return isNum(n) ? `${fmt.num(n)}${NBSP}${plural(n, ["день", "дня", "дней"])}` : "—"; },
};

// Малое число: 1e-9 → «1·10⁻⁹».
function sci(x) {
	if (!isNum(x)) return "—";
	const [m, e] = x.toExponential(0).split("e");
	const sup = { "-": "⁻", "+": "", 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹" };
	return `${m.replace("-", MINUS)}·10${[...e].map((c) => sup[c]).join("")}`;
}

function exactDigits(v, max) {
	for (let k = 0; k < max; k++) if (Math.abs(Math.round(v * 10 ** k) - v * 10 ** k) < 1e-6) return k;
	return max;
}

function pctTicks(marks) {
	const digits = Math.max(0, ...marks.map((t) => exactDigits(t * 100, 3)));
	return (t) => fmt.num(t * 100, digits) + THIN + "%";
}

function formatByUnit(value, unit, d) {
	if (value === null || value === undefined) return "—";
	if (typeof value === "object") return dictText(d, value);
	const u = String(unit || "");
	if (u === "period" || u === "date") return dayOrPeriod(value);
	if (typeof value === "string") return ruText(value);
	if (!isNum(value)) return "—";
	if (u === "pp") return value === 0 ? "без сдвига" : fmt.pp(value, Math.max(1, exactDigits(value * 100, 2)));
	if (u === "pct" || u === "share") return fmt.pct(value, Math.min(2, exactDigits(value * 100, 2)));
	if (u === "bn") return fmt.bn(value, Math.min(1, exactDigits(value, 1)));
	if (u === "rub") return fmt.rub(value, Math.min(2, exactDigits(value, 2)));
	if (u === "bp") return fmt.bp(value);
	if (u === "years") return yearsText(value);
	return fmt.num(value, exactDigits(value, 3));
}

function dictText(d, dict) {
	const w = obj(dict);
	return Object.keys(w).filter((k) => isNum(w[k])).map((k) => `${keyName(d, k)} ${pct1(w[k])}`).join(" · ") || "—";
}

const RU_DECIMAL = /\d{2}\.\d{2}\.\d{4}|§ ?\d+(?:\.\d+)+|(?<![А-яЁё])пп?\. ?\d+(?:\.\d+)+|[A-Za-zА-яЁё][A-Za-zА-яЁё\d]*-\d+(?:\.\d+)+|[A-Za-zА-яЁё]\d+\.\d+|(?:книг[а-яё]{1,3}|верси[а-яё]{1,2}) \d+(?:\.\d+)+(?:-[a-z\d]+)?(?: → \d+(?:\.\d+)+)?|\d+(?:\.\d+){2,}|(\d)\.(\d)/g;

// Свободный текст: десятичная запятая, даты и периоды по-русски; версии и ссылки — как есть.
function ruText(t) {
	return String(t ?? "")
		.replace(/(^|[^0-9])(\d{4})-(\d{2})-(\d{2})(?![0-9])/g, "$1$4.$3.$2")
		.replace(/\b\d{4}(?:Q[1-4]|M(?:0[1-9]|1[0-2]))\b/g, periodLabel)
		.replace(RU_DECIMAL, (m, a, b) => (a === undefined ? m : `${a},${b}`))
		.replace(/(^|[\s(])-(?=\d)/g, `$1${MINUS}`)
		.replace(/(\d) ?%| (₽|п\.п\.|б\.п\.)/g, (m, a, b) => (a ? `${a}${THIN}%` : `${THIN}${b}`));
}

function wordsText(d, t) {
	return ruText(String(t ?? "").replace(/\b[A-Z]\/([a-z_]+)\/[a-z_]+\b/g, (m, r) => (obj(obj(d.regimes).rows)[r] ? cellName(d, m) : m)));
}

function reasonText(t) { return ruText(String(t ?? "").replace(/https?:\/\/([^\/\s?#:]+)[^\s:;,]*/g, "$1")); }

const FILE_TOKEN = /[^\s()«»,;:]*(?:\/[^\s()«»,;]*|\.(?:html?|pdf|xlsx?|json|csv|ya?ml|md|txt)(?![\p{L}\d]))/giu;
function srcText(t) {
	const kept = [];
	const masked = String(t ?? "")
		.replace(FILE_TOKEN, (m) => { kept.push(m); return `${String.fromCharCode(0xE100 + kept.length - 1)}`; });
	return ruText(masked).replace(/(.)/g, (m, c) => kept[c.charCodeAt(0) - 0xE100]);
}

/* ── подсказки ── */

const TIPS = new WeakMap();
let tipOwner = null;

function setTip(node, content) {
	TIPS.set(node, content);
	node.setAttribute("data-tip", "");
	if (!node.hasAttribute("tabindex")) node.setAttribute("tabindex", "0");
}

function tipTarget(node) {
	while (node && node !== document) {
		if (node.nodeType === 1 && TIPS.has(node)) return node;
		node = node.parentNode;
	}
	return null;
}

function tipBody(content) {
	if (typeof content === "string") return [dx(content)];
	const out = [];
	if (content.title) out.push(bx("tip-title", content.title));
	for (const [k, v] of content.rows || []) out.push(bx("tip-row", sp("k", k), sp("v", v)));
	if (content.note) out.push(bx("tip-note", content.note));
	return out;
}

function showTip(owner, x, y) {
	const box = $("#tip");
	if (!box) return;
	if (tipOwner && tipOwner !== owner) tipOwner.classList.remove("is-hot");
	tipOwner = owner;
	owner.classList.add("is-hot");
	box.replaceChildren(...tipBody(TIPS.get(owner)));
	box.hidden = false;
	placeTip(x, y);
}

function placeTip(x, y) {
	const box = $("#tip");
	if (!box || box.hidden) return;
	const pad = 12, w = box.offsetWidth, h = box.offsetHeight;
	let left = x + 14, top = y - h - 12;
	if (left + w > innerWidth - pad) left = Math.max(pad, x - w - 14);
	if (top < pad) top = Math.min(innerHeight - h - pad, y + 18);
	box.style.left = `${left}px`;
	box.style.top = `${top}px`;
}

function hideTip() {
	const box = $("#tip");
	if (box) box.hidden = true;
	if (tipOwner) tipOwner.classList.remove("is-hot");
	tipOwner = null;
}

function wireTips() {
	document.addEventListener("pointerover", (e) => { const o = tipTarget(e.target); if (o) showTip(o, e.clientX, e.clientY); });
	document.addEventListener("pointermove", (e) => { if (tipOwner) placeTip(e.clientX, e.clientY); });
	document.addEventListener("pointerout", (e) => { const o = tipTarget(e.target); if (o && !o.contains(e.relatedTarget)) hideTip(); });
	document.addEventListener("focusin", (e) => {
		const o = tipTarget(e.target);
		if (!o) return;
		const r = o.getBoundingClientRect();
		showTip(o, r.left + r.width / 2, r.top);
	});
	document.addEventListener("focusout", hideTip);
	document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
	window.addEventListener("scroll", hideTip, { passive: true });
}

/* ── графики: основа ── */

const DRAWS = new WeakMap();
const SIZE = typeof ResizeObserver === "function"
	? new ResizeObserver((entries) => {
		for (const entry of entries) {
			const host = entry.target;
			const width = Math.floor(entry.contentRect.width);
			if (width > 0 && String(width) !== host.dataset.w) { host.dataset.w = width; paint(host); }
		}
	})
	: null;

function chart(draw, labelText) {
	const host = el("div", { class: "chart", "aria-label": labelText || null });
	DRAWS.set(host, draw);
	if (SIZE) SIZE.observe(host);
	else requestAnimationFrame(() => { host.dataset.w = host.clientWidth || 640; paint(host); });
	return host;
}

function paint(host) {
	const draw = DRAWS.get(host);
	const width = Number(host.dataset.w);
	if (!draw || !width) return;
	try {
		host.replaceChildren(draw(width));
	} catch (error) {
		console.error(error);
		host.replaceChildren(pr("empty broken", `График не отрисовался: ${error.message}`));
	}
}

function repaint(host) { if (host && host.dataset.w) paint(host); }

function svgBox(width, height, labelText) {
	return sv("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": labelText || null, focusable: "false" });
}

function scale(d0, d1, r0, r1) {
	const k = (r1 - r0) / ((d1 - d0) || 1);
	const f = (v) => r0 + (v - d0) * k;
	f.d = [d0, d1];
	return f;
}

function niceStep(span, count) {
	const raw = Math.abs(span) / Math.max(1, count);
	if (!raw) return 1;
	const mag = 10 ** Math.floor(Math.log10(raw));
	const r = raw / mag;
	return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 5 ? 5 : 10) * mag;
}

function ticks(d0, d1, count) {
	const step = niceStep(d1 - d0, count);
	const out = [];
	for (let v = Math.ceil(d0 / step - 1e-9) * step; v <= d1 + step * 1e-6; v += step) out.push(Number(v.toPrecision(12)));
	return out;
}

let MEASURE = null;
let FAMILY = null;
function textWidth(content, size = 12.5, weight = 500) {
	if (!MEASURE) {
		MEASURE = document.createElement("canvas").getContext("2d");
		FAMILY = getComputedStyle(document.body).fontFamily;
	}
	MEASURE.font = `${weight} ${size}px ${FAMILY}`;
	return MEASURE.measureText(String(content)).width;
}

// Обводка точки графика цветом карточки.
const RING = { stroke: SURF, [SW]: 2 };
const DOT = { dots: true, r: 3 };
function text(x, y, content, attrs = {}) { return sv("text", { x, y, ...attrs }, content); }
function line(x1, y1, x2, y2, attrs = {}) { return sv("line", { x1, y1, x2, y2, ...attrs }); }

function stackLabels(items, gap = 8) {
	const rows = [];
	for (const item of items.sort((a, b) => a.x0 - b.x0)) {
		let row = rows.findIndex((right) => item.x0 >= right + gap);
		if (row < 0) { row = rows.length; rows.push(-Infinity); }
		rows[row] = item.x1;
		item.row = row;
	}
	return rows.length;
}

function label(x, y, content, attrs = {}) { return text(x, y, content, { ...attrs, class: cls("halo", attrs.class || "label") }); }

function axisText(x, y, s, W) {
	const w = textWidth(s, 12.5, 400);
	const anchor = x - w / 2 < 1 ? "start" : x + w / 2 > W - 1 ? "end" : "middle";
	return text(anchor === "start" ? 1 : anchor === "end" ? W - 1 : x, y, s, { class: "tick", "text-anchor": anchor });
}

function placed(x, content, W, size = 12.5, weight = 520) {
	const w = textWidth(content, size, weight);
	const x0 = Math.min(Math.max(2, x - w / 2), W - w - 2);
	return { x, text: content, w, x0, x1: x0 + w };
}

/* ── компоненты ── */

function card(opts, ...body) {
	const { title, sub, link, tools, span = 12, extra, id } = opts || {};
	const head = title || sub || tools || link
		? bx("card-head",
			dx(title ? el("h2", {}, title) : null, sub ? pr("sub", sub) : null),
			tools || null,
			link ? el("a", { class: "card-link", href: `#${link[0]}` }, link[1]) : null)
		: null;
	return el("section", { class: cls("card", `span-${span}`, extra), id: id || null }, head, ...body);
}

function spaced(px, ...kids) { return el("div", { style: `margin-top:${px}px` }, ...kids); }
// Узел с классом и отступом сверху, px.
const mt = (px, tag, c, ...k) => el(tag, { class: c, style: `margin-top:${px}px` }, ...k);
function smallNote(...kids) { return mt(6, "p", "muted small", ...kids); }
// Узел с одним классом: sp — span, bx — div, pr — p; без атрибутов: sx — span, dx — div, lx — li, pa — p.
const sp = (c, ...k) => el("span", { class: c }, ...k), bx = (c, ...k) => el("div", { class: c }, ...k), pr = (c, ...k) => el("p", { class: c }, ...k);
const hint = (...k) => sp("hint", ...k), strong = (...k) => el("strong", {}, ...k), sx = (...k) => el("span", {}, ...k), dx = (...k) => el("div", {}, ...k), lx = (...k) => el("li", {}, ...k), pa = (...k) => el("p", {}, ...k);
// Ряд плиток; первое число — отступ сверху, px.
function kpis(...k) { const mt = isNum(k[0]) ? k.shift() : 0; return el("div", { class: "kpis", style: mt ? `margin-top:${mt}px` : null }, ...k); }
const yy = (y) => `’${String(y).slice(2)}`;
const pct0 = (v) => fmt.pct(v, 0), pct1 = (v) => fmt.pct(v, 1), pct2 = (v) => fmt.pct(v, 2), rub2 = (v) => fmt.rub(v, 2);
// Цена рынка — как в выпуске (шаг 0,001 ₽, П§0.3): 10,105 ₽, а не 10,11.
const rubM = (v) => fmt.rub(v, isNum(v) ? Math.max(2, exactDigits(v, 3)) : 2);
const num1 = (v) => fmt.num(v, 1), num2 = (v) => fmt.num(v, 2), rub1 = (v) => fmt.rub(v, 1), bn0 = (v) => fmt.bn(v, 0);
const numOf = (k, digits = 0) => (r) => fmt.num(r[k], digits), pctOf = (k, digits = 1) => (r) => fmt.pct(r[k], digits);
const rubOf = (k) => (r) => rub2(r[k]), dateOf = (k) => (r) => fmt.date(r[k]);
function empty(message) { return pr("empty", message); }
function tileLabel(...kids) { return sp("tile-label", ...kids); }
function foot(...kids) { return pr("card-foot", ...kids); }
function missing(what) { return empty(`В этом выпуске нет блока «${what}».`); }
// Карточка без своего обязательного блока.
function none(title, what, span) { return card({ title, span }, missing(what)); }
function badge(t, kind) { return el("span", { class: cls("badge", kind && `badge-${kind}`) }, t); }
function detailsBlock(summary, body) { return el("details", {}, el("summary", {}, summary), bx("detail-text", body)); }

// Столбцы таблицы: Nc — числовой (text(row) — ячейка с текстом), Tc — текстовый.
const Nc = (title, value, cls, text) => ({ title, value, cls, num: true, text });
const Tc = (title, value, cls) => ({ title, value, cls });

const COMPACT = { cls: "compact" };
function dataTable(columns, rows, opts = {}) {
	const cols = columns.filter(Boolean);
	const head = el("thead", {}, el("tr", {}, cols.map((c) => el("th", { class: c.num ? "num" : null, scope: "col" }, c.title))));
	const body = el("tbody");
	for (const row of rows) {
		const detail = opts.detail ? opts.detail(row) : null;
		const tr = el("tr", { class: cls(opts.rowClass && opts.rowClass(row), detail && "has-detail") });
		for (const c of cols) tr.append(el("td", { class: cls(c.num && !(c.text && c.text(row)) && "num", c.cls) }, c.value(row)));
		body.append(tr);
		if (detail) body.append(el("tr", { class: "detail" }, el("td", { colspan: cols.length }, detail)));
	}
	return bx("scroll", el("table", { class: cls("data", opts.cls) }, opts.caption ? el("caption", {}, opts.caption) : null, head, body));
}

function withTable(chartNode, makeTable) {
	const box = bx("fig", chartNode);
	let tableNode = null;
	const button = el("button", { class: "view-toggle", type: "button", "aria-pressed": "false" }, "Таблица");
	const refresh = () => {
		const open = button.getAttribute("aria-pressed") === "true";
		if (tableNode) tableNode.remove();
		tableNode = open ? bx("fig-table", makeTable()) : null;
		if (tableNode) box.append(tableNode);
		chartNode.hidden = open;
		button.textContent = open ? "График" : "Таблица";
	};
	button.addEventListener("click", () => { button.setAttribute("aria-pressed", String(button.getAttribute("aria-pressed") !== "true")); refresh(); });
	return { box, button, refresh };
}

function kpi(value, labelText, opts = {}) {
	return el("div", { class: "kpi", tip: opts.tip || null },
		bx("kpi-value", value, opts.unit ? sp("unit", " " + opts.unit) : null),
		bx("kpi-label", labelText));
}

function legend(items) {
	return bx("legend", items.filter(Boolean).map(([key, name]) => sx(el("i", { class: cls("key", key) }), name)));
}

function screenHead(eyebrow, title, lede) {
	return el("header", { class: "screen-head" }, eyebrow ? sp("eyebrow", eyebrow) : null, el("h1", {}, title), lede ? pa(lede) : null);
}

function section(title, ...cards) {
	const items = cards.flat().filter(Boolean);
	return items.length ? bx("section", title ? sp("eyebrow row-label", title) : null, bx("grid", items)) : null;
}
const sec = (...cards) => section("", ...cards);

function more(cards) {
	const items = cards.filter(Boolean);
	const box = el("div", { class: "more" });
	const button = el("button", { class: "more-toggle", type: "button", "aria-expanded": "false" },
		`Ещё ${fmt.num(items.length)} ${plural(items.length, ["карточка", "карточки", "карточек"])}`);
	button.addEventListener("click", () => { box.classList.add("is-open"); button.setAttribute("aria-expanded", "true"); });
	box.append(button, bx("more-body", bx("grid section", items)));
	return box;
}

function chooser(options, current, onPick, labelText) {
	const group = el("div", { class: "chooser", role: "group", "aria-label": labelText });
	for (const opt of options) {
		const button = el("button", { type: "button", "aria-pressed": String(opt.value === current) }, opt.label, opt.hint ? sp("w", opt.hint) : null);
		button.addEventListener("click", () => {
			for (const b of group.children) b.setAttribute("aria-pressed", String(b === button));
			onPick(opt.value);
		});
		group.append(button);
	}
	return group;
}

/* ── заголовок и λ ── */

function quantile7(sorted, q) {
	const n = sorted.length;
	if (!n) return NaN;
	const h = (n - 1) * q;
	const lo = Math.floor(h);
	const hi = Math.min(lo + 1, n - 1);
	return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo]);
}

function roundHalfUp(x) {
	return Math.floor(x + 0.5 + 1e-9);
}

function bookLambda(d) {
	const head = obj(d.fair_value.headline);
	return isNum(head.own_macro_confidence) ? head.own_macro_confidence
		: isNum(d.fair_value.own_macro_confidence) ? d.fair_value.own_macro_confidence : 0.5;
}

// Шаг ползунка — сетка λ выпуска, та же, что у таблиц `by_lambda`.
function lambdaStep(d) {
	const s = obj(d.fair_value.headline).lambda_step;
	return isNum(s) && s > 0 ? s : 0.05;
}

function lambdaNow(d) { return LAMBDA === null ? bookLambda(d) : LAMBDA; }
function atBookLambda(d) { return LAMBDA === null || Math.abs(LAMBDA - bookLambda(d)) < 1e-9; }

function centresAt(head, lam) {
	const n = Math.min(head.low_draws.length, head.high_draws.length);
	const out = new Array(n);
	for (let i = 0; i < n; i++) {
		const lo = head.low_draws[i];
		out[i] = lo + lam * (head.high_draws[i] - lo);
	}
	return out;
}

function headlineAt(head, lam) {
	if (lam === null || Math.abs(lam - head.own_macro_confidence) < 1e-9) {
		return { median: head.median, printed_median: head.printed_median, band80: head.band80, printed_band80: head.printed_band80,
			band50: head.band50, printed_band50: head.printed_band50, release: true };
	}
	const c = centresAt(head, lam).sort((a, b) => a - b);
	const q = (p) => quantile7(c, p);
	const print = (v) => roundHalfUp(v / head.print_step) * head.print_step;
	const median = q(0.5);
	const band80 = [q(0.1), q(0.9)];
	const band50 = [q(0.25), q(0.75)];
	return { median, printed_median: print(median), band80, printed_band80: band80.map(print), band50, printed_band50: band50.map(print), release: false };
}

function pointAt(d, lam) {
	const fv = d.fair_value;
	if (lam === null || Math.abs(lam - bookLambda(d)) < 1e-9) return fv.central;
	const view = obj(fv.rates_view);
	return view.low + lam * (view.high - view.low);
}

function printedPoint(d, lam) {
	const fv = d.fair_value;
	const head = obj(fv.headline);
	if (lam === null || Math.abs(lam - bookLambda(d)) < 1e-9) return isNum(head.printed_point) ? head.printed_point : fv.printed_central;
	return roundHalfUp(pointAt(d, lam) / head.print_step) * head.print_step;
}

function atLambda(rows, lam) {
	if (!Array.isArray(rows) || !isNum(lam)) return null;
	return rows.find((r) => isNum(r.lambda) && Math.abs(r.lambda - lam) < 1e-9) || null;
}

// Знаков после запятой у цены на акцию — по шагу печати выпуска (`headline.print_step`).
function pd(d) { const s = obj(obj(obj(d).fair_value).headline).print_step; return isNum(s) && s > 0 ? exactDigits(s, 3) : 0; }
function priceNum(d, v) { return fmt.num(v, pd(d)); }

function lambdaRow(d, block) {
	const b = obj(block);
	if (atBookLambda(d)) return { row: b, where: "" };
	const at = atLambda(b.by_lambda, LAMBDA);
	return at ? { row: at, where: ` при λ = ${num2(LAMBDA)}` } : { row: b, where: " (при λ книги)" };
}

/* ── эмитент, периоды, подписи из выпуска ── */

function company(d) { return (d && obj(obj(d.meta).company).name) || "эмитент"; }
function tickers(d) { return list(obj(obj(d && d.meta).company).tickers).map(String); }
function ticker(d) { const c = obj(obj(d && d.meta).company); return c.main_ticker || tickers(d)[0] || "акция"; }
function others(d) { return tickers(d).filter((t) => t !== ticker(d)); }
function tickerList(d) { return tickers(d).length ? tickers(d).join(" · ") : ticker(d); }
// Одна категория акций: тикера и слов «обеих категорий» в подписях нет.
function solo(d) { return tickers(d).length < 2; }
function both(d) { return solo(d) ? "" : " обеих категорий"; }
function tk(d, t, sep = " ") { return solo(d) ? "" : sep + t; }
function toPrice(d, t) { return solo(d) ? "к цене" : `к ${t}`; }
// Термины книги — словарь выпуска `meta.terms`; своих слов для них нет: без ключа — родовое слово.
// Подпись прибыли в движке: термин книги, когда он сам называет акционеров («прибыль акционеров» — отчётная МСФО),
// иначе — «Прибыль акционерам».
function shProfit(d) { const t = obj(obj(obj(d).meta).terms).profit_short; return t && /акционер/.test(t) ? upperFirst(ruText(t)) : "Прибыль акционерам"; }
function term(k, a = "") { const t = obj(obj(obj(DATA).meta).terms)[k]; return t ? ruText(t) : a; }
function lt(n, a) { const t = term("lt_level"); return t ? `${n} ${t}` : `${a} ${n}`; }
const roeLt = (a = "долгосрочный") => term("roe_lt") || lt("ROE", a), ci = () => term("cir", "C/I");
// Строка вне основного бизнеса: в шапке столбца — термин без уточнения в скобках, целиком — в подсказке.
function noncoreHead() { const t = upperFirst(term("noncore")); return t ? el("span", { tip: t }, shortAxis(t)) : "Вне осн. бизнеса"; }
// Делитель «на акцию» — число и подпись выпуска; без поля — акции в обращении.
// Форма панели (DASHBOARD §7).
function panelForm(d) { const m = obj(d.meta); return !!(m.basis_labels || obj(m.shares).divisor_mln); }

// Эмитент платит раз в год (документ политики), календарь модели — по кварталам прибыли: карточки — по годам.
function annualPayer(d) { return obj(obj(d.dividends).policy).frequency === "annual"; }
// Годовой плательщик при квартальном календаре модели (есть `model_quarters`): без объявления — ожидание модели (П§2).
function annualModel(d) { return annualPayer(d) && Array.isArray(obj(d.dividends).model_quarters); }
// Делитель дивиденда: акции, на которые эмитент делит пул (`meta.shares.dividend_eligible_mln` — размещённые без
// собственных акций банка); без поля — размещённые акции. `share` — доля прибыли на этих акциях при доле ключа на
// размещённых: DPS один и тот же.
function dpsShares(d) {
	const s = obj(obj(d.meta).shares);
	return isNum(s.dividend_eligible_mln) && isNum(s.issued_mln) && s.dividend_eligible_mln > 0
		? { mln: s.dividend_eligible_mln, words: "акций с правом на дивиденд", short: "акций с правом на дивиденд", share: (v) => (isNum(v) ? v * s.dividend_eligible_mln / s.issued_mln : v) }
		: { mln: s.issued_mln, words: "размещённых акций", short: "акций", share: (v) => v };
}

function divisor(d) {
	const s = obj(obj(d.meta).shares);
	return isNum(s.divisor_mln) ? `${num1(s.divisor_mln)} млн: ${ruText(s.divisor_label || "делитель выпуска")}` : `${num1(s.outstanding_mln)} млн акций в обращении${both(d)}`;
}
// Подписи базиса (`meta.basis_labels`) — подвалом у карточек с ROE и P/E.
function basisLabel(d, k) { return ruText(obj(obj(d.meta).basis_labels)[k] || ""); }
function basisFoot(d, ...keys) {
	const words = { profit: "Прибыль", roe: "ROE", divisor: "На акцию" };
	const out = keys.filter((k) => basisLabel(d, k)).map((k) => `${words[k]} — ${basisLabel(d, k)}.`);
	return out.length ? foot(out.join(" ")) : null;
}
// База суммы дивиденда — код узла (`amount_basis`), подпись — из выпуска; без кода строки нет.
function amountBasis(d, node) { const t = basisLabel(d, `dividend_${obj(node).amount_basis}`); return t ? `Сумма дивиденда — ${t}. ` : ""; }
const splitText = (a) => (isNum(a.factor) ? `1 к ${fmt.num(a.factor, exactDigits(a.factor, 3))}` : "—");
// Слова записи дивиденда: решение из выпуска, иначе период, иначе год прибыли.
function divLabel(r) { return r.label ? ruText(r.label) : `за ${r.period ? periodLabel(r.period) : r.year || "—"}`; }
// Оценочная дата (названа составителем или стоит окном) печатается «≈».
function est(e) { return !!e.estimated || (!!e.precision && e.precision !== "day"); }

const PERIOD_WORDS = { quarter: { one: "квартал", many: "кварталы", pgen: "кварталов" }, month: { one: "месяц", many: "месяцы", pgen: "месяцев" } };
function unitWords(unit) { return PERIOD_WORDS[unit] || PERIOD_WORDS.quarter; }
function modelUnit(d) { return unitWords(obj(d.meta).period_unit); }
function inputUnit(d) { return unitWords(obj(d.meta).input_unit || "month"); }

function periodLabel(id) {
	const s = String(id === null || id === undefined ? "" : id);
	let m = /^(\d{4})Q([1-4])$/.exec(s);
	if (m) return `${m[2]}${NBSP}кв.${NBSP}${m[1]}`;
	m = /^(\d{4})M(\d{2})$/.exec(s);
	if (m && +m[2] >= 1 && +m[2] <= 12) return `${MONTHS_NOM[+m[2] - 1]} ${m[1]}`;
	return s || "—";
}
function periodShort(id) {
	const s = String(id === null || id === undefined ? "" : id);
	let m = /^\d\d(\d\d)Q([1-4])$/.exec(s);
	if (m) return `${m[2]}К’${m[1]}`;
	m = /^\d\d(\d\d)M(\d{2})$/.exec(s);
	if (m && +m[2] >= 1 && +m[2] <= 12) return `${MONTHS_AXIS[+m[2] - 1]}’${m[1]}`;
	return s;
}
function periodWord(id) {
	return periodLabel(id).replace(/\s\d{4}$/, "");
}
function quarterX(id) {
	const m = /^(\d{4})Q([1-4])$/.exec(String(id));
	return m ? +m[1] - 1 + +m[2] / 4 : null;
}

const BASIS = { ifrs: "МСФО группы", ras: "РСБУ банка", mgmt: "упр.", engine: "движок", regulatory: "норматив ЦБ", sector: "прогноз сектора", market: "рынок" };
function basisName(b) { return BASIS[b] || b || ""; }
const CODE_WORDS = { ifrs_ni_shareholders: "прибыль группы по МСФО, приходящаяся на акционеров", ifrs_ni_adjusted: "прибыль группы по МСФО без неденежных статей",
	issued: "размещённые акции", outstanding: "акции в обращении", residual_above_requirement: "остаток сверх требований", ceil_kopeck: "до копейки вверх", half_up_kopeck: "до копейки",
	none: "без округления", quarterly: "ежеквартально", annual: "раз в год", dividend_first: "при нехватке капитала первым уступает рост портфеля; дивиденд снижается только при нулевом росте",
	growth_first: "при нехватке капитала первым уступает дивиденд; рост портфеля замедляется после него" };
function codeText(x) { return x === true ? "да" : x === false ? "нет" : CODE_WORDS[x] || ruText(x); }
function refText(x) { const m = /^ofz_(\d+)y$/.exec(x); return m ? `ОФЗ ${m[1]}${NBSP}г.` : x === "key" ? "ключевая" : ruText(x); }

function worldName(d, k) { return obj(obj(obj(d.worlds).rows)[k]).name || k; }
function regimeName(d, k) { return obj(obj(obj(d.regimes).rows)[k]).title || k; }
function scenarioName(d, k) { return obj(obj(obj(d.capital).scenarios)[k]).title || k; }
function layerTitle(d, k) { return obj(obj(d.layers)[k]).title || k; }
function capTitle(d, k) { return obj(obj(d.capital).titles)[k] || k; }
function metricTitle(d, m) {
	const k = { n20_0: "n20", n1_1: "n11" }[m] || m;
	return obj(obj(d.capital).titles)[k] || m || capTitle(d, "n20");
}
function keyName(d, k) {
	if (!d) return k;
	const w = obj(obj(d.worlds).rows)[k], r = obj(obj(d.regimes).rows)[k], s = obj(obj(d.capital).scenarios)[k];
	return (w && w.name) || (r && r.title) || (s && s.title) || k;
}
function regimeOrder(d) { return list(obj(d.regimes).order).length ? d.regimes.order : Object.keys(obj(obj(d.regimes).rows)); }
function scenarioOrder(d) { return list(obj(d.grid).scenario_order).length ? d.grid.scenario_order : Object.keys(obj(obj(d.capital).scenarios)); }
function worldOrder(d) { return list(obj(d.worlds).order).length ? d.worlds.order : Object.keys(obj(obj(d.worlds).rows)); }

function byYear(rows, year) { const r = list(rows).find((x) => x.year === year); return r ? r.value : null; }

const SERIES = [MODEL, GREY, THIRD, NEG, MARKET];
const SERIES_KEYS = ["key-model", "key-neutral", "key-third", "key-neg", "key-market"];
const WORLD_COLORS = [MODEL, THIRD, MARKET];
const WORLD_KEYS = ["key-line key-model", "key-line key-third", "key-line key-market"];

/* ── распределение (герой) ── */

function distributionChart(d) {
	const head = d.fair_value.headline;
	const markets = tickers(d).map((t) => ({ t, v: obj(head.market_by_ticker)[t], main: t === ticker(d) })).filter((m) => isNum(m.v));
	if (!markets.length && isNum(head.market)) markets.push({ t: ticker(d), v: head.market, main: true });
	return chart((W) => {
		const lam = lambdaNow(d);
		const centres = centresAt(head, lam).sort((a, b) => a - b);
		const hl = headlineAt(head, LAMBDA);
		const point = pointAt(d, LAMBDA);
		const main = markets.find((m) => m.main) || markets[0];
		const narrow = W < 520;
		const H = narrow ? 238 : 286;
		const m = { l: 10, r: 12, t: 40, b: 58 };
		const base = H - m.b;
		const hi = Math.max(quantile7(centres, 0.995), ...markets.map((x) => x.v * 1.12), hl.band80[1] * 1.08);
		const unit = niceStep(hi, 8);
		const xmax = Math.ceil(hi / unit) * unit;
		const x = scale(0, xmax, m.l, W - m.r);
		const n = centres.length;
		const mean = centres.reduce((s, v) => s + v, 0) / n;
		const sd = Math.sqrt(centres.reduce((s, v) => s + (v - mean) ** 2, 0) / Math.max(1, n - 1));
		const iqr = quantile7(centres, 0.75) - quantile7(centres, 0.25);
		const bw = Math.max(xmax / 200, 0.9 * Math.min(sd, iqr / 1.34 || sd) * n ** -0.2);
		const bins = 480, width = xmax / bins;
		const counts = new Float64Array(bins);
		for (const c of centres) if (c >= 0 && c < xmax) counts[Math.floor(c / width)] += 1;
		const density = (v) => {
			let sum = 0;
			for (let j = 0; j < bins; j++) {
				if (!counts[j]) continue;
				const c = (j + 0.5) * width, a = (v - c) / bw, b = (v + c) / bw;
				if (a > -5 && a < 5) sum += counts[j] * Math.exp(-0.5 * a * a);
				if (b > -5 && b < 5) sum += counts[j] * Math.exp(-0.5 * b * b);
			}
			return sum;
		};
		const samples = Math.max(90, Math.min(260, Math.round((W - m.l - m.r) / 2.5)));
		const grid = [];
		for (let i = 0; i <= samples; i++) { const v = (xmax * i) / samples; grid.push([v, density(v)]); }
		const ymax = Math.max(...grid.map((p) => p[1])) * 1.1 || 1;
		const y = scale(0, ymax, base, m.t);
		const areaOn = (a, b) => {
			const pts = [[a, density(a)], ...grid.filter((p) => p[0] > a && p[0] < b), [b, density(b)]];
			return `M${x(a)},${base} ` + pts.map(([v, f]) => `L${x(v).toFixed(1)},${y(f).toFixed(1)}`).join(" ") + ` L${x(b)},${base} Z`;
		};
		const svg = svgBox(W, H, "Распределение справедливой цены по суждениям книги");
		svg.append(
			sv("path", { d: areaOn(0, xmax), fill: "var(--model-wash-1)" }),
			sv("path", { d: areaOn(hl.band80[0], hl.band80[1]), fill: "var(--model-wash-2)" }),
			sv("path", { d: areaOn(hl.band50[0], hl.band50[1]), fill: "var(--model-wash-3)" }),
			sv("path", { d: "M" + grid.map(([v, f]) => `${x(v).toFixed(1)},${y(f).toFixed(1)}`).join(" L"), fill: "none", stroke: MODEL, [SW]: 2, "stroke-linejoin": "round" }),
			line(m.l, base, W - m.r, base, { class: "axisline" }));
		const ys = base + 20;
		svg.append(
			line(x(hl.band80[0]), ys, x(hl.band80[1]), ys, { stroke: MODEL, [SW]: 1.5 }),
			line(x(hl.band80[0]), ys - 5, x(hl.band80[0]), ys + 5, { stroke: MODEL, [SW]: 1.5 }),
			line(x(hl.band80[1]), ys - 5, x(hl.band80[1]), ys + 5, { stroke: MODEL, [SW]: 1.5 }),
			sv("rect", { x: x(hl.band50[0]), y: ys - 6, width: Math.max(2, x(hl.band50[1]) - x(hl.band50[0])), height: 12, rx: 3, fill: "var(--model-wash-3)", stroke: MODEL, [SW]: 1.5 }),
			line(x(hl.median), ys - 8, x(hl.median), ys + 8, { stroke: INK, [SW]: 2.5 }),
			line(x(hl.median), m.t - 4, x(hl.median), base, { stroke: INK, [SW]: 1.5 }));
		for (const mk of markets.slice().sort((a, b) => a.main - b.main)) {
			svg.append(line(x(mk.v), m.t - 4, x(mk.v), ys + 10, { stroke: MARKET, [SW]: mk.main ? 2 : 1.6, "stroke-dasharray": mk.main ? null : "4 3" }));
		}
		const px = x(point);
		svg.append(sv("path", { d: `M${px},${base - 6} L${px + 6},${base} L${px},${base + 6} L${px - 6},${base} Z`, fill: SURF, stroke: INK, [SW]: 1.6 }));
		const marketLeft = main && main.v < hl.median;
		const tops = [
			{ x: x(hl.median), text: `медиана ${fmt.rub(hl.printed_median)}`, pref: marketLeft ? "right" : "left" },
			main ? { x: x(main.v), text: `${solo(d) ? "рынок" : main.t} ${rubM(main.v)}`, pref: marketLeft ? "left" : "right" } : null,
		].filter(Boolean).map((t) => {
			const w = textWidth(t.text, 13, 640);
			let x0 = t.pref === "left" ? t.x - w - 6 : t.x + 6;
			if (x0 < 2) x0 = t.x + 6;
			if (x0 + w > W - 2) x0 = t.x - w - 6;
			return { ...t, w, x0, x1: x0 + w };
		});
		const rows = stackLabels(tops, 10);
		for (const t of tops) svg.append(label(t.x0, 14 + t.row * 16 + (rows === 1 ? 6 : 0), t.text, { class: "label-strong" }));
		const pointText = `точка ${fmt.rub(printedPoint(d, LAMBDA))}`;
		const pw = textWidth(pointText, 12.5, 520);
		let plx = px + 9;
		if (plx + pw > W - 2) plx = px - pw - 9;
		svg.append(label(plx, base - 9, pointText));
		const marks = ticks(0, xmax, narrow ? 4 : 7);
		marks.forEach((t, i) => {
			const tx = x(t);
			const anchor = t === 0 ? "start" : tx > W - 34 ? "end" : "middle";
			svg.append(line(tx, ys + 14, tx, ys + 18, { class: "axisline" }),
				text(anchor === "end" ? W - 1 : tx, H - 6, t === 0 ? "0" : fmt.num(t) + (i === marks.length - 1 ? THIN + "₽" : ""), { class: "tick", "text-anchor": anchor }));
		});
		const hot = (x0, w, tip) => sv("rect", { class: "hit", x: x0, y: m.t - 8, width: w, height: ys + 12 - (m.t - 8), tip });
		svg.append(
			hot(x(hl.band50[0]), Math.max(6, x(hl.band50[1]) - x(hl.band50[0])), { title: "Полоса 50 % (P25–P75)",
				rows: [["от", fmt.rub(hl.printed_band50[0])], ["до", fmt.rub(hl.printed_band50[1])]],
				note: hl.release ? "числа выпуска" : "пересчитано ползунком λ из прогонов выпуска" }),
			hot(x(hl.median) - 8, 16, { title: "Медиана по суждениям книги", rows: [["печать", fmt.rub(hl.printed_median)], ["точно", rub2(hl.median)]] }),
			...markets.map((mk) => hot(x(mk.v) - 6, 12, { title: "Рыночная цена", rows: markets.map((q) => [q.t, rub2(q.v)]),
				note: `на ${fmt.date(obj(d.meta).valuation_date)}` })),
			hot(px - 8, 16, { title: "Точка при значениях книги", rows: [["печать", fmt.rub(printedPoint(d, LAMBDA))], ["точно", rub2(point)]] }));
		return svg;
	}, "Распределение справедливой цены: медиана, полосы 80 и 50 процентов, рынок и точка");
}

/* ── ряд «диапазон книги → что нужно рынку» ── */

function rangeRowChart(row) {
	return chart((W) => {
		const H = 34;
		const [r0, r1] = row.range;
		const vals = [r0, r1, row.book].concat(isNum(row.solved) ? [row.solved] : []);
		let lo = Math.min(...vals), hi = Math.max(...vals);
		const pad = (hi - lo) * 0.12 || Math.abs(hi) * 0.1 || 0.01;
		lo -= pad; hi += pad;
		const x = scale(lo, hi, 8, W - 8);
		const svg = svgBox(W, H);
		const cy = H / 2;
		svg.append(line(8, cy, W - 8, cy, { class: "gridline" }),
			line(x(r0), cy, x(r1), cy, { stroke: "var(--model-wash-3)", [SW]: 8, "stroke-linecap": "round" }),
			line(x(row.book), cy - 8, x(row.book), cy + 8, { stroke: INK, [SW]: 2 }));
		if (isNum(row.solved)) svg.append(sv("circle", { cx: Math.max(8, Math.min(W - 8, x(row.solved))), cy, r: 6, fill: MARKET, ...RING }));
		svg.append(sv("rect", { class: "hit", x: 0, y: 0, width: W, height: H, tip: { title: row.name,
			rows: [["нужно рынку", isNum(row.solved) ? reverseValue(row, row.solved) : "недостижимо"], ["в книге", reverseValue(row, row.book, true)],
				["диапазон книги", reverseRange(row)]] } }));
		return svg;
	}, `${row.name}: диапазон книги и значение, при котором медиана равна рынку`);
}

function reverseRange(r) {
	const [a, b] = list(r.range);
	return isNum(a) && isNum(b) && a !== b ? `${reverseValue(r, a, true)} … ${reverseValue(r, b, true)}` : "—";
}

function reverseValue(row, value, bookSide = false) {
	if (!isNum(value)) return "—";
	const u = row.unit;
	if (u === "pp") return bookSide && value === 0 ? "0" : fmt.pp(value, bookSide ? exactDigits(value * 100, 2) : 2);
	if (u === "number") return fmt.num(value, bookSide ? exactDigits(value, 3) : 3);
	if (u === "mix") return pct0(value);
	if (u === "bn") return fmt.bn(value);
	return fmt.num(value * 100, bookSide ? exactDigits(value * 100, 2) : 2) + THIN + "%";
}

/* ── гантели, столбцы, линии, полосы ── */

function dumbbellChart(rows, opts = {}) {
	const f = opts.fmt || num2;
	return chart((W) => {
		const rowH = 46;
		const H = rows.length * rowH + 24;
		const values = rows.flatMap((r) => [r.a, r.b]).concat(opts.extra || []).filter(isNum);
		const lo = Math.min(...values), hi = Math.max(...values);
		const pad = (hi - lo) * 0.2 || Math.abs(hi) * 0.1 || 1;
		const x = scale(lo - pad, hi + pad, 8, W - 8);
		const svg = svgBox(W, H);
		for (const t of ticks(lo - pad, hi + pad, W < 420 ? 3 : 6)) {
			const s = f(t), half = textWidth(s, 12.5, 400) / 2;
			svg.append(line(x(t), 0, x(t), H - 20, { class: "gridline" }));
			if (x(t) - half >= 0 && x(t) + half <= W) svg.append(text(x(t), H - 4, s, { class: "tick", "text-anchor": "middle" }));
		}
		rows.forEach((r, i) => {
			const cy = i * rowH + 30, both = isNum(r.a) && isNum(r.b), left = Math.min(r.a, r.b), right = Math.max(r.a, r.b), wide = (v) => textWidth(f(v), 12.5, 520) + 12;
			// Опорная вертикаль — отрезками у строк, мимо подписей строк и значений.
			for (const v of opts.refs || []) {
				const at = x(v), struck = both && ((at > x(left) - wide(left) && at < x(left) - 8) || (at > x(right) + 8 && at < x(right) + wide(right)));
				svg.append(line(at, cy + (struck ? 9 : -9), at, cy + 21, { stroke: INK2, [SW]: 1.2, "stroke-dasharray": "3 3" }));
			}
			svg.append(label(8, cy - 13, r.name));
			if (both) svg.append(line(x(r.a), cy, x(r.b), cy, { stroke: "var(--axis)", [SW]: 2 }));
			for (const [v, color, name] of [[r.a, MODEL, r.aLabel], [r.b, MARKET, r.bLabel]]) {
				if (isNum(v)) svg.append(sv("circle", { cx: x(v), cy, r: 6, fill: color, ...RING, tip: { title: `${r.name}: ${name}`, rows: [[name, f(v)]] } }));
			}
			if (both) svg.append(label(x(left) - 10, cy + 4, f(left), { "text-anchor": "end" }), label(x(right) + 10, cy + 4, f(right)));
		});
		return svg;
	}, opts.label);
}

function columnsChart(items, opts = {}) {
	return chart((W) => {
		const H = opts.height || 220;
		const m = { l: 8, r: 8, t: 22, b: 26 };
		const values = items.map((i) => i.value).filter(isNum);
		const refs = (opts.refs || []).filter((r) => isNum(r.value) && r.value >= 0);
		const vmax = Math.max(...values, ...refs.map((r) => r.value), ...items.flatMap((i) => [i.pair, i.hi, i.mark]).filter(isNum), 1e-9) * 1.14;
		const vmin = Math.min(0, ...values) * 1.14;
		const y = scale(vmin, vmax, H - m.b, m.t);
		const band = (W - m.l - m.r) / Math.max(1, items.length);
		const bw = Math.min(28, band * (opts.pairColor ? 0.36 : 0.56));
		const widest = Math.max(...items.map((it) => textWidth(it.label || String(it.key), 12.5, 400)));
		const every = Math.max(1, Math.ceil((widest + 8) / band));
		const svg = svgBox(W, H, opts.label);
		for (const t of ticks(vmin, vmax, 4)) svg.append(line(m.l, y(t), W - m.r, y(t), { class: "gridline" }));
		items.forEach((it, i) => {
			const mid = m.l + band * (i + 0.5), cx = mid + (opts.pairColor ? bw / 2 + 1 : 0);
			if (isNum(it.pair)) svg.append(sv("rect", { x: mid - bw - 1, y: y(Math.max(0, it.pair)), width: bw, height: Math.max(1, y(0) - y(Math.max(0, it.pair))), rx: 3, fill: opts.pairColor }));
			// Ноль — не пропуск: подпись «0» и цель подсказки.
			if (isNum(it.value)) {
				const top = y(Math.max(0, it.value)), bottom = y(Math.min(0, it.value));
				const tip = { title: it.tipTitle || String(it.key), rows: [[opts.valueName || "значение", opts.fmt ? opts.fmt(it.value) : num1(it.value)]].concat(it.tipRows || []) };
				svg.append(it.value === 0 ? sv("rect", { class: "hit", x: cx - bw / 2, y: top - 22, width: bw, height: 22, tip })
					: sv("rect", { x: cx - bw / 2, y: top, width: bw, height: Math.max(1, bottom - top), rx: 3,
						fill: it.color || opts.color || MODEL, opacity: it.faded ? 0.55 : null, tip }));
				if (isNum(it.lo) && isNum(it.hi)) svg.append(line(cx, y(it.lo), cx, y(it.hi), { stroke: INK2, [SW]: 1.4 }));
				if (isNum(it.mark)) svg.append(line(cx - bw / 2 - 2, y(it.mark), cx + bw / 2 + 2, y(it.mark), { stroke: INK, [SW]: 1.8 }));
				const s = opts.short ? opts.short(it.value, it, band) : fmt.num(it.value);
				const ly = Math.min(top, ...[it.hi, it.mark, it.pair].filter(isNum).map(y));
				if (s && textWidth(s, 12.5, 520) < band - 2) svg.append(label(mid, it.value >= 0 ? ly - 6 : bottom + 14, s, { "text-anchor": "middle" }));
			}
			if ((items.length - 1 - i) % every === 0) svg.append(axisText(mid, H - 8, it.label || String(it.key), W));
		});
		svg.append(line(m.l, y(0), W - m.r, y(0), { class: "axisline" }));
		for (const ref of refs) {
			svg.append(line(m.l, y(ref.value), W - m.r, y(ref.value), { stroke: ref.color || MARKET, [SW]: 1.5, "stroke-dasharray": ref.dash || null }),
				label(W - m.r, y(ref.value) - 6, ref.text, { "text-anchor": "end" }));
		}
		return svg;
	}, opts.label);
}

// Линия идёт по непрерывным участкам: `null` её рвёт; `step` — ступени, `area` — полоса.
function linesChart(series, opts = {}) {
	return chart((W) => {
		const H = opts.height || 240;
		const m = { l: opts.left || 46, r: opts.right || 16, t: opts.top || 18, b: 28 };
		const all = series.flatMap((s) => s.points).filter((p) => isNum(p[1]));
		const areas = series.flatMap((s) => (s.area || []).flatMap((p) => [p[1], p[2]]));
		const refs = (opts.hrefs || []).filter((r) => isNum(r.value));
		const bandKeys = opts.xType === "band" ? opts.categories : null;
		const yvals = all.map((p) => p[1]).concat(areas, refs.map((r) => r.value)).filter(isNum);
		if (!yvals.length) return svgBox(W, 20);
		let y0 = opts.yMin ?? Math.min(...yvals);
		let y1 = opts.yMax ?? Math.max(...yvals);
		const pad = (y1 - y0) * 0.1 || Math.abs(y1) * 0.1 || 1;
		if (opts.yMin === undefined) y0 -= pad;
		if (opts.yMax === undefined) y1 += pad;
		const yMarks = ticks(y0, y1, opts.yTicks || 4);
		const yLabel = opts.yPct ? pctTicks(yMarks) : opts.yFmt || ((t) => fmt.num(t));
		m.l = Math.max(m.l, Math.ceil(Math.max(0, ...yMarks.map((t) => textWidth(yLabel(t), 12.5, 400)))) + 12);
		let x;
		if (bandKeys) {
			const step = (W - m.l - m.r) / bandKeys.length;
			x = (k) => { const i = bandKeys.indexOf(k); return i < 0 ? NaN : m.l + step * (i + 0.5); };
		} else {
			const xs = all.map((p) => p[0]).concat(series.flatMap((s) => (s.area || []).map((p) => p[0])));
			const x0 = opts.xMin ?? Math.min(...xs), x1 = opts.xMax ?? Math.max(...xs);
			x = scale(x0, x1, m.l, W - m.r);
		}
		// Подпись вертикали: на узком экране — короткая (`short`); линия идёт от строки своей подписи и чужих не перечёркивает.
		const vItems = [];
		for (const v of opts.vlines || []) {
			const vx = x(v.x), s = W < 480 && v.short ? v.short : v.text;
			if (!isNum(vx) || !s) continue;
			const w = textWidth(s, 12.5, 520);
			const x0 = vx + 5 + w > W - m.r ? vx - 5 - w : vx + 5;
			vItems.push({ v, text: s, x0, x1: x0 + w });
		}
		const vRows = stackLabels(vItems, 8);
		const y = scale(y0, y1, H - m.b, m.t + Math.max(0, vRows) * 16);
		const svg = svgBox(W, H, opts.label);
		for (const t of yMarks) {
			svg.append(line(m.l, y(t), W - m.r, y(t), { class: "gridline" }), text(m.l - 8, y(t) + 4, yLabel(t), { class: "tick", "text-anchor": "end" }));
		}
		if (bandKeys) {
			const step = (W - m.l - m.r) / bandKeys.length;
			const widest = Math.max(...bandKeys.map((k) => textWidth(opts.xFmt ? opts.xFmt(k) : k, 12.5, 400)));
			const every = Math.max(1, Math.ceil((widest + 10) / step));
			bandKeys.forEach((k, i) => {
				if ((bandKeys.length - 1 - i) % every === 0) svg.append(axisText(x(k), H - 8, opts.xFmt ? opts.xFmt(k) : String(k), W));
			});
		} else {
			let left = Infinity;
			for (const t of (opts.xTicks || ticks(x.d[0], x.d[1], W < 420 ? 4 : 7)).slice().sort((a, b) => b - a)) {
				const s = opts.xFmt ? opts.xFmt(t) : fmt.num(t);
				const tx = x(t), w = textWidth(s, 12.5, 400);
				const anchor = tx - w / 2 < 0 ? "start" : tx + w / 2 > W ? "end" : "middle";
				const x0 = anchor === "start" ? Math.max(0, tx - 2) : anchor === "end" ? W - 1 - w : tx - w / 2;
				if (x0 + w + 8 > left) continue;
				left = x0;
				svg.append(text(anchor === "end" ? W - 1 : anchor === "start" ? Math.max(0, tx - 2) : tx, H - 8, s, { class: "tick", "text-anchor": anchor }));
			}
		}
		svg.append(line(m.l, H - m.b, W - m.r, H - m.b, { class: "axisline" }));
		for (const s of series) {
			if (!s.area || s.area.length < 2) continue;
			const pts = s.area.filter((p) => isNum(x(p[0])) && isNum(p[1]) && isNum(p[2]));
			const up = pts.map((p) => `${x(p[0]).toFixed(1)},${y(p[2]).toFixed(1)}`);
			const down = pts.slice().reverse().map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`);
			if (up.length > 1) svg.append(sv("path", { d: `M${up.join(" L")} L${down.join(" L")} Z`, fill: s.areaFill || "var(--model-wash-2)" }));
		}
		for (const ref of refs) svg.append(line(m.l, y(ref.value), W - m.r, y(ref.value), { stroke: ref.color, [SW]: 1.5, "stroke-dasharray": ref.dash || null }));
		for (const v of opts.vlines || []) {
			const vx = x(v.x), own = vItems.find((t) => t.v === v);
			if (isNum(vx)) svg.append(line(vx, m.t - 6 + (own ? own.row * 16 : 0), vx, H - m.b, { stroke: v.color || INK2, [SW]: 1.2, "stroke-dasharray": v.solid ? null : v.dash || "3 3", tip: v.tip || null }));
		}
		for (const s of series) {
			const ok = (p) => isNum(p[1]) && isNum(x(p[0]));
			const pts = s.points.filter(ok);
			let run = [];
			for (const p of s.line === false ? [] : [...s.points, null]) {
				if (p && ok(p)) { run.push(p); continue; }
				if (run.length > 1) {
					svg.append(sv("path", { d: "M" + run.map((q, k) => (s.step && k ? `H${x(q[0]).toFixed(1)} V${y(q[1]).toFixed(1)}` : `${x(q[0]).toFixed(1)},${y(q[1]).toFixed(1)}`)).join(s.step ? " " : " L"),
						fill: "none", stroke: s.color, [SW]: s.width || 2, "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": s.dash || (s.dashed ? "5 4" : null) }));
				} else if (run.length && !s.dots) svg.append(sv("circle", { cx: x(run[0][0]), cy: y(run[0][1]), r: 2.5, fill: s.color }));
				run = [];
			}
			if (s.dots) {
				for (const p of pts) {
					svg.append(sv("circle", { cx: x(p[0]), cy: y(p[1]), r: s.r || 4.5, fill: s.hollow ? SURF : s.color, stroke: s.hollow ? s.color : SURF, [SW]: 2,
						tip: { title: `${s.name}: ${opts.xFmt ? opts.xFmt(p[0]) : p[0]}`, rows: [[s.name, opts.tipFmt ? opts.tipFmt(p[1]) : num2(p[1])]] } }));
				}
			}
		}
		const refLabels = refs.filter((r) => r.text).map((r) => ({ r, y: y(r.value) + (r.below ? 16 : -6) })).sort((a, b) => a.y - b.y);
		for (let i = 1; i < refLabels.length; i++) if (refLabels[i].y - refLabels[i - 1].y < 15) refLabels[i].y = refLabels[i - 1].y + 15;
		// Подпись горизонтали — у правого края либо там, где её не пересекает вертикаль события.
		const cut = (a, w) => (opts.vlines || []).some((v) => x(v.x) > a - 2 && x(v.x) < a + w + 2);
		for (const { r, y: ly } of refLabels) {
			const s = W < 480 && r.short ? r.short : r.text, w = textWidth(s, 12.5, 520), end = W - m.r - w;
			const a = cut(end, w) ? [m.l + 4, ...opts.vlines.flatMap((v) => [x(v.x) - w - 6, x(v.x) + 6])].find((q) => q >= m.l && q <= end && !cut(q, w)) : null;
			svg.append(label(a ?? W - m.r, Math.min(ly, H - m.b - 4), s, { "text-anchor": isNum(a) ? null : "end" }));
		}
		for (const t of vItems) svg.append(label(t.x0, m.t + 6 + t.row * 16, t.text));
		return svg;
	}, opts.label);
}

function barTrack(segments, domain, opts = {}) {
	const [d0, d1] = domain;
	const pos = (v) => (100 * (v - d0)) / ((d1 - d0) || 1);
	const track = el("div", { class: "bt-track" });
	if (isNum(opts.center)) track.append(el("i", { class: "bt-center", style: `left:${pos(opts.center)}%` }));
	for (const seg of segments) {
		const a = Math.min(seg.from, seg.to), b = Math.max(seg.from, seg.to);
		track.append(el("i", { class: cls("bt-bar", seg.cls), style: `left:${pos(a)}%;width:${Math.max(0.4, pos(b) - pos(a))}%`, tip: seg.tip || null }));
	}
	for (const mark of opts.marks || []) track.append(el("i", { class: cls("bt-mark", mark.cls), style: `left:${pos(mark.at)}%`, tip: mark.tip || null }));
	return track;
}

function waterfall(steps, wide = false) {
	const lo = Math.min(0, ...steps.map((s) => Math.min(s.from, s.to)));
	const hi = Math.max(...steps.map((s) => Math.max(s.from, s.to)));
	return el("div", { class: cls("wf", wide && "wide") }, steps.map((s) => el("div", { class: cls("wf-row", s.total && "is-total") },
		sp("wf-name", s.title, s.hint ? hint(s.hint) : null),
		sp("wf-bar", barTrack([{ from: s.from, to: s.to, cls: s.total ? "is-total" : s.to < s.from ? "is-down" : "is-up",
			tip: { title: s.title, rows: [["значение", s.text]] } }], [lo, hi])),
		sp("wf-val", s.text))));
}

function hbar(name, share, max, opts = {}) {
	return el("div", { class: "hbar", tip: opts.tip || null },
		sp("hbar-name", name),
		sp("hbar-track", el("i", { class: "hbar-fill", style: `width:${Math.max(0, (100 * share) / (max || 1))}%${opts.color ? `;background:${opts.color}` : ""}` })),
		sp("hbar-val", opts.value || fmt.pct(share, share < 0.1 ? 1 : 0)));
}

function sparkline(item, valueText, span = "за год") {
	const h = obj(item.history);
	const pts = list(h.date).map((dt, i) => ({ date: dt, value: list(h.value)[i] })).filter((p) => isNum(p.value));
	if (pts.length < 2) return null;
	const vals = pts.map((p) => p.value);
	const lo = isNum(obj(item.min).value) ? item.min.value : Math.min(...vals);
	const hi = isNum(obj(item.max).value) ? item.max.value : Math.max(...vals);
	const plot = chart((W) => {
		const H = 40;
		const x = scale(0, pts.length - 1, 3, W - 5);
		const y = hi > lo ? scale(lo, hi, H - 5, 5) : () => H / 2;
		const svg = svgBox(W, H, `История ряда «${item.title}»`);
		svg.append(sv("polyline", { points: pts.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" "),
			fill: "none", stroke: MODEL, [SW]: 1.6, "stroke-linejoin": "round", "stroke-linecap": "round" }));
		const last = pts[pts.length - 1];
		svg.append(sv("circle", { cx: x(pts.length - 1), cy: y(last.value), r: 3, fill: MODEL,
			tip: { title: item.title, rows: [[dayOrPeriod(pts[0].date), valueText(pts[0].value)], [dayOrPeriod(last.date), valueText(last.value)]] } }));
		return svg;
	}, `История ряда «${item.title}»`);
	return bx("spark", plot, sp("muted small", `${span}: мин ${valueText(lo)} · макс ${valueText(hi)}`));
}

function stripChart(marks, opts = {}) {
	return chart((W) => {
		const vals = marks.map((mk) => mk.v).concat(opts.band || []).filter(isNum);
		const lo = Math.min(...vals), hi = Math.max(...vals);
		const pad = (hi - lo) * 0.1 || Math.abs(hi) * 0.05 || 0.002;
		const x = scale(lo - pad, hi + pad, 10, W - 10);
		const cy = 26;
		const labelled = marks.filter((mk) => mk.text && isNum(mk.v)).map((mk) => ({ ...placed(x(mk.v), mk.text, W, mk.kind === "model" ? 13 : 12.5, mk.kind === "model" ? 640 : 520), strong: mk.kind === "model" }));
		const rows = stackLabels(labelled, 10);
		const H = cy + 22 + rows * 16 + 20;
		const svg = svgBox(W, H, opts.label);
		svg.append(line(10, cy, W - 10, cy, { class: "gridline" }));
		if (opts.band && isNum(opts.band[0]) && isNum(opts.band[1])) {
			svg.append(sv("rect", { x: x(opts.band[0]), y: cy - 9, width: Math.max(3, x(opts.band[1]) - x(opts.band[0])), height: 18, rx: 6,
				fill: opts.bandFill || "var(--model-wash-2)", stroke: opts.bandStroke || MODEL, [SW]: 1, tip: opts.bandTip || null }));
		}
		const order = { neutral: 0, bench: 1, guide: 2, market: 3, model: 4 };
		for (const mk of marks.slice().sort((a, b) => (order[a.kind] ?? 0) - (order[b.kind] ?? 0))) {
			if (!isNum(mk.v)) continue;
			const mx = x(mk.v);
			if (mk.kind === "neutral") svg.append(line(mx, cy - 12, mx, cy + 12, { stroke: INK2, [SW]: 1.4, "stroke-dasharray": "2 2", tip: mk.tip || null }));
			else if (mk.kind === "guide") svg.append(line(mx, cy - 13, mx, cy + 13, { stroke: MARKET, [SW]: 2.2, tip: mk.tip || null }));
			else if (mk.kind === "bench") svg.append(sv("circle", { cx: mx, cy, r: 5, fill: THIRD, ...RING, tip: mk.tip || null }));
			else if (mk.kind === "market") svg.append(sv("circle", { cx: mx, cy, r: 6.5, fill: MARKET, ...RING, tip: mk.tip || null }));
			else svg.append(sv("circle", { cx: mx, cy, r: 7, fill: MODEL, ...RING, tip: mk.tip || null }));
		}
		for (const t of labelled) svg.append(label(t.x0, cy + 30 + t.row * 16, t.text, { class: t.strong ? "label-strong" : "label" }));
		const tickMarks = ticks(lo - pad, hi + pad, W < 420 ? 3 : 5);
		const tickLabel = opts.pct ? pctTicks(tickMarks) : opts.fmt || ((t) => fmt.num(t));
		for (const t of tickMarks) {
			const s = tickLabel(t), w = textWidth(s, 12.5, 400);
			if (x(t) - w / 2 >= 0 && x(t) + w / 2 <= W) svg.append(text(x(t), H - 3, s, { class: "tick", "text-anchor": "middle" }));
		}
		return svg;
	}, opts.label);
}

/* ── экран «Оценка» ── */

function screenOverview(d) {
	return bx("screen", hero(d), passportRow(d), section("Почему такая оценка", levelsCard(d), pricedTeaser(d), bandDrivers(d)),
		section("Что дальше", reportTeaser(d), dividendsTeaser(d)), sec(eventsCard(d, 6), changesCard(d)), sec(methodNote(d)));
}

const kindName = (k) => (k === "cor" ? "CoR" : "ЧПМ");

function diagWords(target) {
	return target === "median"
		? { subj: "медиана", acc: "медиану", gen: "медианы" }
		: { subj: "точка", acc: "точку", gen: "точки" };
}

function pointVsMedianText(d, lam) {
	const point = pointAt(d, lam);
	const median = headlineAt(obj(d.fair_value.headline), lam).median;
	if (!isNum(point) || !isNum(median) || Math.abs(point - median) < 0.5) return "Точка совпадает с медианой.";
	const above = point > median;
	const pulls = list(obj(d.judgements).rows).filter((j) => j.in_band !== false && isNum(j.mean_shift) && j.mean_shift !== 0 && (j.mean_shift < 0) === above)
		.sort((a, b) => Math.abs(b.mean_shift) - Math.abs(a.mean_shift)).slice(0, 2);
	const detail = pulls.length
		? ` Сильнее всего прогоны ${above ? "вниз" : "вверх"} от точки уводят ${pulls.map((j) => `${lowerFirst(shortAxis(j.name))} (${fmt.signedRub(j.mean_shift, 1)})`).join(" и ")}`
			+ ` — вклад в «среднее прогонов − точка», первый порядок${atBookLambda(d) ? "" : ", при λ книги"}.`
		: "";
	return `Точка ${above ? "выше" : "ниже"} медианы: диапазоны суждений асимметричны.${detail}`;
}

function shortAxis(name) { return String(name || "").replace(/\s*\(.*?\)\s*/g, " ").trim(); }

function isDict(j) { return !!j && [j.book, j.low, j.high].some((v) => v && typeof v === "object"); }

function rangeText(d, j, short = false) {
	if (!j) return "—";
	if (isDict(j)) {
		const lo = obj(j.low), hi = obj(j.high);
		const end = (v, pct) => (isNum(v) ? (pct ? pct1(v) : num1(v * 100)) : "—");
		const keys = Object.keys(obj(j.book)).concat(Object.keys(lo), Object.keys(hi)).filter((k, i, a) => a.indexOf(k) === i);
		const pairs = keys.map((k) => ({ move: Math.abs(hi[k] - lo[k]) || 0, text: `${keyName(d, k)} ${end(lo[k], !isNum(hi[k]))} → ${end(hi[k], true)}` }));
		if (!short || pairs.length < 2) return pairs.map((x) => x.text).join(" · ") || "—";
		return pairs.slice().sort((a, b) => b.move - a.move)[0].text + " · …";
	}
	if (j.unit === "pp") { const k = Math.max(1, exactDigits(j.low * 100, 2), exactDigits(j.high * 100, 2)); return `${fmt.pp(j.low, k)} … ${fmt.pp(j.high, k)}`; }
	return `${formatByUnit(j.low, j.unit, d)} … ${formatByUnit(j.high, j.unit, d)}`;
}

function pBelowText(p) { return fmt.pct(p, isNum(p) && p > 0 && p < 0.01 ? 2 : 0); }

function hero(d) {
	const fv = d.fair_value;
	const head = obj(fv.headline);
	if (!list(head.low_draws).length || !list(head.high_draws).length) return heroWithoutBand(d);
	const markets = obj(head.market_by_ticker);
	const main = ticker(d);
	const view = obj(fv.rates_view);
	// Оси полосы — суждения `in_band`, включая оси-словари.
	const axes = list(obj(d.judgements).rows).filter((j) => j.in_band === true).length || list(head.contributions).length;
	const copy = el("div", { class: "hero-copy", id: "fv-hero" });
	const tiles = el("div", { class: "tiles", id: "fv-tiles" });
	const plot = distributionChart(d);
	const table = () => {
		const hl = headlineAt(head, LAMBDA);
		const { row, where } = lambdaRow(d, head);
		return dataTable([
			Tc("Величина", (r) => r[0], "name"),
			Nc("Точно", (r) => r[1]),
			Nc("Печать", (r) => r[2]),
		], [
			["P10 — нижний край полосы 80 %", rub2(hl.band80[0]), fmt.rub(hl.printed_band80[0])],
			["P25 — нижний край полосы 50 %", rub2(hl.band50[0]), fmt.rub(hl.printed_band50[0])],
			["Медиана", rub2(hl.median), fmt.rub(hl.printed_median)],
			["P75 — верхний край полосы 50 %", rub2(hl.band50[1]), fmt.rub(hl.printed_band50[1])],
			["P90 — верхний край полосы 80 %", rub2(hl.band80[1]), fmt.rub(hl.printed_band80[1])],
			["Точка при значениях книги", rub2(pointAt(d, LAMBDA)), fmt.rub(printedPoint(d, LAMBDA))],
			["Среднее прогонов" + where, rub2(row.mean), "—"],
			...tickers(d).map((t) => [`Рынок${tk(d, t, ", ")}`, rubM(markets[t]), "—"]),
			...tickers(d).map((t) => [`P(центр ниже ${solo(d) ? "рынка" : t})${where}`, pBelowText(obj(row.p_below_by_ticker)[t]), "—"]),
		], { caption: atBookLambda(d) ? "Числа выпуска" : `λ = ${num2(LAMBDA)}: квантили и точка — пересчёт из прогонов выпуска, остальное — таблица выпуска для этого λ` });
	};
	const fig = withTable(plot, table);
	const out = el("output", { class: "lambda-out", for: "lambda" });
	const reset = el("button", { class: "lambda-reset", type: "button", hidden: true }, "вернуть λ книги");
	const slider = el("input", { id: "lambda", type: "range", min: "0", max: "1", step: String(lambdaStep(d)),
		value: String(bookLambda(d)), "aria-label": "Вес собственного взгляда на инфляцию и ставки, λ" });
	const lambdaBox = bx("lambda",
		bx("lambda-top", sp("lambda-title", "Взгляд на инфляцию и ставки"), out),
		bx("lambda-ends",
			sx(el("i", { class: "key key-market" }), layerTitle(d, "macro_neutral")),
			sx(layerTitle(d, "analytical"), el("i", { class: "key key-model" }))),
		slider,
		pr("lambda-note",
			isNum(view.low) ? `Ось ставок — не интервал, а вклад собственного взгляда: низ ${fmt.rub(view.low)} — слой «${layerTitle(d, "macro_neutral")}», верх ${fmt.rub(view.high)} — «${layerTitle(d, "analytical")}». ` : "",
			"Ползунок пересчитывает полосу из прогонов выпуска; прочие числа — таблица выпуска на шаге ползунка. ", reset));
	const chartCard = el("section", { class: "card hero-chart" },
		bx("card-head",
			dx(el("h2", {}, "Распределение справедливой цены"),
				pr("sub", `${fmt.num(head.draws)} прогонов по ${fmt.num(axes)} ${plural(axes, ["суждению", "суждениям", "суждениям"])} книги в их диапазонах`)),
			fig.button),
		fig.box,
		legend([["key-b80", "80 % прогонов"], ["key-b50", "50 %"], ["key-line key-ink", "медиана"], isNum(markets[main]) && ["key-line key-market", `рынок${tk(d, main, ", ")}`],
			...others(d).filter((t) => isNum(markets[t])).map((t) => ["key-line key-market2", `рынок, ${t}`]), ["key-diamond", "точка при значениях книги"]]),
		lambdaBox);

	const update = () => {
		const lam = LAMBDA;
		const hl = headlineAt(head, lam);
		const { row, where } = lambdaRow(d, head);
		const pBelow = row.p_below_market;
		const percentile = row.market_percentile;
		const upside = obj(row.upside);
		copy.replaceChildren(
			sp("eyebrow", `Справедливая стоимость акции · ${tickerList(d)} · ${fmt.date(d.meta.valuation_date)}`),
			el("div", { class: "hero-figure", id: "fv-headline" },
				sp("hero-approx", "≈"),
				el("span", { class: "hero-value", id: "kpi-central" }, priceNum(d, hl.printed_median)),
				sp("hero-unit", "₽")),
			pr("hero-caption", `медиана по суждениям книги ${d.meta.book_version || ""}`,
				sp("muted", ` · точно ${rub2(hl.median)}${atBookLambda(d) ? "" : ` · при λ = ${num2(lam)}`}`)),
			el("div", { class: "upside", id: "fv-upside" }, tickers(d).map((t) => sx(`${toPrice(d, t)} `, strong(fmt.signedPct(upside[t], 0)))),
				where ? sp("muted", where.trim()) : null),
			bx("bands",
				bx("band-row", el("i", { class: "band-key b80" }), sp("what", "полоса 80 %"),
					sp("range", `${priceNum(d, hl.printed_band80[0])}–${priceNum(d, hl.printed_band80[1])}${THIN}₽`)),
				bx("band-row", el("i", { class: "band-key b50" }), sp("what", "полоса 50 %"),
					sp("range", `${priceNum(d, hl.printed_band50[0])}–${priceNum(d, hl.printed_band50[1])}${THIN}₽`))),
			el("div", { class: "verdict", id: "fv-verdict" },
				bx("verdict-top",
					sp("verdict-num", pBelowText(pBelow)),
					sp("verdict-title", `вероятность, что справедливая цена ниже рыночной цены${tk(d, main)} — ${rubM(markets[main])}`)),
				el("div", { class: "meter", role: "img", "aria-label": `P(ниже рынка) ${pBelowText(pBelow)}` },
					el("i", { style: `width:${Math.max(0, Math.min(100, (pBelow || 0) * 100))}%` })),
				sp("verdict-note", `по ${fmt.num(head.draws)} прогонам`,
					isNum(percentile) ? ` · рынок — на ${fmt.num(percentile * 100, percentile > 0 && percentile < 0.01 ? 2 : 0)}-м перцентиле распределения центра` : "",
					others(d).map((t) => ` · ${t}: ${pBelowText(obj(row.p_below_by_ticker)[t])}`).join(""), where)));
		tiles.replaceChildren(...heroTiles(d, lam));
		out.value = atBookLambda(d) ? `λ = ${num2(bookLambda(d))} · книга` : `λ = ${num2(lam)} · точка ${fmt.rub(printedPoint(d, lam))}`;
		reset.hidden = atBookLambda(d);
	};
	slider.addEventListener("input", () => {
		const v = Number(slider.value);
		LAMBDA = Math.abs(v - bookLambda(d)) < 1e-9 ? null : v;
		update();
		repaint(plot);
		fig.refresh();
	});
	reset.addEventListener("click", () => {
		LAMBDA = null;
		slider.value = String(bookLambda(d));
		update();
		repaint(plot);
		fig.refresh();
		slider.focus();
	});
	if (LAMBDA !== null) slider.value = String(LAMBDA);
	update();
	return dx(bx("hero", copy, chartCard), tiles);
}

function heroTiles(d, lam) {
	const fv = d.fair_value;
	const out = [];
	const bfl = obj(fv.bank_first_line);
	const { row, where } = lambdaRow(d, bfl);
	const w = diagWords(bfl.target);
	if (isNum(row.fair_pb_median)) {
		out.push(el("section", { class: "card tile" },
			tileLabel("Капитал: модель против рынка"),
			sp("tile-value", fmt.x(row.fair_pb_median, 2), sp("unit", `P/B против ${fmt.x(row.market_pb, 2)}`)),
			pr("tile-note", `Справедливый P/B (${w.subj}) против рыночного${where}. PV доходности сверх стоимости капитала: модель ${fmt.signedBn(row.excess_median, 0)}, `
				+ `рынок ${fmt.signedBn(row.excess_market, 0)} (капитализация ${fmt.num(obj(d.market).cap)} минус капитал ${fmt.num(row.bv_v)}).`)));
		out.push(el("section", { class: "card tile" },
			tileLabel(`Цена 1 п.п. ${roeLt("долгосрочного")}`),
			sp("tile-value", priceNum(d, row.rub_per_1pp_roe), sp("unit", "₽ на акцию")),
			pr("tile-note", `${upperFirst(roeLt())} ${pct1(row.roe_tc)} против стоимости капитала ${pct1(row.k_tc)}${where}; `
				+ `0,1${NBSP}п.п. CoR — ${fmt.signedRub(row.rub_per_01pp_cor)}, 0,1${NBSP}п.п. ЧПМ — ${fmt.signedRub(row.rub_per_01pp_nim)}`
				+ `${isNum(row.rub_per_1pp_buffer) ? `, 1${NBSP}п.п. запаса капитала — ${fmt.signedRub(row.rub_per_1pp_buffer)}` : ""}. Оценки — по срединным прогонам, до ${pd(d) ? fmt.rub(10 ** -pd(d)) : "рубля"}.`)));
	}
	out.push(el("section", { class: "card tile" },
		tileLabel("Точка при значениях книги"),
		sp("tile-value", priceNum(d, printedPoint(d, lam)), sp("unit", "₽")),
		el("p", { class: "tile-note", id: "fv-lede" }, `Все суждения — значения книги: точно ${rub2(pointAt(d, lam))}. ${pointVsMedianText(d, lam)}`)));
	const view = obj(fv.rates_view);
	if (isNum(view.rub)) {
		out.push(el("section", { class: "card tile" },
			tileLabel("Вклад взгляда на ставки"),
			sp("tile-value", fmt.signed(view.rub, pd(d)), sp("unit", "₽")),
			pr("tile-note", `${upperFirst(layerTitle(d, "macro_neutral"))} — ${rub2(view.low)}, ${layerTitle(d, "analytical")} — ${rub2(view.high)}. Это ось выбора слоя, а не интервал неопределённости.`)));
	}
	return out;
}

function heroWithoutBand(d) {
	const fv = d.fair_value;
	const market = obj(obj(d.market).prices)[ticker(d)];
	const price = obj(market).price;
	return bx("hero",
		el("div", { class: "hero-copy", id: "fv-hero" },
			sp("eyebrow", `Справедливая стоимость акции · ${tickerList(d)} · ${fmt.date(obj(d.meta).valuation_date)}`),
			el("div", { class: "hero-figure", id: "fv-headline" }, sp("hero-approx", "≈"),
				el("span", { class: "hero-value", id: "kpi-central" }, priceNum(d, fv.printed_central)), sp("hero-unit", "₽")),
			pr("hero-caption", "точка при значениях книги", sp("muted", ` · точно ${rub2(fv.central)}`)),
			bx("verdict", bx("verdict-top", sp("verdict-num", rubM(price)),
				sp("verdict-title", `рыночная цена${tk(d, ticker(d))}`)),
			sp("verdict-note", "В выпуске нет прогонов по суждениям: медианы и полосы нет, крупно печатается точка."))),
		card({ title: "Точка на оси ставок", extra: "hero-chart" }, kpis(
			kpi(rub2(fv.low), layerTitle(d, "macro_neutral")), kpi(rub2(fv.central), "точка"), kpi(rub2(fv.high), layerTitle(d, "analytical")))));
}

// Запас якоря — до требования с глиссадой (`req20_glide_next`: с ним сравнивает правило роста), рядом — до требования года.
function reqWords(d) {
	const C = obj(d.capital), a = obj(C.anchor);
	const policy = C.policy_threshold > 0 && Math.abs(a.req20_now - C.policy_threshold) < 1e-9;
	const day = parseDay(obj(d.meta).valuation_date);
	return { name: policy ? "порог дивидендной политики — требование года" : "требование года: минимум с надбавками + запас",
		to: policy ? "порога дивидендной политики" : "требования (минимум с надбавками + запас)",
		glide: isNum(a.n20_headroom_glide) ? `требования с глиссадой к концу ${periodLabel(a.req20_glide_period)}` : "",
		floor: list(obj(C.mix).floor20)[day ? list(C.years).indexOf(day.getFullYear()) : -1] };
}

function recordIn(d, next) {
	const n = daysBetween(obj(d.meta).valuation_date, next.record_date);
	return isNum(n) && n >= 0 ? `, через ${fmt.days(n)}` : "";
}
function recordWords(d, next) { return next.record_date ? `дата реестра${recordIn(d, next)}` : "ожидаемая дата реестра"; }

function passportRow(d) {
	const req = reqWords(d);
	const mk = obj(obj(d.market).multiples);
	const ltm = obj(obj(d.history).ltm);
	const iss = obj(ltm.roe_issuer);
	const anchor = obj(obj(d.capital).anchor);
	const n11 = obj(anchor.n11_bank).value;
	const next = obj(obj(d.dividends).next_expected);
	const main = ticker(d);
	const mark = anchor.estimated ? ", оценка" : "";
	const status = next.status === "model" ? modelDps(d) : divWord(next.status);
	const items = [
		[fmt.x(mk.pb, 2), "P/B к капиталу на дату оценки", { title: "P/B", rows: [["на дату оценки", fmt.x(mk.pb, 3)], ["к последнему отчёту", fmt.x(mk.pb_reported, 3)]] }],
		[`${fmt.x(mk.pe_ltm, 1)} / ${fmt.x(mk.pe_fwd, 1)}`, "P/E за 12 мес. / вперёд", null],
		[pct1(ltm.roe), `ROE за 12 мес. (${basisName(ltm.basis)})`, null],
		isNum(iss.value) ? [pct1(iss.value), "ROE эмитента за 12 мес.", null] : null,
		[pct1(obj(mk.dividend_yield_fwd)[main]), next.yield_period ? "дивдоходность: четыре ближайших квартала, без объявления — по политике" : `дивдоходность вперёд${next.status === "model" && annualModel(d) ? " (ожидание модели)" : ""}${tk(d, main, ", ")}`,
			{ title: "Дивдоходность вперёд", rows: tickers(d).map((t) => [t, pct2(obj(mk.dividend_yield_fwd)[t])]) }],
		[fmt.pp(req.glide ? anchor.n20_headroom_glide : anchor.n20_headroom, 1), `запас ${capTitle(d, "n20")} до ${req.glide ? `требования с глиссадой (${periodShort(anchor.req20_glide_period)})` : req.to}${mark}`
			+ (req.glide ? `; до требования года — ${fmt.pp(anchor.n20_headroom, 1)}` : ""),
			{ title: capTitle(d, "n20"), rows: [["после дивиденда", pct2(anchor.n20_post_dividend)], ...(req.glide ? [["требование с глиссадой", pct2(anchor.req20_glide_next)]] : []),
				[req.name, pct2(anchor.req20_now)], ["регуляторный пол года", pct2(req.floor)]], note: "запас — до требования, не до пола" }],
		isNum(n11) && isNum(anchor.req11_now) ? [isNum(anchor.n11_headroom) ? fmt.pp(anchor.n11_headroom, 1) : `${num1(n11 * 100)} / ${pct1(anchor.req11_now)}`,
			isNum(anchor.n11_headroom) ? `запас ${capTitle(d, "n11")} до его требования${mark}` : `${capTitle(d, "n11")} против требования${mark}`,
			{ title: capTitle(d, "n11"), rows: [["на отчётную дату", pct2(n11)], ["требование года", pct2(anchor.req11_now)]] }] : null,
		[rub2(next.dps), `DPS ${divLabel(next)} (${status}); реестр ${nextRecordText(next)}${recordIn(d, next)}`,
			{ title: `Дивиденд ${divLabel(next)}`, rows: [["по политике", rub2(next.dps_policy)], ["в среднем по клеткам", rub2(next.dps_mean)], ["риск отмены", pct0(next.p_cancel)]] }],
	].filter(Boolean);
	const labels = [basisLabel(d, "profit") && `прибыль в P/E и ROE — ${basisLabel(d, "profit")}`, basisLabel(d, "roe") && `ROE — ${basisLabel(d, "roe")}`,
		iss.label && `ROE эмитента — ${ruText(iss.label)}`, basisLabel(d, "divisor") && `на акцию — ${basisLabel(d, "divisor")}`].filter(Boolean);
	return el("div", { class: "card passport", id: "passport" }, items.map(([v, t, tip]) => el("div", { class: "pp", tip: tip || null },
		bx("pp-value", v), bx("pp-label", t))),
	labels.length ? pr("pp-foot", sentence(upperFirst(labels.join("; ")))) : null);
}

// Суждение книги о марже. Узел уровня (`level`): ключ цели и есть суждение — стационарная маржа мира уровня. Без него рядом
// с ключом цели — стационарная маржа мира суждения (`nim_stationary`, `stationary_*`) либо маржа модальной клетки (`printed_*`).
const NIM_KEY = "nii.nim_lt_target_mgmt";
const trans = (d) => obj(obj(d.nii).transmission), nimLevel = (d) => obj(trans(d).level);
const nimNode = (d) => (nimLevel(d).world ? nimLevel(d) : obj(trans(d).nim_stationary));
const nimWords = (d) => `стационарная маржа мира «${worldName(d, nimNode(d).world)}»`, nimTol = (x) => `цель ${pct2(x.target)} ± ${num2(x.tolerance * 100)}${NBSP}п.п.`;
// Ось ключа цели; её диапазон подписан диапазоном ключа, пока ключ — не само суждение.
const nimAxis = (j) => j.kind !== "bundle" && list(j.paths).includes(NIM_KEY);
const isNimKey = (j) => nimAxis(j) && !nimLevel(DATA).world;
// [слова, число на книге, число при нужном рынку значении]; у ключа-суждения последнее — само решение строки.
function nimJudged(d, r) {
	return isNum(r.stationary_book) ? [`${nimWords(d)} —`, r.stationary_book, nimLevel(d).world ? null : r.stationary_solved] : ["модальная клетка печатает", r.printed_book, r.printed_solved];
}
function nimPrinted(d, r) {
	const [w, a, b] = nimJudged(d, r);
	return !isNum(a) ? null : hint(nimLevel(d).world ? `суждение книги — ${nimWords(d)} на составе баланса якоря`
		: `ключ цели; ${w} ${pct2(a)}${isNum(b) ? `, при нужном рынку значении — ${pct2(b)}` : ""}`);
}
// Уровни смеси при нужном рынку ключе цели (`levels_solved`).
function levelsSolved(r) {
	const v = obj(obj(r.levels_solved).point);
	return isNum(v.nim) ? hint(`смесь заголовка при нём печатает ЧПМ ${pct2(v.nim)}, CoR ${pct2(v.cor)}, ${ci()} ${pct1(v.cir)}`) : null;
}

// На чём стоит заголовок: суждение о марже, уровни клеток и слоёв (`paths.levels`), под таблицей — мерка: окно фактов
// (`levels.window`); путь прибыли смеси рядом с модальной клеткой (`paths.modal_cell`); `brief` — без графика.
function levelsCard(d, brief) {
	const P = obj(d.paths), L = obj(P.levels), R = obj(L.rows), keys = list(L.order).filter((k) => R[k]);
	if (!keys.length) return null;
	const s = nimNode(d), m = obj(P.modal_cell), A = list(P.annual), b = obj(obj(d.market).brokers), t = trans(d);
	const mix = lowerFirst(ruText(obj(R.point).title || "смесь заголовка"));
	const at = (ys, vs) => list(ys).map((y, i) => [y, list(vs)[i]]);
	const W = obj(L.window), ls = obj(W.loans_share), low = (k) => Math.min(...keys.map((q) => R[q][k]));
	const span = (name, k, dg) => { const x = obj(W[k]); return isNum(x.min) && isNum(x.max) ? [`${name} `, el("span", { style: "white-space:nowrap" }, `${fmt.num(x.min * 100, dg)}…${fmt.pct(x.max, dg)}`),
		`${isNum(x.mean) ? ` (среднее ${fmt.pct(x.mean, dg)})` : ""}; `] : null; };
	const lines = [{ name: mix, key: "key-line key-model", color: MODEL, width: 2.2, ...DOT, points: A.map((a) => [a.year, a.ni_sh]) },
		{ name: "модальная клетка", key: "key-line key-third2", color: THIRD, dashed: true, ...DOT, points: at(m.years, m.ni_sh) }].filter((x) => x.points.some((p) => isNum(p[1])));
	return card({ title: `На чём стоит заголовок: ${lt("уровни", "долгосрочные")}`, link: ["capital", "Путь смеси по годам"],
		sub: (isNum(s.value) ? `Суждение книги о марже — стационарная маржа при ставках мира «${worldName(d, s.world)}» на составе баланса якоря, упр.: ${pct2(s.value)}`
			+ (s.reference_world ? `; уровень мира-опоры «${worldName(d, s.reference_world)}» выведен из неё — ${pct2(s.reference_value)}. `
				: ` (${nimTol(s)}); ключ цели — уровень мира-опоры — ${pct2(t.nim_lt_target_mgmt)}. `) : "")
			+ `Уровни клеток и слоёв — результат, а не суждение: состав баланса у каждой клетки свой, кредит вместо ликвидных активов поднимает маржу. Оценка стоит на строке «${mix}»: клетки под вероятностями точки.` },
	el("div", { class: brief || !lines.length ? null : "split wide-left" },
		dx(dataTable([
			Tc("Клетки и слои", (k) => ruText(R[k].title), "name"),
			Nc("ЧПМ", (k) => pct2(R[k].nim)), Nc("CoR", (k) => pct2(R[k].cor)), Nc(ci(), (k) => pct1(R[k].cir)), Nc("Кредиты", (k) => pct1(R[k].loans_share)),
		], keys, { cls: "compact dense", rowClass: (k) => (k === "point" ? "is-pick" : null), caption: `средние за ${L.from_year}–${L.to_year} годы, упр. базис; кредиты — доля в процентных активах` }),
		// Фраза о марже — по числам выпуска: только пока ЧПМ каждой строки выше наибольшего квартала окна.
		L.window ? smallNote("Окно фактов, от наименьшего квартала до наибольшего: ", span("ЧПМ", "nim", 2), span("CoR", "cor", 2), span(ci(), "cir", 1),
			`кредиты — ${isNum(ls.window) ? `${pct1(ls.window)} в среднем за окно, ` : ""}${pct1(ls.anchor)} на дату якоря.`
			+ (isNum(obj(W.nim).max) && low("nim") > W.nim.max ? ` ЧПМ всех строк выше наибольшего квартала окна${isNum(ls.window) && low("loans_share") > Math.max(ls.window, ls.anchor)
				? ": состав баланса у них другой — кредитов в процентных активах больше, чем в окне и на якоре" : ""}.` : "")) : null,
		R.modal_cell ? smallNote(`${ruText(R.modal_cell.title)} — ${cellName(d, L.cell)}${isNum(m.p_point)
			? `: вес ${pct1(m.p_analytical)} в слое «${layerTitle(d, "analytical")}» и ${pct1(m.p_point)} в смеси; цена клетки ${fmt.rub(m.price)}` : ""}.`) : null),
		brief || !lines.length ? null : dx(tileLabel(`${shProfit(d)} по годам, млрд ₽`), legend(lines.map((x) => [x.key, x.name])),
			linesChart(lines, { xType: "band", categories: A.map((a) => a.year), height: 190, tipFmt: bn0, xFmt: yy, label: `${shProfit(d)}: смесь заголовка и модальная клетка` }))),
	isNum(b.median) && !brief ? foot(`Цели брокеров на ${fmt.date(b.as_of)}: ${fmt.num(b.min)}–${fmt.rub(b.max)}, медиана ${fmt.rub(b.median)} (${fmt.num(b.n)} ${plural(b.n || 0, ["цель", "цели", "целей"])}).`) : null,
	gateNote(d, "window_backtest"), gateNote(d, "nim_stationary"));
}

function pricedHeadline(rows) {
	const share = (r) => {
		const end = r.solved >= r.book ? r.range[1] : r.range[0];
		return end === r.book ? 0 : (r.solved - r.book) / (end - r.book);
	};
	const inside = rows.filter(inRange).map((r) => ({ r, s: share(r) })).sort((a, b) => a.s - b.s);
	if (!rows.length) return "Что заложено в рыночную цену";
	if (!inside.length) return "Ни одно суждение в пределах книги не объясняет рыночную цену";
	return `Рыночную цену объясняет суждение внутри диапазона книги: ${lowerFirst(shortAxis(inside[0].r.name))} — ${pct0(inside[0].s)} пути к краю`;
}

function inRange(r) { return r.status === "solved" && isNum(r.solved) && !!r.in_range; }
function reverseBadge(r) {
	return r.status === "not_computed" ? badge("не считалось", "out") : !isNum(r.solved) || r.status !== "solved" ? badge("недостижимо", "out")
		: r.in_range ? badge("в диапазоне книги", "good") : badge("вне диапазона", "out");
}
function reverseNeed(r) { return r.status === "not_computed" ? "не считалось" : isNum(r.solved) && r.status === "solved" ? reverseValue(r, r.solved) : "недостижимо"; }
// Решение строки, которую список книги (`refine_rows`) не называет, на полной полосе не уточнялось.
function bySample(d, r) {
	const named = obj(d.reverse_dcf).refine_rows;
	return Array.isArray(named) && r.status === "solved" && !named.includes(r.key) ? "оценка по подвыборке" : "";
}

function pricedTeaser(d) {
	const block = obj(d.reverse_dcf);
	const rows = list(block.rows);
	if (!rows.length) return card({ title: "Что заложено в цену", span: 6, link: ["market", "Подробно"] }, missing("обратный расчёт"));
	const inside = rows.filter(inRange);
	const outside = rows.filter((r) => !inRange(r));
	const roe = list(block.bank_rows).find((r) => r.key === "implied_roe_through_cycle");
	const yrs = list(block.bank_rows).find((r) => r.key === "excess_return_years");
	const w = diagWords(block.number);
	return card({ title: "Что заложено в цену", span: 6, link: ["market", "Все оси"],
		sub: `Значение одного суждения, при котором ${w.subj} равна цене${tk(d, ticker(d))} (${rub2(block.target)}); прочие разыгрываются как в полосе.` },
	inside.length ? bx("rows", inside.map((r) => bx("rrow",
		bx("rrow-name", r.name, nimPrinted(d, r)), rangeRowChart(r),
		bx("rrow-need", sp("v", reverseValue(r, r.solved)),
			sp("b", [`книга ${reverseValue(r, r.book, true)}`, "в диапазоне книги", bySample(d, r)].filter(Boolean).join(" · "))))))
		: empty("Ни одно суждение в пределах своего диапазона не даёт рыночную цену."),
	roe || yrs ? mt(12, "p", "note-box",
		roe ? `Рынку нужен ${lowerFirst(ruText(roe.title || "вменённый ROE"))} ${pct1(roe.implied)} против ${pct1(roe.book)} книги. ` : "", yrs ? yearsInPrice(yrs) : "") : null,
	outside.length ? foot("Вне диапазона книги: ", sentence(
		outside.map((r) => { const [w, , at] = nimJudged(d, r); return `${lowerFirst(shortAxis(r.name))} ${isNum(r.solved) && r.status === "solved" ? reverseNeed(r) + (isNum(at) ? ` (ключ цели; ${w} ${pct2(at)})` : "") : `— ${reverseNeed(r)}`}`; }).join("; "))) : null);
}

// Срок избыточной доходности в цене (строка обратного расчёта панели).
function yearsInPrice(r) {
	return r.status === "unreachable" || !isNum(r.implied) ? "В цене — больше избыточной доходности, чем даёт модель вместе с терминалом."
		: `В цене — ${yearsText(r.implied)} избыточной доходности${r.implied ? "" : ": капитализация не выше капитала"}.`;
}

// Вклад ниже 1 % — «< 1 %» без порядка.
const SHARE_FLOOR = 0.01;
const SHARE_SMALL = `<${NBSP}1${THIN}%`;
function shareText(share) { return !isNum(share) ? "—" : share < SHARE_FLOOR ? SHARE_SMALL : fmt.pct(share, share < 0.1 ? 1 : 0); }
function offBand(d) { return list(obj(d.judgements).rows).filter((j) => j.in_band === false); }
// Мера осей вне полосы — как у правила М§10: сдвиг заголовка и порог гейта.
function offBandNote(d) {
	const s = obj(obj(d.judgements).off_band_shift);
	return isNum(s.rub) ? `их фиксация сдвигает заголовок на ${fmt.signedRub(s.rub, 1)} при пороге ${rub1(s.limit)}` : "не разыгрываются";
}

function bandDrivers(d) {
	const head = obj(d.fair_value.headline);
	const rows = list(head.contributions);
	if (!rows.length) return none("Что определяет полосу", "вклады суждений в полосу", 6);
	const judg = Object.fromEntries(list(obj(d.judgements).rows).map((j) => [j.id, j]));
	const big = rows.filter((r) => isNum(r.share) && r.share >= SHARE_FLOOR).sort((a, b) => b.share - a.share);
	const small = rows.filter((r) => !big.includes(r)).map((r) => lowerFirst(shortAxis(r.name))).sort((a, b) => a.localeCompare(b, "ru"));
	const off = offBand(d).map((j) => lowerFirst(shortAxis(j.name)));
	const max = Math.max(...big.map((r) => r.share), SHARE_FLOOR);
	const bar = (r) => {
		const j = judg[r.judgement_key];
		return hbar(r.name, r.share, max, { value: shareText(r.share), tip: { title: r.name, rows: [["доля полосы", shareText(r.share)], ["ранговая корреляция", num2(r.rank_corr)],
			...(j ? [[isNimKey(j) ? "диапазон ключа цели" : "диапазон книги", rangeText(d, j)]] : [])], note: r.rank_corr < 0 ? "больше значение — ниже цена" : "больше значение — выше цена" } });
	};
	const rest = big.slice(6);
	return card({ title: "Что определяет полосу", span: 6, link: ["book", "Все суждения"],
		sub: `Вклад суждения — доля квадрата ранговой корреляции с центром по ${fmt.num(head.draws)} прогонам; доли меньше 1 % не различимы и не упорядочены.` },
	bx("hbars", big.slice(0, 6).map(bar)),
	rest.length || small.length || off.length ? bx("card-foot stack",
		rest.length ? detailsBlock(`Ещё ${rest.length} ${plural(rest.length, ["суждение", "суждения", "суждений"])}`, bx("hbars", rest.map(bar))) : null,
		small.length ? pr("muted small", sentence(`Вклад ${SHARE_SMALL}: ${small.join(", ")}`)) : null,
		off.length ? pr("muted small", sentence(`Вне полосы (${offBandNote(d)}): ${off.join(", ")}`)) : null) : null);
}

function countdown(days, what, approx) {
	return bx("countdown", sp("big", (approx ? "≈" + NBSP : "") + fmt.num(days)),
		sp("ink-2", `${plural(days, ["день", "дня", "дней"])} — ${what}`));
}

function reportPublished(d) {
	const c = obj(obj(d.next_report).closing);
	return pr("note-box", strong(`Отчёт вышел ${c.confirmed ? "" : "≈" + NBSP}${fmt.date(c.date)}; факт ещё не внесён в модель. `),
		c.title ? sentence(`По календарю — ${lowerFirst(c.title)}`) : "", " До новой версии книги ожидание модели и «что даст отчёт» считаются без этого факта.");
}

// Месячного релиза у эмитента нет (у месяца нет даты релиза): месяц входит формой 0409102 банка (дата — оценка), события
// календаря о месяце — окна выкладки форм ЦБ, а не релиз.
function formOnly(d) { const r = obj(obj(d.calendar).next_ras); return r.enters_via === "form102" && !r.release_date && !list(obj(d.calendar).events).some((e) => e.kind === "ops_release"); }
// Месячный вход — событие календаря; слова о РСБУ — только когда такой релиз есть.
function monthly(d) { return formOnly(d) ? null : list(obj(d.calendar).events).find((e) => e.kind === "ras" || e.kind === "ops_release"); }
function rasForm(d) { if (formOnly(d)) return false; const e = monthly(d); return e ? e.kind === "ras" : list(obj(obj(d.nowcast).months).rows).length > 0 || !obj(d.nowcast).ops; }
// Два ритма отчётности — словами для подписей.
function monthWords(d) { return formOnly(d) ? "формы ЦБ банка за месяц" : rasForm(d) ? "месячная РСБУ банка" : "месячный релиз и формы ЦБ"; }

// Дата формы ЦБ — оценка: печатается окном.
function earlierReport(d) {
	const ras = obj(obj(d.calendar).next_ras);
	if (!ras.month) return null;
	const form = ras.enters_via === "form102";
	const win = `≈${NBSP}${fmt.date(ras.date)}${parseDay(ras.form102_latest_est) ? `–${fmt.date(ras.form102_latest_est)}` : ""}`;
	if (formOnly(d)) return foot(`Форма 0409102 банка за ${periodLabel(ras.month)} — ${win} (дата — оценка): процентные доходы банка — оценка ЧПМ квартала; к цене нау-каст не подключён.`);
	if (!rasForm(d)) return foot(`Форма 0409102 за ${periodLabel(ras.month)} — ${win} (дата — оценка): прибыль банка за месяц для сверки с релизом; к цене нау-каст не подключён.`);
	return foot(`Раньше МСФО: ${form ? win : fmt.date(ras.date)} — РСБУ банка за ${periodLabel(ras.month)} `,
		`(${form ? "по форме 0409102, дата — оценка" : "релиз, принятый по двум источникам"}): вход нау-каста; к цене нау-каст не подключён.`);
}

function nextRasLine(d) {
	const ras = obj(obj(d.calendar).next_ras), e = monthly(d);
	if (e && e.kind !== "ras") return isNum(e.days) ? countdown(e.days, `${lowerFirst(ruText(e.title))} (${est(e) ? "≈" + NBSP : ""}${fmt.date(e.date)})`, est(e)) : null;
	if (formOnly(d)) return isNum(ras.days) ? countdown(ras.days, `форма 0409102 банка за ${periodLabel(ras.month)}`, true) : null;
	return isNum(ras.days) ? countdown(ras.days, `РСБУ за ${periodLabel(ras.month)} попадёт в нау-каст`) : null;
}

function nextFactLine(d) {
	const nf = obj(obj(d.calendar).next_fact);
	if (obj(obj(d.next_report).closing).published) return reportPublished(d);
	return isNum(nf.days) ? countdown(nf.days, `МСФО за ${periodLabel(nf.covers || obj(d.next_report).period)} (${nf.confirmed ? "" : "≈" + NBSP}${fmt.date(nf.date)}`
		+ `${est(nf) && nf.earliest && nf.latest ? `, окно ${fmt.dateShort(nf.earliest)}–${fmt.dateShort(nf.latest)}` : ""})`, !nf.confirmed) : null;
}

function dpsInterval(y, digits) {
	const [lo, hi] = list(y.dps_interval);
	return isNum(lo) && isNum(hi) ? `интервал ${fmt.num(lo, digits)}–${fmt.num(hi, digits)}${THIN}₽` : "интервал не оценён";
}

// DPS года — по политике; ожидание по клеткам — строкой, когда оно ниже: доли среза капиталом и отмены — раздельно.
const yearModel = (d, y) => obj(list(obj(d.dividends).model).find((r) => r.year === y.year));
function dpsExpected(d, y) {
	const m = yearModel(d, y);
	return isNum(m.dps) && m.dps < m.dps_policy ? hint(`ожидание по клеткам — ${rub2(m.dps)}: урезано капиталом в ${pct0(m.p_cut)} массы, без выплаты — ${pct0(m.p_zero)}`) : null;
}
// Годовой плательщик при квартальном календаре модели: главная цифра DPS года — ожидание модели, DPS по политике — второй строкой с условием.
function dpsYearKpi(d, y, words) {
	const m = yearModel(d, y);
	if (!annualModel(d) || !isNum(m.dps)) return null;
	return kpi(rub2(m.dps), [`DPS за ${y.year} — ожидание модели${words}, P10–P90 ${num2(m.dps_p10)}–${num2(m.dps_p90)}${THIN}₽`,
		hint(`по политике ${rub2(m.dps_policy)} — при запасе капитала; капитал урезал выплату в ${pct0(m.p_cut)} массы, без выплаты — ${pct0(m.p_zero)}`)]);
}

function reportTeaser(d) {
	const nr = obj(d.next_report);
	const year = obj(obj(d.nowcast).year);
	const n = obj(obj(nr.neutral).cor);
	return card({ title: `Ближайший отчёт: ${periodLabel(nr.period)}`, span: 6, link: ["report", "Подробно"], sub: `два ритма: ${monthWords(d)} и квартальная МСФО группы` },
		nextRasLine(d), nextFactLine(d),
		isNum(year.ni_year) ? kpis(14,
			kpi(bn0(year.ni_year), `прибыль ${year.year}: факт + ожидание модели${rasForm(d) ? " с поправкой нау-каста" : ""}`),
			dpsYearKpi(d, year, "") || kpi(rub2(year.dps), [`DPS за ${year.year}${rasForm(d) ? " с нау-кастом" : " по политике"}, ${dpsInterval(year, 1)}`, dpsExpected(d, year)])) : null,
		list(nr.cor_table).length ? spaced(14,
			tileLabel(`Если CoR ${periodLabel(nr.period)} (упр.) выйдет …, ${diagWords(nr.target).subj} станет:`),
			impactChart(d, "cor", true)) : null,
		isNum(n.value) ? foot(neutralSentence(d, "cor")) : null);
}

function neutralSentence(d, kind) {
	const nr = obj(d.next_report);
	const n = obj(obj(nr.neutral)[kind]);
	const slope = obj(nr.slope)[`rub_per_01pp_${kind}`];
	const re = obj(obj(nr.reaction)[kind]);
	const ni = obj(nr.expectation).ni;
	const what = kindName(kind);
	if (!isNum(n.value)) return obj(nr.neutral).error ? sentence(`Нейтральное значение ${what} не найдено: ${ruText(nr.neutral.error)}`) : "";
	const w = diagWords(nr.target);
	const dir = kind === "cor" ? ["снизится", "вырастет"] : ["вырастет", "снизится"];
	return sentence(`Нейтральная ${what} ${periodLabel(nr.period)} (упр.) — ${pct2(n.value)}: при таком факте ${w.subj} не изменится; выше — ${dir[0]}, ниже — ${dir[1]}`
		+ (isNum(slope) ? `; у ${obj(nr.slope)[`at_${kind}`] === "expectation" ? "ожидания" : "нейтрального значения"} — около ${fmt.rub(Math.abs(slope), Math.abs(slope) < 10 ? 1 : 0)} на 0,1${NBSP}п.п.` : "")
		+ (isNum(re.d_median_min) && isNum(re.d_median_max) ? `, дальше реакция упирается в предел сдвига режимов: от ${fmt.signed(re.d_median_min, 1)} до ${fmt.signedRub(re.d_median_max, 1)}` : "")
		+ (isNum(n.ni_equivalent) ? `; при ней прибыль квартала ≈${NBSP}${fmt.bn(n.ni_equivalent)}${isNum(ni) ? ` (ожидание модели — ${num1(ni)})` : ""}` : ""));
}

/* ── дивиденды (кратко) ── */

const DIV_STATUS = { declared: ["объявлен", "warn"], recommended: ["рекомендован", "model"], paid: ["выплачен", "good"], model: ["модель", null] };

const divWord = (s) => (DIV_STATUS[s] || [s])[0];
function divStatus(r) {
	const [name, kind] = DIV_STATUS[r.status] || [r.status || "—", null];
	return badge(name, kind);
}
function registerCutoff(r) { return fmt.date(r.ex_date || r.record_date); }
// Без объявления у годового плательщика — ожидание модели (П§2).
const modelDps = (d) => annualModel(d) ? "ожидание модели" : "по политике";
function nextDpsLabel(d, next) {
	return next.status === "model" ? `${annualModel(d) ? "ожидание модели" : "DPS по политике"} · риск отмены ${pct0(next.p_cancel)}`
		: { declared: "объявленный DPS", recommended: "рекомендованный DPS (до решения собрания)" }[next.status] || "DPS реестра";
}
function nextDpsMean(d, next) {
	const p = `P10–P90 ${num2(next.dps_p10)}–${num2(next.dps_p90)}${THIN}₽`;
	return annualModel(d) ? hint(`${p}; по политике ${rub2(next.dps_policy)}: капитал урезал выплату в ${pct0(obj(next.condition).p_limited)} массы`)
		: isNum(next.dps_mean) ? hint(`в среднем по клеткам ${rub2(next.dps_mean)}, ${p}`) : null;
}
// `declared` — при двух источниках (М§15).
function registerSources(r) {
	const s = list(r.sources);
	return sx(s.length ? s.map(ruText).join(" + ") : "—",
		sp("cell-badge", s.length > 2 ? badge(`${fmt.num(s.length)} ${plural(s.length, ["источник", "источника", "источников"])}`, "good")
			: s.length === 2 ? badge("два источника", "good") : badge("один источник", r.status === "paid" ? "out" : "warn")));
}
function nextRecordText(next) {
	return next.record_date ? fmt.date(next.record_date) : parseDay(next.record_date_est) ? `≈${NBSP}${fmt.date(next.record_date_est)}` : ruText(next.record_date_note || "—");
}

const DIV_KINDS = ["agm", "dividend_decision", "record", "pay"];
function yieldWords(d, next, t) { return `доходность ${next.yield_period ? "квартальной выплаты " : ""}${toPrice(d, t)}`; }
function divCell(r) { return sx(upperFirst(divLabel(r)), sp("cell-badge", divStatus(r))); }

function dividendsTeaser(d) {
	const dv = obj(d.dividends);
	const next = obj(dv.next_expected);
	const reg = list(dv.register).slice().sort((a, b) => String(b.ex_date || b.record_date).localeCompare(String(a.ex_date || a.record_date))).slice(0, 3);
	const cal = list(obj(d.calendar).events).filter((e) => DIV_KINDS.includes(e.kind)).slice(0, 3);
	if (!isNum(next.dps) && !reg.length) return none("Дивиденды", "дивиденды", 6);
	return card({ title: `Дивиденд ${divLabel(next)}`, span: 6, link: ["capital", "Капитал и дивиденды"],
		sub: next.status === "model" ? `объявления ещё нет: ${annualModel(d) ? "ожидание модели по клеткам" : "DPS по политике на прибыли модели"}` : `статус — ${divWord(next.status)}` },
	kpis(
		kpi(rub2(next.dps), [nextDpsLabel(d, next), next.status === "model" ? nextDpsMean(d, next) : null]),
		...tickers(d).map((t) => kpi(pct1(obj(next.yield)[t]), yieldWords(d, next, t))),
		kpi(nextRecordText(next), recordWords(d, next))),
	reg.length ? spaced(14, dataTable([
		Tc("Дивиденд", divCell, "name"),
		Nc("На акцию", rubOf("dps")),
		Nc("Реестр", registerCutoff),
	], reg, COMPACT)) : null,
	cal.length ? foot(sentence("В календаре: " + cal.map((e) => `${est(e) ? "≈" + NBSP : ""}${fmt.date(e.date)} — ${lowerFirst(ruText(e.title))}`).join("; "))) : null);
}

/* ── события, изменения, метод ── */

function eventsCard(d, limit, span = 6) {
	const cal = obj(d.calendar);
	const nf = obj(cal.next_fact);
	const events = list(cal.events).slice(0, limit || 99);
	if (!events.length) return card({ title: "События", span }, empty("Ближайших событий в выпуске нет."));
	const when = (e) => (est(e) ? "≈" + NBSP : "") + fmt.dateShort(e.date);
	return card({ title: "События", span, sub: `отсчёт — от даты оценки ${fmt.date(cal.today || d.meta.valuation_date)}` },
		el("ol", { class: "timeline" }, events.map((e) => el("li", { class: cls(e.id === nf.id && "is-fact", DIV_KINDS.includes(e.kind) && "is-div") },
			sp("tl-date", when(e), sp("muted", `${e.estimated ? "≈" + NBSP : ""}через ${fmt.days(e.days)}`)),
			sp("tl-rail", el("i")),
			sp("tl-body", strong(ruText(e.title)), e.in_book === false ? sx(badge("в книге нет", "warn")) : null,
				e.precision === "window" && e.earliest && e.latest ? sp("muted", `окно ${fmt.dateShort(e.earliest)}–${fmt.dateShort(e.latest)}`) : null,
				e.note ? sp("muted", ruText(e.note)) : null)))));
}

function changesCard(d, span = 6) {
	const ch = obj(d.changes).vs_previous;
	if (!ch) return card({ title: "Что изменилось с прошлого выпуска", span }, empty("Прошлого выпуска нет: это первый выпуск."));
	const rows = list(ch.rows);
	const moves = Object.entries(obj(ch.market_price));
	return card({ title: "Что изменилось с прошлого выпуска", span,
		sub: ch.previous_published_at ? `против выпуска ${fmt.stamp(ch.previous_published_at)}; ₽ на акцию — точка и медиана` : "" },
	rows.length ? el("ul", { class: "list" },
		rows.map((r) => lx(sp("t", r.title, r.note ? sp("muted", ruText(r.note)) : null),
			sp("v", `${fmt.signedRub(r.point_rub, 1)} · ${fmt.signedRub(r.median_rub, 1)}`))),
		el("li", { class: "total" }, sp("t", strong("Итого: точка · медиана")),
			sp("v", `${fmt.signedRub(ch.total_point_rub, 1)} · ${fmt.signedRub(ch.total_median_rub, 1)}`))) : empty("Разложения нет."),
	foot(moves.length ? `Цена: ${moves.map(([t, m]) => `${t} ${num2(obj(m).from)} → ${rub2(obj(m).to)}`).join(", ")} — меняет сравнения, а не стоимость. ` : "",
		ch.note ? phrase(ch.note) : ""));
}

function methodNote(d) {
	const meta = obj(d.meta);
	const bridge = obj(d.fair_value.bridge);
	return card({ title: "Как читать эту оценку" },
		bx("prose",
			pa(strong("Крупное число — медиана, а не точка. "),
				"Каждый прогон сдвигает суждения книги в их диапазонах одновременно (треугольно, мода — значение книги) и пересчитывает всю сетку, слои и цену. Полоса 80 % честнее одной цифры."),
			pa(strong("Капитал считается напрямую. "),
				`Цена — капитал на дату оценки плюс PV доходности сверх стоимости капитала (остаточный доход, проверенный дивидендной моделью), минус дисконт за управление ${pct2(meta.governance_discount)}, `
				+ `плюс объявленный дивиденд до отсечки (${fmt.bn(bridge.amount)}), на ${divisor(d)}. База — ${basisName(meta.basis)}${basisLabel(d, "profit") ? `; прибыль — ${basisLabel(d, "profit")}` : ""}.`),
			solo(d) ? null : pa("Одна справедливая стоимость на обе категории акций: главная — первой линией рынка, вторая — пунктиром.")),
		foot(el("a", { href: "#model" }, "Как устроен расчёт →")));
}

/* ── экран «Что в цене» ── */

function screenMarket(d) {
	const block = obj(d.reverse_dcf);
	const w = diagWords(block.number);
	return bx("screen",
		screenHead("Что в цене", pricedHeadline(list(block.rows)),
			`Рынок платит ${rubM(d.market.price)} за акцию${tk(d, ticker(d))} (${fmt.date(d.meta.valuation_date)}). Ниже — какое значение одного суждения делает ${w.acc} равной рынку, `
			+ "как расходятся справедливый и рыночный P/B, что говорят брокеры и аналоги."),
		sec(reverseDcfCard(d)), sec(bankLineCard(d)), sec(limitsCard(d)), sec(priceCard(d)), sec(brokersCard(d), peersCard(d)), sec(spreadCard(d)));
}

function reverseDcfCard(d) {
	const block = obj(d.reverse_dcf);
	const rows = list(block.rows);
	if (!rows.length) return none("Обратный расчёт по осям книги", "обратный расчёт");
	const w = diagWords(block.number);
	// Нет решения — об этом говорит бейдж, а не число.
	const need = (r) => (r.status === "solved" && isNum(r.solved) ? reverseValue(r, r.solved) : null);
	const table = () => dataTable([
		Tc("Ось", (r) => [r.name, nimPrinted(d, r)], "name"),
		Nc("Нужно рынку", (r) => need(r) || "—"),
		Nc("В книге", (r) => reverseValue(r, r.book, true)),
		Nc("Диапазон книги", reverseRange),
		Nc("Невязка, ₽", numOf("gap", 2)),
		Tc("", (r) => [reverseBadge(r), bySample(d, r) ? hint(bySample(d, r)) : null]),
	], rows);
	const box = bx("rows", rows.map((r) => bx("rrow",
		bx("rrow-name", r.name, hint(`книга ${reverseValue(r, r.book, true)}${reverseRange(r) === "—" ? " · оси с диапазоном в книге нет" : ` · диапазон ${reverseRange(r)}`}`), nimPrinted(d, r), levelsSolved(r)),
		rangeRowChart(r),
		bx("rrow-need", need(r) ? sp("v", need(r)) : null, " ", reverseBadge(r), bySample(d, r) ? sp("b", bySample(d, r)) : null,
			r.status === "unreachable" && r.reason ? sp("b", ruText(r.reason)) : null,
			isNum(r.gap) && Math.abs(r.gap) >= 0.5 ? sp("b", `невязка ${rub1(r.gap)}`) : null))));
	const fig = withTable(box, table);
	return card({ title: "Обратный расчёт по осям книги", tools: fig.button,
		sub: `Значение одной оси, при котором ${w.subj} полосы равна цене${tk(d, ticker(d))} ${rub2(block.target)}; прочие суждения разыгрываются как в полосе. Строки решаются по одной: решения разных строк не перемножаются. «Недостижимо» — цена не достигается на всём отрезке поиска.` },
	legend([["key-b50", "диапазон книги"], ["key-line key-ink", "значение книги"], ["key-dot key-market", "нужно рынку"]]),
	fig.box,
	block.method ? foot(phrase(block.method)) : null);
}

function bankLineCard(d) {
	const b = obj(d.fair_value.bank_first_line);
	if (!isNum(b.market_pb)) return none("Капитал: модель против рынка", "язык банка");
	const L = obj(b.layers);
	const rows = [{ name: `${diagWords(b.target).subj} (λ книги)`, a: b.fair_pb_median, b: b.market_pb, aLabel: "справедливый P/B", bLabel: "рыночный P/B" },
		{ name: "точка при значениях книги", a: b.fair_pb_point, b: b.market_pb, aLabel: "справедливый P/B", bLabel: "рыночный P/B" },
		...["analytical", "macro_neutral"].filter((k) => L[k]).map((k) => ({ name: layerTitle(d, k), a: L[k].fair_pb, b: b.market_pb, aLabel: "P/B слоя", bLabel: "рыночный P/B" }))];
	const plot = dumbbellChart(rows, { fmt: (v) => fmt.x(v, 2), refs: [1], label: "Справедливый и рыночный P/B по слоям" });
	const fig = withTable(plot, () => dataTable([
		Tc("Слой", (r) => r.name, "name"),
		Nc("Справедливый P/B", (r) => fmt.x(r.a, 3)),
		Nc("Рыночный P/B", (r) => fmt.x(r.b, 3)),
	], rows));
	const bank = Object.fromEntries(list(obj(d.reverse_dcf).bank_rows).map((r) => [r.key, r]));
	const roe = obj(bank.implied_roe_through_cycle), coe = obj(bank.implied_cost_of_equity);
	return card({ title: "Капитал: модель против рынка", tools: fig.button,
		sub: `Капитал на дату оценки ${bn0(b.bv_v)}; рынок платит ${fmt.x(b.market_pb, 2)} капитала (капитализация ${bn0(d.market.cap)}). Вертикаль — P/B = 1.` },
	legend([["key-dot key-model", "справедливый P/B"], ["key-dot key-market", "рыночный P/B"]]),
	fig.box,
	kpis(14,
		kpi(fmt.signedBn(b.excess_median, 0), "PV доходности сверх стоимости капитала: модель (медиана)"),
		kpi(fmt.signedBn(b.excess_market, 0), "то же, вменённое рынком: капитализация − капитал"),
		isNum(roe.implied) ? kpi(`${pct1(roe.implied)} / ${pct1(roe.book)}`, `${lowerFirst(ruText(roe.title || "вменённый ROE"))}: нужен рынку / в книге`) : null,
		isNum(coe.implied) ? kpi(`${pct1(coe.implied)} / ${pct1(coe.book)}`, "стоимость капитала: вменённая рынком / в книге",
			{ tip: { title: "Вменённая стоимость капитала по мирам", rows: Object.entries(obj(coe.by_world)).map(([k, v]) => [worldName(d, k), pct2(v)]) } }) : null,
		kpi(`${pct1(b.roe_tc)} / ${pct1(b.k_tc)}`, `${roeLt()} / стоимость капитала (λ книги)`)),
	b.sensitivity_basis ? foot(sentence(`Чувствительности: ${ruText(b.sensitivity_basis)}`)) : null, basisFoot(d, "roe"));
}

function limitsCard(d) {
	const rows = Object.fromEntries(list(obj(d.reverse_dcf).bank_rows).map((r) => [r.key, r]));
	const bv = obj(rows.book_value_per_share), flat = obj(rows.value_without_excess_growth), yrs = rows.excess_return_years;
	if (!isNum(bv.implied) && !isNum(flat.implied) && !yrs) return null;
	const point = d.fair_value.central, price = d.market.price;
	const by = list(obj(yrs).by_year).filter((r) => isNum(r.pv_excess_cum));
	// Обе границы выпуск считает от точки (`delta`); у медианы полосы база другая — на этой шкале её нет.
	const mark = (r, name) => ({ v: r.implied, kind: "bench", text: `${name} ${fmt.rub(r.implied)}${isNum(r.delta) ? ` (${fmt.signedRub(r.delta)})` : ""}` });
	return card({ title: "Пределы и срок",
		sub: "Сколько цены стоит сам рост и сколько — доходность сверх стоимости капитала: «капитал без премии» — избыточной доходности нет, «без опережающего роста» — рост кончился сегодня. "
			+ "Обе границы считаны от точки при значениях книги, а не от медианы полосы; в скобках — разность с точкой." },
	stripChart([mark(bv, "капитал без премии"), mark(flat, "без опережающего роста"),
		{ v: price, kind: "market", text: `цена ${fmt.rub(price)}` }, { v: point, kind: "model", text: `точка ${fmt.rub(point)}` }],
	{ label: "Пределы оценки, цена и точка модели на одной шкале" }),
	yrs ? mt(14, "div", "split",
		dx(kpis(
			kpi(yrs.status === "unreachable" || !isNum(yrs.implied) ? "недостижимо" : yearsText(yrs.implied), "избыточной доходности в цене"),
			isNum(yrs.market_excess) ? kpi(fmt.signedBn(yrs.market_excess, 0), "капитализация минус капитал") : null),
		smallNote(yearsInPrice(yrs), " Срок — годы, за которые накопленный приведённый остаточный доход модели покрывает «капитализация минус капитал».")),
		by.length ? columnsChart(by.map((r, i) => ({ key: r.year, label: i === by.length - 1 ? "терминал" : yy(r.year), value: r.pv_excess_cum, faded: i === by.length - 1,
			tipTitle: i === by.length - 1 ? "с терминалом" : `до конца ${r.year}` })),
		{ height: 190, valueName: "накоплено", fmt: bn0, refs: [{ value: yrs.market_excess, text: "капитализация − капитал", dash: "5 4" }],
			label: "Накопленная приведённая стоимость остаточного дохода по годам" }) : null) : null);
}

const dayMs = (iso) => { const day = parseDay(iso); return day ? day.getTime() : NaN; };
// Узлы кривой — точки по сроку (LT — на отметке 25 лет); ось сроков.
const curvePoints = (nodes) => Object.entries(obj(nodes)).map(([t, v]) => [t === "LT" ? 25 : Number(t), v]).sort((a, b) => a[0] - b[0]);
const CURVE_AXIS = { xMin: 0, xMax: 26, xTicks: [1, 3, 5, 10, 25], xFmt: (t) => (t === 25 ? "LT" : `${fmt.num(t)}${NBSP}г.`), yPct: true, tipFmt: pct2 };

function priceCard(d) {
	const mk = obj(d.market);
	const hist = obj(mk.price_history);
	const main = ticker(d);
	const title = `Цена ${solo(d) ? "акции" : "акций"} за 12 месяцев`;
	const series = tickers(d).map((s) => ({ name: solo(d) ? "цена" : s, color: MARKET, width: s === main ? 1.9 : 1.5, dashed: s !== main,
		points: list(hist[s]).filter((p) => isNum(p.close)).map((p) => [dayMs(p.date), p.close]).filter((p) => isNum(p[0])) })).filter((s) => s.points.length > 1);
	if (!series.length) return card({ title }, empty("Истории цены в выпуске нет."));
	const xs = series.flatMap((s) => s.points.map((p) => p[0]));
	const first = Math.min(...xs), last = Math.max(...xs);
	const inside = (iso) => dayMs(iso) >= first && dayMs(iso) <= last;
	const median = obj(d.fair_value.headline).printed_median;
	const exd = list(mk.ex_dividend).filter((e) => isNum(e.dps) && inside(e.date));
	const splits = list(obj(obj(d.meta).shares).corporate_actions).filter((a) => a.kind === "split" && inside(a.date));
	const monthTicks = [];
	const start = new Date(first);
	for (let k = 1; k <= 13; k++) { const ms = new Date(start.getFullYear(), start.getMonth() + k, 1).getTime(); if (ms > first && ms < last) monthTicks.push(ms); }
	const monthLabel = (ms) => { const day = new Date(ms); return day.getMonth() === 0 ? String(day.getFullYear()) : MONTHS_AXIS[day.getMonth()]; };
	const plot = linesChart(series, { height: 250, xMin: first, xMax: last, xTicks: monthTicks, xFmt: monthLabel, left: 52,
		tipFmt: rub2,
		hrefs: isNum(median) ? [{ value: median, text: `медиана модели ${fmt.rub(median)}`, short: fmt.rub(median), color: MODEL, dash: "5 4" }] : [],
		vlines: [...exd.map((e) => ({ x: dayMs(e.date), text: `дивиденд ${rub2(e.dps)}`, short: rub2(e.dps),
			tip: { title: "Экс-дата дивиденда", rows: [["дата", fmt.date(e.date)], ["на акцию", rub2(e.dps)], ["решение", divLabel(e)]] } })),
		...splits.map((a) => ({ x: dayMs(a.date), text: lowerFirst(ruText(a.title)), short: isNum(a.factor) && splitText(a), color: THIRD, solid: true,
			tip: { title: ruText(a.title), rows: [["дата", fmt.date(a.date)], ["коэффициент", splitText(a)]], note: "цены до этой даты пересчитаны" } }))],
		label: title });
	const rows = list(hist[main]).slice().reverse();
	const fig = withTable(plot, () => dataTable([
		Tc("Дата", (p) => fmt.date(p.date), "name"),
		...tickers(d).map((s) => (Nc(solo(d) ? "Закрытие" : s, (p) => { const q = list(hist[s]).find((x) => x.date === p.date); return q ? rub2(q.close) : "—"; }))),
	], rows));
	const prices = obj(mk.prices);
	const lo = obj(obj(mk.price_min)[main]), hi = obj(obj(mk.price_max)[main]);
	const m = obj(mk.multiples), dv = obj(d.dividends), lp = list(dv.yield_ltm_periods);
	return card({ title, tools: fig.button, sub: `дневные закрытия основной сессии; вертикали — экс-даты дивидендов; пунктир — медиана модели${splits.length ? "; цены до дробления пересчитаны" : ""}` },
		legend([...series.map((s) => [s.dashed ? "key-line key-market2" : "key-line key-market", s.name]), isNum(median) && ["key-line key-model2", "медиана модели"], exd.length && ["key-line key-dash", "экс-дата"],
			splits.length && ["key-line key-third", "дробление"]]),
		fig.box,
		kpis(12,
			...tickers(d).map((s) => { const p = obj(prices[s]); return kpi(rub2(p.price), `${solo(d) ? "" : `${s}: `}${p.time ? "последняя сделка" : "закрытие"} · ${fmt.date(p.date)}${p.time ? ` ${p.time}${NBSP}МСК` : ""}${p.source ? ` · ${p.source}` : ""}`); }),
			kpi(`${num2(lo.close)}–${num2(hi.close)}${THIN}₽`, `минимум и максимум${tk(d, main)} за период`),
			kpi(pct1(obj(dv.yield_ltm || m.dividend_yield_ltm)[main]), lp.length ? `дивдоходность за 12 мес.: объявленные кварталы прибыли ${periodShort(lp[0])}–${periodShort(lp[lp.length - 1])}`
				: `дивиденды за 12 мес. к цене${tk(d, main)}`),
			kpi(fmt.x(m.pe_ltm, 1), "P/E за 12 месяцев")),
		basisFoot(d, "profit"));
}

function brokersCard(d) {
	const b = obj(d.market.brokers);
	if (!isNum(b.median)) return card({ title: "Цели брокеров", span: 6 }, empty("Целей брокеров в выпуске нет."));
	const model = obj(d.fair_value.headline).printed_median;
	const price = d.market.price;
	const plot = stripChart([
		{ v: b.median, kind: "bench", text: `медиана целей ${fmt.rub(b.median)}`, tip: { title: "Цели брокеров", rows: [["минимум", fmt.rub(b.min)], ["медиана", fmt.rub(b.median)], ["максимум", fmt.rub(b.max)], ["целей", fmt.num(b.n)]] } },
		{ v: price, kind: "market", text: `рынок ${fmt.rub(price)}` },
		{ v: model, kind: "model", text: `модель ${fmt.rub(model)}` },
	], { band: [b.min, b.max], bandFill: "var(--market-wash)", bandStroke: MARKET, label: "Цели брокеров, рынок и медиана модели" });
	const rec = obj(b.recommendations);
	const histRows = list(b.history).filter((h) => isNum(h.median));
	const spark = histRows.length > 1 ? sparkline({ title: "медиана целей", history: { date: histRows.map((h) => h.date), value: histRows.map((h) => h.median) } }, fmt.rub, "по снимкам") : null;
	return card({ title: "Цели брокеров", span: 6, sub: `на ${fmt.date(b.as_of)} · ${fmt.num(b.n)} ${plural(b.n || 0, ["цель", "цели", "целей"])} · ${b.source || ""}` },
		legend([["key-band", "разброс целей"], ["key-dot key-third", "медиана целей"], ["key-dot key-market", "рынок"], ["key-dot key-model", "модель"]]),
		plot,
		kpis(10,
			kpi(`${fmt.num(b.min)}–${fmt.num(b.max)}${THIN}₽`, "минимум и максимум целей"),
			kpi(`${fmt.num(rec.buy)} / ${fmt.num(rec.hold)} / ${fmt.num(rec.sell)}`, "покупать / держать / продавать")),
		spark ? spaced(10, tileLabel("Медиана целей по снимкам"), spark) : null);
}

function peersCard(d) {
	const p = obj(d.market.peers);
	const rows = list(p.rows);
	if (!rows.length) return card({ title: "Аналоги", span: 6 }, empty("Аналогов в выпуске нет."));
	const subject = p.subject_ticker || ticker(d);
	// Дата отчётности — `bv_date` строки; `as_of` — день снимка.
	const day = obj(rows.find((r) => r.ticker === subject) || rows[0]).bv_date;
	return card({ title: "Аналоги на одной базе", span: 6, sub: `отчётность на ${fmt.date(day)}; снимок аналогов ${fmt.date(p.as_of)}; цены — день оценки` },
		dataTable([
			Tc("Эмитент", (r) => sx(r.name, sp("hint",
				[r.ticker, obj(r.capital_ratio).name, r.ticker === subject ? ruText(r.basis || "") : null, r.bv_date && r.bv_date !== day ? `отчётность на ${fmt.date(r.bv_date)}` : null].filter(Boolean).join(" · "))), "name"),
			Nc("P/B", (r) => (isNum(r.pb) ? fmt.x(r.pb, 2) : "—")),
			Nc("P/E", (r) => (isNum(r.pe) ? fmt.x(r.pe, 1) : "—")),
			Nc("ROE 12 мес.", pctOf("roe_ltm", 1)),
			Nc("Дивдоходность", pctOf("dividend_yield", 1)),
			Nc("Норматив", (r) => { const c = obj(r.capital_ratio); return isNum(c.value) ? el("span", { tip: { title: c.name || "норматив", rows: [["на", fmt.date(c.as_of)]] } }, pct1(c.value)) : "—"; }),
		], rows, { rowClass: (r) => (r.ticker === subject ? "is-pick" : r.status === "missing" ? "is-muted" : null),
			detail: (r) => (r.status !== "live" && r.reason ? detailsBlock("Нет живой цены", phrase(r.reason)) : null) }),
		p.basis ? bx("card-foot", detailsBlock("База сравнения", phrase(p.basis))) : null);
}

function spreadCard(d) {
	const rows = list(obj(d.judgements).rows).filter((j) => isNum(j.price_low) && isNum(j.price_high)).slice(0, 8);
	// Быстрая сборка цену на краях суждений не считает — так и сказано, а не «нет блока».
	if (!rows.length) return card({ title: "Цена по одному суждению" }, list(obj(d.judgements).rows).some((j) => j.status === "not_computed") ? empty("В быстрой сборке цена на краях суждений не считалась.") : missing("суждения по цене ошибки"));
	const center = d.fair_value.central;
	const all = rows.flatMap((j) => [j.price_low, j.price_high]).concat(center);
	const step = niceStep(Math.max(...all), 6);
	const dom = [Math.max(0, Math.floor((Math.min(...all) * 0.94) / step) * step), Math.ceil((Math.max(...all) * 1.06) / step) * step];
	const box = bx("tornado", rows.map((j) => {
		const lo = Math.min(j.price_low, j.price_high), hi = Math.max(j.price_low, j.price_high);
		return bx("tn-row",
			bx("tn-name", j.name),
			bx("tn-bar", barTrack([
				{ from: lo, to: Math.min(center, hi), cls: "is-down" }, { from: Math.max(center, lo), to: hi, cls: "is-up" },
			].filter((s) => s.to > s.from), dom, { center, marks: [
				{ at: j.price_low, cls: "end", tip: { title: `${j.name}: нижний край`, rows: [["значение", formatByUnit(j.low, j.unit, d)], ["точка", rub1(j.price_low)]] } },
				{ at: j.price_high, cls: "end", tip: { title: `${j.name}: верхний край`, rows: [["значение", formatByUnit(j.high, j.unit, d)], ["точка", rub1(j.price_high)]] } },
			] })),
			bx("tn-vals", `${fmt.num(j.price_low)} … ${fmt.num(j.price_high)}${THIN}₽`, hint(isNimKey(j) ? "ключ цели: " : "", rangeText(d, j, true))));
	}));
	return card({ title: "Цена по одному суждению",
		sub: `Главные суждения книги по одному, каждое на краях своего диапазона; вертикаль — точка при значениях книги ${rub1(center)}. Это не полоса: полоса двигает все суждения сразу.` },
	legend([["key-neg", "ниже точки"], ["key-model", "выше точки"]]), box,
	el("div", { class: "tn-row tn-axis-row", "aria-hidden": "true" }, el("span"),
		bx("tn-axis", sx(fmt.rub(dom[0])), sx(fmt.rub(dom[1]))), el("span")));
}

/* ── экран «Расчёт» ── */

function screenModel(d) {
	return bx("screen",
		screenHead("Расчёт", "Как из допущений получается цена",
			"Капитал группы оценивается напрямую — остаточным доходом по сетке сценариев с явными вероятностями: миры ставок × режимы доходности и кредитного цикла × регуляторные сценарии капитала. "
			+ "Гайденс — сверка пути, а не вход. Все числа — из выпуска."),
		sec(flowCard(d)), sec(layersCard(d)), section("Путь доходности", roeTreeCard(d), fadeCard(d)), sec(guidanceCard(d)),
		more([regimesCard(d), capitalScenariosCard(d), worldsCard(d), transmissionCard(d), gridCard(d), varianceCard(d), governanceCard(d)]));
}

function flowCard(d) {
	const fv = d.fair_value;
	const head = obj(fv.headline);
	const g = obj(d.grid);
	const cells = list(g.cells);
	const meta = obj(d.meta);
	const L = obj(d.layers);
	const v0 = ["macro_neutral", "market_implied", "analytical"].map((k) => obj(L[k]).v0).filter(isNum);
	const inv = list(obj(d.checks).invariants).find((i) => i.name === "ddm_equals_ri");
	const n = (a, words) => `${fmt.num(list(a).length)} ${plural(list(a).length, words)}`;
	const steps = [
		["Сетка", `${fmt.num(cells.length)} ${plural(cells.length, CELL_WORDS)}`,
			`${n(g.world_order, ["мир", "мира", "миров"])} ставок × ${n(g.regime_order, ["режим", "режима", "режимов"])} доходности и кредитного цикла × `
			+ `${n(g.scenario_order, ["сценарий", "сценария", "сценариев"])} капитала; шаг — ${modelUnit(d).one}, ${periodLabel(list(meta.horizon)[0])} — ${periodLabel(list(meta.horizon)[1])}, база — ${basisName(meta.basis)}.`],
		["В клетке", inv ? (inv.ok ? "DDM = RI ✓" : "DDM ≠ RI") : "остаточный доход",
			"Капитал на дату оценки + PV (ROE − k)·капитал + терминал; дивидендная модель с капитальным ограничением проверяет каждую клетку."],
		["Слои", v0.length ? `V0 ${fmt.num(Math.min(...v0))}–${fmt.num(Math.max(...v0))}` : "—",
			`Три набора весов миров на одних клетках: ${["macro_neutral", "market_implied", "analytical"].map((k) => layerTitle(d, k)).join(", ")} (млрд ₽).`],
		["Цена и точка", `${priceNum(d, fv.low)} → ${priceNum(d, fv.central)} → ${priceNum(d, fv.high)}`,
			`[V0·(1 − g) + объявленный дивиденд до отсечки] на ${divisor(d)}; точка = низ + λ·(верх − низ), λ = ${num2(fv.own_macro_confidence)}.`],
		["Полоса", isNum(head.median) ? `медиана ${fmt.num(head.median, Math.max(pd(d), 1))}` : "нет в выпуске",
			isNum(head.median) ? `${fmt.num(head.draws)} прогонов по суждениям в их диапазонах; печать шагом ${fmt.num(head.print_step, pd(d))}${THIN}₽ половиной вверх → ${fmt.rub(head.printed_median)}.` : "Прогонов в выпуске нет."],
	];
	return card({ title: "Пять шагов от допущений к цене" },
		bx("flow", steps.map(([t, big, p]) => bx("flow-step", el("h3", {}, t), bx("big", big), pa(p)))));
}

function layersCard(d) {
	const L = obj(d.layers);
	const order = ["macro_neutral", "market_implied", "analytical"].filter((k) => L[k]);
	if (!order.length) return none("Слои", "слои");
	const mix = obj(L.headline_mix);
	return card({ title: "Слои: капитал, избыточная доходность и цена",
		sub: `Цена слоя — [V0·(1 − g) + дивиденд до отсечки] на акцию; V0 — оценка капитала; PV терминала — остаточного дохода (RI), доля терминала — в дивидендной модели (DDM); P(…) — масса клеток под весами слоя. Рынок${tk(d, ticker(d), ", ")} — ${rub2(d.market.price)}.` },
	dataTable([
		Tc("Слой", (k) => sx(layerTitle(d, k), hint(dictText(d, L[k].world_weights))), "name"),
		Nc("V0, млрд ₽", (k) => fmt.num(L[k].v0)),
		Nc("Капитал", (k) => fmt.num(L[k].bv_v)),
		Nc("P/B", (k) => fmt.x(L[k].pb, 2)),
		Nc("PV RI явный", (k) => fmt.num(L[k].pv_ri_explicit)),
		Nc("PV терминала RI", (k) => fmt.num(L[k].pv_terminal)),
		Nc("Доля терминала DDM", (k) => pct0(L[k].terminal_share)),
		Nc("Цена, ₽", (k) => strong(num1(L[k].price))),
		Nc("P(ниже рынка)", (k) => pct0(L[k].p_price_below_market)),
		Nc("P(ROE < k)", (k) => pct0(L[k].p_roe_below_k)),
		Nc("Разрыв капитала", (k) => pct1(L[k].capital_gap_mass)),
	], order),
	foot(`${upperFirst(ruText(mix.title || "смесь заголовка"))}: V0 ${bn0(mix.v0)}, цена ${rub2(mix.price)} = точка при λ = ${num2(mix.lambda)}.`));
}

function roeTreeCard(d) {
	const p = obj(d.paths);
	const tree = list(p.roe_tree);
	const annual = list(p.annual);
	if (!tree.length) return none("Дерево ROE", "путь");
	const hist = list(obj(d.history).annual);
	const years = [...new Set([...hist.map((h) => h.year), ...annual.map((a) => a.year)])];
	const mini = (title, fact, path, f) => bx("mini", tileLabel(title),
		linesChart([{ name: "факт", color: INK, ...DOT, points: fact }, { name: "модель", color: MODEL, ...DOT, points: path }],
			{ xType: "band", categories: years, height: 150, left: 44, yFmt: f, tipFmt: f, xFmt: yy }));
	const part = (v) => num2(v * 100);
	return card({ title: "Дерево ROE: от строк ОПУ к доходности капитала",
		sub: `${upperFirst(ruText(obj(obj(d.layers).headline_mix).title || obj(p.mix).title || "смесь заголовка"))}; строки — % средних активов; ROA × рычаг = ROE. Год якоря — факт отчётных ${modelUnit(d).pgen} + модель; упр. ЧПМ и CoR — мостом сборки.` },
	bx("minis",
		mini("ЧПМ, упр.", hist.map((h) => [h.year, obj(h.mgmt).nim]), annual.map((a) => [a.year, a.nim_mgmt]), pct1),
		mini("CoR, упр.", hist.map((h) => [h.year, obj(h.mgmt).cor]), annual.map((a) => [a.year, a.cor_mgmt]), pct2),
		mini("ROE (МСФО группы)", hist.map((h) => [h.year, obj(h.ifrs).roe]), annual.map((a) => [a.year, a.roe]), pct1)),
	spaced(16, dataTable([
		Tc("Год", (r) => String(r.year), "name"),
		Nc("ЧПД", (r) => part(r.nii_to_assets)),
		Nc("Услуги и комиссии", (r) => part(r.fees_to_assets)),
		Nc("Прочее", (r) => part(r.other_to_assets)),
		Nc(noncoreHead(), (r) => part(r.noncore_to_assets)),
		Nc("Расходы", (r) => part(r.opex_to_assets)),
		Nc("Резервы", (r) => part(r.llp_to_assets)),
		Nc("Налог", (r) => part(r.tax_to_assets)),
		Nc("ROA", (r) => strong(pct2(r.roa))),
		Nc("Рычаг", (r) => fmt.x(r.leverage, 1)),
		Nc("ROE", (r) => strong(pct1(r.roe))),
	], tree, { caption: "% средних активов" })), basisFoot(d, "roe"));
}

function fadeCard(d) {
	const f = obj(obj(d.paths).fade);
	const years = list(f.years);
	if (!years.length) return null;
	const at = (k) => years.map((y, i) => [y, list(f[k])[i]]);
	return card({ title: "Путь ROE и роста капитала к терминалу",
		sub: "Линии — средние по клеткам под вероятностями точки. Остаточный доход считается в каждой клетке по её ставкам, поэтому знак разности линий — не знак прироста стоимости"
			+ `${list(obj(d.reverse_dcf).bank_rows).some((r) => r.by_year) ? ": накопленный приведённый доход по годам — на экране «Что в цене»" : ""}. За горизонтом избыток доходности угасает.` },
		legend([["key-line key-model", "ROE"], ["key-line key-ink", "стоимость капитала"], ["key-line key-third", "рост капитала г/г"]]),
		linesChart([{ name: "ROE", color: MODEL, width: 2.2, ...DOT, points: at("roe") }, { name: "стоимость капитала", color: INK, width: 1.5, points: at("k") },
			{ name: "рост капитала", color: THIRD, ...DOT, points: at("bv_growth") }],
		{ xType: "band", categories: years, height: 230, yPct: true, tipFmt: pct1, xFmt: yy, label: "ROE, стоимость капитала и рост капитала по годам" }),
		kpis(12,
			kpi(`${num1(f.roe_t_raw * 100)} → ${pct1(f.roe_t)}`, "ROE терминала на капитале без избытка: до угасания → после"), kpi(pct1(f.k_t), "стоимость капитала терминала"), kpi(pct1(f.g_t), "рост терминала"),
			kpi(num2(f.fade), "множитель угасания избыточной доходности"), kpi(pct0(obj(obj(d.paths).terminal).payout_t), "доля выплаты терминала")),
		basisFoot(d, "roe"));
}

const GUIDE_STATUS = { inside: ["в гайденсе", "good"], outside: ["вне гайденса", "warn"], "n/a": ["не сравнивается", "out"] };
const GUIDE_RELATION = { above: "лучше сектора", in_line: "в соответствии с сектором" };
function guideStatus(r) {
	const [t, k] = GUIDE_STATUS[r.status] || [r.status, null];
	return r.scope !== "sector" || r.status === "n/a" ? badge(t, k) : badge(r.status === "inside" ? "в прогнозе сектора" : "вне прогноза сектора", k);
}

function guideValue(kind, key, v) {
	if (v === null || v === undefined) return "эмитент числа не называет";
	if (Array.isArray(v)) return `${num1(v[0] * 100)}–${pct1(v[1])}`;
	const s = fmt.pct(v, key === "nim" ? 2 : 1);
	const k = kind || (key === "cor_max" ? "max" : "point");
	return k === "max" ? `≤${NBSP}${s}` : k === "min" ? `≥${NBSP}${s}` : s;
}

// Пересмотры гайденса: только смены значения строки.
function guidanceChanges(g) {
	const last = {};
	const out = [];
	for (const r of list(g.revisions).slice().sort((a, b) => String(a.date).localeCompare(String(b.date)))) {
		const was = last[r.key];
		if (was !== undefined && JSON.stringify(was) !== JSON.stringify(r.value)) out.push({ ...r, was });
		last[r.key] = r.value;
	}
	return out;
}

// С какой даты гайденс стоит в нынешнем составе: поздняя из первых записей строк.
function guidanceSince(g) {
	const first = {};
	for (const r of list(g.revisions)) if (!(String(r.date) >= first[r.key])) first[r.key] = String(r.date);
	return Object.values(first).sort().pop();
}

function guidanceCard(d) {
	const g = obj(d.guidance);
	const items = list(g.items);
	if (!items.length) return none("Гайденс", "гайденс");
	const changes = guidanceChanges(g);
	const gate = obj(g.gate);
	const st = obj(g.strategy);
	const kindOf = Object.fromEntries(items.map((r) => [r.key, r.kind]));
	const titleOf = Object.fromEntries(items.map((r) => [r.key, r.title]));
	const sector = items.some((r) => r.scope === "sector");
	return card({ title: `Гайденс ${g.year || ""}${st.name ? " и стратегия" : ""} против пути модели`,
		sub: `Гайденс от ${fmt.date(g.as_of)} (${ruText(g.src || "")}); базис — ${basisName(g.basis)}, иной базис строки — в подписи; ЧПМ, CoR и ${ci()} модели переведены в упр. базис мостами сборки. Модель года — факт отчётных кварталов + смесь заголовка.`
			+ (sector ? " Строки сектора — прогноз сектора, а не гайденс эмитента: гейт их не берёт." : "") },
	dataTable([
		Tc("Показатель", (r) => el("span", { tip: r.scope_note ? ruText(r.scope_note) : null }, r.title,
			hint([basisName(r.basis), GUIDE_RELATION[r.relation]].filter(Boolean).join("; "))), "name"),
		Nc("Гайденс", (r) => guideValue(r.kind, r.key, r.guidance), "", (r) => r.guidance === null),
		Nc("Факт с начала года", (r) => (isNum(r.fact_ytd) ? pct2(r.fact_ytd) : "—")),
		Nc("Модель года", (r) => strong(isNum(r.model_year) ? pct2(r.model_year) : "—")),
		items.some((r) => isNum(r.required_rest)) ? Nc("Нужно в остатке года", (r) => (isNum(r.required_rest) ? pct2(r.required_rest) : "—")) : null,
		Tc("Статус", guideStatus),
		Nc("Масса вне", pctOf("mass_outside", 0)),
	], items),
	gate.fired ? mt(14, "div", "note-box",
		strong(`Гейт «${gateTitle(d, gate.name)}» сработал: ${pct0(gate.mass)} массы клеток. `),
		gate.explanation ? ruText(gate.explanation) : "Объяснения нет.", gate.valid_until ? ` Объяснение действует по ${fmt.date(gate.valid_until)}.` : "") : null,
	list(st.targets).length ? spaced(16,
		tileLabel(`${st.name || "Стратегия"}${obj(st.next_event).date ? ` · ${fmt.date(st.next_event.date)} — ${lowerFirst(st.next_event.title)}` : ""}`),
		dataTable([
			Tc("Цель", (t) => t.title, "name"),
			Nc("Ориентир", (t) => pct1(t.target)),
			Nc("Факт", (t) => `${pct1(t.fact_last)} · ${periodLabel(t.fact_period)}`),
			Nc("Модель", (t) => list(t.model).map((m) => `${m.year}: ${pct1(m.value)}`).join("; ") || "—"),
			Tc("", (t) => (t.met === true ? badge("выполнена", "good") : t.met === false ? badge("не выполнена", "warn") : "—")),
		], list(st.targets), COMPACT)) : null,
	changes.length ? bx("card-foot", detailsBlock(`Пересмотры гайденса · ${changes.length}`,
		changes.map((r) => `${fmt.date(r.date)} — ${titleOf[r.key] || "строка гайденса"}: ${guideValue(kindOf[r.key], r.key, r.was)} → ${guideValue(kindOf[r.key], r.key, r.value)} (${ruText(r.event)})`).join("; ") + "."))
		: list(g.revisions).length ? foot(`Гайденс года с ${fmt.date(guidanceSince(g))} не пересматривался.`) : null);
}

function gateTitle(d, name) {
	const g = list(obj(d.checks).gates).find((x) => x.name === name);
	return (g && g.title) || name;
}
// Объяснение сработавшего гейта — в карточке его темы.
function gateNote(d, name) {
	const g = list(obj(d.checks).gates).find((x) => x.name === name);
	return g && g.fired && g.explanation ? detailsBlock(`Гейт «${g.title || name}»`, ruText(g.explanation)) : null;
}

let REGIME_BASIS = null;

function regimesCard(d) {
	const R = obj(d.regimes);
	const order = regimeOrder(d);
	const rows = obj(R.rows);
	if (!order.length) return none("Режимы доходности и кредитного цикла", "режимы", 12);
	const bookBasis = R.cor_basis || "mgmt";
	if (!REGIME_BASIS) REGIME_BASIS = bookBasis;
	const body = el("div");
	const years = [...new Set(order.flatMap((k) => list(obj(rows[k]).cor).map((p) => p.year)))].sort();
	const draw = () => {
		const engine = REGIME_BASIS === "engine" && bookBasis !== "engine";
		const key = engine ? "cor_engine" : "cor";
		const lt = engine ? "cor_lt_engine" : "cor_lt";
		const cats = [...years, "LT"];
		const series = order.map((k, i) => ({ name: regimeName(d, k), color: SERIES[i % SERIES.length], dots: true, r: 3.5,
			points: [...list(obj(rows[k])[key]).map((p) => [p.year, p.value]), ["LT", obj(rows[k])[lt]]] }));
		const plot = linesChart(series, { xType: "band", categories: cats, height: 230, yFmt: pct1, tipFmt: pct2,
			label: "CoR режимов по годам" });
		const crisis = obj(obj(rows.crisis).crisis);
		fill(body, 
			legend(series.map((s, i) => [SERIES_KEYS[i % SERIES_KEYS.length], s.name])), plot,
			engine ? foot(`Базис движка: путь книги + мост ${fmt.pp(obj(R.cor_bridge).value)} (${ruText(obj(R.cor_bridge).method || "")}).`) : null,
			list(crisis.cor_quarters).length ? foot(`${regimeName(d, "crisis")}: год шока ${crisis.shock_year}, по кварталам (${basisName(bookBasis)}) `
				+ list(crisis.cor_quarters).map((q) => `${periodShort(q.period)} ${pct1(q.value)}`).join(" · ")
				+ (obj(crisis.one_off_loss).amount ? `; разовый убыток ${bn0(crisis.one_off_loss.amount)} в ${periodLabel(crisis.one_off_loss.period)}` : "") + ".") : null);
	};
	draw();
	const stack = (field) => bx("stackbar", order.map((k, i) => el("i", {
		style: `flex:${obj(rows[k])[field] || 0} 1 0;background:${SERIES[i % SERIES.length]}`,
		tip: { title: regimeName(d, k), rows: [["вероятность", pct1(obj(rows[k])[field])]] } })));
	const exp = obj(R.expected);
	const obs = list(obj(R.update).observations);
	const near = list(R.near_nim_shift).filter((q) => isNum(q.value));
	return card({ title: "Режимы доходности и кредитного цикла",
		sub: `Пути CoR — в базисе книги (${basisName(bookBasis)}); переключатель показывает их после моста так, как видит движок. Сдвиги ЧПМ режимов — без ближнего сдвига: он общий для режимов и миров.`,
		tools: chooser([{ value: bookBasis, label: `книга (${basisName(bookBasis)})` }, { value: "engine", label: "движок" }], REGIME_BASIS, (v) => { REGIME_BASIS = v; draw(); }, "Базис CoR") },
	body,
	mt(16, "div", "split",
		dx(tileLabel("Вероятности: книга"), stack("prior"),
			tileLabel("после наблюдений кварталов"), stack("posterior"),
			smallNote(`Ожидание: сдвиг ЧПМ ${fmt.pp(exp.nim_shift_lt)}; ${lt("CoR", "долгосрочная")} ${pct2(exp.cor_lt)} (${basisName(bookBasis)}), ${pct2(exp.cor_lt_engine)} (движок).`
				+ (R.reference_world ? ` Пути и уровни CoR режимов стоят при ставках мира «${worldName(d, R.reference_world)}»: в других мирах их сдвигает разность реальных ставок.` : "")
				+ (obj(d.paths).levels ? " Это ожидание по ключам режимов книги, а не уровень слоя: уровни, которые печатают клетки и слои, — на экране «Оценка»." : ""))),
		dataTable([
			Tc("Режим", (k) => regimeName(d, k), "name"),
			Nc("Книга", (k) => pct1(obj(rows[k]).prior)),
			Nc("После наблюдений", (k) => strong(pct1(obj(rows[k]).posterior))),
			Nc(lt("CoR", "долгосрочная"), (k) => pct2(obj(rows[k]).cor_lt)),
			Nc(`Сдвиг ${lt("ЧПМ", "долгосрочной")}`, (k) => fmt.pp(obj(rows[k]).nim_shift_lt, 1)),
		], order, COMPACT)),
	near.length ? foot(`Ближний сдвиг ЧПМ, общий для режимов и миров (${basisName(R.basis || "engine")}, п.п.): `
		+ near.map((q) => `${periodShort(q.period)} ${fmt.num(q.value * 100, exactDigits(q.value * 100, 3))}`).join(" · ") + ".") : null,
	obs.length ? bx("card-foot", detailsBlock(`Наблюдения кварталов · ${obs.length}`,
		obs.map((o) => `${periodLabel(o.period)}: CoR ${pct2(o.cor)}, ЧПМ ${pct2(o.nim)} (${basisName(o.basis)})`).join("; ")
			+ (isNum(obj(R.update).window_obs) ? `. Фильтр читает не больше ${fmt.num(R.update.window_obs)} последних; априорные вероятности — книги` : "")
			+ (R.update.floor_share > 0 ? `; вероятность режима после наблюдений — не ниже ${pct0(R.update.floor_share)} книжной` : "") + ".")) : null,
	regimeHistory(d), referenceClass(d));
}

function regimeHistory(d) {
	const h = list(obj(d.regimes).history);
	if (h.length < 2) return null;
	const cats = h.map((r) => r.period);
	return detailsBlock("История CoR и ЧПМ по кварталам (упр. и движок)", linesChart([
		{ name: "CoR упр.", color: NEG, ...DOT, points: h.map((r) => [r.period, r.cor_mgmt]) },
		{ name: "CoR движок", color: NEG, dashed: true, points: h.map((r) => [r.period, r.cor_engine]) },
		{ name: "ЧПМ упр.", color: MODEL, ...DOT, points: h.map((r) => [r.period, r.nim_mgmt]) },
		{ name: "ЧПМ движок", color: MODEL, dashed: true, points: h.map((r) => [r.period, r.nim_engine]) },
	], { xType: "band", categories: cats, height: 200, yFmt: pct1, tipFmt: pct2, xFmt: periodShort, label: "История CoR и ЧПМ" }));
}

// Референс-класс эпизодов — справочно, движок его не читает.
function referenceClass(d) {
	const rc = obj(obj(d.regimes).reference_class);
	if (rc.error) return foot(`Референс-класс не собран: ${ruText(rc.error)}.`);
	if (!list(rc.shares).length) return null;
	return detailsBlock(`Референс-класс эпизодов · ${list(rc.episodes).length} — справочно`, el("div", {},
		dataTable([
			Tc("Режим", (r) => regimeName(d, r.regime), "name"),
			Nc("Книга", pctOf("book", 0)),
			Nc("Класс", pctOf("class", 0)),
			Nc("95 % Уилсона", (r) => `${fmt.num(r.lo * 100)}–${pct0(r.hi)}`),
		], list(rc.shares), COMPACT),
		list(rc.episodes).length ? smallNote(
			list(rc.episodes).map((e) => `${e.name} (${ruText(e.period)}): пик CoR ${pct1(e.cor_peak)}`).join("; ") + ".") : null));
}

let CAP_SCENARIO = null;

function capitalScenariosCard(d) {
	const C = obj(d.capital);
	const S = obj(C.scenarios);
	const keys = scenarioOrder(d).filter((k) => S[k]);
	if (!keys.length) return none("Регуляторные сценарии капитала", "сценарии капитала");
	if (!CAP_SCENARIO || !S[CAP_SCENARIO]) CAP_SCENARIO = keys[0];
	const years = list(C.years);
	const body = el("div");
	const draw = () => {
		const s = S[CAP_SCENARIO];
		const lines = [["conservation", "надбавка поддержания достаточности"], ["sifi", "надбавка за системную значимость"], ["ccyb", "антициклическая"], ["deduction_n20", `вычеты, ${capTitle(d, "n20")}`],
			["floor20", `пол ${capTitle(d, "n20")}`], ["req20", `требование ${capTitle(d, "n20")}`], ["floor11", `пол ${capTitle(d, "n11")}`], ["req11", `требование ${capTitle(d, "n11")}`]];
		fill(body, dataTable([
			Tc("", (r) => r[1], "name"),
			...years.map((y, i) => (Nc(String(y), (r) => pct2(list(s[r[0]])[i])))),
		], lines, { cls: "compact", rowClass: (r) => (r[0].startsWith("req") ? "is-total" : null) }));
	};
	draw();
	const regs = regimeOrder(d);
	return card({ title: "Регуляторные сценарии капитала",
		sub: `Минимум ${capTitle(d, "n20")} ${pct1(obj(C.minimum).n20_0)}, ${capTitle(d, "n11")} ${pct1(obj(C.minimum).n1_1)}; запас менеджмента ${fmt.pp(obj(C.mgmt_buffer).n20_0, 1)}${C.policy_threshold > 0 ? `; порог дивидендной политики ${pct1(C.policy_threshold)}.` : ""}` },
	bx("pick-row", chooser(keys.map((k) => ({ value: k, label: scenarioName(d, k), hint: pct0(S[k].mass) })), CAP_SCENARIO, (v) => { CAP_SCENARIO = v; draw(); }, "Сценарий капитала")),
	body,
	spaced(14, dataTable([
		Tc("P(сценарий | режим)", (k) => scenarioName(d, k), "name"),
		...regs.map((r) => (Nc(regimeName(d, r), (k) => pct0(obj(S[k].p_given_regime)[r])))),
		Nc("Масса", (k) => strong(pct0(S[k].mass))),
	], keys, COMPACT)), gateNote(d, "stress_sign"));
}

function worldsRecord(d) {
	const v = /book-(\d+(?:\.\d+)+)/.exec(obj(obj(d.worlds).source).origin || "");
	return `запись семейства 850${v ? `, версия ${v[1]}` : ""}`;
}

function worldsCard(d) {
	const W_ = obj(obj(d.worlds).rows);
	const keys = worldOrder(d).filter((k) => W_[k]);
	if (!keys.length) return none("Миры ставок", "миры");
	const series = keys.map((k, i) => ({ name: `${k} — ${W_[k].name}`, color: WORLD_COLORS[i % 3], dots: true,
		points: curvePoints(W_[k].zero_curve) }));
	const curve = obj(obj(d.live).curve);
	if (Object.keys(obj(curve.nodes)).length) {
		series.push({ name: `ОФЗ ${fmt.date(curve.as_of)}`, color: INK, width: 1.5, dots: true, r: 3,
			points: curvePoints(curve.nodes) });
	}
	const plot = linesChart(series, { height: 240, ...CURVE_AXIS, label: "Бескупонные кривые миров" });
	const fig = withTable(plot, () => dataTable([
		Tc("Мир", (k) => `${k} — ${W_[k].name}`, "name"),
		...["1", "3", "5", "10", "LT"].map((t) => (Nc(t === "LT" ? "LT" : `${t} г.`, (k) => pct2(obj(W_[k].zero_curve)[t])))),
	], keys));
	const by = obj(d.fair_value.by_world);
	const years = list(obj(W_[keys[0]]).key_rate).map((p) => p.year).slice(0, 5);
	return card({ title: "Миры ставок", tools: fig.button,
		sub: "Мир — согласованная макротраектория: ключевая, инфляция, кривая, рост кредита и средств (банковская надстройка). Веса миров задают слои." },
	bx("split",
		dx(legend(series.map((s, i) => [i < keys.length ? WORLD_KEYS[i % 3] : "key-line key-ink", s.name])), fig.box),
		dataTable([
			Tc("Мир", (k) => sx(W_[k].name, hint(k)), "name"),
			...["analytical", "market_implied"].map((l) => Nc(`Вес: ${lowerFirst(layerTitle(d, l))}`, (k) => pct0(obj(W_[k].weights)[l]))),
			Nc("Стоимость капитала", (k) => pct1(W_[k].k_t)),
			Nc("Рост терминала", (k) => pct1(W_[k].g_t)),
			Nc("Цена мира", (k) => fmt.rub(obj(by[k]).price)),
		], keys, COMPACT)),
	spaced(14, dataTable([
		Tc("Мир, по годам", (r) => r[0], "name"),
		...years.map((y) => (Nc(String(y), (r) => pct1(byYear(r[1], y))))),
	], keys.flatMap((k) => [[`${k}: ключевая`, W_[k].key_rate], [`${k}: инфляция`, W_[k].cpi], [`${k}: кредит ЮЛ`, obj(W_[k].credit_growth).corporate],
		[`${k}: средства ФЛ`, obj(W_[k].funds_growth).retail]]), COMPACT)),
	foot(`Цена мира — оценка при весе мира 100 %. Миры: ${worldsRecord(d)}, кривые ${fmt.date(obj(obj(d.worlds).source).curve_date)}.`));
}

function transmissionCard(d) {
	const n = obj(d.nii);
	const t = obj(n.transmission);
	if (!isNum(t.target)) return none("Книги ЧПД и передача ставки", "ЧПД");
	const nw = obj(n.nim_by_world);
	const keys = worldOrder(d).filter((k) => Array.isArray(nw[k]));
	const plot = linesChart(keys.map((k, i) => ({ name: worldName(d, k), color: WORLD_COLORS[i % 3], ...DOT, points: list(nw.years).map((y, j) => [y, nw[k][j]]) })),
		{ xType: "band", categories: list(nw.years), height: 200, yFmt: pct1, tipFmt: pct2, xFmt: yy, label: "ЧПМ по мирам, упр." });
	const cs = obj(n.current_share);
	const pairs = list(t.pairs);
	const range = list(t.pairs_range);
	const np = obj(t.nim_lt_printed), ns = nimNode(d), head = `${lt("ЧПМ", "долгосрочная")}, упр.`, eng = `; ключ в движке — ${pct2(t.target_eng)}`;
	const roe = (v) => (isNum(v) ? `${num2(v)}${NBSP}п.п.` : "—");
	const dis = obj(n.disclosed);
	const margin = obj(t.loan_margin);
	const rows = [...pairs, pairs.length ? { from: pairs[0].from, to: pairs[pairs.length - 1].to, key_from: pairs[0].key_from, key_to: pairs[pairs.length - 1].key_to,
		value: t.realized, roe_equiv: t.roe_equiv, total: true } : null].filter(Boolean);
	return card({ title: "Книги ЧПД и передача ставки",
		sub: `Передача — ${ruText(t.definition || "")}: ось книги M − N решается точно (инвариант); по парам соседних миров — гейт с коридором; локальная передача по мирам и по клеткам — диагностика.` },
	kpis(
		kpi(fmt.num(t.target, 3), "передача M − N в книге (T*)"),
		kpi(`${fmt.num(t.realized, 3)} ${t.solved ? "✓" : "✗"}`, `реализованная, допуск ${sci(t.tol)}`),
		isNum(np.value) ? kpi(`${num2(t.nim_lt_target_mgmt * 100)} / ${pct2(np.value)}`, `${head}: ключ цели / печатает модальная клетка (${cellName(d, np.cell)}) в среднем за ${np.from_year}–${np.to_year} годы; ${nimTol(np)}${eng}`)
			: ns.reference_world ? kpi(`${num2(ns.value * 100)} / ${pct2(ns.reference_value)}`, `${head}: суждение книги — ${nimWords(d)} на составе баланса якоря / выведенный из неё уровень мира-опоры «${worldName(d, ns.reference_world)}»${eng}`)
			: isNum(ns.value) ? kpi(`${num2(t.nim_lt_target_mgmt * 100)} / ${pct2(ns.value)}`, `${head}: ключ цели — уровень мира-опоры / суждение книги — ${nimWords(d)} на составе баланса якоря; ${nimTol(ns)}${eng}`)
			: kpi(pct2(t.nim_lt_target_mgmt), `${head} (движок ${pct2(t.target_eng)})`),
		isNum(t.sigma0_liab) ? kpi(`${fmt.signed(t.sigma0 * 100, 2)} / ${fmt.pp(t.sigma0_liab)}`, `сдвиг LT-спредов σ0: активы / пассивы; на активах — ${pct0(t.sigma0_split)} сдвига`)
			: kpi(fmt.pp(t.sigma0), "общий сдвиг LT-спредов σ0"),
		isNum(t.phi_assets) ? kpi(`${fmt.num(t.phi_assets, 3)} / ${fmt.num(t.phi_liab, 3)}`, `сжатие φ со ставкой: спреды кредитных книг / стоимость средств клиентов; на кредитных книгах — ${pct0(t.phi_split)} сжатия φ = ${fmt.num(t.phi, 3)}`)
			: kpi(fmt.num(t.phi, 3), "сжатие спреда со ставкой φ"),
		isNum(dis.nii_per_100bp) ? kpi(bn0(dis.nii_per_100bp), "раскрытая чувствительность ЧПД к ±100 б.п.") : null),
	isNum(dis.nii_per_100bp) ? null : smallNote(sentence(`Раскрытой чувствительности ЧПД к ±100 б.п. нет: ${ruText(dis.src || "в фактах её нет")}`)),
	rows.length ? spaced(16,
		tileLabel(`Передача по парам соседних миров${range.length === 2 ? `: коридор ${num2(range[0])} … ${num2(range[1])}` : ""}`),
		dataTable([
			Tc("Пара миров", (p) => sx(p.total ? `${p.to} − ${p.from}` : `${p.from} → ${p.to}`,
				hint(p.total ? "реализованная передача — ось книги" : `${worldName(d, p.from)} → ${worldName(d, p.to)}`)), "name"),
			Nc("Ключевая LT", (p) => `${num1(p.key_from * 100)} → ${pct1(p.key_to)}`),
			Nc("Передача", (p) => strong(fmt.num(p.value, 3))),
			Nc("ROE на 1 п.п. ключевой", (p) => roe(p.roe_equiv)),
			Tc("", (p) => (p.total ? badge(t.solved ? "решена точно" : "не решена", t.solved ? "good" : "bad") : p.inside ? badge("в коридоре", "good") : badge("вне коридора", "warn"))),
		], rows, { cls: "compact", rowClass: (p) => (p.total ? "is-total" : null) }),
		["transmission_pairs", "lt_spread_floor", "nim_lt", "nim_stationary", "funds_cost_to_key"].map((k) => gateNote(d, k))) : null,
	mt(16, "div", "split",
		dx(tileLabel("ЧПМ по мирам (упр.)"), legend(keys.map((k, i) => [WORLD_KEYS[i % 3], worldName(d, k)])), plot),
		dx(tileLabel("Диагностики — гейта нет"), dataTable([
			Tc("Мир", (k) => worldName(d, k), "name"),
			Nc("Локальная T(W)", (k) => fmt.num(obj(t.by_world)[k], 3)),
			Nc("Доля текущих счетов, LT", (k) => pct1(list(obj(cs.by_world)[k]).slice(-1)[0])),
			Object.keys(margin).length ? Nc("Кредитная маржа, п.п.", (k) => num2(margin[k] * 100)) : null,
		], keys, COMPACT),
		keys.some((k) => margin[k] < 0) ? smallNote("Кредитная маржа — доходность кредитов минус CoR и ставка балансирующих активов; где она отрицательна, рост кредита стоимость разрушает.") : null,
		smallNote(`Передача по клеткам (M, норм., по графику) − (N, …): ${fmt.num(t.realized_cells, 3)}. Доля текущих счетов: якорь ${pct1(cs.c_ref)}, ψ ${num2(cs.psi)}, границы ${list(cs.bounds).map((b) => pct0(b)).join("–")}.`))),
	spaced(14, dataTable([
		Tc("Книга", (b) => sx(b.title, hint(`${b.side === "asset" ? "актив" : "пассив"} · опора — ${refText(b.ref)}${b.balancing ? " · балансирующая" : ""}${isNum(b.spread_floor) ? ` · пол спреда ${num2(b.spread_floor * 100)}${NBSP}п.п.` : ""}`)), "name"),
		Nc("Остаток, млрд ₽", (b) => fmt.num(b.balance_anchor)),
		Nc("Ставка якоря", (b) => pct2(b.rate_anchor)),
		Nc(el("span", { tip: "ρ — доля разрыва ставки книги к цели, закрываемая за квартал" }, "ρ"), (b) => num2(b.rho)),
		Nc(el("span", { tip: "β — передача ставки опоры книги в стоимость пассива" }, "β"), (b) => (isNum(b.beta) ? fmt.num(b.beta, 3) : "—")),
		Nc("φ", (b) => (b.phi ? "да" : "—")),
		Nc(`LT-спред к опоре: ${keys.join(" / ")}, п.п.`, (b) => (b.spread_lt_world
			? el("span", { tip: { title: b.title, rows: [["ключ книги (без сдвига и сжатия)", fmt.pp(b.spread_lt)]] } }, keys.map((k) => fmt.signed(obj(b.spread_lt_world)[k] * 100, 2)).join(" / "))
			: fmt.pp(b.spread_lt))),
		...keys.map((k) => (Nc(`Ставка LT, ${k}`, (b) => pct2(obj(b.rate_lt)[k])))),
	], list(n.books), { caption: "Книги ЧПД: LT-спред — эффективный, со сдвигом σ0 и сжатием φ (у кредитной книги сжимается спред, у средств клиентов дорожает фондирование)" })));
}

const HEAT_STEPS = [0.5, 0.75, 1, 1.5, 2, 3];
function heatClass(price, market) {
	if (!isNum(price) || price <= 0 || !isNum(market) || market <= 0) return "h0";
	let i = 0;
	while (i < HEAT_STEPS.length && price >= HEAT_STEPS[i] * market) i++;
	return `h${i + 1}`;
}
const FLAG_MARKS = { capital_gap: "⚠", roe_below_k: "↓", dividend_cut: "✂", crisis_skip: "✕", growth_cut: "◔" };
// Отмена кризисом — не урезание капиталом (М§5.3).
const FLAG_WORDS = { capital_gap: "капитальный разрыв", roe_below_k: "ROE < k", dividend_cut: "дивиденд урезан капиталом", crisis_skip: "решения года кризиса отменены",
	growth_cut: "рост урезан капиталом", growth_solver: "доля прироста найдена с невязкой" };

function gridCard(d) {
	const g = obj(d.grid);
	const cells = list(g.cells);
	if (!cells.length) return none("Сетка сценариев", "сетка");
	const market = d.market.price;
	const worlds = list(g.world_order), regimes = list(g.regime_order), scen = list(g.scenario_order);
	const panels = worlds.map((w) => el("div", {},
		bx("heat-title", strong(`${w} — ${worldName(d, w)}`)),
		el("table", { class: "heat" },
			el("thead", {}, el("tr", {}, el("th", { class: "row-h" }, "режим / капитал"), scen.map((s) => el("th", {}, scenarioName(d, s))))),
			el("tbody", {}, regimes.map((r) => el("tr", {}, el("th", { class: "row-h" }, regimeName(d, r)),
				scen.map((s) => {
					const c = cells.find((x) => x.world === w && x.regime === r && x.scenario === s);
					if (!c) return el("td", {}, "—");
					const flags = list(c.flags);
					return el("td", { class: heatClass(c.price, market), tip: { title: `${worldName(d, w)} · ${regimeName(d, r)} · ${scenarioName(d, s)}`,
						rows: [["цена клетки", rub1(c.price)], ["P/B", fmt.x(c.pb, 2)], [`${roeLt()} / стоимость капитала`, `${pct1(c.roe_t)} / ${pct1(c.k_t)}`],
							[`минимум ${capTitle(d, "n20")}`, pct1(c.n20_min)], ["DPS года якоря", rub2(c.dps_first)], [`вероятность («${layerTitle(d, "analytical")}»)`, pct2(c.p_analytical)]],
						note: flags.map((f) => FLAG_WORDS[f] || f).join("; ") || null } },
					sp("p", fmt.num(c.price)), sp("w", pct1(c.p_analytical)),
					flags.length ? el("span", { class: "flag", "aria-label": "флаги" }, flags.map((f) => FLAG_MARKS[f]).filter(Boolean).join(" ")) : null);
				})))))));
	const steps = ["var(--seq-0)", "var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)", "var(--seq-5)", "var(--seq-6)"];
	return card({ title: `Сетка: ${fmt.num(cells.length)} ${plural(cells.length, CELL_WORDS)}`,
		sub: `В клетке — цена (₽) и вероятность под весами «${layerTitle(d, "analytical")}»; цвет — порядок цены к рынку${tk(d, ticker(d))} (${rub2(market)}). Базис путей — ${basisName(g.basis)}.` },
	bx("heat-wrap", panels),
	bx("scale", sx("цена клетки к рынку:"),
		...steps.flatMap((c, i) => [el("i", { style: `background:${c}` }), i === 0 ? `<${NBSP}×${num2(HEAT_STEPS[0])}` : `×${num2(HEAT_STEPS[i - 1])}${i === steps.length - 1 ? "+" : ""}`]),
		sp("gap", Object.entries(FLAG_MARKS).filter(([k]) => cells.some((c) => list(c.flags).includes(k))).map(([k, v]) => `${v} ${FLAG_WORDS[k]}`).join(" · "))));
}

function varianceCard(d) {
	const v = obj(obj(d.variance).price);
	const names = { world: "мир ставок", regime: "режим", scenario: "сценарий капитала", interaction: "взаимодействие" };
	const rows = Object.entries(v).filter(([, s]) => isNum(s)).sort((a, b) => b[1] - a[1]);
	if (!rows.length) return none("Что разводит клетки", "разброс сетки", 6);
	const max = Math.max(...rows.map((r) => r[1]));
	return card({ title: "Что разводит клетки", span: 6, sub: phrase(d.variance.method || "доли дисперсии цены клеток") },
		bx("hbars", rows.map(([k, s]) => hbar(names[k] || k, s, max, { color: GREY }))),
		foot("Это описание сценариев сетки, а не неопределённость печатаемого числа — её показывает полоса."));
}

function governanceCard(d) {
	const g = obj(d.governance);
	const comps = list(g.components);
	if (!comps.length && !isNum(g.discount)) return none("Дисконт за управление", "дисконт за управление", 6);
	let run = 0;
	const steps = comps.map((c) => { const v = (c.sign || 1) * c.value; const from = run; run += v; return { title: c.name, from, to: run, text: fmt.pp(v) }; });
	steps.push({ title: "Дисконт g", from: 0, to: g.sum_signed, total: true, text: pct2(g.sum_signed) });
	return card({ title: `Дисконт за управление: ${pct2(g.discount)}`, span: 6, sub: "Каналы снизу вверх; канал без опоры — 0. Налоги, капитал и кризис в дисконт не входят." },
		comps.length ? waterfall(steps) : pa("Каналов с опорой нет: дисконт — число книги."),
		isNum(g.price_at_low) ? foot(`Точка на краях оси дисконта: ${rub1(g.price_at_low)} … ${rub1(g.price_at_high)}.`) : null,
		comps.some((c) => c.basis) ? bx("card-foot", detailsBlock(`Основания каналов · ${comps.length}`, comps.map((c) => pa(strong(c.name), `: ${sentence(ruText(c.basis || "—"))}`)))) : null);
}

/* ── экран «Ближайший отчёт» ── */

function screenReport(d) {
	const nr = obj(d.next_report);
	const nf = obj(obj(d.calendar).next_fact);
	return bx("screen",
		screenHead("Ближайший отчёт", nf.title ? `${ruText(nf.title)}: что он даст оценке` : `Что даст отчёт за ${periodLabel(nr.period)}`,
			`Два ритма: ${formOnly(d) ? "формы ЦБ банка за месяц — наблюдение и оценка ЧПМ квартала" : rasForm(d) ? "месячная РСБУ банка — вход нау-каста" : "месячный релиз эмитента и формы ЦБ — наблюдение"}, и квартальная МСФО группы — факт для книги, журнала и обучения вероятностей режимов. `
			+ `Нау-каст к цене не подключён до допуска: экран показывает, что сделает с оценкой факт ${periodLabel(nr.period)}, и копит зачёт против наивных эталонов.`),
		sec(countdownCard(d), nowcastCard(d)), sec(yearDpsCard(d)), sec(impactCard(d)),
		more([retroBenchmarksCard(d), journalCard(d), rasMonthsCard(d), indicatorsCard(d), eventsCard(d, 99, 12)]));
}

function countdownCard(d) {
	const a = obj(obj(d.nowcast).admission);
	const status = { collecting: ["копим события", "warn"], passed: ["допущен", "good"], failed: ["не допущен", "bad"] }[a.status] || [a.status || "—", null];
	const needed = isNum(a.events_needed) ? a.events_needed : 0;
	const mse = Object.entries(obj(a.mse_ratio)).filter(([, v]) => isNum(v));
	return card({ title: "До отчёта", span: 5, sub: "отсчёт — от даты оценки" },
		nextRasLine(d) || empty(formOnly(d) ? "Даты формы ЦБ банка в выпуске нет." : "Даты месячного релиза в выпуске нет."),
		nextFactLine(d) || empty("Даты МСФО открытого квартала в выпуске нет."),
		earlierReport(d),
		bx("admission",
			bx("admission-top", tileLabel("Допуск нау-каста к цене"), needed ? badge(status[0], status[1]) : null),
			needed ? el("div", { class: "progress", role: "img", "aria-label": `${fmt.num(a.events_scored)} из ${fmt.num(needed)} событий` },
				Array.from({ length: needed }, (_, i) => el("i", { class: i < Math.min(a.events_scored || 0, needed) ? "on" : null }))) : null,
			// Выпуск без слоя индикаторов: вместо счёта событий — слова выпуска (`nowcast.absent`).
			mt(8, "p", "ink-2 small", needed ? `Засчитано ${fmt.num(a.events_scored)} из ${fmt.num(needed)}; первое засчитываемое — ${dayOrPeriod(a.first_event)}, решение — не раньше ${dayOrPeriod(a.earliest_decision)}.`
				: phrase(obj(d.nowcast).absent || "в этом выпуске нет блока «допуск нау-каста»")),
			mse.length ? pr("ink-2 small", `Отношение MSE к лучшему эталону: ${mse.map(([k, v]) => `${targetTitle(d, k)} ${num2(v)}`).join(", ")}.`) : null,
			a.rule ? detailsBlock("Правило допуска", phrase(a.rule)) : null));
}

function dayOrPeriod(x) { return parseDay(x) ? fmt.date(x) : periodLabel(x); }

const targetOf = (d, key) => list(obj(d.nowcast).targets).find((x) => x.key === key);
// Базис прибыли квартала — базис её цели в выпуске.
const profitBasis = (d) => basisName(obj(targetOf(d, "ni_q")).basis || "ifrs");
function targetTitle(d, key) {
	const t = targetOf(d, key);
	return t ? t.title : key;
}

function targetValue(d, key, v) {
	const t = targetOf(d, key);
	if (!isNum(v)) return "—";
	return t && t.unit === "bn" ? fmt.bn(v) : pct2(v);
}
function targetError(d, key, v) {
	const t = targetOf(d, key);
	if (!isNum(v)) return "—";
	return t && t.unit === "bn" ? `± ${fmt.bn(v)}` : `± ${num2(v * 100)}${NBSP}п.п.`;
}

let NOWCAST_TARGET = null;

function nowcastCard(d) {
	const nc = obj(d.nowcast);
	const q = obj(nc.quarter);
	const targets = list(nc.targets);
	const by = obj(q.by_target);
	if (!targets.length || !Object.keys(by).length) return none("Нау-каст квартала", "нау-каст", 7);
	if (!NOWCAST_TARGET || !by[NOWCAST_TARGET]) NOWCAST_TARGET = targets.find((t) => by[t.key]).key;
	const body = el("div");
	const draw = () => {
		const key = NOWCAST_TARGET;
		const b = obj(by[key]);
		const months = list(q.months);
		const field = key === "ni_q" ? "ni" : key === "nim_q" ? "nii" : "llp";
		const fieldName = { ni: "прибыль", nii: "ЧПД", llp: "резервы" }[field];
		const bars = columnsChart(months.map((m) => ({ key: m.month, label: periodWord(m.month), value: m[field], faded: m.status !== "known",
			color: m.status === "known" ? MODEL : GREY, tipTitle: periodLabel(m.month),
			tipRows: [["статус", m.status === "known" ? `известен (${m.source === "form102" ? "форма 0409102" : "релиз"})` : "оценка профилем"]] })),
		{ height: 150, valueName: `${fieldName}, млрд ₽`, fmt: fmt.bn, short: (v) => fmt.num(v), label: `${upperFirst(fieldName)} по месяцам квартала, РСБУ банка` });
		const iv = list(b.interval);
		// Эталоны — выпуска и последней записи журнала; на полосе — те, что в пределах оси.
		const names = benchNames(d);
		const entry = list(obj(nc.journal).entries).filter((e) => e.target === key && e.period === q.period).sort((x, y) => String(y.recorded_at).localeCompare(String(x.recorded_at)))[0];
		const bench = list(b.benchmarks).map((x) => [x.name, x.value]).concat(Object.entries(obj(obj(entry).benchmarks)).map(([k, v]) => [names[k], v]));
		const core = [b.forecast, b.expectation, ...iv].filter(isNum);
		const pad = (Math.max(...core) - Math.min(...core)) * 0.1 || Math.abs(Math.max(...core)) * 0.05;
		const shown = bench.filter(([name, v], i) => name && isNum(v) && v !== b.expectation && v >= Math.min(...core) - pad && v <= Math.max(...core) + pad
			&& bench.findIndex((x) => x[0] === name) === i);
		const strip = stripChart([
			{ v: b.forecast, kind: "model", text: `нау-каст ${targetValue(d, key, b.forecast)}` },
			{ v: b.expectation, kind: "neutral", text: `ожидание ${targetValue(d, key, b.expectation)}`, tip: { title: "Ожидание модели", rows: [["значение", targetValue(d, key, b.expectation)]] } },
			...shown.map(([name, v]) => ({ v, kind: "bench", tip: { title: `Эталон: ${name}`, rows: [["значение", targetValue(d, key, v)]] } })),
		], { band: iv, fmt: (v) => (key === "ni_q" ? num1(v) : num2(v * 100)), label: "Нау-каст, ожидание модели и эталоны на одной шкале" });
		fill(body, 
			months.length ? [tileLabel(`${upperFirst(fieldName)} по месяцам, РСБУ банка: ${fmt.num(q.months_known)} из ${fmt.num(months.length)} известны`), bars] : null,
			kpis(10,
				isNum(b.ras_estimate) ? kpi(targetValue(d, key, b.ras_estimate), "оценка квартала по РСБУ") : null,
				isNum(b.bridge) ? kpi(fmt.num(b.bridge, 3), "сезонный мост МСФО / РСБУ") : null,
				kpi(targetValue(d, key, b.expectation), `ожидание модели, слой «${layerTitle(d, "analytical")}» (${basisName(b.basis)})`),
				b.w > 0 ? kpi(num2(b.w), "вес индикаторов w") : null,
				kpi(targetValue(d, key, b.forecast), isNum(b.std_error) ? `нау-каст ${targetError(d, key, b.std_error)}` : "нау-каст: ожидание модели")),
			spaced(10, strip),
			legend([isNum(iv[0]) && isNum(iv[1]) && ["key-b50", "интервал нау-каста"], isNum(b.forecast) && ["key-dot key-model", "нау-каст"], isNum(b.expectation) && ["key-dash", "ожидание модели"],
				shown.length && ["key-dot key-third", "эталоны"]]),
			bx("card-foot", b.equation ? detailsBlock("Уравнение словами", phrase(b.equation)) : null));
	};
	draw();
	return card({ title: `Нау-каст ${periodLabel(q.period)}`, span: 7,
		sub: `${list(q.months).length ? `входы — ${inputUnit(d).many} РСБУ банка; ` : ""}цель — ${modelUnit(d).one} МСФО; ${nc.connected_to_price ? "подключён к цене" : "к цене не подключён"}` },
	bx("pick-row", chooser(targets.filter((t) => by[t.key]).map((t) => ({ value: t.key, label: t.title })), NOWCAST_TARGET, (v) => { NOWCAST_TARGET = v; draw(); }, "Цель нау-каста")),
	body);
}

function yearDpsCard(d) {
	const y = obj(obj(d.nowcast).year);
	if (!isNum(y.ni_year)) return none("Прибыль года → дивиденд", "прибыль года");
	const steps = [];
	let run = 0;
	for (const [title, v] of [[`Факт отчётных ${modelUnit(d).pgen} (${profitBasis(d)})`, y.ni_fact], [`Открытый ${modelUnit(d).one}: смесь заголовка и отклонение нау-каста`, y.ni_quarter],
		[`Смесь заголовка: оставшиеся ${modelUnit(d).many}`, y.ni_rest]]) {
		if (!isNum(v)) continue;
		steps.push({ title, from: run, to: run + v, text: num1(v) });
		run += v;
	}
	steps.push({ title: `${shProfit(d)} ${y.year}`, from: 0, to: y.ni_year, total: true, text: num1(y.ni_year), hint: isNum(y.ni_year_se) ? `± ${num1(y.ni_year_se)}` : "ошибка года не оценена" });
	if (y.at1_coupon_after_tax) steps.push({ title: "Купон AT1 после налога", from: y.ni_year, to: y.base, text: num1(-y.at1_coupon_after_tax) });
	steps.push({ title: "База дивиденда", from: 0, to: y.base, total: true, text: num1(y.base) });
	const cc = obj(y.capital_check);
	const ds = dpsShares(d);
	const W = obj(obj(d.dividends).policy).base_window_quarters;
	return card({ title: `Прибыль ${y.year} → дивиденд на акцию`, sub: `млрд ₽; год — на одном слое (смесь заголовка)${rasForm(d) ? ": нау-каст двигает его только своим отклонением от ожидания" : ""}; дивиденд — `
		+ (annualPayer(d) ? `доля прибыли года на ${num1(ds.mln)} млн ${ds.words}` : `${W ? `сумма решений за кварталы прибыли года, база решения — средняя прибыль ${fmt.num(W)} последних кварталов,` : "формулой политики"} на размещённые акции${both(d)}`) },
		bx("split wide-left",
			waterfall(steps),
			kpis(
				dpsYearKpi(d, y, " по клеткам"),
				kpi(rub2(y.dps), [`DPS${rasForm(d) ? "" : " по политике"}: ${pct0(ds.share(y.payout))} базы на ${num1(ds.mln)} млн ${ds.short}; ${dpsInterval(y, 2)}`, annualModel(d) ? null : dpsExpected(d, y)]),
				kpi(rub2(y.dps_model), "DPS политики на прибыли смеси заголовка (без нау-каста)"),
				...tickers(d).map((t) => kpi(pct1(obj(y.yield)[t]), `доходность${rasForm(d) ? "" : " по политике"} ${toPrice(d, t)}`)),
				cc.requirement ? kpi(`${pct1(cc.n20_expected)} ${cc.ok ? "≥" : "<"} ${pct1(cc.requirement)}`, `проверка капитала: ${capTitle(d, "n20")} после выплаты против требования`) : null)),
		y.note ? foot(phrase(y.note)) : null, basisFoot(d, "profit"));
}

function impactMarks(d, kind, compact = false) {
	const nr = obj(d.next_report);
	const rows = list(kind === "cor" ? nr.cor_table : nr.nim_table).filter((r) => isNum(r[kind]) && isNum(r.median));
	const b = obj(obj(obj(obj(d.nowcast).quarter).by_target)[`${kind}_q`]);
	const iv = list(b.interval).filter(isNum);
	const all = list(nr.benchmarks).filter((x) => isNum(x[kind]));
	const neutral = obj(obj(nr.neutral)[kind]).value;
	const xs = rows.map((r) => r[kind]);
	const lo = Math.min(...xs), hi = Math.max(...xs), span = hi - lo;
	const marks = compact ? [] : [neutral, b.forecast, ...iv, ...all.map((x) => x[kind])].filter(isNum);
	const x0 = Math.max(Math.min(lo, ...marks), lo - span / 2) - span * 0.06;
	const x1 = Math.min(Math.max(hi, ...marks), hi + span / 2) + span * 0.06;
	const on = (v) => isNum(v) && v >= x0 && v <= x1;
	const bench = compact ? [] : all.filter((x) => on(x[kind]));
	return { rows, x0, x1, neutral: on(neutral) ? neutral : null, forecast: !compact && on(b.forecast) ? b.forecast : null,
		iv: !compact && iv.length === 2 && Math.min(x1, iv[1]) > Math.max(x0, iv[0]) ? iv : null,
		bench, guide: bench.some((x) => x.key === "guidance"), other: bench.some((x) => x.key !== "guidance"),
		band: rows.filter((r) => isNum(r.median_low) && isNum(r.median_high)) };
}

function impactChart(d, kind, compact = false) {
	const median = obj(d.fair_value.headline).median;
	const market = d.market.price;
	const { rows, x0, x1, neutral, forecast, iv, bench, guide, other, band } = impactMarks(d, kind, compact);
	return chart((W) => {
		if (rows.length < 2) return svgBox(W, 20);
		const H = compact ? 200 : 300;
		const top = compact ? 16 : 52;
		const m = { l: 50, r: 14, t: top, b: 30 };
		const x = scale(x0, x1, m.l, W - m.r);
		const vals = rows.flatMap((r) => [r.median_low, r.median_high, r.median]).concat([median, market]).filter(isNum);
		const vpad = (Math.max(...vals) - Math.min(...vals)) * 0.08;
		const y = scale(Math.max(0, Math.min(...vals) - vpad), Math.max(...vals) + vpad, H - m.b, m.t);
		const svg = svgBox(W, H, `Медиана в зависимости от факта ${kindName(kind)}`);
		for (const t of ticks(y.d[0], y.d[1], compact ? 3 : 5)) svg.append(line(m.l, y(t), W - m.r, y(t), { class: "gridline" }), text(m.l - 8, y(t) + 4, fmt.num(t), { class: "tick", "text-anchor": "end" }));
		const xMarks = ticks(x0, x1, W < 420 ? 4 : 7);
		const xl = pctTicks(xMarks);
		for (const t of xMarks) { const s = xl(t), w = textWidth(s, 12.5, 400); if (x(t) - w / 2 >= 0 && x(t) + w / 2 <= W) svg.append(text(x(t), H - 8, s, { class: "tick", "text-anchor": "middle" })); }
		svg.append(line(m.l, H - m.b, W - m.r, H - m.b, { class: "axisline" }));
		if (band.length > 1) {
			const up = band.map((r) => `${x(r[kind]).toFixed(1)},${y(r.median_high).toFixed(1)}`);
			const down = band.slice().reverse().map((r) => `${x(r[kind]).toFixed(1)},${y(r.median_low).toFixed(1)}`);
			svg.append(sv("path", { d: `M${up.join(" L")} L${down.join(" L")} Z`, fill: "var(--model-wash-1)" }));
		}
		for (const [v, color, t] of [[median, INK, `сейчас ${fmt.rub(median)}`], [market, MARKET, ""]]) {
			if (!isNum(v)) continue;
			svg.append(line(m.l, y(v), W - m.r, y(v), { stroke: color, [SW]: 1.2 }));
		}
		if (neutral !== null) {
			svg.append(line(x(neutral), m.t - 4, x(neutral), H - m.b, { stroke: INK2, [SW]: 1.2, "stroke-dasharray": "1 3",
				tip: { title: `Нейтральная ${kindName(kind)}`, rows: [["значение", pct2(neutral)]] } }));
		}
		svg.append(sv("path", { d: "M" + rows.map((r) => `${x(r[kind]).toFixed(1)},${y(r.median).toFixed(1)}`).join(" L"), fill: "none", stroke: MODEL, [SW]: 2.2, "stroke-linejoin": "round" }));
		for (const r of rows) {
			svg.append(sv("circle", { cx: x(r[kind]), cy: y(r.median), r: compact ? 3.5 : 4.5, fill: MODEL, ...RING,
				tip: { title: `${kindName(kind)} квартала ${pct1(r[kind])}`, rows: [["медиана", rub1(r.median)], ["ось ставок", `${fmt.num(r.median_low)}–${fmt.num(r.median_high)}${THIN}₽`],
					["точка", rub1(r.point)], ...Object.entries(obj(r.posterior)).map(([k, v]) => [regimeName(d, k), pct1(v)])] } }));
		}
		// Подпись горизонтали встаёт туда, где нет точек кривой.
		const put = (v, s, right, under) => {
			if (!isNum(v)) return;
			const w = textWidth(s, 12.5, 520);
			const spots = [[right, under], [right, !under], [!right, under], [!right, !under]].map(([r, below]) => [r ? W - m.r - w - 2 : m.l + 4, below ? Math.min(H - m.b - 4, y(v) + 15) : y(v) - 6]);
			const [sx, sy] = spots.find(([px, py]) => !rows.some((r) => x(r[kind]) > px - 7 && x(r[kind]) < px + w + 7 && y(r.median) > py - 18 && y(r.median) < py + 9)) || spots[0];
			svg.append(label(sx, sy, s));
		};
		put(median, `сейчас ${fmt.rub(median)}`, false, false);
		put(market, `${solo(d) ? "рынок" : ticker(d)} ${fmt.rub(market)}`, true, true);
		if (!compact) {
			const by = m.t - 26;
			if (iv) {
				const lo = Math.max(x0, iv[0]), hi = Math.min(x1, iv[1]);
				svg.append(sv("rect", { x: x(lo), y: by - 5, width: Math.max(2, x(hi) - x(lo)), height: 10, rx: 5, fill: "var(--model-wash-3)",
					tip: { title: "Нау-каст квартала", rows: [["от", pct2(iv[0])], ["до", pct2(iv[1])]] } }));
			}
			// Точка прогноза рисуется и без интервала.
			if (forecast !== null) svg.append(sv("circle", { cx: x(forecast), cy: by, r: 5, fill: MODEL, ...RING,
				tip: { title: "Нау-каст квартала", rows: [["значение", pct2(forecast)]] } }));
			for (const bm of bench) {
				svg.append(sv("circle", { cx: x(bm[kind]), cy: by, r: 4.5, fill: bm.key === "guidance" ? MARKET : THIRD, ...RING,
					tip: { title: bm.name, rows: [["значение", pct2(bm[kind])]], note: bm.note ? ruText(bm.note) : null } }));
			}
			const names = [forecast !== null && `нау-каст ${pct2(forecast)}`, other && "эталоны", guide && "гайденс"].filter(Boolean);
			if (names.length) svg.append(label(m.l, by - 12, names.join(" · ")));
		}
		return svg;
	}, `Что даст отчёт: ${kindName(kind)} квартала и медиана`);
}

let IMPACT_KIND = "cor";

function impactCard(d) {
	const nr = obj(d.next_report);
	if (!list(nr.cor_table).length && !list(nr.nim_table).length) {
		return card({ title: "Что даст отчёт" }, nr.status === "not_computed" ? empty(sentence(`Таблицы не считались: ${ruText(nr.reason || "быстрая сборка")}`)) : missing("что даст отчёт"));
	}
	const w = diagWords(nr.target);
	const body = el("div");
	const slot = el("span");
	const draw = () => {
		const kind = IMPACT_KIND;
		const rows = list(kind === "cor" ? nr.cor_table : nr.nim_table);
		const f = withTable(impactChart(d, kind, false), () => dataTable([
			Tc(`${kindName(kind)} квартала, упр.`, (r) => pct1(r[kind]), "name"),
			...regimeOrder(d).map((k) => (Nc(regimeName(d, k), (r) => pct1(obj(r.posterior)[k])))),
			Nc(`${upperFirst(w.subj)}, ₽`, (r) => strong(num1(r.median))),
			Nc("Ось ставок, ₽", (r) => `${fmt.num(r.median_low)}–${fmt.num(r.median_high)}`),
			Nc("Сдвиг, ₽", (r) => fmt.signed(r.d_median, 1)),
		], rows));
		slot.replaceChildren(f.button);
		const exp = obj(nr.expectation);
		const mine = (r) => (kind === "cor" ? r.cor_mgmt : r.nim_mgmt);
		const by = list(exp.by_regime).map(mine).filter(isNum);
		// Обучение (М§12–§13): равные ожидания режимов факт не различает.
		const learn = by.length < 2 ? "" : Math.max(...by) - Math.min(...by) < 5e-6
			? ` Ожидания ${kindName(kind)} у режимов равны: такой факт вероятностей режимов не меняет, оценку двигает только сам квартал.`
			: " Ожидание — среднее по режимам: равный ему факт тоже перевзвешивает режимы, поэтому нейтральное значение от него отличается.";
		const M = impactMarks(d, kind);
		fill(body,
			legend([["key-line key-model", w.subj], M.band.length > 1 && ["key-b80", "ось ставок"], ["key-line key-ink", `${w.subj} сейчас`], ["key-line key-market", `рынок${tk(d, ticker(d), ", ")}`],
				M.neutral !== null && ["key-dash", "нейтральное значение"], M.iv && ["key-b50", "интервал нау-каста"], M.forecast !== null && ["key-dot key-model", "нау-каст"],
				M.other && ["key-dot key-third", "эталоны"], M.guide && ["key-dot key-market", "гайденс"]]),
			f.box,
			foot(neutralSentence(d, kind),
				` Ожидание модели на ${periodLabel(nr.period)}: CoR ${pct2(exp.cor_mgmt)}, ЧПМ ${pct2(exp.nim_mgmt)} (упр.); по режимам — `
				+ list(exp.by_regime).map((r) => `${lowerFirst(regimeName(d, r.regime))} ${pct2(mine(r))}`).join(", ") + "." + learn));
	};
	draw();
	return card({ title: `Что даст отчёт: факт ${periodLabel(nr.period)} → оценка`,
		sub: `Факт CoR или ЧПМ квартала сдвигает вероятности режимов по правилу книги, а с ними — ${w.acc}. Строка отвечает «что даст это число отчёта»: второй показатель в ней считается ненаблюдавшимся. Базис значений — упр.; мост в движок применяет сборка.`,
		tools: el("div", { class: "pick-row", style: "margin:0" }, chooser([{ value: "cor", label: "CoR" }, { value: "nim", label: "ЧПМ" }], IMPACT_KIND, (v) => { IMPACT_KIND = v; draw(); }, "Показатель отчёта"), slot) },
	body);
}

function benchNames(d) {
	const out = { ...obj(obj(obj(d.nowcast).retro).titles) };
	for (const b of list(obj(d.next_report).benchmarks)) out[b.key] = out[b.key] || b.name;
	for (const t of Object.values(obj(obj(obj(d.nowcast).quarter).by_target))) for (const b of list(obj(t).benchmarks)) out[b.key] = out[b.key] || b.name;
	return out;
}

let RETRO_HORIZON = null;

function retroBenchmarksCard(d) {
	const base = obj(obj(d.nowcast).retro);
	const byH = obj(base.by_horizon);
	const horizons = Object.keys(byH).filter((h) => list(obj(byH[h]).periods).length);
	if (!list(base.periods).length && !horizons.length) return null;      // блока ретро-проверки нет — карточки нет, без заглушки
	if (!RETRO_HORIZON || !byH[RETRO_HORIZON]) RETRO_HORIZON = byH[base.horizon] ? base.horizon : horizons[0] || null;
	const names = benchNames(d);
	const body = el("div");
	const pick = horizons.length > 1 ? bx("pick-row", chooser(horizons.map((h) => ({ value: h, label: h })), RETRO_HORIZON, (v) => { RETRO_HORIZON = v; draw(); }, "Горизонт")) : null;
	const draw = () => {
		const r = { ...base, ...obj(byH[RETRO_HORIZON]) };
		const periods = list(r.periods);
		const name = (k) => names[k] || k;
		const keys = Object.keys(obj(r.rmse));
		const main = periods.some((p) => isNum(obj(p.benchmarks)[r.main]));
		const plot = linesChart([
			{ name: "факт", color: INK, dots: true, r: 3.5, points: periods.map((p) => [p.period, p.actual]) },
			{ name: `эталон: ${name(r.main)}`, color: THIRD, line: false, dots: true, r: 4, points: periods.map((p) => [p.period, obj(p.benchmarks)[r.main]]) },
		], { xType: "band", categories: periods.map((p) => p.period), height: 220, tipFmt: fmt.bn, xFmt: periodShort, label: "Прибыль квартала: факт и главный эталон" });
		fill(body,
			legend([["key-line key-ink", "факт"], main && ["key-dot key-third", `главный эталон: ${name(r.main)}`]]), plot,
			main ? null : smallNote(`У главного эталона (${name(r.main)}) истории ещё нет: зачёт начнётся с первого события.`),
			spaced(12, dataTable([
				Tc("Эталон", (k) => sx(upperFirst(name(k)), k === r.main ? hint("главный — по нему зачёт") : null), "name"),
				Nc("RMSE", (k) => pct1(obj(r.rmse)[k])),
				Nc("Смещение", (k) => fmt.signedBn(obj(r.bias)[k], 1)),
				Nc(`${upperFirst(modelUnit(d).pgen)}`, (k) => fmt.num(obj(r.n)[k])),
			], keys, { cls: "compact", rowClass: (k) => (k === r.main ? "is-pick" : null) })));
	};
	draw();
	return card({ title: "Эталоны на истории: планка для нау-каста", span: 6,
		sub: `прибыль квартала (${profitBasis(d)}); RMSE — доля факта, смещение (эталон − факт) — млрд ₽; горизонт — дней до отчёта${horizons.length > 1 ? "" : `: ${base.horizon || "—"}`}` },
	pick, body, basisFoot(d, "profit"));
}

// Месяцы релиза РСБУ общей формы.
function rasMonthsCard(d) {
	const m = obj(obj(d.nowcast).months);
	const rows = list(m.rows);
	if (!rows.length) return null;
	return card({ title: `${upperFirst(inputUnit(d).many)} РСБУ банка`, sub: `базис — ${basisName(m.basis)}; млрд ₽ и доли; последний — ${periodLabel(rows[rows.length - 1].month)}` },
		sparkline({ title: "прибыль месяца", history: { date: rows.map((r) => r.month), value: rows.map((r) => r.ni) } }, fmt.bn, `за ${fmt.num(rows.length)} мес.`),
		spaced(10, dataTable([
			Tc("Месяц", (r) => periodLabel(r.month), "name nowrap"),
			Nc("ЧП", numOf("ni", 1)),
			Nc("С начала года", numOf("ni_ytd", 1)),
			Nc("ЧПД", numOf("nii", 1)),
			Nc("Комиссии", numOf("fees", 1)),
			Nc("Резервы", numOf("llp", 1)),
			Nc("Расходы", numOf("opex", 1)),
			Nc("CoR", pctOf("cor", 2)),
			Nc("ROE", pctOf("roe", 1)),
			Nc("Кредиты ЮЛ", numOf("loans_corporate", 0)),
			Nc("Кредиты ФЛ", numOf("loans_retail", 0)),
			Nc("Средства ФЛ", numOf("funds_retail", 0)),
			Nc("Средства ЮЛ", numOf("funds_corporate", 0)),
			Nc(capTitle(d, "n1_0"), pctOf("n1_0", 1)),
			Nc(capTitle(d, "n11_observed"), pctOf("n1_1", 1)),
		], rows.slice().reverse(), COMPACT)),
		form102List(d));
}

function form102List(d) {
	const rows = list(obj(d.nowcast).form102);
	return rows.length ? spaced(12, tileLabel("Сверка прибыли релиза с формой 0409102"),
		el("ul", { class: "list" }, rows.map((x) => lx(sp("t", periodLabel(x.month),
			sp("muted", isNum(x.ni) ? `форма ${fmt.bn(x.ni)} · релиз ${fmt.bn(x.release_ni)}` : "форма ещё не раскрыта")),
		sp("v", x.ok === true ? badge("совпало", "good") : x.ok === false ? badge(`расхождение ${fmt.bn(x.diff)}`, "bad") : badge("ждём форму", "out")))))) : null;
}

function indicatorValue(item, v = item.value) {
	if (!isNum(v)) return "—";
	switch (item.unit) {
		case "share": case "pct": return pct2(v);
		case "bn": return fmt.bn(v, Math.abs(v) >= 1000 ? 0 : 1);
		case "price": case "rub": return rub2(v);
		case "level": case "count": return fmt.num(v);
		case "pp": case "bp": case "years": return formatByUnit(v, item.unit);
		default: return fmt.num(v, Math.abs(v) < 1000 ? Math.min(2, exactDigits(v, 2)) : 0);
	}
}

function indicatorsCard(d) {
	const ind = obj(d.indicators);
	const tiles = list(ind.tiles);
	if (!tiles.length) return none("Опережающие индикаторы", "индикаторы");
	const groups = list(ind.groups);
	const main = [];
	for (const g of groups) main.push(...tiles.filter((t) => t.group === g.id && t.status !== "missing").slice(0, 2));
	const top = main.slice(0, 8);
	const tile = (i) => bx("ind-tile",
		tileLabel(i.title),
		sp("ind-value", i.status === "missing" ? "—" : indicatorValue(i)),
		sp("muted small", i.status === "missing" ? phrase(i.reason || "ряда нет") : `${dayOrPeriod(i.date)} · ${basisName(i.basis)}${i.status === "stale" ? " · устарел" : ""}`),
		i.note ? sp("muted small", phrase(i.note)) : null,
		i.status === "missing" ? null : sparkline(i, (v) => indicatorValue(i, v)));
	return card({ title: "Опережающие индикаторы", sub: `${fmt.num(tiles.length)} ${plural(tiles.length, ["ряд", "ряда", "рядов"])}; у плиток — линия и мин–макс за год; ряд без данных — с причиной` },
		bx("ind-tiles", top.map(tile)),
		mt(16, "div", "stack", groups.map((g) => {
			const rows = tiles.filter((t) => t.group === g.id);
			return rows.length ? detailsBlock(`${g.title} · ${rows.length}`, dataTable([
				Tc("Ряд", (i) => i.title, "name"),
				Nc("Значение", (i) => indicatorValue(i)),
				Nc("Изменение", (i) => (isNum(i.change) ? (["share", "pct"].includes(i.unit) ? fmt.pp(i.change) : fmt.signed(i.change, 1)) : "—")),
				Nc("Дата", (i) => dayOrPeriod(i.date)),
				Tc("Источник", (i) => srcText(i.source), "txt"),
			], rows, { cls: "compact", detail: (i) => (i.status === "missing" && i.reason ? ruText(i.reason) : null) })) : null;
		})));
}

function journalCard(d) {
	const j = obj(obj(d.nowcast).journal);
	const rows = list(j.entries);
	const names = benchNames(d);
	return card({ title: "Журнал прогнозов", span: 6, sub: `неизменяемые записи 4 последних событий МСФО; всего записей — ${fmt.num(j.total_entries || 0)}` },
		rows.length ? dataTable([
			Tc("Цель", (r) => sx(targetTitle(d, r.target), hint(`${periodLabel(r.period)} · ${r.horizon}`)), "name"),
			Nc("Прогноз", (r) => strong(targetValue(d, r.target, r.forecast))),
			Nc("Факт", (r) => targetValue(d, r.target, r.actual)),
			Nc("Записан", (r) => fmt.date(mskDay(r.recorded_at))),
		], rows, { detail: (r) => (Object.keys(obj(r.benchmarks)).length ? sp("muted",
			"Эталоны: " + Object.entries(r.benchmarks).map(([k, v]) => `${lowerFirst(names[k] || k)} ${targetValue(d, r.target, v)}`).join("; ")) : null) }) : empty("Журнал пуст: первая запись — перед первым событием МСФО после начала журнала."),
		j.rule ? foot(phrase(j.rule)) : null);
}

/* ── экран «Капитал и дивиденды» ── */

let CAP_PICK = "mix";

function screenCapital(d) {
	const S = obj(obj(d.capital).scenarios);
	const keys = scenarioOrder(d).filter((k) => S[k]);
	if (CAP_PICK !== "mix" && !S[CAP_PICK]) CAP_PICK = "mix";
	const path = el("div", { class: "grid" });
	const drawPath = () => fill(path, ratioPathCard(d, CAP_PICK), growthCard(d, CAP_PICK));
	drawPath();
	return bx("screen",
		screenHead("Капитал и дивиденды", `${capTitle(d, "n20")}, требования и дивиденд`,
			"Нормативы на отчётную дату и их путь против требования и регуляторного пола по сценариям капитала; мост от капитала к цене; дивидендная политика, "
			+ "следующая выплата и дивиденды по годам. Переключатель сценария управляет картами пути; остальные карточки — смесь заголовка."),
		sec(capitalKpis(d)),
		bx("section", bx("pick-row", sp("muted", "Путь нормативов:"),
			chooser([{ value: "mix", label: "Ожидание" }, ...keys.map((k) => ({ value: k, label: scenarioName(d, k), hint: pct0(S[k].mass) }))], CAP_PICK,
				(v) => { CAP_PICK = v; drawPath(); }, "Сценарий капитала")), path),
		sec(rulePriceCard(d)), sec(bridgeCard(d), ratioBridgeCard(d)), section("Дивиденды", dividendsCard(d), dividendCard(d)),
		sec(buybackCard(d), tokenCard(d)),
		sec(quarterlyDpsCard(d)), sec(dividendHistoryCard(d)), sec(sharesCard(d)), sec(annualCard(d)));
}

function capitalKpis(d) {
	const C = obj(d.capital);
	const a = obj(C.anchor);
	const o = obj(C.observed);
	const req = reqWords(d);
	if (!isNum(a.n20)) return none("Капитал на отчётную дату", "капитал");
	return card({ title: `Капитал на ${fmt.date(a.as_of)}${a.estimated ? " — оценка до выхода формы" : ""}`, sub: `база — ${basisName(a.basis)}; ${ruText(a.src || "")}` },
		kpis(
			kpi(pct2(a.n20), `${capTitle(d, "n20")}${a.n20_pre_dividend ? " до вычета объявленного дивиденда" : ""}`),
			kpi(pct2(a.n20_post_dividend), "после вычета объявленного дивиденда"),
			kpi(pct2(a.req20_now), req.name),
			kpi(fmt.pp(a.n20_headroom), `запас до ${req.to}`),
			req.glide ? [kpi(pct2(a.req20_glide_next), `требование с глиссадой к концу ${periodLabel(a.req20_glide_period)}: с ним сравнивает норматив правило роста`),
				kpi(fmt.pp(a.n20_headroom_glide), `запас до ${req.glide}`)] : null,
			isNum(req.floor) ? kpi(pct2(req.floor), "регуляторный пол года (ожидание по сценариям)") : null,
			kpi(pct2(obj(a.n11_bank).value), `${capTitle(d, "n11")} на ${fmt.date(obj(a.n11_bank).as_of)}${isNum(a.req11_now) ? `; требование ${pct2(a.req11_now)}` : ""}${isNum(a.n11_headroom) ? `, запас ${fmt.pp(a.n11_headroom)}` : ""}`),
			kpi(bn0(a.rwa), "RWA"),
			kpi(bn0(a.bv_common), "капитал акционеров"),
			kpi(rub2(obj(obj(d.market).multiples).bv_per_share), `капитал на акцию на дату оценки — на ${divisor(d)}`),
			kpi(`${fmt.num(a.ded20)} / ${fmt.num(a.ded11)}`, "вычеты из капитала в нормативы, млрд ₽"),
			a.at1 ? kpi(`${fmt.num(a.at1)} / ${fmt.num(a.t2)}`, panelForm(d) ? "инструменты добавочного / дополнительного капитала, млрд ₽" : "AT1 / T2, млрд ₽") : kpi(bn0(a.t2), "регуляторные инструменты капитала")),
		isNum(o.n1_1) && !(o.as_of === obj(a.n11_bank).as_of && o.n1_1 === obj(a.n11_bank).value && !isNum(o.n1_0) && !isNum(o.n1_2)) ? mt(14, "p", "note-box",
			strong(`${capTitle(d, "n11_observed")} на ${fmt.date(o.as_of)}: ${pct2(o.n1_1)}`
				// слот второго норматива несёт тот же норматив, что Н1.2 (подписи книги совпадают началом) — второй раз не печатается
				+ `${isNum(o.n1_0) ? `; ${capTitle(d, "n1_0")} — ${pct2(o.n1_0)}${capTitle(d, "n11_observed").startsWith(capTitle(d, "n1_2")) && o.n1_2 === o.n1_1 ? "" : `, ${capTitle(d, "n1_2")} — ${pct2(o.n1_2)}`}` : ""}. `),
			`Последнее наблюдение (${ruText(o.source || "")}); в оценку не входит.`) : null);
}

function ratioPathCard(d, pick) {
	const C = obj(d.capital);
	const years = list(C.years);
	const mix = pick === "mix";
	const src = mix ? obj(C.mix) : obj(obj(C.by_scenario)[pick]);
	const sc = mix ? obj(C.mix) : obj(obj(C.scenarios)[pick]);
	if (!years.length || !list(src.n20).length) return none("Путь нормативов", "путь нормативов");
	const R = obj(C.requirement), Rm = obj(R.mix), Rq = mix ? Rm : obj(obj(R.by_scenario)[pick]);
	// С требованием сравнивается строка, названная выпуском (`compare`): у второго норматива — с прибылью периода; отчётный — справочно.
	// Годовой путь смеси — против требования с глиссадой (`years_mix`); требование года — тонкой линией.
	const star = obj(R.compare).n11 === "n11_star", ym = obj(mix && R.years_mix), stars = list(star && ym.n11_star), g20 = list(ym.req20_glide), notes = obj(R.notes);
	const periods = list(R.periods);
	const at = (arr) => years.map((y, i) => [y, list(arr)[i]]);
	const quarters = periods.length ? [] : list(obj(d.paths).quarters);
	const n20 = capTitle(d, "n20"), n11 = capTitle(d, "n11");
	const series = [
		{ name: n20, key: "key-line key-model", color: MODEL, width: 2.2, dots: true, r: 3.5, points: at(src.n20),
			area: list(src.n20_p10).length ? years.map((y, i) => [y, src.n20_p10[i], src.n20_p90[i]]) : null },
		stars.length ? { name: `${n11} с прибылью периода`, key: "key-line key-third", color: THIRD, ...DOT, points: at(stars) } : null,
		stars.length ? { name: `${n11} отчётный — справочно`, key: "key-line key-third2", color: THIRD, dashed: true, points: at(src.n11) }
			: { name: n11, key: "key-line key-third", color: THIRD, ...DOT, points: at(src.n11) },
		g20.length ? { name: `требование ${n20} с глиссадой`, key: "key-line key-ink", color: INK, width: 1.5, points: at(g20) } : null,
		g20.length ? { name: "требование года, без глиссады", key: "key-dash", color: INK2, width: 1.2, dash: "1 3", points: at(sc.req20) }
			: { name: `требование ${n20}`, key: "key-line key-ink", color: INK, width: 1.5, points: at(sc.req20) },
		{ name: `пол ${n20}`, color: NEG, width: 1.5, dashed: true, points: at(sc.floor20), key: "key-line key-neg2" },
		{ name: `пол ${n11}`, color: NEG, width: 1.5, dash: "1 4", points: at(sc.floor11), key: "key-line key-neg3" },
	].filter(Boolean);
	if (mix && quarters.length) {
		series.push({ name: `${n20}, кварталы`, color: MODEL, line: false, dots: true, hollow: true, r: 3.5,
			points: quarters.map((q) => [quarterX(q.period), q.n20]).filter((p) => isNum(p[0])) });
	}
	const xmin = Math.min(years[0], ...quarters.map((q) => quarterX(q.period)).filter(isNum));
	const live = (rows) => rows.filter((s) => s.points.some((p) => isNum(p[1])));
	const keysOf = (rows) => rows.filter((s) => s.key).map((s) => [s.key, s.name]);
	const drawn = live(series);
	const policy = C.policy_threshold > 0;
	const plot = linesChart(drawn, { height: 280, xMin: xmin, xMax: years[years.length - 1], xTicks: years,
		xFmt: yy, yPct: true, tipFmt: pct2,
		hrefs: policy ? [{ value: C.policy_threshold, text: `порог политики ${pct1(C.policy_threshold)}`, color: MARKET, dash: "5 4", below: true }] : [],
		label: "Путь нормативов против требования и пола" });
	const fig = withTable(plot, () => dataTable([
		Tc("Год", (r) => String(r[0]), "name"),
		Nc(n20, (r) => pct2(list(src.n20)[r[1]])),
		list(src.n20_p10).length ? Nc("P10–P90", (r) => `${num1(src.n20_p10[r[1]] * 100)}–${pct1(src.n20_p90[r[1]])}`) : null,
		g20.length ? Nc("Требование с глиссадой", (r) => pct2(g20[r[1]])) : null,
		Nc(g20.length ? "Требование года" : "Требование", (r) => pct2(list(sc.req20)[r[1]])),
		Nc("Пол", (r) => pct2(list(sc.floor20)[r[1]])),
		stars.length ? Nc(`${n11} с прибылью периода`, (r) => pct2(stars[r[1]])) : null,
		stars.length ? Nc(`Требование ${n11} с глиссадой`, (r) => pct2(list(ym.req11_glide)[r[1]])) : null,
		Nc(star ? `${n11} отчётный — справочно` : n11, (r) => pct2(list(src.n11)[r[1]])),
	], years.map((y, i) => [y, i])));
	const byQ = (arr) => periods.map((p, i) => [p, list(arr)[i]]);
	const glide = live([
		{ name: n20, key: "key-line key-model", color: MODEL, width: 2.2, points: byQ(Rm.n20) },
		{ name: star ? `${n11} с прибылью периода` : n11, key: "key-line key-third", color: THIRD, points: byQ(star ? Rm.n11_star : Rm.n11) },
		{ name: star ? `${n11} отчётный — справочно` : `${n11} с прибылью периода`, key: "key-line key-third2", color: THIRD, dashed: true, points: byQ(star ? Rm.n11 : Rm.n11_star) },
		{ name: "требование с глиссадой", key: "key-line key-ink", color: INK, width: 1.5, step: true, points: byQ(Rq.req20_glide) },
		{ name: "требование с глиссадой", color: INK, width: 1.5, step: true, points: byQ(Rq.req11_glide) },
		{ name: "требование без глиссады", key: "key-dash", color: INK2, width: 1.2, dash: "1 3", step: true, points: byQ(Rq.req20) },
	]);
	const gap = obj(C.capital_gap);
	return card({ title: `Путь нормативов: ${mix ? "ожидание смеси заголовка" : scenarioName(d, pick)}`, tools: fig.button,
		sub: `норматив на конец года после дивидендов; полоса — P10–P90 клеток сценария под весами «${layerTitle(d, "analytical")}»${quarters.length ? "; полые точки — первые кварталы смеси" : ""}` },
	legend([...keysOf(drawn), policy && ["key-line key-market2", "порог дивидендной политики"]]),
	fig.box,
	glide.length ? spaced(16,
		tileLabel(`По кварталам: требование — минимум сценария с надбавками и запас менеджмента; ступени минимума набираются заранее, по ${num2(R.glide_pp_per_quarter * 100)}${NBSP}п.п. `
			+ `за квартал за ${fmt.num(R.lookahead_quarters)}${NBSP}кв. до ступени. Рост ограничивает норматив с прибылью периода.`),
		legend(keysOf(glide)),
		linesChart(glide, { xType: "band", categories: periods, height: 240, yPct: true, tipFmt: pct2, xFmt: periodShort, label: "Нормативы против требования с глиссадой по кварталам" }),
		notes.n11 ? smallNote(sentence(`${n11}: ${ruText(notes.n11_star)}; ${ruText(notes.n11)}`)) : null) : null,
	foot(`Капитальный разрыв: масса ${pct1(gap.mass)} (${fmt.num(gap.cells)} ${plural(gap.cells || 0, CELL_WORDS)}`
		+ (list(gap.cell_list).length ? `: ${list(gap.cell_list).map((c) => cellName(d, c)).join("; ")}` : "") + ")"
		+ (gap.first_period ? `, первый квартал — ${periodLabel(gap.first_period)}` : "") + ". ", gateNote(d, "capital_gap"), gateNote(d, "step_dividend")));
}

function growthCard(d, pick) {
	const G = obj(obj(d.capital).growth);
	const years = list(G.years);
	if (!years.length) return null;
	const sc = pick === "mix" ? G : { ...G, ...obj(obj(G.by_scenario)[pick]) };
	const at = (k, i) => list(sc[k])[i];
	// Плитки — экстремумы рядов смеси, а не год якоря.
	const worst = (k, sign) => { let b = -1; list(G[k]).forEach((v, i) => { if (isNum(v) && (b < 0 || sign * v > sign * G[k][b])) b = i; }); return b; };
	const iP = worst("p_cut", 1), iL = worst("lam_min", -1), n = years.length - 1, tail = pick === "mix" ? "" : " (смесь заголовка)";
	const q = obj(G.quarters);
	return card({ title: `Рост, на который хватает капитала: ${pick === "mix" ? "ожидание смеси заголовка" : scenarioName(d, pick)}`,
		sub: `${upperFirst(codeText(G.order))}. Потенциальный рост кредитных книг — сектор мира и премия; фактический — что остаётся после требования к капиталу; над парой — доля урезанного на конец года, %.` },
	legend([["key-neutral", "потенциальный рост"], ["key-model", "фактический"]]),
	columnsChart(years.map((y, i) => ({ key: y, label: yy(y), value: at("actual", i), pair: at("potential", i), cut: at("cut_share", i), tipTitle: `${y}: фактический рост`,
		tipRows: [["потенциальный", pct1(at("potential", i))], ["урезано на конец года", pct1(at("cut_share", i))], ["навёрстано", fmt.bn(at("catch_up", i))]] })),
	{ height: 220, valueName: "за год", fmt: pct1, short: (v, it, w) => (it.cut > 0 ? MINUS + (textWidth(pct1(it.cut), 12.5, 520) < w - 10 ? pct1(it.cut) : fmt.num(it.cut * 100)) : ""), pairColor: GREY, label: "Потенциальный и фактический рост кредитных книг по годам" }),
	kpis(12,
		iP < 0 ? null : kpi(pct0(G.p_cut[iP]), `наибольшая вероятность урезания роста — в ${years[iP]} году${tail}`),
		iL < 0 ? null : kpi(pct0(G.lam_min[iL]), `наименьшая доля прироста за квартал — в ${years[iL]} году${tail}`),
		kpi(pct1(at("cut_share", n)), `урезано на конец ${years[n]}${NBSP}г.`),
		G.catch_up_rate > 0 ? kpi(fmt.bn(Math.max(0, ...list(G.catch_up).filter(isNum))), "навёрстано за год, наибольшее") : null),
	list(q.periods).length ? spaced(12, tileLabel("Доля прироста по кварталам (смесь заголовка): 100 % — рост не урезан"),
		linesChart([{ name: "доля прироста", color: MODEL, ...DOT, points: q.periods.map((p, i) => [p, list(q.lam)[i]]) }],
			{ xType: "band", categories: q.periods, height: 150, yMin: 0, yMax: 1, yPct: true, tipFmt: pct1, xFmt: periodShort, label: "Доля прироста кредитных книг по кварталам" })) : null,
	gateNote(d, "growth_cut"), gateNote(d, "volume_sign"));
}

// Строка цены сухим перевыводом: подписи строки — пометки и причина «без цены» (книга с записью развилок, М§14.5).
const rowNotes = (r) => [r.note, r.why, r.mark, r.median_mark].filter(Boolean).map((t) => hint(ruText(t)));
const dCols = (point) => [Nc(point, (r) => (isNum(r.d_point) ? strong(fmt.signedRub(r.d_point, 1)) : "без цены")), Nc("К медиане книги", (r) => (isNum(r.d_median) ? fmt.signedRub(r.d_median, 1) : "—"))];

function rulePriceCard(d) {
	const rows = list(obj(obj(d.capital).rule_price).rows);
	if (!rows.length) return null;
	const dry = rows.some((r) => "d_point" in r);
	return card({ title: "Цена правила", id: "rule-price", sub: "Оценка при трёх замыканиях капитала: что уступает первым, когда капитала не хватает." },
		dataTable([
			Tc("Замыкание", (r) => sx(ruText(r.title), r.current ? sp("cell-badge", badge("в книге", "model")) : null, ...rowNotes(r)), "name"),
			Nc("Точка", (r) => rub1(r.point)),
			...(dry ? dCols("К точке книги") : [Nc("Медиана", (r) => strong(rub1(r.median)))]),
			Nc("Капитальный разрыв", pctOf("capital_gap_mass", 1)),
		], rows, { cls: "compact", rowClass: (r) => (r.current ? "is-pick" : null) }),
		foot(dry ? `Другие замыкания — книга, перевыведенная под замыкание (корни, концы осей и проверки заново); разности медиан — малая полоса на общих случайных числах. В выпуске не пересчитывается.`
			: "Оценка при других правилах — из таблиц книги; в выпуске не пересчитывается."));
}

function bridgeCard(d) {
	const mix = obj(obj(d.layers).headline_mix);
	const rows = list(mix.waterfall);
	if (!rows.length) return none("Мост капитала", "мост капитала", 7);
	const steps = [];
	let run = 0;
	for (const r of rows) {
		if (r.total || r.key === "bv_v") { steps.push({ title: r.title, from: 0, to: r.amount, total: true, text: `${fmt.num(r.amount)} · ${rub1(r.per_share)}` }); run = r.amount; continue; }
		steps.push({ title: r.title, from: run, to: run + r.amount, text: `${fmt.signed(r.amount, 0)} · ${fmt.signedRub(r.per_share, 1)}` });
		run += r.amount;
	}
	const br = list(obj(d.fair_value.bridge).rows);
	return card({ title: "Мост капитала: от капитала к цене", span: 7,
		sub: `млрд ₽ · ₽ на акцию${basisLabel(d, "divisor") ? ` (${basisLabel(d, "divisor")})` : ""}; смесь заголовка при λ = ${num2(mix.lambda)}; цена ${rub2(mix.price)} = точка` },
		waterfall(steps, true),
		br.length ? spaced(14, dataTable([
			Tc("Дивиденд реестра", (r) => `${divLabel(r)}: ${rub2(r.dps)}`, "name"),
			Nc("Сумма, млрд ₽", numOf("amount", 1)),
			Nc("Вычет из капитала", dateOf("deducted_on")),
			Nc("Последний день покупки", dateOf("last_buy_date")),
			Nc("Экс-дата", dateOf("ex_date")),
			Nc("В мосте", (r) => (r.sign > 0 ? "+" : r.sign < 0 ? MINUS : "0")),
		], br, COMPACT)) : null,
		foot(amountBasis(d, d.fair_value.bridge), "Мост не несёт дисконта за управление: объявленная сумма — обязательство, а не будущая стоимость."));
}

function ratioBridgeCard(d) {
	const b = obj(obj(d.capital).bridge);
	const rows = list(b.rows);
	if (!rows.length) return none("Мост норматива", "мост норматива", 5);
	const steps = [{ title: `${periodLabel(b.from)}`, from: 0, to: b.start, total: true, text: pct2(b.start) }];
	let run = b.start;
	for (const r of rows) {
		steps.push({ title: r.title, from: run, to: run + r.pp, text: fmt.pp(r.pp), hint: isNum(r.amount) ? fmt.signedBn(r.amount, 0) : null });
		run += r.pp;
	}
	steps.push({ title: periodLabel(b.to), from: 0, to: b.end, total: true, text: pct2(b.end) });
	return card({ title: `Мост ${capTitle(d, "n20")}`, span: 5, sub: "расчёт модели на смеси заголовка, включая уровень на дату якоря; п.п. норматива, в подписи — млрд ₽ капитала или RWA" }, waterfall(steps));
}

function dividendsCard(d) {
	const dv = obj(d.dividends);
	const pol = obj(dv.policy);
	const ladder = list(dv.ladder);
	const check = list(dv.formula_check);
	const cap = list(dv.cap_check);
	const W = pol.base_window_quarters;
	if (!ladder.length && !pol.name) return none("Дивидендная политика", "дивидендная политика", 6);
	return card({ title: "Дивидендная политика", span: 6,
		sub: `${ruText(pol.name || "")}; ${!pol.valid_until ? ruText(pol.valid_until_note || "срок действия в документе не задан")
			: flag(d, "policy_expired") ? `срок истёк ${fmt.date(pol.valid_until)}: до новой политики действует прежняя` : `действует по ${fmt.date(pol.valid_until)}`}` },
		pol.text ? pr("prose", sentence(ruText(pol.text))) : null,
		mt(12, "ol", "ladder", ladder.map((r) => el("li", { class: cls(r.current && "is-current") },
			sp("ladder-rung", r.current ? (isNum(pol.cap) ? `до ${pct0(pol.cap)}` : "сейчас") : isNum(r.payout) ? pct0(r.payout) : "остаток"),
			sx(strong(ruText(r.title)), ` — ${ruText(r.condition)}`)))),
		check.length ? spaced(14, tileLabel("Проверка формулы на истории"), dataTable([
			Tc("Год", (r) => String(r.year), "name"),
			Nc("ЧП, млрд ₽", numOf("ni_shareholders", 1)),
			Nc("База", numOf("base", 1)),
			Nc("Пул", numOf("pool", 1)),
			Nc("DPS точно", numOf("dps_exact", 4)),
			Nc("Округл.", numOf("dps_rounded", 2)),
			Nc("Объявлен", numOf("dps_declared", 2)),
			Tc("", (r) => (r.ok ? badge("до копейки", "good") : badge("расхождение", "bad"))),
		], check, COMPACT)) : null,
		cap.length ? spaced(14, tileLabel("Проверка потолка выплат: потолок политики считается от отчётной прибыли акционеров"), dataTable([
			Tc("Год", (r) => String(r.year), "name"),
			Nc("Объявлено, млрд ₽", numOf("pool", 1)),
			Nc("Отчётная прибыль", numOf("ni_shareholders", 1)),
			Nc("Доля", pctOf("share", 1)),
			Nc("Потолок", pctOf("cap", 0)),
			Tc("", (r) => (r.ok === true ? badge("в пределах", "good") : r.ok === false ? badge("выше потолка", "bad") : badge("год не завершён", "out"))),
		], cap, COMPACT)) : null,
		foot(pol.valid_until && pol.valid_until_note ? `${phrase(pol.valid_until_note)} ` : "",
			`База — ${basisLabel(d, "profit") || codeText(pol.base || "")}${W > 1 ? `, средняя за ${fmt.num(W)} ${plural(W, ["последний квартал", "последних квартала", "последних кварталов"])}` : ""}; `
			+ `${pol.frequency ? `решения — ${codeText(pol.frequency)}; ` : ""}делитель — ${isNum(obj(obj(d.meta).shares).dividend_eligible_mln) ? `${num1(dpsShares(d).mln)} млн ${dpsShares(d).words}` : codeText(pol.divisor || "")}${both(d)}; `
			+ `${check.length ? `округление — ${codeText(obj(check[0]).rounding || "")}; ` : ""}нехватка капитала — ${codeText(pol.shortfall_rule || "")}`
			+ `${isNum(pol.cap) ? `; потолок — до ${pct0(pol.cap)} прибыли года` : ""}. `
			+ (obj(pol.excess).from_profit_year ? `Выплата избытка с прибыли ${pol.excess.from_profit_year} г.: ε = ${num2(pol.excess.epsilon)}`
				+ (isNum(pol.excess.ramp_years) ? `, ввод линейно за ${yearsText(pol.excess.ramp_years)}. ` : ". ") : "")
			+ (obj(pol.crisis).skip_in_shock_year ? `В год кризиса решения о выплате отменяются; догоняющая выплата — ${codeText(pol.crisis.catch_up)}.` : ""), gateNote(d, "payout_cap")));
}

function dividendCard(d) {
	const dv = obj(d.dividends);
	const next = obj(dv.next_expected);
	const reg = list(dv.register).slice().sort((a, b) => String(b.ex_date || b.record_date).localeCompare(String(a.ex_date || a.record_date)));
	if (!isNum(next.dps) && !reg.length) return none("Следующая выплата", "следующая выплата", 6);
	const cond = obj(next.condition);
	const buy = next.last_buy_date ? daysBetween(d.meta.valuation_date, next.last_buy_date) : null;
	const model = next.status === "model", annual = model && annualModel(d);
	return card({ title: `Следующая выплата: ${divLabel(next)}`, span: 6, sub: model ? `объявления нет — ${annual ? "ожидание модели по клеткам" : "DPS по политике на прибыли модели"}` : `статус — ${divWord(next.status)}` },
		kpis(
			kpi(rub2(next.dps), annual ? [nextDpsLabel(d, next), hint(`P10–P90 ${num2(next.dps_p10)}–${num2(next.dps_p90)}${THIN}₽`)] : nextDpsLabel(d, next)),
			model ? kpi(rub2(annual ? next.dps_policy : next.dps_mean), annual ? "DPS политики без среза капиталом" : `в среднем по клеткам с нулями отмены; P10–P90 ${num2(next.dps_p10)}–${num2(next.dps_p90)}${THIN}₽`)
				: kpi(rub2(next.dps_policy), "DPS политики на прибыли модели"),
			kpi(pct0(next.p_cancel), `риск отмены: масса клеток «${layerTitle(d, "analytical")}», где выплата отменена`),
			next.last_buy_date ? kpi(fmt.date(next.last_buy_date), `последний день покупки${isNum(buy) ? `, через ${fmt.days(buy)}` : ""}`) : null,
			kpi(nextRecordText(next), recordWords(d, next)),
			kpi(fmt.date(next.pay_date_est), "ожидаемая выплата"),
			...tickers(d).map((t) => kpi(pct1(obj(next.yield)[t]), yieldWords(d, next, t)))),
		mt(12, "p", "note-box", cond.threshold > 0 ? `Условие капитала: ${metricTitle(d, cond.metric)} после выплаты не ниже ${pct1(cond.threshold)}; ожидание — ${pct2(cond.n20_expected)}; `
			: `Капитал: ожидаемый ${metricTitle(d, cond.metric)} в квартале вычета этой выплаты — ${pct2(cond.n20_expected)}; `,
		`капитал урезал выплату в ${pct1(cond.p_limited)} массы клеток.`, next.record_date_note && !next.record_date ? ` Дата реестра: ${ruText(next.record_date_note)}.` : ""),
		reg.length ? spaced(14, dataTable([
			Tc("Дивиденд", divCell, "name"),
			Nc("DPS", rubOf("dps")),
			Nc("Сумма, млрд ₽", numOf("amount", 1)),
			reg.some((r) => r.decided_date) ? Nc("Решение", dateOf("decided_date")) : null,
			Nc("Последний день покупки", dateOf("last_buy_date")),
			Nc("Реестр", registerCutoff),
			Nc("Выплата до", dateOf("pay_date")),
		], reg, { cls: "compact dense", detail: (r) => sp("muted", "Источники: ", registerSources(r)) }),
		foot(amountBasis(d, dv), obj(obj(d.live).register).note ? `${phrase(d.live.register.note)} ` : "", "Объявленной запись становится при двух источниках; рекомендация совета директоров — только плашка.")) : null);
}

function quarterlyDpsCard(d) {
	const dv = obj(d.dividends);
	if (annualPayer(d)) return null;
	const hist = list(dv.history).filter((r) => r.period && isNum(r.dps)).slice(-8);
	const reg = list(dv.register).filter((r) => r.period && isNum(r.dps) && !hist.some((h) => h.period === r.period));
	const model = list(dv.model_quarters).filter((r) => ![...hist, ...reg].some((x) => x.period === r.period));
	if (!hist.length && !model.length) return null;
	const rub = rub2;
	const row = (rows, it) => obj(list(rows).find((x) => x.period === it.key));
	const fact = (r, what) => ({ r, what, key: r.period, value: r.dps, color: MARKET, tipTitle: `${upperFirst(divLabel(r))}: ${what}`,
		tipRows: [["реестр", fmt.date(r.record_date)], ...(isNum(r.dps_pre_split) ? [["объявлено до дробления", rub(r.dps_pre_split)]] : [])] });
	const items = [...hist.map((r) => fact(r, "решение собрания")), ...reg.map((r) => ({ ...fact(r, `реестр, ${divWord(r.status)}`), faded: true })),
		...model.map((r) => ({ r, what: "модель", key: r.period, value: r.dps, lo: r.dps_p10, hi: r.dps_p90, mark: r.dps_policy, color: MODEL, tipTitle: `${periodLabel(r.period)}: модель`,
			tipRows: [["по политике", rub(r.dps_policy)], ["P10–P90", `${num2(r.dps_p10)}–${rub(r.dps_p90)}`], ["решение", periodLabel(r.decision_period)], ["выплата", periodLabel(r.pay_period)],
				["урезано капиталом", pct0(r.p_cut)], ["без выплаты", pct0(r.p_zero)]] }))].map((it) => ({ ...it, label: periodShort(it.key) }));
	const plot = columnsChart(items, { height: 220, valueName: "₽ на акцию", fmt: rub, short: (v) => num1(v), label: "Дивиденд на акцию по кварталам прибыли" });
	const fig = withTable(plot, () => dataTable([
		Tc("Квартал прибыли", (it) => sx(periodLabel(it.key), hint(it.what)), "name"),
		Nc("DPS", (it) => rub(it.value)),
		Nc("По политике", (it) => rub(isNum(it.mark) ? it.mark : row(dv.model_quarters, it).dps_policy)),
		Nc("P10–P90", (it) => (isNum(it.lo) ? `${num2(it.lo)}–${num2(it.hi)}` : "—")),
		model.length ? Nc("Без выплаты", (it) => pct0(it.r.p_zero)) : null,
		Nc("Решение", (it) => (it.r.decision_period ? periodLabel(it.r.decision_period) : fmt.date(it.r.decided_date || row(dv.register, it).decided_date))),
		Nc("Выплата", (it) => (it.r.pay_period ? periodLabel(it.r.pay_period) : it.r.pay_date ? `до ${fmt.date(it.r.pay_date)}` : "—")),
	], items.slice().reverse(), COMPACT));
	return card({ title: "Квартальные DPS", tools: fig.button,
		sub: "по кварталам прибыли, на акцию после дробления; у модели — ожидание смеси заголовка, усы P10–P90 по клеткам и черта DPS политики" },
	legend([["key-market", "решения собраний и реестр"], model.length && ["key-model", "модель"], model.length && ["key-line key-ink", "DPS политики"]]), fig.box);
}

// Годы с одним источником — одной записью («2013–2020, 2022–2025»).
function sourcesByYear(rows) {
	const groups = new Map();
	for (const r of rows) if (r.src) groups.set(r.src, [...new Set([...(groups.get(r.src) || []), r.year])]);
	const spans = (years) => {
		const out = [];
		for (const y of years) { const last = out[out.length - 1]; if (last && y === last[1] + 1) last[1] = y; else out.push([y, y]); }
		return out.map(([a, b]) => (a === b ? String(a) : `${a}–${b}`)).join(", ");
	};
	return [...groups].map(([src, years]) => [spans(years), srcText(src)]);
}

// Годовой плательщик: строки истории одного года (промежуточный и годовой дивиденды, выплаты до IPO) — одной
// строкой, сумма DPS; доля выплаты года — из `history.annual`, где она есть.
function yearRows(rows, annual) {
	const out = new Map();
	for (const r of rows) {
		const row = out.get(r.year) || { year: r.year, dps: 0, parts: [], record_date: null, payout_ratio: null, src: r.src };
		row.dps += r.dps;
		row.parts.push({ label: divLabel(r), dps: r.dps });
		row.record_date = r.record_date || row.record_date;
		out.set(r.year, row);
	}
	for (const a of annual) if (out.has(a.year) && isNum(a.payout)) out.get(a.year).payout_ratio = a.payout;
	// слова строки — в подсказке, когда год сложен из нескольких решений или строка — не «за год» (выплаты до IPO по году выплаты)
	for (const row of out.values()) if (row.parts.length < 2 && /^за /.test(String(obj(row.parts[0]).label))) row.parts = [];
	return [...out.values()].sort((a, b) => a.year - b.year);
}

// DPS по году прибыли; при квартальных решениях факт — годовые суммы `history.annual`.
function dividendHistoryCard(d) {
	const dv = obj(d.dividends);
	const annual = annualPayer(d);
	const quarterly = !annual && list(dv.history).some((r) => r.period);
	const hist = quarterly ? list(obj(d.history).annual).filter((r) => isNum(r.dps)).map((r) => ({ year: r.year, dps: r.dps, payout_ratio: r.payout }))
		: annual ? yearRows(list(dv.history).filter((r) => isNum(r.dps)), list(obj(d.history).annual))
			: list(dv.history).filter((r) => isNum(r.dps));
	const model = list(dv.model).filter((r) => isNum(r.dps));
	if (!hist.length && !model.length) return none("Дивиденды по годам", "история дивидендов");
	const items = [
		...hist.map((r) => ({ key: r.year, label: yy(r.year), value: r.dps, color: MARKET, tipTitle: `${r.year}: факт`,
			tipRows: [["доля выплаты", pct0(r.payout_ratio)], ...(r.record_date ? [["отсечка", fmt.date(r.record_date)]] : []),
				...list(r.parts).map((x) => [ruText(x.label), rub2(x.dps)])] })),
		...model.filter((r) => !hist.some((h) => h.year === r.year)).map((r) => ({ key: r.year, label: yy(r.year), value: r.dps, color: MODEL,
			tipTitle: `${r.year}: модель`, tipRows: [["по политике", rub2(r.dps_policy)], ["P10–P90", `${num1(r.dps_p10)}–${num1(r.dps_p90)}`], ["урезано капиталом", pct0(r.p_cut)], ["без выплаты", pct0(r.p_zero)]] })),
	];
	const plot = columnsChart(items, { height: 220, valueName: "₽ на акцию", fmt: rub2, short: (v) => fmt.num(v, v && Math.abs(v) < 1 ? 2 : 0), label: "Дивиденд на акцию по году прибыли" });
	const fig = withTable(plot, () => bx("split",
		dataTable([
			Tc("Год прибыли", (r) => String(r.year), "name"),
			Nc("DPS", rubOf("dps")),
			quarterly || !hist.some((r) => isNum(r.pool)) ? null : Nc("Пул, млрд ₽", numOf("pool", 1)),
			Nc("Доля", pctOf("payout_ratio", 0)),
		], hist, { cls: "compact", caption: "Факт" }),
		dataTable([
			Tc("Год прибыли", (r) => `${r.year} → ${r.pay_year}`, "name"),
			Nc("DPS", rubOf("dps")),
			Nc("По политике", rubOf("dps_policy")),
			Nc("P10–P90", (r) => `${num1(r.dps_p10)}–${num1(r.dps_p90)}`),
			Nc("Урезано капиталом", pctOf("p_cut", 0)),
			Nc("Без выплаты", pctOf("p_zero", 0)),
		], model, { cls: "compact", caption: `Модель: ожидание смеси заголовка по клеткам; доли клеток с урезанием капиталом и без выплаты за весь год${annual ? "" : " — отмена решения за отдельный квартал видна в «Квартальных DPS»"}` })));
	const sources = sourcesByYear(list(dv.history).filter((r) => isNum(r.dps)));
	return card({ title: "Дивиденды по году прибыли", tools: fig.button,
		sub: `факт — выплаты по решениям собраний${quarterly ? ", сумма кварталов года" : ""}; модель — ожидание смеси заголовка; на ${num1(dpsShares(d).mln)} млн ${dpsShares(d).words}${both(d)}` },
	legend([hist.length && ["key-market", "факт"], ["key-model", "модель"]]), fig.box,
	sources.length === 1 ? foot(sentence(`Источник факта: ${sources[0][1]}`))
		: sources.length <= 3 ? (sources.length ? foot(sentence(`Источники факта: ${sources.map(([years, src]) => `${years} — ${src}`).join("; ")}`)) : null)
			: bx("card-foot", detailsBlock(`Источники факта по годам · ${sources.length}`, el("ul", { class: "list stacked" },
				sources.map(([years, src]) => lx(sp("t", years), sp("v", src)))))));
}

// Выкуп акций по цене мира (`dividends.buyback`): суммы, цена покупок, путь акций и делитель после выкупа.
function buybackCard(d) {
	const b = obj(obj(d.dividends).buyback);
	const Y = list(b.years);
	if (!Y.length) return null;
	const W = Object.entries(obj(b.by_world));
	const span = `${periodLabel(b.first_period)} — ${periodLabel(b.last_period)}`;
	return card({ title: upperFirst(ruText(b.title || "выкуп акций")), span: 6, sub: `${span}; смесь заголовка; цена покупок — форвард рынка мира от ${fmt.rub(b.price_book, Math.max(2, exactDigits(b.price_book, 4)))}` },
		kpis(
			kpi(bn0(b.amount), "сумма выкупа"),
			kpi(rub2(b.price), "средняя цена покупок"),
			kpi(num1(b.shares_bought_mln), "куплено, млн акций"),
			kpi(num1(b.divisor_after_mln), `акций в обращении после выкупа, млн (было ${num1(b.shares_start_mln)})`)),
		spaced(12, dataTable([
			Tc("Год", (r) => String(r.year), "name"),
			Nc("Сумма, млрд ₽", numOf("amount", 1)),
			Nc("Цена", rubOf("price")),
			Nc("Куплено, млн", numOf("shares_bought_mln", 1)),
			Nc("В обращении на конец года, млн", numOf("shares_end_mln", 1)),
		], Y, COMPACT)),
		W.length ? spaced(12, dataTable([
			Tc("Мир", (r) => worldName(d, r[0]), "name"),
			Nc("Цена выкупа", (r) => rub2(obj(r[1]).price)),
			Nc("В обращении после выкупа, млн", (r) => num1(obj(r[1]).divisor_after_mln)),
		], W, COMPACT)) : null,
		list(b.closed).length ? foot(`Закрытые кварталы — по средней цене рынка: ${list(b.closed).map((c) => `${periodLabel(c.period)} — ${fmt.rub(c.price, Math.max(2, exactDigits(c.price, 4)))}`).join(", ")}.`) : null);
}

// Жетон DPS (`dividends.token`): минимум за год прибыли и масса клеток, где рост урезан под него.
function tokenCard(d) {
	const t = obj(obj(d.dividends).token);
	if (!isNum(t.min_dps)) return null;
	const Y = list(t.years).filter((r) => r.p_token > 0);
	return card({ title: `Жетон DPS: ${rub2(t.min_dps)}`, span: 6, sub: "минимум за год прибыли; рост урезается под выплату, пока норматив после неё не ниже требования без запаса менеджмента" },
		Y.length ? dataTable([
			Tc("Год прибыли", (r) => String(r.year), "name"),
			Nc("DPS, ожидание", rubOf("dps")),
			Nc("Клетки с жетоном", pctOf("p_token", 0)),
		], Y, COMPACT) : empty("Жетон не связывает ни в одной клетке."));
}

function sharesCard(d) {
	const s = obj(obj(d.meta).shares);
	const acts = list(s.corporate_actions);
	if (!isNum(s.divisor_mln) && !acts.length) return null;
	const mln = (v, t) => (isNum(v) ? kpi(num1(v), t) : null);
	const kinds = { split: "дробление", issue: "выпуск акций", buyback_program: "программа выкупа", buyback: "выкуп", cancellation: "погашение", deal: "сделка" };
	return card({ title: "Число акций и события", sub: `млн шт. на ${fmt.date(s.as_of)}; ${srcText(s.src || "")}` },
		kpis(
			mln(s.divisor_mln, `делитель: ${ruText(s.divisor_label || "")}`), mln(s.issued_mln, "размещённые акции"), mln(s.outstanding_mln, "акции в обращении"),
			solo(d) ? mln(obj(obj(s.by_ticker)[ticker(d)]).treasury_mln, "собственные акции") : null,
			mln(s.depositary_block_mln, "на счёте депозитарных программ: без голосов и выплат, в делитель входят"),
			mln(s.economic_treasury_mln, "экономически собственные: из делителя вычитаются"),
			mln(s.dividend_eligible_mln, "с правом на дивиденд: размещённые без собственных акций банка")),
		isNum(s.divisor_mln) ? smallNote("На делитель делятся цена, капитал на акцию, P/B и P/E; дивиденд уходит из капитала по акциям в обращении.") : null,
		acts.length ? spaced(12, dataTable([
			Tc("Дата", (a) => fmt.date(a.date), "name nowrap"),
			Tc("Событие", (a) => kinds[a.kind] || "событие"),
			Tc("Название", (a) => ruText(a.title), "txt"),
			Nc("Коэффициент", splitText),
		], acts, COMPACT)) : null);
}

// Путь фондирования (`paths.funding`): кредиты к средствам клиентов и доля оптового фондирования на конец года.
function fundingTable(d) {
	const F = obj(obj(d.paths).funding), a = obj(F.anchor), Y = list(F.years);
	const col = (part, k) => (i) => pct1(list(obj(F[part])[k])[i]);
	return Y.length ? spaced(16, smallNote(`Чем закрыт рост кредитов. На дату якоря кредиты к средствам клиентов — ${pct1(a.loans_to_funds)}, доля оптового фондирования — ${pct1(a.wholesale_share)}; модальная клетка — ${cellName(d, F.cell)}.`), dataTable([
		Tc("На конец года", (i) => String(Y[i]), "name"),
		Nc("Кредиты к средствам клиентов: смесь", col("mix", "loans_to_funds")), Nc("модальная клетка", col("modal_cell", "loans_to_funds")),
		Nc("Доля оптового фондирования: смесь", col("mix", "wholesale_share")), Nc("модальная клетка", col("modal_cell", "wholesale_share")),
	], Y.map((y, i) => i), { cls: "compact dense" })) : null;
}

function annualCard(d) {
	const p = obj(d.paths);
	const A = list(p.annual);
	if (!A.length) return none("По годам", "путь по годам");
	const u = modelUnit(d);
	const year = (r) => sx(String(r.year), r.fact_quarters ? hint(`${fmt.num(r.fact_quarters)}${NBSP}кв. факт + модель`) : null);
	const mini = (title, key, f, color) => bx("mini", tileLabel(title),
		linesChart([{ name: title, color, ...DOT, points: A.map((r) => [r.year, r[key]]) }],
			{ xType: "band", categories: A.map((r) => r.year), height: 150, left: 44, yFmt: f, tipFmt: f, xFmt: yy }));
	const t = obj(p.terminal);
	return card({ title: "По годам: смесь заголовка", sub: `млрд ₽ и доли; год якоря — факт отчётных ${u.pgen} + модель; упр. ЧПМ, CoR и ${ci()} — мостом сборки` },
		bx("minis",
			mini(`${shProfit(d)}, млрд ₽`, "ni_sh", fmt.num, MODEL),
			mini("ROE", "roe", pct1, THIRD),
			mini(capTitle(d, "n20"), "n20_end", pct1, MARKET)),
		spaced(16, dataTable([
			Tc("Год", year, "name"),
			Nc("ЧПД", numOf("nii")),
			Nc("ЧПМ упр.", pctOf("nim_mgmt", 2)),
			Nc("Услуги и комиссии", numOf("fees")),
			Nc("Расходы", numOf("opex")),
			Nc(`${ci()} упр.`, pctOf("cir_mgmt", 1)),
			Nc("Резервы", numOf("llp")),
			Nc("CoR упр.", pctOf("cor_mgmt", 2)),
			A.some((r) => r.fvc) ? Nc(el("span", { tip: "Кредитная переоценка кредитов по справедливой стоимости сверх опоры; расход — со знаком плюс, как резервы" }, "FVC"), numOf("fvc")) : null,
			A.some((r) => r.one_off) ? Nc("Разовые", (r) => fmt.signed(r.one_off, 0)) : null,
			Nc(noncoreHead(), numOf("noncore")),
			Nc(shProfit(d), (r) => strong(fmt.num(r.ni_sh))),
			Nc("ROE", pctOf("roe", 1)),
			Nc("Капитал", numOf("bv_end")),
			Nc("RWA", numOf("rwa_end")),
			Nc(capTitle(d, "n20"), pctOf("n20_end", 2)),
			Nc(capTitle(d, "n11"), pctOf("n11_end", 2)),
			Nc("DPS", numOf("dps", 2)),
			Nc("Доля выплаты", pctOf("payout", 0)),
		], A, { cls: "dense", rowClass: (r) => (r.fact_quarters ? "is-muted" : null) })),
		fundingTable(d),
		isNum(t.roe_t) ? foot(`Терминал: ROE ${pct1(t.roe_t)}, стоимость капитала ${pct1(t.k_t)}, рост ${pct1(t.g_t)}, доля выплаты ${pct0(t.payout_t)}, избыток капитала ${bn0(t.x_t)}; `
			+ `горизонт ${periodLabel(obj(d.meta).first_period)} — ${periodLabel(list(obj(d.meta).horizon)[1])}.`) : null, basisFoot(d, "profit", "roe"));
}

/* ── экран «Допущения» ── */

let ALL_JUDGEMENTS = false;

function screenBook(d) {
	return bx("screen",
		screenHead("Допущения", `Книга допущений ${obj(d.meta).book_version || ""}`,
			"Каждое суждение — с диапазоном, ценой ошибки и источником. Ниже — проверки с письменными объяснениями, свежесть живых входов, кривая книги против рынка, история оценки по выпускам и отчётная история."),
		sec(bookMetaCard(d)), sec(levelsCard(d, true), variantsCard(d)), sec(judgementsCard(d)), sec(gatesCard(d)), sec(freshnessCard(d), curveCard(d)),
		sec(valuationHistoryCard(d)), more([controlCard(d), historyCard(d)]));
}

// Цена правил и развилок (`book.reference_variants`) — из таблиц книги; порядок строк — выпуска: по модулю цены, без цены — последними.
function variantsCard(d) {
	const v = obj(obj(d.book).reference_variants), rows = list(v.rows);
	if (!rows.length) return null;
	const dry = rows.some((r) => "d_median" in r || r.why);
	return card({ title: "Цена правил и развилок", sub: (dry ? `Книга, перевыведенная под одно изменённое правило (корни, концы осей и проверки заново), прочее — как в книге: сколько рублей стоит каждое правило. `
		: `Точка книги при одном изменённом правиле, прочее — как в книге: сколько рублей стоит каждое правило точки. `)
		+ `На цене и дате книги точка — ${rub2(v.point)}; в выпуске варианты не пересчитываются.` },
	v.warning ? smallNote(ruText(`Цены не напечатаны: ${v.warning}.`)) : null,
	dataTable([Tc("Правило или развилка", (r) => [ruText(r.title), ...rowNotes(r)], "name"), Nc("Точка", (r) => (isNum(r.point) ? rub1(r.point) : "—")),
		...(dry ? dCols("К точке книги") : [Nc("К точке книги", (r) => strong(fmt.signedRub(r.d_point, 1)))])], rows, COMPACT),
	v.basis ? foot(upperFirst(ruText(v.basis)) + ".") : null);
}

function bookMetaCard(d) {
	const m = obj(d.meta);
	const live = obj(d.live);
	const src = obj(obj(d.worlds).source);
	const ov = obj(obj(d.worlds).overlay);
	const b = obj(d.book);
	return card({ title: "Выпуск и книга" },
		kpis(
			kpi(`${m.book_version || "—"}`, `книга допущений (${m.book_tag || "—"}) от ${fmt.date(m.book_date)}`),
			kpi(fmt.date(m.valuation_date), "дата оценки"),
			kpi(fmt.date(m.facts_date), `отчётные факты (${periodLabel(m.anchor_period)})`),
			kpi(fmt.date(m.curve_as_of), "кривые миров"),
			kpi(fmt.days(live.book_age_days), "возраст книги"),
			kpi(`${periodShort(list(m.horizon)[0])}–${periodShort(list(m.horizon)[1])}`, `горизонт, шаг — ${modelUnit(d).one}`),
			kpi(fmt.date(mskDay(m.generated_at)), `выпуск собран в ${fmt.time(m.generated_at)}`),
			kpi(fmt.date(mskDay(m.published_at)), `опубликован в ${fmt.time(m.published_at)}`),
			kpi(String(m.engine_commit || "—").slice(0, 7), "коммит ядра"),
			kpi(`${fmt.num((m.bytes || 0) / 1000)} КБ`, "размер выпуска")),
		foot(`Контракт ${d.schema}; хэш содержания ${String(m.payload_sha256 || "").slice(0, 16)}…${m.fast ? "; быстрая сборка." : ""} `
			+ `Миры: ${worldsRecord(d)} от ${fmt.date(src.record_asof)}, sha256 ${String(src.sha256 || "").slice(0, 12)}…; банковская надстройка — sha256 ${String(ov.sha256 || "").slice(0, 12)}…`
			+ (obj(b.changes_last).summary ? ` Изменения с ${b.changes_last.from_version}: ${ruText(b.changes_last.summary)}.` : "")),
		basisFoot(d, "profit", "roe", "divisor"));
}

function judgementsCard(d) {
	const rows = list(obj(d.judgements).rows);
	if (!rows.length) return none("Суждения книги", "суждения");
	const center = d.fair_value.central;
	const prices = rows.flatMap((r) => [r.price_low, r.price_high]).filter(isNum);
	const step = niceStep(Math.max(center, ...prices), 6);
	const dom = [Math.max(0, Math.floor((Math.min(center, ...prices) * 0.94) / step) * step), Math.ceil((Math.max(center, ...prices) * 1.04) / step) * step];
	const body = el("div");
	const key = { stationary_book: nimNode(d).value, printed_book: obj(trans(d).nim_lt_printed).value };
	// Связка печатается значением первого пути под именем оси; сколько чисел книги идут вместе — строкой.
	const note = (r) => (r.kind === "bundle" ? hint(`связка: чисел книги — ${fmt.num(list(r.paths).length)}, к своим концам идут вместе; в строке — первое`)
		: nimAxis(r) ? [nimPrinted(d, key), isNimKey(r) ? hint("диапазон — тоже ключа цели") : null] : null);
	const draw = () => {
		const shown = ALL_JUDGEMENTS ? rows : rows.slice(0, 12);
		fill(body, dataTable([
			Tc("Суждение", (r) => r.name, "name"),
			Tc("В книге", (r) => [r.kind === "bundle" && r.unit === "pp" ? fmt.pp(r.book, 1) : formatByUnit(r.book, r.unit, d), note(r)], "txt"),
			Nc("Диапазон", (r) => rangeText(d, r), "", isDict),
			Tc("Точка на краях, ₽", (r) => (isNum(r.price_low) ? bx("tn-cell",
				barTrack([
					{ from: Math.min(r.price_low, r.price_high), to: Math.min(center, Math.max(r.price_low, r.price_high)), cls: "is-down" },
					{ from: Math.max(center, Math.min(r.price_low, r.price_high)), to: Math.max(r.price_low, r.price_high), cls: "is-up" },
				].filter((s) => s.to > s.from), dom, { center }),
				sp("tn-nums", `${fmt.num(r.price_low)} / ${fmt.num(r.price_high)}`)) : "—")),
			Nc("Цена ошибки", (r) => strong(fmt.rub(r.swing))),
			Nc("Сдвиг положения, ₽", (r) => fmt.signed(r.mean_shift, 1)),
			Nc("Вклад в полосу", (r) => (r.in_band === false ? el("span", { class: "muted", tip: `ось стоит на значении книги и не разыгрывается; ${offBandNote(d)}` }, "вне полосы")
				: r.status === "not_computed" ? "не считалось" : shareText(r.share))),
		], shown, { detail: (r) => (r.source ? detailsBlock("Источник", srcText(r.source)) : null) }),
		rows.length > 12 ? el("button", { class: "view-toggle", type: "button", style: "margin-top:12px",
			on: { click: () => { ALL_JUDGEMENTS = !ALL_JUDGEMENTS; draw(); } } }, ALL_JUDGEMENTS ? "Показать главные 12" : `Показать все ${rows.length}`) : null);
	};
	draw();
	return card({ title: "Суждения книги по цене ошибки",
		sub: `Точка на краях диапазона каждого суждения (по одному, прочие — книга); вертикаль — точка ${rub1(center)}. Цена ошибки — размах точки на диапазоне; `
			+ "сдвиг положения — на сколько асимметрия диапазона уводит среднее прогонов от точки (первый порядок); вклад меньше 1 % не различим."
			+ (offBand(d).length ? ` Вне полосы — ${fmt.num(offBand(d).length)}: ${offBandNote(d)}.` : "") },
	legend([["key-neg", "ниже точки"], ["key-model", "выше точки"]]), body);
}

// Клетка — именами выпуска: мир, режим, сценарий капитала.
function cellName(d, label) {
	const [w, r, s] = String(label).split("/");
	return [worldName(d, w), regimeName(d, r), scenarioName(d, s)].filter(Boolean).join(" · ");
}

const CELL_WORDS = ["клетка", "клетки", "клеток"];
const GATE_STATUS = { quiet: ["тихо", "out"], explained: ["объяснён", "good"], unexplained: ["без объяснения", "bad"], expired: ["объяснение истекло", "bad"], mass_off: ["масса вне ожидания", "warn"] };

function gatesCard(d) {
	const c = obj(d.checks);
	const gates = list(c.gates);
	const fired = gates.filter((g) => g.fired);
	const quiet = gates.filter((g) => !g.fired);
	const inv = list(c.invariants);
	const flags = list(c.flags);
	const corridor = (g) => { const k = obj(g.corridor); return k.text ? wordsText(d, k.text) : ""; };
	const expected = (g) => (Array.isArray(g.expected_mass) ? `${num1(g.expected_mass[0] * 100)}–${pct1(g.expected_mass[1])}` : pct1(g.expected_mass));
	// Счётчик согласован с числом: «1 поднятый флаг», «4 сработавших гейта».
	const count = (n, adj, noun, tail = "") => kpi(fmt.num(n), `${plural(n, adj)} ${plural(n, noun)}${tail}`);
	const raised = flags.filter((f) => f.raised).length;
	return card({ title: "Проверки",
		sub: "Инварианты — тождества, их нарушение блокирует выпуск; гейт правдоподобия срабатывает на части клеток и требует письменного объяснения с ожидаемой массой и сроком; флаги — совещательные." },
	kpis(
		count(c.invariants_broken || 0, ["нарушенный", "нарушенных", "нарушенных"], ["инвариант", "инварианта", "инвариантов"], ` из ${fmt.num(inv.length)}`),
		count(fired.length, ["сработавший", "сработавших", "сработавших"], ["гейт", "гейта", "гейтов"], ` из ${fmt.num(gates.length)}`),
		count(raised, ["поднятый", "поднятых", "поднятых"], ["флаг", "флага", "флагов"])),
	fired.length ? bx("gates", fired.map((g) => { const [t, k] = GATE_STATUS[g.status] || [g.status, null]; return el("article", { class: "gate" },
		bx("gate-head", strong(g.title || g.name),
			sp("gate-mass", `${g.cells > 0 ? `${fmt.num(g.cells)} ${plural(g.cells, CELL_WORDS)} · ` : ""}${pct1(g.mass)} массы${g.expected_mass !== null && g.expected_mass !== undefined ? ` · ожидалось ${expected(g)}` : ""}`),
			badge(t, k), g.expiring ? badge("срок истекает", "warn") : null),
		g.valid_until ? mt(4, "p", "muted small", `Объяснение действует по ${fmt.date(g.valid_until)} включительно. Коридор: ${corridor(g)}.`) : null,
		g.message ? mt(6, "p", "ink-2", sentence(upperFirst(wordsText(d, g.message)))) : null,
		g.explanation ? mt(6, "p", "ink-2", ruText(g.explanation)) : null,
		list(g.cell_list).length ? detailsBlock(`Клетки${g.cells > list(g.cell_list).length ? ` (первые ${list(g.cell_list).length} из ${fmt.num(g.cells)})` : ""}`,
			list(g.cell_list).map((c) => cellName(d, c)).join("; ") + ".") : null); })) : empty("Ни один гейт не сработал."),
	bx("card-foot stack",
		quiet.length ? detailsBlock(`Коридоры несработавших гейтов · ${quiet.length}`, el("ul", { class: "list stacked" },
			quiet.map((g) => lx(sp("t", g.title || g.name), sp("v", corridor(g) || "—"),
				g.message ? mt(2, "p", "muted small", sentence(upperFirst(wordsText(d, g.message)))) : null)))) : null,
		inv.length ? detailsBlock(`Инварианты · ${inv.length}`, el("ul", { class: "list" }, inv.map((i) => el("li", {},
			sp("t", i.title || i.name, i.detail ? sp("muted", ruText(i.detail)) : null), sp("v", i.ok ? badge("в допуске", "good") : badge("нарушен", "bad")))))) : null,
		flags.length ? detailsBlock(`Флаги · ${flags.length}`, el("ul", { class: "list" }, flags.map((f) => el("li", {},
			sp("t", f.title || f.name, f.detail ? sp("muted", wordsText(d, f.detail)) : null), sp("v", f.raised ? badge("поднят", "warn") : badge("нет", "out")))))) : null,
		obj(d.capital).rule_price ? pr("muted small", "Цена правила — оценка при трёх замыканиях капитала: ", el("a", { href: "#capital" }, "«Капитал и дивиденды» →")) : null));
}

const INPUT_STATUS = { ok: ["в норме", "good"], stale: ["устарел", "warn"], fallback: ["запасное значение", "warn"] };

function freshnessCard(d) {
	const live = obj(d.live);
	const rows = list(obj(d.inputs).rows);
	const prices = obj(live.prices);
	return card({ title: "Свежесть входов", span: 6, sub: `дата оценки ${fmt.date(d.meta.valuation_date)} — от неё, а не от времени сборки, меряется свежесть; живые входы ${live.applied ? "применены" : "не применены (книжные)"}` },
		rows.length ? dataTable([
			Tc("Вход", (r) => r.name, "name"),
			Nc("Значение", (r) => (r.unit === "version" ? String(r.value) : formatByUnit(r.value, r.unit, d))),
			Nc("На дату", dateOf("as_of")),
			Tc("", (r) => { const [t, k] = INPUT_STATUS[r.status] || [r.status, null]; return badge(t, k); }),
		], rows, { cls: "compact", detail: (r) => (r.source ? sp("muted", srcText(r.source)) : null) }) : empty("Строк входов в выпуске нет."),
		mt(12, "ul", "list stacked",
			...tickers(d).map((t) => { const p = obj(prices[t]); return lx(sp("t", `Цена${tk(d, t)}`),
				sp("v", `${rub2(p.value)} · ${fmt.date(p.date)} ${p.time || ""} · ${p.accepted ? "принята" : `не принята: ${ruText(p.reason || "")}; последняя принятая ${rub2(obj(p.last_accepted).value)}`}`)); }),
			lx(sp("t", "Ключевая ставка"), sp("v", `${pct2(obj(live.key_rate).value)} с ${fmt.date(obj(live.key_rate).since)}`)),
			lx(sp("t", "Реестр дивидендов"), sp("v", `${fmt.num(obj(live.register).entries)} ${plural(obj(live.register).entries || 0, ["запись", "записи", "записей"])} на ${fmt.date(obj(live.register).as_of)}; ${ruText(obj(live.register).note || "")}`)),
			obj(obj(d.capital).anchor).estimated ? lx(sp("t", "Нормативы якоря"), sp("v", "оценка до выхода формы группы")) : null),
		list(live.degraded).length ? mt(12, "div", "note-box", strong("Деградация входов:"),
			el("ul", { class: "reasons" }, list(live.degraded).map((n) => lx(reasonText(n))))) : null);
}

function neutralWorld(d) {
	const w = obj(obj(obj(d.layers).macro_neutral).world_weights);
	const keys = Object.keys(w).filter((k) => isNum(w[k]));
	return keys.length ? keys.sort((a, b) => w[b] - w[a])[0] : null;
}

function curveCard(d) {
	const curve = obj(obj(d.live).curve);
	const nk = neutralWorld(d);
	const book = obj(obj(obj(obj(d.worlds).rows)[nk]).zero_curve);
	const series = [];
	if (Object.keys(book).length) series.push({ name: `книга: мир ${worldName(d, nk)}`, color: MARKET, dots: true, points: curvePoints(book) });
	if (Object.keys(obj(curve.nodes)).length) series.push({ name: `ОФЗ ${fmt.date(curve.as_of)}`, color: INK, width: 1.6, ...DOT, points: curvePoints(curve.nodes) });
	if (!series.length) return none("Кривая ОФЗ: книга и рынок", "кривая", 6);
	const plot = linesChart(series, { height: 220, ...CURVE_AXIS, label: "Кривая книги и наблюдаемая кривая ОФЗ" });
	return card({ title: "Кривая ОФЗ: книга и рынок", span: 6,
		sub: `В оценку идут миры книги; живая кривая — диагностика флага «книгу пора обновить».${curve.as_of ? "" : " Наблюдаемая кривая не принята — причина в свежести входов."}` },
	legend(series.map((s, i) => [i === 0 && Object.keys(book).length ? "key-line key-market" : "key-line key-ink", s.name])), plot,
	Object.keys(obj(curve.shift_bp)).length ? kpis(12,
		Object.entries(curve.shift_bp).map(([t, v]) => kpi(fmt.bp(v), `сдвиг узла ${isNum(+t) ? yearsText(+t) : t} к книге`))) : null);
}

function valuationHistoryCard(d) {
	const h = obj(d.valuation_history);
	const dates = list(h.date);
	const head = obj(d.fair_value.headline);
	const main = ticker(d);
	const nowDay = mskDay(obj(d.meta).published_at || obj(d.meta).generated_at) || obj(d.meta).valuation_date;
	const rows = dates.map((dt, i) => ({ date: dt, median: list(h.median)[i], p10: list(h.p10)[i], p25: list(h.p25)[i], p75: list(h.p75)[i], p90: list(h.p90)[i],
		point: list(h.point)[i], price: Object.fromEntries(tickers(d).map((s) => [s, list(obj(h.price)[s])[i]])), rollback: list(h.rollbacks).includes(i) }));
	if (isNum(head.median) && !dates.includes(nowDay)) {
		rows.push({ date: nowDay, median: head.median, p10: list(head.band80)[0], p25: list(head.band50)[0], p75: list(head.band50)[1], p90: list(head.band80)[1],
			point: head.point, price: Object.fromEntries(tickers(d).map((s) => [s, obj(head.market_by_ticker)[s]])), current: true });
	}
	if (rows.length < 2) return card({ title: "История оценки по выпускам" }, empty("Прошлых выпусков в выпуске нет: история начнётся со второй публикации."));
	const xs = rows.map((r) => dayMs(r.date));
	const first = Math.min(...xs), last = Math.max(...xs);
	const ex = [...list(obj(d.dividends).history), ...list(obj(d.dividends).register)].filter((r) => isNum(dayMs(r.ex_date)) && dayMs(r.ex_date) >= first && dayMs(r.ex_date) <= last);
	const exUnique = ex.filter((r, i) => ex.findIndex((q) => q.ex_date === r.ex_date) === i);
	const marks = [...exUnique.map((r) => ({ x: dayMs(r.ex_date), text: `дивиденд ${rub2(r.dps)}`, short: rub2(r.dps), tip: { title: "Экс-дата", rows: [["дата", fmt.date(r.ex_date)], ["DPS", rub2(r.dps)]] } })),
		...list(h.book_changes).filter((b) => isNum(dayMs(b.date))).map((b) => ({ x: dayMs(b.date), text: `книга ${b.to}`, color: MODEL, tip: { title: "Смена книги", rows: [["было", String(b.from)], ["стало", String(b.to)]] } }))];
	const plot = linesChart([
		{ name: "медиана", color: MODEL, width: 2.2, points: rows.map((r) => [dayMs(r.date), r.median]), area: rows.map((r) => [dayMs(r.date), r.p10, r.p90]), areaFill: "var(--model-wash-1)" },
		{ name: "полоса 50 %", color: MODEL, line: false, points: [], area: rows.map((r) => [dayMs(r.date), r.p25, r.p75]), areaFill: "var(--model-wash-2)" },
		...tickers(d).map((s) => ({ name: s, color: MARKET, width: s === main ? 1.8 : 1.4, dashed: s !== main, points: rows.map((r) => [dayMs(r.date), r.price[s]]) })),
		{ name: "откат", color: NEG, line: false, dots: true, hollow: true, r: 4.5, points: rows.filter((r) => r.rollback).map((r) => [dayMs(r.date), r.median]) },
		{ name: "текущий выпуск", color: MODEL, line: false, dots: true, r: 5, points: rows.filter((r) => r.current).map((r) => [dayMs(r.date), r.median]) },
	], { height: 260, xMin: first, xMax: last, xFmt: (ms) => fmt.dateShort(new Date(ms).toISOString().slice(0, 10)), xTicks: ticks(first, last, 5), left: 52,
		tipFmt: rub1,
		vlines: marks, label: "История оценки по выпускам" });
	const fig = withTable(plot, () => dataTable([
		Tc("Выпуск", (r) => sx(fmt.date(r.date), r.current ? hint("текущий") : r.rollback ? hint("откат") : null), "name"),
		Nc("Медиана", numOf("median", 1)),
		Nc("P10–P90", (r) => `${fmt.num(r.p10)}–${fmt.num(r.p90)}`),
		Nc("Точка", numOf("point", 1)),
		...tickers(d).map((s) => (Nc(solo(d) ? "Цена" : s, (r) => num2(r.price[s])))),
	], rows.slice().reverse()));
	return card({ title: "История оценки по выпускам", tools: fig.button,
		sub: `медиана и полосы 80 % и 50 % против цены${tk(d, main)}; после экс-даты оценка честно падает на DPS; ${ruText(h.rule || "")}` },
	legend([["key-b80", "полоса 80 %"], ["key-b50", "полоса 50 %"], ["key-line key-model", "медиана"], ["key-line key-market", solo(d) ? "цена" : main], ...others(d).map((s) => ["key-line key-market2", s]),
		exUnique.length && ["key-line key-dash", "экс-дата"], marks.length > exUnique.length && ["key-line key-model2", "смена книги"]]),
	fig.box,
	h.source ? foot(sentence(`Источник: ${srcText(h.source)}`)) : null);
}

function controlCard(d) {
	const cm = obj(d.checks).control_model;
	if (!cm || !list(cm.rows).length) return null;
	// Единица строки: доля и сдвиг доли считаются в п.п.
	const share = (r) => ["pct", "share", "pp"].includes(r.unit);
	const tail = (r) => (share(r) ? `${NBSP}п.п.` : { bn: `${NBSP}млрд${NBSP}₽`, rub: `${THIN}₽`, price: `${THIN}₽` }[r.unit] || "");
	const inUnit = (r, v) => (share(r) ? v * 100 : v);
	const level = (r, v) => (!isNum(v) ? "—" : r.unit === "pp" ? fmt.num(v * 100, 2) + tail(r) : share(r) ? fmt.pct(v, 2)
		: v !== 0 && Math.abs(v) < 1e-4 ? sci(v) : fmt.num(v, v === 0 ? 0 : ["rub", "price"].includes(r.unit) ? 2 : Math.abs(v) < 10 ? 4 : 1) + tail(r));
	const digits = (r, t) => Math.max(share(r) || ["rub", "price"].includes(r.unit) ? 2 : r.unit === "bn" ? 1 : 0, isNum(t) && t > 0 ? Math.ceil(-Math.log10(inUnit(r, t)) - 1e-9) : 0);
	const tolAbs = (r, t) => (!isNum(t) ? "—" : digits(r, t) > 4 ? sci(inUnit(r, t)) : fmt.num(inUnit(r, t), digits(r, t))) + tail(r);
	// Разность мельче знаков своего допуска — ноль, пока строка в допуске.
	const diffAbs = (r) => {
		if (!isNum(r.diff)) return "—";
		const t = r.tol_kind === "abs" ? r.tol : r.tol_abs, k = Math.min(4, digits(r, t)), v = inUnit(r, r.diff);
		return (fmt.num(v, k) !== fmt.num(0, k) ? fmt.signed(v, k) : v === 0 || r.ok ? "0" : sci(v)) + tail(r);
	};
	const rel = (r) => r.tol_kind === "rel" && isNum(r.diff_rel);
	const rows = list(cm.rows);
	const bad = rows.filter((r) => !r.ok).length;
	// Числа сводки — на цене и дате книги (`valuation_date`), день счёта — `as_of`; на экране — выдержка из `n_rows` строк.
	return card({ title: "Сверка с контрольной моделью",
		sub: `годовая модель, написанная отдельно; ${cm.book_version ? `сводка на книге ${cm.book_version}, на её цене и дате${cm.valuation_date ? ` (${fmt.date(cm.valuation_date)})` : ""}; посчитана ` : ""}${fmt.date(cm.as_of)}, коммит ${String(cm.commit || "—").slice(0, 7)}; `
			+ `${isNum(cm.n_rows) ? "на экране " : ""}${fmt.num(rows.length)} ${plural(rows.length, ["строка", "строки", "строк"])}${isNum(cm.n_rows) ? ` из ${fmt.num(cm.n_rows)}, вне допуска во всей сводке — ${fmt.num(cm.n_bad)}` : `, вне допуска — ${fmt.num(bad)}`}. `
			+ "Разность и допуск — по виду допуска: относительные — в процентах, абсолютные — в единице строки (доли и сдвиги — в п.п.); разность мельче знаков допуска — ноль." },
		dataTable([
			Tc("Что", (r) => wordsText(d, r.what), "name"),
			Nc("Ядро", (r) => level(r, r.core)),
			Nc("Контрольная", (r) => level(r, r.control)),
			Nc("Разница", (r) => (rel(r) ? fmt.signedPct(r.diff_rel, 2) : diffAbs(r))),
			Nc("Допуск", (r) => (r.tol_kind === "rel" ? fmt.pct(r.tol, 1) + (isNum(r.tol_abs) ? ` или ${tolAbs(r, r.tol_abs)}` : "") : tolAbs(r, r.tol))),
			Tc("", (r) => (r.ok ? badge("в допуске", "good") : badge("вне допуска", "bad"))),
		], rows));
}

function historyCard(d) {
	const h = obj(d.history);
	const q = list(h.quarters);
	if (!q.length) return none("Отчётная история", "история");
	const cats = q.map((r) => r.period);
	const ni = columnsChart(q.map((r) => ({ key: r.period, label: periodShort(r.period), value: obj(r.ifrs).ni_sh, tipTitle: periodLabel(r.period) })),
		{ height: 190, color: GREY, valueName: "млрд ₽", fmt: fmt.bn, short: () => "", label: `${shProfit(d)} по кварталам` });
	const lines = linesChart([
		{ name: "ЧПМ, упр.", color: MODEL, ...DOT, points: q.map((r) => [r.period, obj(r.mgmt).nim]) },
		{ name: "CoR, упр.", color: NEG, ...DOT, points: q.map((r) => [r.period, obj(r.mgmt).cor]) },
		{ name: "CoR, движок", color: NEG, dashed: true, points: q.map((r) => [r.period, obj(r.ifrs).cor]) },
	], { xType: "band", categories: cats, height: 190, yFmt: pct1, tipFmt: pct2, xFmt: periodShort, label: "ЧПМ и CoR по кварталам" });
	const both = bx("split",
		dx(tileLabel(`${shProfit(d)}, ${basisName("ifrs")}, млрд ₽`), ni),
		dx(tileLabel("ЧПМ и CoR"), legend([["key-line key-model", "ЧПМ, упр."], ["key-line key-neg", "CoR, упр."], ["key-line key-neg2", "CoR, движок"]]), lines));
	const fig = withTable(both, () => dataTable([
		Tc(upperFirst(modelUnit(d).one), (r) => periodLabel(r.period), "name"),
		Nc(shProfit(d), (r) => num1(obj(r.ifrs).ni_sh)),
		Nc("ROE", (r) => pct1(obj(r.ifrs).roe)),
		obj(obj(h.ltm).roe_issuer).label ? Nc("ROE эмитента", (r) => pct1(obj(r.mgmt).roe)) : null,
		Nc("ЧПМ упр.", (r) => pct2(obj(r.mgmt).nim)),
		Nc("CoR упр.", (r) => pct2(obj(r.mgmt).cor)),
		Nc(`${ci()} упр.`, (r) => pct1(obj(r.mgmt).cir)),
		Nc(capTitle(d, "n20"), pctOf("n20", 1)),
	], q.slice().reverse()));
	return card({ title: "Отчётная история", tools: fig.button, sub: "МСФО группы и управленческие метрики — раздельно; нераскрытое не рисуется: линия через него не проводится" },
		fig.box,
		list(h.gaps).length ? foot(sentence("Провалы раскрытия: " + list(h.gaps).map((g) => `${g.basis ? `${basisName(g.basis)}, ` : ""}${String(g.period).replace(/\d{4}Q[1-4]/g, (m) => periodLabel(m))} — ${ruText(g.reason)}`).join("; "))) : null,
		basisFoot(d, "profit", "roe"));
}

/* ── пояс плашек ── */

function flag(d, name) { return list(obj(d.checks).flags).find((f) => f.name === name && f.raised) || null; }
function releaseAgeHours(d) {
	const m = obj(d.meta);
	const t = Date.parse(m.published_at || m.generated_at);
	return Number.isFinite(t) ? (Date.now() - t) / 3.6e6 : null;
}

// Условия плашек — только выпуск и часы зрителя.
function banners(d) {
	const out = [];
	const m = obj(d.meta);
	const age = releaseAgeHours(d);
	if (isNum(age) && age > STALE_HOURS) out.push(plain("banner-stale", `Выпуску ${fmt.days(Math.floor(age / 24))}: опубликован ${fmt.stamp(m.published_at || m.generated_at)}, а конвейер обновляет панель каждый будний день. Числа ниже — не сегодняшние.`));
	const live = obj(d.live);
	if (live.degraded_flag) {
		const notes = list(live.degraded);
		out.push(plain("banner-degraded", [strong("Часть входов не свежая."),
			notes.length ? el("ul", { class: "reasons" }, notes.map((n) => lx(reasonText(n)))) : " Причина в выпуске не названа."]));
	}
	const say = (name, kind, extra) => {
		const f = flag(d, name);
		if (f) out.push(plain(kind, [strong(sentence(f.title || name)), f.detail ? " " + sentence(upperFirst(wordsText(d, f.detail))) : "", extra || ""]));
	};
	say("price_fallback", "banner-degraded");
	say("report_fact", "banner-event");
	const overdue = list(obj(d.checks).gates).find((g) => g.name === "manual_input_overdue" && g.fired);
	if (overdue) out.push(plain("banner-degraded", [strong(sentence(overdue.title || "Ручной вход просрочен")), " ", sentence(upperFirst(wordsText(d, overdue.message || overdue.explanation || "причина в выпуске не названа")))]));
	say("book_update", "banner-degraded");
	say("deal_pending", "banner-event");
	say("capital_estimated", "banner-info");
	say("explanation_expiring", "banner-info");
	say("policy_expired", "banner-info");
	say("ni_jump", "banner-info");
	say("dividend_register", "banner-event");
	const rec = list(obj(d.dividends).register).find((r) => r.status === "recommended");
	say("dividend_recommended", "banner-event", rec ? ` DPS ${rub2(rec.dps)} ${divLabel(rec)}; до решения собрания модель платит по политике.` : "");
	say("ras_mismatch", "banner-degraded");
	if (m.book_first_period_closed) {
		// До отчёта — справка; тревога — флаг report_fact и отставание больше чем на период.
		const nf = obj(obj(d.calendar).next_fact), head = `Первый прогнозный ${modelUnit(d).one} книги (${periodLabel(m.first_period)}) закрыт по календарю`;
		if (m.periods_closed > 1) out.push(plain("banner-degraded", `${head}, а факты и книга прежние: оценка на ${fmt.date(m.valuation_date)} считается на них.`));
		else if (!flag(d, "report_fact")) out.push(plain("banner-info", `${head}${nf.covers === m.first_period ? `, отчёт за него ожидается ${nf.confirmed ? "" : "≈" + NBSP}${fmt.date(nf.date)}` : ""}: до отчёта оценка считается на фактах ${periodLabel(m.anchor_period)} и прогнозе книги.`));
	}
	for (const r of list(obj(d.dividends).register)) {
		const left = daysBetween(m.valuation_date, r.last_buy_date);
		if ((r.status === "declared" || r.status === "recommended") && isNum(left) && left >= 0 && left <= 7) {
			// ключ без счёта дней: свёрнутая не разворачивается каждое утро, только в последний день
			out.push(plain("banner-event", `Последний день покупки скоро: дивиденд ${rub2(r.dps)} ${divLabel(r)} — ${fmt.date(r.last_buy_date)}${left === 0 ? " (сегодня)" : `, через ${fmt.days(left)}`}.`, `buy${r.last_buy_date}${left ? "" : "!"}`));
		}
	}
	const week = list(obj(d.calendar).recent).filter((e) => ["ifrs", "databook", "agm", "dividend_decision", "record", "cbr_rate", "form805", "call_option", "deal", "regulation", "investor_day"].includes(e.kind));
	if (week.length) out.push(plain("banner-info", `События недели: ${week.map((e) => `${fmt.date(e.date)} — ${lowerFirst(ruText(e.title))}${e.note ? ` (${ruText(e.note)})` : ""}`).join("; ")}.`));
	for (const k of [...folded()]) if (!out.some((n) => n.foldKey === k)) folded().delete(k);       // плашки нет — ключ не копится
	return out.length ? [bx("belt", out)] : [];
}

// Плашку сворачивают нажатием в строку-ярлык (кроме «выпуск устарел»); свёрнутое помнит браузер, пока
// у плашки тот же ключ (по умолчанию — её текст): новая или изменившаяся приходит развёрнутой.
const FOLD = "tzi-banners";
let FOLDED = null;
function folded() {
	if (!FOLDED) {
		try { FOLDED = new Set(list(JSON.parse(window.localStorage.getItem(FOLD)))); } catch (e) { FOLDED = new Set(); }
	}
	return FOLDED;
}

function plain(kind, message, key) {
	const node = el("div", { class: cls("banner", kind), role: "status" }, el("span", { class: "banner-icon", "aria-hidden": "true" }, "!"), bx("banner-body", message));
	if (kind === "banner-stale") return node;
	const id = key || node.textContent, set = folded();
	const show = () => {
		const off = set.has(id);
		node.classList[off ? "add" : "remove"]("is-folded");
		node.setAttribute("aria-expanded", String(!off));
		node.title = off ? node.textContent.slice(1) : "Свернуть";
	};
	const flip = (e) => {
		if (e.key ? e.key !== "Enter" && e.key !== " " : window.getSelection && String(window.getSelection())) return;
		e.preventDefault();
		if (!set.delete(id)) set.add(id);
		try { window.localStorage.setItem(FOLD, JSON.stringify([...set])); } catch (err) { /* нет хранилища — до перезагрузки */ }
		show();
	};
	setAttrs(node, { role: "button", tabindex: "0", on: { click: flip, keydown: flip } });
	node.foldKey = id;
	show();
	return node;
}

/* ── экраны и переходы ── */

const SCREENS = {
	overview: screenOverview,
	market: screenMarket,
	model: screenModel,
	report: screenReport,
	capital: screenCapital,
	book: screenBook,
};

const OLD_HASHES = { debt: "capital", money: "capital", value: "overview", priced: "market" };

// Битый или незнакомый хэш — «Оценка», а не исключение.
function screenFromHash() {
	let name = location.hash.replace(/^#/, "");
	try { name = decodeURIComponent(name); } catch (error) { name = ""; }
	if (Object.prototype.hasOwnProperty.call(OLD_HASHES, name)) name = OLD_HASHES[name];
	return Object.prototype.hasOwnProperty.call(SCREENS, name) ? name : "overview";
}

function syncHash(name) {
	if (location.hash.replace(/^#/, "") !== name) history.replaceState(null, "", `#${name}`);
}

function render(name) {
	const app = $("#app");
	CURRENT = name;
	hideTip();
	for (const tab of document.querySelectorAll(".tab")) {
		const on = tab.dataset.screen === name;
		tab.setAttribute("aria-selected", String(on));
		tab.tabIndex = on ? 0 : -1;
		if (on && tab.scrollIntoView) tab.scrollIntoView({ block: "nearest", inline: "nearest" });
	}
	let screen;
	RUB_DIGITS = pd(DATA);
	try {
		screen = SCREENS[name](DATA);
	} catch (error) {
		console.error(error);
		screen = bx("screen", card({ title: "Экран не отрисовался", extra: "broken" },
			pr("prose", "Ошибка витрины на этом экране; данные выпуска и остальные экраны не затронуты."),
			el("pre", { class: "fatal" }, String((error && error.stack) || error).slice(0, 800))));
	}
	let belt = [];
	try { belt = banners(DATA); } catch (error) { console.error(error); }
	app.replaceChildren(...belt, screen);
	const title = document.querySelector(`.tab[data-screen="${name}"]`);
	document.title = `${title ? title.textContent + " · " : ""}${company(DATA)} — справедливая стоимость`;
}

function go(name, push = true) {
	if (!Object.prototype.hasOwnProperty.call(SCREENS, name)) name = "overview";
	if (push && location.hash !== `#${name}`) history.pushState(null, "", `#${name}`);
	else if (!push) syncHash(name);
	render(name);
	window.scrollTo({ top: 0 });
}

function wireTabs() {
	const tabs = [...document.querySelectorAll(".tab")];
	for (const tab of tabs) {
		tab.addEventListener("click", () => { if (DATA) go(tab.dataset.screen); });
		tab.addEventListener("keydown", (e) => {
			const i = tabs.indexOf(tab);
			const next = e.key === "ArrowRight" ? tabs[(i + 1) % tabs.length] : e.key === "ArrowLeft" ? tabs[(i - 1 + tabs.length) % tabs.length]
				: e.key === "Home" ? tabs[0] : e.key === "End" ? tabs[tabs.length - 1] : null;
			if (next) { e.preventDefault(); next.focus(); if (DATA) go(next.dataset.screen); }
		});
	}
	window.addEventListener("hashchange", () => {
		if (!DATA) return;
		const name = screenFromHash();
		syncHash(name);
		if (name === CURRENT) return;
		render(name);
		window.scrollTo({ top: 0 });
	});
	const skip = $(".skip");
	if (skip) skip.addEventListener("click", (e) => { e.preventDefault(); $("#app").focus(); });
}

function wireTheme() {
	const button = $("#theme-toggle");
	if (!button) return;
	button.addEventListener("click", () => {
		const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
		document.documentElement.dataset.theme = next;
		if (window.__theme) window.__theme.remember(next);
	});
}

/* ── шапка и подвал ── */

function releaseChip(d) {
	const chip = $("#release-chip");
	if (!chip) return;
	const m = obj(d.meta);
	const age = releaseAgeHours(d);
	const warn = obj(d.live).degraded_flag || ["price_fallback", "report_fact", "book_update"].some((n) => flag(d, n))
		|| list(obj(d.checks).gates).some((g) => g.name === "manual_input_overdue" && g.fired) || m.periods_closed > 1;
	chip.dataset.state = isNum(age) && age > STALE_HOURS ? "stale" : warn ? "warn" : "ok";
	const at = m.published_at || m.generated_at;
	$(".chip-text", chip).replaceChildren(sx(sp("chip-word", "Выпуск "), `${fmt.dateShort(mskDay(at))}, ${fmt.time(at)}`), sp("chip-extra", ` · книга ${m.book_version || "—"}`));
	chip.title = chip.dataset.state === "stale" ? "Выпуск старше 96 часов" : warn ? "Есть предупреждения — см. плашки" : "Выпуск свежий";
}

function colophon(d) {
	const node = $("#colophon-release");
	const m = obj(d.meta);
	if (node) {
		node.textContent = `Модель 850 · ${company(d)} (${tickerList(d)}) · книга допущений ${m.book_version || "—"} · оценка на ${fmt.date(m.valuation_date)} · `
			+ `факты на ${fmt.date(m.facts_date)} · выпуск ${String(m.payload_sha256 || "—").slice(0, 12)} · код ${String(m.engine_commit || "—").slice(0, 7)} · контракт ${d.schema}`;
	}
	const brand = $(".brand-name");
	if (brand) brand.textContent = company(d);
}

/* ── загрузка ── */

function fatal(title, detail, lede = "Прежний выпуск остаётся на месте; витрина покажет его, как только ответ придёт.") {
	$("#app").replaceChildren(bx("fatal", el("h1", {}, title), lede ? pa(lede) : null, detail ? el("pre", {}, detail) : null));
	const chip = $("#release-chip");
	if (chip) { chip.dataset.state = "stale"; $(".chip-text", chip).textContent = "данные недоступны"; }
}

async function boot() {
	wireTips();
	wireTabs();
	wireTheme();
	let response, body;
	const abort = new AbortController();
	const timer = setTimeout(() => abort.abort(), API_TIMEOUT_MS);
	try {
		response = await fetch(API, { headers: { accept: "application/json" }, cache: "no-cache", signal: abort.signal });
		body = await response.text();
	} catch (error) {
		fatal("Данные недоступны", abort.signal.aborted ? `Сервер не ответил за ${API_TIMEOUT_MS / 1000} с` : `Сеть: ${error.message}`);
		return;
	} finally {
		clearTimeout(timer);
	}
	if (!response.ok) {
		// Два 503 двери: выпуска ещё нет — или источник не ответил.
		let reason = null;
		try { reason = obj(JSON.parse(body)).error; } catch (error) { reason = null; }
		const detail = `HTTP ${response.status} · ${String(body).slice(0, 600)}`;
		if (response.status === 503 && reason === "not published yet") fatal("Выпуск ещё не опубликован", detail, "Конвейер ещё не выложил ни одного выпуска; витрина покажет его, как только он появится.");
		else if (response.status === 503) fatal("Источник данных временно недоступен", detail);
		else fatal("Данные недоступны", detail);
		return;
	}
	try {
		DATA = JSON.parse(body);
	} catch (error) {
		fatal("Ответ не разобрался как JSON", String(body).slice(0, 400));
		return;
	}
	if (!DATA || !DATA.meta || !DATA.fair_value) {
		DATA = null;
		fatal("Выпуск без обязательных блоков", "нет meta или fair_value");
		return;
	}
	try { releaseChip(DATA); colophon(DATA); } catch (error) { console.error(error); }
	const name = screenFromHash();
	syncHash(name);
	render(name);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
