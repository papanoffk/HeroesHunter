"use strict";

// Session lives in sessionStorage: every browser tab can be logged in with its own role
// (a hero in one tab, a corporation in another) to watch notifications going both ways.
const SESSION_KEY = "hh.session";
const PAGE_SIZE = 100;

const ENTITIES = {
  resume: {
    path: "/v1/resumes",
    id: "resume_uuid",
    ownTitle: "Мои резюме",
    browseTitle: "Резюме героев",
    createTitle: "Новое резюме",
    extra: [{ name: "previous_works", label: "Предыдущие работы", tag: "textarea" }],
    people: { all: "invitations_corp_uuids", fresh: "new_invitations_corp_uuids", label: "Приглашения от корпораций" },
    action: { path: "invitation", label: "Пригласить", done: "Приглашение отправлено", conflict: "Уже приглашали" },
    filters: [
      { name: "min_offer", label: "Оплата от" },
      { name: "max_offer", label: "Оплата до" },
      { name: "min_work_experience", label: "Опыт от (лет)" },
    ],
  },
  mission: {
    path: "/v1/missions",
    id: "missions_uuid",
    ownTitle: "Мои миссии",
    browseTitle: "Миссии корпораций",
    createTitle: "Новая миссия",
    extra: [{ name: "location", label: "Локация", tag: "input", maxlength: 255 }],
    people: { all: "respondents_uuids", fresh: "new_respondents_uuids", label: "Отклики героев" },
    action: { path: "respond", label: "Откликнуться", done: "Отклик отправлен", conflict: "Уже откликались" },
    filters: [
      { name: "min_offer", label: "Оплата от" },
      { name: "max_offer", label: "Оплата до" },
      { name: "max_work_experience", label: "Опыт до (лет)" },
    ],
  },
};

const ROLES = {
  hero: {
    label: "Герой",
    own: "resume",
    browse: "mission",
    profilePath: "/v1/heroes",
    tabs: [["profile", "Профиль"], ["own", "Мои резюме"], ["browse", "Миссии"]],
  },
  corporation: {
    label: "Корпорация",
    own: "mission",
    browse: "resume",
    profilePath: "/v1/corporations",
    tabs: [["profile", "Профиль"], ["own", "Мои миссии"], ["browse", "Резюме"]],
  },
};

const state = {
  token: null,
  expiresAt: 0,
  me: null,
  powers: new Map(),
  tab: "own",
  own: new Map(),
  unseen: 0,
  filters: { resume: {}, mission: {} },
  browseOwner: null,
  ws: null,
  wsRetry: 0,
  wsTimer: null,
};

const $ = (selector) => document.querySelector(selector);

// ---------- DOM helpers ----------

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (key === "value" || key === "checked") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat().filter((c) => c != null && c !== false).map((c) => (c instanceof Node ? c : String(c))));
  return el;
}

const field = (label, input) => h("label", {}, label, input);
const short = (uuid) => String(uuid).slice(0, 8);
const fmtDate = (iso) => new Date(iso).toLocaleString("ru-RU");

function uuidTag(uuid) {
  return h("code", {
    class: "mono",
    title: `${uuid}\n(клик — скопировать)`,
    style: "cursor:pointer",
    onclick: () => navigator.clipboard?.writeText(uuid).then(() => toast("UUID скопирован")),
  }, short(uuid));
}

function toast(message, kind = "ok") {
  const el = h("div", { class: `toast ${kind}` }, message);
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "err" ? 6000 : 4000);
}

// ---------- API ----------

class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
  }
}

function formatDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => `${(e.loc ?? []).slice(1).join(".") || "body"}: ${e.msg}`).join("; ");
  }
  return JSON.stringify(detail);
}

function buildQuery(query) {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    // Lists are sent as repeated keys: powers_ids=1&powers_ids=2.
    for (const v of [value].flat()) if (v !== "" && v != null) params.append(key, v);
  }
  const str = params.toString();
  return str ? `?${str}` : "";
}

