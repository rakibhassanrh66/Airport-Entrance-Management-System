/* Airport Operations — demo UI.
 *
 * Talks to the API deployed on Render. The UI holds no logic of its own worth
 * the name: every rule it appears to enforce is enforced server-side, and the
 * point of the race demo is that this page cannot cheat even if it wanted to.
 */

const API =
  new URLSearchParams(location.search).get("api") ||
  "https://airport-entrance-management-system.onrender.com";

// A demo credential for a demo deployment holding demo data. It is in the
// README too. Everything it can reach is seeded and disposable.
const DEMO = { email: "admin@airport.example.com", password: "AirportDemo2026!" };

const $ = (id) => document.getElementById(id);
const state = {
  token: null, flights: [], flight: null,
  taken: new Set(), mine: new Set(),
  capacity: 0, available: 0,
};

/* ── plumbing ─────────────────────────────────────────────── */

async function api(method, path, body, token = state.token) {
  const r = await fetch(API + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await r.json(); } catch { /* 204 and friends */ }
  return { status: r.status, ok: r.ok, data };
}

function conn(kind, text) {
  $("dot").className = "dot " + kind;
  $("conn-text").textContent = text;
}

/* ── boot ─────────────────────────────────────────────────── */

async function boot() {
  $("api-host").textContent = new URL(API).host;
  $("docs-link").href = API + "/docs";
  conn("wait", "waking…");

  // The free instance sleeps. Say so rather than looking broken for 50 seconds.
  const slow = setTimeout(() => $("waking").classList.remove("hidden"), 2500);
  try {
    await api("GET", "/health", null, null);
  } catch {
    clearTimeout(slow);
    $("waking").classList.add("hidden");
    conn("bad", "unreachable");
    $("flights").innerHTML =
      `<div class="loading">Could not reach <code>${API}</code>. It may still be waking — reload in a moment.</div>`;
    return;
  }
  clearTimeout(slow);
  $("waking").classList.add("hidden");

  const login = await api("POST", "/api/v1/auth/login", DEMO, null);
  if (!login.ok) {
    conn("bad", "login failed");
    $("flights").innerHTML = `<div class="loading">Login rejected: ${login.data?.message || login.status}</div>`;
    return;
  }
  state.token = login.data.access_token;
  conn("ok", "connected");

  await loadFlights();
}

/* ── departures ───────────────────────────────────────────── */

async function loadFlights() {
  const r = await api("GET", "/api/v1/flights?limit=20");
  if (!r.ok) { $("flights").innerHTML = `<div class="loading">Could not load flights.</div>`; return; }

  state.flights = r.data.items || r.data;
  if (!state.flights.length) { $("flights").innerHTML = `<div class="loading">No flights seeded.</div>`; return; }

  $("flights").innerHTML = state.flights.map((f) => `
    <div class="board-row" data-id="${f.id}">
      <span class="flightno">${f.flight_number}</span>
      <span class="route">${f.source}<span class="arrow">→</span>${f.destination}</span>
      <span class="when">${fmt(f.departure_time)}</span>
      <span><span class="pill ${f.status}">${f.status}</span></span>
      <span><button class="btn sm">seats</button></span>
    </div>`).join("");

  $("flights").querySelectorAll(".board-row").forEach((row) =>
    row.addEventListener("click", () => selectFlight(+row.dataset.id)));

  selectFlight(state.flights[0].id);
}

const fmt = (iso) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

/* ── seat map ─────────────────────────────────────────────── */

async function selectFlight(id) {
  state.flight = state.flights.find((f) => f.id === id);
  state.mine.clear();

  document.querySelectorAll(".board-row").forEach((r) =>
    r.classList.toggle("sel", +r.dataset.id === id));

  $("seat-panel").hidden = false;
  $("life-panel").hidden = false;
  $("seat-flight").textContent = state.flight.flight_number;
  $("race-out").classList.add("hidden");
  $("life-out").classList.add("hidden");

  renderLifecycle();

  $("cabin").innerHTML = `<div class="loading">loading seat map…</div>`;
  const r = await api("GET", `/api/v1/flights/${id}/seats`);
  if (!r.ok) { $("cabin").innerHTML = `<div class="loading">Could not load seats.</div>`; return; }

  // The endpoint returns booked_seats / seats_available / seat_capacity.
  // Reading a field that does not exist yields undefined, an empty Set, and a
  // seat map that cheerfully draws every seat as free — wrong, and convincing.
  state.taken = new Set(r.data.booked_seats || []);
  state.capacity = r.data.seat_capacity;
  state.available = r.data.seats_available;
  renderCabin();
}