function logApi(method, url, status, ms) {
  const list = $("#api-log");
  const cls = typeof status === "number" ? `s${String(status)[0]}` : "s5";
  list.prepend(h("li", { class: cls, title: url }, `${new Date().toLocaleTimeString("ru-RU")}  ${status}  ${method} ${url}  ${ms}ms`));
  while (list.children.length > 100) list.lastChild.remove();
}

async function api(method, path, { json, form, query, raw } = {}) {
  const url = path + buildQuery(query);
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }
  const started = performance.now();
  let res;
  try {
    res = await fetch(url, { method, headers, body });
  } catch (err) {
    logApi(method, url, "NET", Math.round(performance.now() - started));
    throw new ApiError(0, `Сеть недоступна: ${err.message}`);
  }
  logApi(method, url, res.status, Math.round(performance.now() - started));
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = formatDetail((await res.json()).detail);
    } catch {}
    if (res.status === 401 && state.token) logout("Сессия истекла — войдите снова");
    throw new ApiError(res.status, `${res.status}: ${detail}`);
  }
  if (raw) return res;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

/** Services have no "owner" filter, so the owner's items are picked from the full list. */
async function fetchAll(path) {
  const items = [];
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const page = await api("GET", path, { query: { limit: PAGE_SIZE, offset } });
    items.push(...page);
    if (page.length < PAGE_SIZE || offset > 50 * PAGE_SIZE) return items;
  }
}

// ---------- Session ----------

function saveSession() {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ token: state.token, expiresAt: state.expiresAt, me: state.me }));
  } catch {}
}

function loadSession() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? "null");
    if (saved && saved.expiresAt > Date.now()) Object.assign(state, saved);
  } catch {}
}

async function login(email, password, role) {
  const token = await api("POST", "/auth/login", { json: { email, password, role } });
  state.token = token.access_token;
  state.expiresAt = Date.now() + token.expires_in * 1000;
  state.me = await api("GET", "/auth/me");
  saveSession();
  await enterApp();
}

function logout(reason) {
  closeWs();
  Object.assign(state, { token: null, expiresAt: 0, me: null, own: new Map(), unseen: 0, browseOwner: null });
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {}
  $("#feed").replaceChildren(h("li", { class: "muted" }, "Пока тихо…"));
  showAuth();
  if (reason) toast(reason, "err");
}

// ---------- Notifications WebSocket ----------

function setWsState(wsState) {
  const el = $("#ws-status");
  el.dataset.state = wsState;
  el.textContent = `WS: ${wsState}`;
}

function connectWs() {
  closeWs();
  if (!state.token) return;
  setWsState("connecting");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/v1/notifications/ws?token=${encodeURIComponent(state.token)}`);
  state.ws = ws;
  ws.onopen = () => {
    state.wsRetry = 0;
    setWsState("open");
    addFeed("system", "Подключено к уведомлениям");
  };
  ws.onmessage = (e) => handleEvent(e.data);
  ws.onclose = (e) => {
    if (state.ws !== ws) return; // closed on purpose or replaced by a new connection
    state.ws = null;
    setWsState("off");
    if (state.expiresAt <= Date.now()) return logout("Токен истёк — войдите снова");
    // The gateway rejects before the handshake completes, so the browser only sees 1006 — just retry with backoff.
    const delay = Math.min(30_000, 1000 * 2 ** state.wsRetry++);
    addFeed("system", `Соединение закрыто (${e.code}), повтор через ${delay / 1000} с`);
    state.wsTimer = setTimeout(connectWs, delay);
  };
}

function closeWs() {
  clearTimeout(state.wsTimer);
  const ws = state.ws;
  state.ws = null;
  ws?.close(1000);
  setWsState("off");
}

function ownTitle(uuid) {
  return state.own.get(uuid)?.title ?? short(uuid);
}

function describeEvent(ev) {
  switch (ev.event) {
    case "resume.invited":
      return `Корпорация ${short(ev.corp_uuid)} пригласила вас по резюме «${ownTitle(ev.resume_uuid)}»`;
    case "mission.responded":
      return `Герой ${short(ev.hero_uuid)} откликнулся на миссию «${ownTitle(ev.mission_uuid)}»`;
    default:
      return JSON.stringify(ev);
  }
}

function addFeed(event, text) {
  const feed = $("#feed");
  feed.querySelector(".muted")?.remove();
  feed.prepend(h("li", {}, h("div", { class: "muted" }, new Date().toLocaleTimeString("ru-RU"), " · ", h("b", {}, event)), text));
}

function handleEvent(data) {
  let ev;
  try {
    ev = JSON.parse(data);
  } catch {
    return addFeed("raw", data);
  }
  const text = describeEvent(ev);
  addFeed(ev.event ?? "event", text);
  toast(text, "event");
  if (state.tab === "own") {
    render(ev.resume_uuid ?? ev.mission_uuid);
  } else {
    state.unseen++;
    renderNav();
  }
}

// ---------- Views ----------

function showAuth() {
  $("#session").classList.add("hidden");
  $("#app-view").classList.add("hidden");
  $("#auth-view").classList.remove("hidden");
}

async function enterApp() {
  $("#auth-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#session").classList.remove("hidden");
  const role = state.me.role;
  $("#me-role").textContent = ROLES[role].label;
  $("#me-role").className = `badge ${role}`;
  $("#me-email").textContent = state.me.email;
  state.tab = "own";
  connectWs();
  try {
    const powers = await api("GET", "/v1/heroes/powers");
    state.powers = new Map(powers.map((p) => [p.power_id, p.title]));
  } catch (err) {
    toast(`Не удалось загрузить способности: ${err.message}`, "err");
  }
  render();
}

function renderNav() {
  const tabs = ROLES[state.me.role].tabs.map(([key, label]) =>
    h("button", {
      class: `tab ${state.tab === key ? "active" : ""}`,
      onclick: () => {
        state.tab = key;
        if (key !== "browse") state.browseOwner = null;
        render();
      },
    }, label, key === "own" && state.unseen ? h("span", { class: "badge new", style: "margin-left:6px" }, state.unseen) : null),
  );
  $("#nav").replaceChildren(...tabs);
}

async function render(flashId) {
  if (!state.me) return;
  if (state.tab === "own") state.unseen = 0;
  renderNav();
  const root = $("#content");
  root.replaceChildren(h("div", { class: "card muted" }, "Загрузка…"));
  const view = { profile: profileView, own: ownView, browse: browseView }[state.tab];
  try {
    root.replaceChildren(...(await view(flashId)));
  } catch (err) {
    root.replaceChildren(h("div", { class: "card" }, h("p", { class: "hint" }, err.message)));
  }
}

function powersPicker(selected = []) {
  if (!state.powers.size) return h("span", { class: "muted" }, "Список способностей недоступен");
  return h("div", { class: "powers" },
    [...state.powers].map(([id, title]) =>
      h("label", {}, h("input", { type: "checkbox", name: "powers_ids", value: id, checked: selected.includes(id) }), title),
    ),
  );
}

const checkedPowers = (form) => [...form.querySelectorAll("input[name=powers_ids]:checked")].map((i) => Number(i.value));
const powerChips = (ids) => ids.map((id) => h("span", { class: "chip" }, state.powers.get(id) ?? `#${id}`));
const numberOrNull = (value) => (value === "" ? null : Number(value));

function itemMeta(kind, item) {
  return h("div", { class: "item-meta" },
    h("span", {}, "Оплата: ", item.offer ?? "—"),
    h("span", {}, "Опыт: ", item.work_experience, " лет"),
    kind === "mission" ? h("span", {}, "Локация: ", item.location ?? "—") : null,
    h("span", {}, "Создано: ", fmtDate(item.created_at)),
    h("span", {}, "ID: ", uuidTag(item[ENTITIES[kind].id])),
  );
}

function itemBody(kind, item) {
  return [
    item.descriptions ? h("div", { class: "item-body" }, item.descriptions) : null,
    kind === "resume" && item.previous_works ? h("div", { class: "item-body muted" }, "Работы: ", item.previous_works) : null,
    item.powers_ids.length ? h("div", {}, powerChips(item.powers_ids)) : null,
  ];
}

// --- Own resumes (hero) / missions (corporation) ---

function entityForm(kind, item, onClose) {
  const cfg = ENTITIES[kind];
  const hint = h("p", { class: "hint" });
  const form = h("form", { class: "form item" },
    h("h3", {}, item ? `Редактирование «${item.title}»` : cfg.createTitle),
    field("Название *", h("input", { name: "title", required: true, maxlength: 200, value: item?.title ?? "" })),
    field("Описание", h("textarea", { name: "descriptions", value: item?.descriptions ?? "" })),
    cfg.extra.map((f) => field(f.label, h(f.tag, { name: f.name, maxlength: f.maxlength, value: item?.[f.name] ?? "" }))),
    h("div", { class: "row" },
      field("Опыт (лет)", h("input", { name: "work_experience", type: "number", min: 0, value: item?.work_experience ?? 0 })),
      field("Оплата", h("input", { name: "offer", type: "number", min: 0, value: item?.offer ?? "" })),
    ),
    field("Способности", powersPicker(item?.powers_ids)),
    hint,
    h("div", { class: "actions" },
      h("button", { type: "submit", class: "primary" }, item ? "Сохранить" : "Создать"),
      h("button", { type: "button", onclick: onClose }, "Отмена"),
    ),
  );
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(form);
    const body = {
      title: data.get("title").trim(),
      descriptions: data.get("descriptions").trim() || null,
      work_experience: Number(data.get("work_experience") || 0),
      offer: numberOrNull(data.get("offer")),
      powers_ids: checkedPowers(form),
    };
    for (const f of cfg.extra) body[f.name] = data.get(f.name).trim() || null;
    try {
      if (item) await api("PATCH", `${cfg.path}/${item[cfg.id]}`, { json: body });
      else await api("POST", cfg.path, { json: body });
      toast(item ? "Сохранено" : "Создано");
      render();
    } catch (err) {
      hint.textContent = err.message;
    }
  });
  return form;
}