function renderCabin() {
  const ROWS = 12, COLS = ["A", "B", "C", "D", "E", "F"];
  // Counts describe the whole aircraft; the grid only draws the first 12 rows,
  // so say both rather than implying 72 seats is the flight.
  const booked = state.capacity - state.available;
  $("seat-count").textContent =
    `${booked} booked · ${state.available} of ${state.capacity} free (showing rows 1–${ROWS})`;

  let html = "";
  for (let row = 1; row <= ROWS; row++) {
    html += `<div class="seat-row"><span class="row-no">${row}</span>`;
    COLS.forEach((col, i) => {
      const seat = `${row}${col}`;
      const taken = state.taken.has(seat);
      const mine = state.mine.has(seat);
      const cls = mine ? "mine" : taken ? "taken" : "";
      html += `<button class="seat ${cls}" data-seat="${seat}" ${taken && !mine ? "disabled" : ""}>${seat}</button>`;
      if (i === 2) html += `<span class="aisle"></span>`;
    });
    html += `</div>`;
  }
  $("cabin").innerHTML = html;

  $("cabin").querySelectorAll(".seat:not([disabled])").forEach((b) =>
    b.addEventListener("click", () => bookSeat(b.dataset.seat)));

  $("race-seat").textContent = firstFreeSeat() || "—";
  $("race-btn").disabled = !firstFreeSeat();
}

function firstFreeSeat() {
  const ROWS = 12, COLS = ["A", "B", "C", "D", "E", "F"];
  for (let row = 1; row <= ROWS; row++)
    for (const col of COLS) {
      const s = `${row}${col}`;
      if (!state.taken.has(s)) return s;
    }
  return null;
}

async function bookSeat(seat) {
  const r = await api("POST", "/api/v1/tickets", {
    flight_id: state.flight.id, passenger_id: 1, seat_number: seat,
    ticket_class: "economy", price: "450.00",
  });
  if (r.ok) { state.taken.add(seat); state.mine.add(seat); state.available--; }
  else if (r.status === 409) { state.taken.add(seat); state.available--; alert(r.data?.message || "Seat taken."); }
  else { alert(r.data?.message || `Booking failed (${r.status}).`); }
  renderCabin();
}

/* ── the race ─────────────────────────────────────────────── */

/** A passenger with no ticket on this flight yet.
 *
 * Reusing the seeded passengers looks fine and quietly demonstrates the wrong
 * rule: a passenger may hold only one live ticket per flight, so a rerun trips
 * *that* constraint and the loser says "This passenger already holds a live
 * ticket on this flight". Still a 409 — but not the seat conflict this is
 * meant to prove. Fresh passengers leave the seat as the only rule to break.
 */
async function freshPassenger(tag) {
  const n = Date.now().toString().slice(-7) + tag;
  const r = await api("POST", "/api/v1/passengers", {
    first_name: `Racer${tag}`,
    last_name: `Demo${n}`,
    date_of_birth: "1995-05-05",
    passport_number: `RC${n}`,
    nationality: "Bangladesh",
  });
  return r.ok ? r.data.id : null;
}