function peopleSection(kind, item) {
  const cfg = ENTITIES[kind];
  const all = item[cfg.people.all] ?? [];
  const fresh = new Set(item[cfg.people.fresh] ?? []);
  // Invitations come from corporations → look at their missions; respondents are heroes → at their resumes.
  const otherLabel = kind === "resume" ? "миссии" : "резюме";
  return h("div", { class: "people" },
    h("div", { class: "item-meta" }, h("b", {}, `${cfg.people.label}: ${all.length}`), fresh.size ? h("span", { class: "badge new" }, `новых: ${fresh.size}`) : null),
    all.length
      ? h("ul", {}, all.map((uuid) =>
          h("li", {},
            uuidTag(uuid),
            fresh.has(uuid) ? h("span", { class: "badge new" }, "new") : null,
            h("button", { class: "ghost small", onclick: () => { state.browseOwner = uuid; state.tab = "browse"; render(); } }, `${otherLabel} владельца →`),
          )))
      : null,
    fresh.size
      ? h("button", {
          class: "small",
          onclick: async () => {
            try {
              await api("POST", `${cfg.path}/${item[cfg.id]}/view`, { json: { [cfg.people.all]: [...fresh] } });
              render();
            } catch (err) {
              toast(err.message, "err");
            }
          },
        }, "Отметить просмотренными")
      : null,
  );
}

async function ownView(flashId) {
  const kind = ROLES[state.me.role].own;
  const cfg = ENTITIES[kind];
  const formSlot = h("div");
  const items = (await fetchAll(cfg.path)).filter((i) => i.owner_uuid === state.me.client_id);
  state.own = new Map(items.map((i) => [i[cfg.id], i]));

  const openForm = (item) => formSlot.replaceChildren(entityForm(kind, item, () => formSlot.replaceChildren()));
  const cards = items.map((item) =>
    h("div", { class: `item ${item[cfg.id] === flashId ? "flash" : ""}` },
      h("div", { class: "item-head" },
        h("div", { class: "item-title" }, item.title),
        h("div", { class: "item-actions" },
          h("button", { class: "small", onclick: () => { openForm(item); formSlot.scrollIntoView({ behavior: "smooth" }); } }, "Редактировать"),
          h("button", {
            class: "small danger",
            onclick: async () => {
              if (!confirm(`Удалить «${item.title}»?`)) return;
              try {
                await api("DELETE", `${cfg.path}/${item[cfg.id]}`);
                toast("Удалено");
                render();
              } catch (err) {
                toast(err.message, "err");
              }
            },
          }, "Удалить"),
        ),
      ),
      itemMeta(kind, item),
      itemBody(kind, item),
      peopleSection(kind, item),
    ),
  );

  return [
    h("div", { class: "card" },
      h("div", { class: "item-head" },
        h("h2", {}, cfg.ownTitle),
        h("div", { class: "item-actions" },
          h("button", { class: "ghost", onclick: () => render() }, "Обновить"),
          h("button", { class: "primary", onclick: () => openForm(null) }, "+ Создать"),
        ),
      ),
      formSlot,
      h("div", { class: "list" }, cards.length ? cards : h("p", { class: "muted" }, "Пока ничего нет — создайте первое.")),
    ),
  ];
}

// --- Browse missions (hero) / resumes (corporation) ---

async function browseView() {
  const kind = ROLES[state.me.role].browse;
  const cfg = ENTITIES[kind];
  const filters = state.filters[kind];
  const owner = state.browseOwner;

  const filtersForm = h("form", { class: "filters" },
    cfg.filters.map((f) => field(f.label, h("input", { name: f.name, type: "number", min: 0, value: filters[f.name] ?? "" }))),
    h("button", { type: "submit", class: "primary" }, "Искать"),
    h("button", { type: "button", onclick: () => { state.filters[kind] = {}; render(); } }, "Сбросить"),
  );
  const powersForm = h("div", { style: "margin-top:10px" }, powersPicker(filters.powers_ids ?? []));
  filtersForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const data = new FormData(filtersForm);
    state.filters[kind] = {
      ...Object.fromEntries(cfg.filters.map((f) => [f.name, data.get(f.name)])),
      powers_ids: checkedPowers(powersForm),
    };
    render();
  });

  let items;
  if (owner) {
    items = (await fetchAll(cfg.path)).filter((i) => i.owner_uuid === owner);
  } else {
    items = await api("GET", cfg.path, { query: { ...filters, limit: PAGE_SIZE } });
  }

  const cards = items.map((item) => {
    const mine = item.owner_uuid === state.me.client_id;
    return h("div", { class: "item" },
      h("div", { class: "item-head" },
        h("div", { class: "item-title" }, item.title),
        mine
          ? h("span", { class: "muted" }, "ваше")
          : h("button", {
              class: "primary small",
              onclick: async (e) => {
                try {
                  await api("POST", `${cfg.path}/${item[cfg.id]}/${cfg.action.path}`);
                  toast(cfg.action.done);
                  e.target.disabled = true;
                  e.target.textContent = "✓";
                } catch (err) {
                  toast(err.status === 409 ? cfg.action.conflict : err.message, err.status === 409 ? "ok" : "err");
                }
              },
            }, cfg.action.label),
      ),
      h("div", { class: "item-meta" }, h("span", {}, kind === "resume" ? "Герой: " : "Корпорация: ", uuidTag(item.owner_uuid))),
      itemMeta(kind, item),
      itemBody(kind, item),
    );
  });

  return [
    h("div", { class: "card" },
      h("h2", {}, cfg.browseTitle),
      owner
        ? h("div", { class: "item-meta" },
            h("span", {}, "Только владельца ", uuidTag(owner)),
            h("button", { class: "ghost small", onclick: () => { state.browseOwner = null; render(); } }, "✕ показать все"),
          )
        : [filtersForm, powersForm],
    ),
    h("div", { class: "list" }, cards.length ? cards : h("div", { class: "card muted" }, "Ничего не найдено")),
  ];
}

// --- Profile (hero / corporation card) ---

async function loadImage(url, img) {
  try {
    const blob = await (await api("GET", url, { raw: true })).blob();
    img.src = URL.createObjectURL(blob);
  } catch {}
}