$("race-btn").addEventListener("click", async () => {
  const seat = firstFreeSeat();
  if (!seat) return;

  const btn = $("race-btn");
  btn.disabled = true;
  btn.textContent = "preparing…";
  document.querySelector(`.seat[data-seat="${seat}"]`)?.classList.add("racing");

  const [pa, pb] = await Promise.all([freshPassenger("A"), freshPassenger("B")]);
  if (!pa || !pb) {
    btn.textContent = "Run the race";
    btn.disabled = false;
    alert("Could not create demo passengers.");
    return;
  }

  btn.textContent = "racing…";
  const shoot = (passenger_id) =>
    api("POST", "/api/v1/tickets", {
      flight_id: state.flight.id, passenger_id, seat_number: seat,
      ticket_class: "economy", price: "450.00",
    });

  // Promise.all fires both without awaiting the first. Two separate HTTP
  // connections, in flight simultaneously — the browser cannot serialise them
  // into a safe order, which is the whole point.
  const [a, b] = await Promise.all([shoot(pa), shoot(pb)]);

  $("race-out").classList.remove("hidden");
  paint($("res-a"), "Request A", a);
  paint($("res-b"), "Request B", b);

  const codes = [a.status, b.status].sort();
  const loser = a.status === 409 ? a : b;
  const oneEach = codes[0] === 201 && codes[1] === 409;
  // Assert the loser lost on the *seat*, not on some other 409. Claiming the
  // seat rule while showing a different constraint is the kind of thing an
  // interviewer reads the error message and catches.
  const onSeat = oneEach && /seat/i.test(loser.data?.message || "");

  $("verdict").innerHTML = onSeat
    ? `<b>Exactly one won.</b> Both requests were in flight at the same instant, from two passengers with no other booking — so the only rule left to break was the seat. PostgreSQL rejected the loser with <code>409</code>. No application code made that call.`
    : oneEach
      ? `<b>One won, but not on the seat rule.</b> The loser said “${loser.data?.message}” — a different constraint. Reload and try a clean seat.`
      : `<b>Unexpected:</b> got ${codes.join(" and ")}, expected 201 and 409.`;

  state.taken.add(seat);
  if (a.ok || b.ok) { state.mine.add(seat); state.available--; }
  renderCabin();

  btn.textContent = "Run the race";
  btn.disabled = !firstFreeSeat();
});

function paint(el, who, r) {
  const won = r.status === 201;
  el.className = "result " + (won ? "won" : "lost");
  el.innerHTML =
    `<span class="who">${who}</span>` +
    `<span class="code">${r.status}</span>` +
    `<span class="msg">${won ? `booked seat ${r.data.seat_number} · ticket #${r.data.id}` : (r.data?.message || "rejected")}</span>`;
}

/* ── lifecycle ────────────────────────────────────────────── */

const NEXT = {
  scheduled: ["boarding", "delayed", "cancelled"],
  delayed:   ["delayed", "boarding", "cancelled"],
  boarding:  ["departed", "cancelled"],
  departed:  ["completed"],
  completed: [], cancelled: [],
};

function renderLifecycle() {
  const f = state.flight;
  $("life-flight").textContent = f.flight_number;
  $("life-status").textContent = f.status;
  $("life-status").className = "pill " + f.status;

  // Deliberately offers every status, including illegal ones. Letting the
  // server say no is the demo; a UI that greys out the illegal buttons hides
  // the thing worth showing.
  const all = ["scheduled", "delayed", "boarding", "departed", "completed", "cancelled"];
  $("life-btns").innerHTML = all
    .filter((s) => s !== f.status)
    .map((s) => {
      const legal = (NEXT[f.status] || []).includes(s);
      return `<button class="btn sm" data-to="${s}" title="${legal ? "legal move" : "server will reject this"}">${s}${legal ? "" : " ⚠"}</button>`;
    }).join("");

  $("life-btns").querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => moveTo(b.dataset.to)));
}

async function moveTo(status) {
  const r = await api("PATCH", `/api/v1/flights/${state.flight.id}/status`, { status });
  const out = $("life-out");
  out.classList.remove("hidden");
  out.className = "resp " + (r.ok ? "ok" : "err");
  out.textContent = `${r.status}\n\n` + JSON.stringify(r.data, null, 2);

  if (r.ok) {
    state.flight.status = r.data.status;
    const row = document.querySelector(`.board-row[data-id="${state.flight.id}"] .pill`);
    if (row) { row.textContent = r.data.status; row.className = "pill " + r.data.status; }
    renderLifecycle();
  }
}

boot();