async function profileView() {
  const role = state.me.role;
  const isCorp = role === "corporation";
  const path = `${ROLES[role].profilePath}/${state.me.client_id}`;
  let profile = null;
  try {
    profile = await api("GET", path);
  } catch (err) {
    if (err.status !== 404) throw err;
  }

  const account = h("div", { class: "card" },
    h("h2", {}, "Аккаунт"),
    h("div", { class: "item-meta" },
      h("span", {}, "client_id: ", uuidTag(state.me.client_id)),
      h("span", {}, "email: ", state.me.email),
      h("span", {}, "роль: ", state.me.role),
      h("span", {}, "зарегистрирован: ", fmtDate(state.me.created_at)),
      h("span", {}, "токен до: ", new Date(state.expiresAt).toLocaleTimeString("ru-RU")),
    ),
  );

  const hint = h("p", { class: "hint" });
  const form = h("form", { class: "form" },
    field(profile ? "Имя" : "Имя *", h("input", { name: "name", required: !profile, maxlength: isCorp ? 150 : 100, value: profile?.name ?? "" })),
    isCorp ? field("Описание", h("textarea", { name: "description", value: profile?.description ?? "" })) : null,
    field("Картинка (PNG/JPEG/GIF/WebP)", h("input", { name: "image", type: "file", accept: "image/png,image/jpeg,image/gif,image/webp" })),
    hint,
    h("div", { class: "actions" }, h("button", { type: "submit", class: "primary" }, profile ? "Сохранить" : "Создать профиль")),
  );
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(form);
    if (!data.get("image")?.size) data.delete("image");
    if (!profile) data.append("client_uuid", state.me.client_id);
    try {
      await api(profile ? "PATCH" : "POST", profile ? path : ROLES[role].profilePath, { form: data });
      toast(profile ? "Профиль обновлён" : "Профиль создан");
      render();
    } catch (err) {
      hint.textContent = err.message;
    }
  });

  const img = h("img", { class: "avatar", alt: "" });
  if (profile?.image_url) loadImage(profile.image_url, img);

  return [
    account,
    h("div", { class: "card" },
      h("h2", {}, isCorp ? "Профиль корпорации" : "Профиль героя"),
      profile
        ? h("div", { class: "profile", style: "margin-bottom:16px" },
            img,
            h("div", {}, h("div", { class: "item-title" }, profile.name), isCorp && profile.description ? h("div", { class: "item-body" }, profile.description) : null),
          )
        : h("p", { class: "muted" }, "Профиль ещё не создан."),
      form,
    ),
  ];
}

// ---------- Auth form ----------

function setupAuthForm() {
  let mode = "login";
  const form = $("#auth-form");
  const hint = $("#auth-hint");
  for (const tab of document.querySelectorAll("#auth-tabs .tab")) {
    tab.addEventListener("click", () => {
      mode = tab.dataset.mode;
      document.querySelectorAll("#auth-tabs .tab").forEach((t) => t.classList.toggle("active", t === tab));
      $("#auth-submit").textContent = mode === "login" ? "Войти" : "Зарегистрироваться";
      form.password.minLength = mode === "register" ? 8 : 0;
      form.password.autocomplete = mode === "register" ? "new-password" : "current-password";
      hint.textContent = "";
    });
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hint.textContent = "";
    const { email, password, role } = Object.fromEntries(new FormData(form));
    const submit = $("#auth-submit");
    submit.disabled = true;
    try {
      if (mode === "register") {
        await api("POST", "/auth/register", { json: { email, password, role } });
        toast("Регистрация успешна");
      }
      await login(email, password, role);
      form.password.value = "";
    } catch (err) {
      hint.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
}

// ---------- Bootstrap ----------

document.addEventListener("DOMContentLoaded", async () => {
  setupAuthForm();
  $("#logout").addEventListener("click", () => logout());
  $("#ws-toggle").addEventListener("click", () => {
    state.wsRetry = 0;
    connectWs();
  });
  loadSession();
  if (!state.token) return showAuth();
  try {
    state.me = await api("GET", "/auth/me");
    saveSession();
    await enterApp();
  } catch {
    if (state.token) logout();
  }
});
