/* Belgrade Waterfront listings dashboard — pure client-side, reads data/*.json */
(() => {
  "use strict";

  const LAYOUT_ORDER = ["Studio", "1-Bedroom", "1.5-Bedroom", "2-Bedroom", "2.5-Bedroom",
                         "3-Bedroom", "3.5-Bedroom", "4-Bedroom", "5+-Bedroom", "Unspecified"];

  const SERIES = () => {
    const cs = getComputedStyle(document.documentElement);
    return [1, 2, 3, 4, 5, 6, 7, 8].map(i => cs.getPropertyValue(`--series-${i}`).trim());
  };
  const ink = (role) => getComputedStyle(document.documentElement).getPropertyValue(`--text-${role}`).trim();
  const gridColor = () => getComputedStyle(document.documentElement).getPropertyValue("--grid").trim();

  const state = {
    sale: [], rent: [], meta: {}, leaderboard: {}, history: {},
    filters: {
      priceMin: "", priceMax: "", sizeMin: "", sizeMax: "", psqmMin: "", psqmMax: "",
      floorMin: "", floorMax: "", rooms: "", building: "", agency: "", section: "",
      seller: "all", offplan: "all", dupOnly: false, search: "",
    },
    sort: { key: "scraped_at", dir: "desc" },
    page: 1,
    pageSize: 25,
    roi: { vacancy: 8, mgmtFee: 10, maintenance: 1, otherAnnual: 300, sizeTolerance: 20 },
    roiSort: { key: "gross_yield_pct", dir: "desc" },
    charts: {},
  };

  const fmtEUR = (n) => n == null || isNaN(n) ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);
  const fmtNum = (n, d = 0) => n == null || isNaN(n) ? "—" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
  const fmtPct = (n) => n == null || isNaN(n) ? "—" : `${fmtNum(n, 1)}%`;

  function median(nums) {
    const arr = nums.filter((n) => n != null && !isNaN(n)).sort((a, b) => a - b);
    if (!arr.length) return null;
    const mid = Math.floor(arr.length / 2);
    return arr.length % 2 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
  }
  const avg = (nums) => {
    const arr = nums.filter((n) => n != null && !isNaN(n));
    return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
  };
  const uniqueSorted = (arr, key) => [...new Set(arr.map((x) => x[key]).filter(Boolean))].sort();

  async function loadJSON(path, fallback) {
    try {
      const res = await fetch(path, { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      return await res.json();
    } catch (e) {
      console.warn("Could not load", path, e);
      return fallback;
    }
  }

  async function loadAll() {
    const [sale, rent, meta, leaderboard, history] = await Promise.all([
      loadJSON("data/listings_sale_latest.json", []),
      loadJSON("data/listings_rent_latest.json", []),
      loadJSON("data/meta.json", {}),
      loadJSON("data/agency_leaderboard.json", {}),
      loadJSON("data/history_summary.json", { new_today: [], removed_vs_7d: [], daily_new_counts: [] }),
    ]);
    state.sale = sale; state.rent = rent; state.meta = meta;
    state.leaderboard = leaderboard; state.history = history;

    const metaLine = document.getElementById("meta-line");
    if (!sale.length && !rent.length) {
      metaLine.textContent = "No data yet — the scheduled scraper hasn't produced data/*.json in this branch yet.";
    } else {
      const when = meta.last_run_utc ? new Date(meta.last_run_utc).toLocaleString() : "unknown";
      metaLine.textContent = `${sale.length} sale · ${rent.length} rental listings · last scraped ${when}`;
    }
  }

  // ---------- filtering / sorting ----------
  function applyFilters(list) {
    const f = state.filters;
    return list.filter((l) => {
      if (f.priceMin && (l.price_eur ?? -Infinity) < +f.priceMin) return false;
      if (f.priceMax && (l.price_eur ?? Infinity) > +f.priceMax) return false;
      if (f.sizeMin && (l.size_sqm ?? -Infinity) < +f.sizeMin) return false;
      if (f.sizeMax && (l.size_sqm ?? Infinity) > +f.sizeMax) return false;
      if (f.psqmMin && (l.price_per_sqm_eur ?? -Infinity) < +f.psqmMin) return false;
      if (f.psqmMax && (l.price_per_sqm_eur ?? Infinity) > +f.psqmMax) return false;
      if (f.floorMin && (l.floor_numeric ?? -Infinity) < +f.floorMin) return false;
      if (f.floorMax && (l.floor_numeric ?? Infinity) > +f.floorMax) return false;
      if (f.rooms && l.rooms_category !== f.rooms) return false;
      if (f.building && (l.building || "Unspecified") !== f.building) return false;
      if (f.agency && (l.agency_name || "Unknown") !== f.agency) return false;
      if (f.section && (l.section || "Unspecified") !== f.section) return false;
      if (f.seller === "owner" && !l.is_owner) return false;
      if (f.seller === "agency" && l.is_owner) return false;
      if (f.offplan === "offplan" && l.off_plan !== true) return false;
      if (f.offplan === "resale" && l.off_plan !== false) return false;
      if (f.dupOnly && !l.is_duplicate) return false;
      if (f.search) {
        const hay = `${l.title || ""} ${l.description || ""} ${l.address || ""}`.toLowerCase();
        if (!hay.includes(f.search.toLowerCase())) return false;
      }
      return true;
    });
  }

  function sortList(list, sortState) {
    const { key, dir } = sortState;
    const mul = dir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => {
      let va = a[key], vb = b[key];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "string") return va.localeCompare(vb) * mul;
      return (va - vb) * mul;
    });
  }

  // ---------- KPIs ----------
  function renderKPIs() {
    const sale = state.sale;
    const active = sale.length;
    const psqm = median(sale.map((l) => l.price_per_sqm_eur));
    const owners = sale.filter((l) => l.is_owner).length;
    const dupGroups = new Set(sale.filter((l) => l.is_duplicate).map((l) => l.duplicate_group_id)).size;
    const newToday = (state.history.new_today || []).filter((l) => l.ad_type === "prodaja").length;
    const offplan = sale.filter((l) => l.off_plan === true).length;

    const tiles = [
      ["Active sale listings", fmtNum(active)],
      ["Median €/m²", psqm ? fmtEUR(psqm) : "—"],
      ["Owner-listed", `${fmtNum(owners)} (${active ? fmtPct((owners / active) * 100) : "—"})`],
      ["Duplicate groups", fmtNum(dupGroups)],
      ["Off-plan units", fmtNum(offplan)],
      ["New today", fmtNum(newToday)],
      ["Rental comps tracked", fmtNum(state.rent.length)],
    ];
    document.getElementById("kpi-row").innerHTML = tiles.map(([label, val]) => `
      <div class="kpi-tile"><div class="kpi-value">${val}</div><div class="kpi-label">${label}</div></div>
    `).join("");
  }

  // ---------- charts ----------
  function destroyChart(id) {
    if (state.charts[id]) { state.charts[id].destroy(); delete state.charts[id]; }
  }

  function baseOptions(extra = {}) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false, labels: { color: ink("secondary") } },
        tooltip: { enabled: true },
      },
      scales: {
        x: { ticks: { color: ink("secondary") }, grid: { color: gridColor() } },
        y: { ticks: { color: ink("secondary") }, grid: { color: gridColor() }, beginAtZero: true },
      },
      ...extra,
    };
  }

  function groupCountsByLayout(list) {
    const counts = Object.fromEntries(LAYOUT_ORDER.map((k) => [k, 0]));
    for (const l of list) counts[l.layout_group || "Unspecified"] = (counts[l.layout_group || "Unspecified"] || 0) + 1;
    return LAYOUT_ORDER.filter((k) => counts[k] > 0).map((k) => [k, counts[k]]);
  }

  function renderOverviewCharts() {
    const sale = state.sale;
    const colors = SERIES();

    // 1. count by layout
    destroyChart("layoutCount");
    const layoutCounts = groupCountsByLayout(sale);
    state.charts.layoutCount = new Chart(document.getElementById("chart-layout-count"), {
      type: "bar",
      data: { labels: layoutCounts.map((d) => d[0]), datasets: [{ data: layoutCounts.map((d) => d[1]), backgroundColor: colors[0], borderRadius: 4, maxBarThickness: 38 }] },
      options: baseOptions(),
    });

    // 2. median psqm by layout
    destroyChart("layoutPsqm");
    const byLayout = {};
    for (const l of sale) {
      const k = l.layout_group || "Unspecified";
      (byLayout[k] = byLayout[k] || []).push(l.price_per_sqm_eur);
    }
    const psqmData = LAYOUT_ORDER.filter((k) => byLayout[k]?.length).map((k) => [k, median(byLayout[k])]);
    state.charts.layoutPsqm = new Chart(document.getElementById("chart-layout-psqm"), {
      type: "bar",
      data: { labels: psqmData.map((d) => d[0]), datasets: [{ data: psqmData.map((d) => Math.round(d[1] || 0)), backgroundColor: colors[1], borderRadius: 4, maxBarThickness: 38 }] },
      options: baseOptions({ plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => fmtEUR(ctx.parsed.y) } } } }),
    });

    // 3. owner vs agency
    destroyChart("ownerAgency");
    const owners = sale.filter((l) => l.is_owner).length;
    const agencies = sale.length - owners;
    state.charts.ownerAgency = new Chart(document.getElementById("chart-owner-agency"), {
      type: "doughnut",
      data: { labels: ["Agency", "Owner"], datasets: [{ data: [agencies, owners], backgroundColor: [colors[0], colors[2]] }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: ink("secondary") } } } },
    });

    // 4. off-plan vs resale
    destroyChart("offplan");
    const off = sale.filter((l) => l.off_plan === true).length;
    const resale = sale.filter((l) => l.off_plan === false).length;
    const unknown = sale.length - off - resale;
    const labels = ["Off-plan", "Resale"].concat(unknown ? ["Unknown"] : []);
    const data = [off, resale].concat(unknown ? [unknown] : []);
    const bg = [colors[6], colors[3]].concat(unknown ? [gridColor()] : []);
    state.charts.offplan = new Chart(document.getElementById("chart-offplan"), {
      type: "doughnut",
      data: { labels, datasets: [{ data, backgroundColor: bg }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: ink("secondary") } } } },
    });

    // 5. daily new listings
    destroyChart("dailyNew");
    const daily = state.history.daily_new_counts || [];
    state.charts.dailyNew = new Chart(document.getElementById("chart-daily-new"), {
      type: "line",
      data: {
        labels: daily.map((d) => d.date),
        datasets: [
          { label: "New listings", data: daily.map((d) => d.new_count), borderColor: colors[0], backgroundColor: colors[0], tension: 0.25, spanGaps: true, pointRadius: 3 },
          { label: "Removed listings", data: daily.map((d) => d.removed_count), borderColor: colors[7], backgroundColor: colors[7], tension: 0.25, spanGaps: true, pointRadius: 3 },
        ],
      },
      options: baseOptions({ plugins: { legend: { display: true, position: "bottom", labels: { color: ink("secondary") } } } }),
    });
  }

  function renderBuildingsChart() {
    destroyChart("buildings");
    const counts = {};
    for (const l of state.sale) {
      const k = l.building || l.section || "Unspecified";
      counts[k] = (counts[k] || 0) + 1;
    }
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 15);
    state.charts.buildings = new Chart(document.getElementById("chart-buildings"), {
      type: "bar",
      data: { labels: entries.map((e) => e[0]), datasets: [{ data: entries.map((e) => e[1]), backgroundColor: SERIES()[4], borderRadius: 4 }] },
      options: { ...baseOptions(), indexAxis: "y" },
    });
  }

  // ---------- filters bar ----------
  function renderFiltersBar() {
    const rooms = [...new Set(state.sale.map((l) => l.rooms_category).filter(Boolean))].sort((a, b) => a - b);
    const buildings = uniqueSorted(state.sale, "building");
    const agencies = uniqueSorted(state.sale, "agency_name");
    const sections = uniqueSorted(state.sale, "section");
    const f = state.filters;

    const opt = (val, label) => `<option value="${val}">${label}</option>`;
    document.getElementById("filters-bar").innerHTML = `
      <div class="filter-field"><label>Search</label><input id="f-search" type="text" placeholder="title, address…" value="${f.search}"></div>
      <div class="filter-field"><label>Price €</label><div class="filter-range">
        <input id="f-priceMin" type="number" placeholder="min" value="${f.priceMin}">
        <input id="f-priceMax" type="number" placeholder="max" value="${f.priceMax}"></div></div>
      <div class="filter-field"><label>Size m²</label><div class="filter-range">
        <input id="f-sizeMin" type="number" placeholder="min" value="${f.sizeMin}">
        <input id="f-sizeMax" type="number" placeholder="max" value="${f.sizeMax}"></div></div>
      <div class="filter-field"><label>€/m²</label><div class="filter-range">
        <input id="f-psqmMin" type="number" placeholder="min" value="${f.psqmMin}">
        <input id="f-psqmMax" type="number" placeholder="max" value="${f.psqmMax}"></div></div>
      <div class="filter-field"><label>Floor</label><div class="filter-range">
        <input id="f-floorMin" type="number" placeholder="min" value="${f.floorMin}">
        <input id="f-floorMax" type="number" placeholder="max" value="${f.floorMax}"></div></div>
      <div class="filter-field"><label>Rooms</label><select id="f-rooms">${opt("", "Any")}${rooms.map((r) => opt(r, r)).join("")}</select></div>
      <div class="filter-field"><label>Building</label><select id="f-building">${opt("", "Any")}${buildings.map((b) => opt(b, b)).join("")}</select></div>
      <div class="filter-field"><label>Section</label><select id="f-section">${opt("", "Any")}${sections.map((s) => opt(s, s)).join("")}</select></div>
      <div class="filter-field"><label>Agency</label><select id="f-agency">${opt("", "Any")}${agencies.map((a) => opt(a, a)).join("")}</select></div>
      <div class="filter-field"><label>Seller</label><select id="f-seller">${opt("all", "Any")}${opt("agency", "Agency")}${opt("owner", "Owner")}</select></div>
      <div class="filter-field"><label>Sale type</label><select id="f-offplan">${opt("all", "Any")}${opt("offplan", "Off-plan")}${opt("resale", "Resale")}</select></div>
      <div class="filter-field"><label><input id="f-dupOnly" type="checkbox" ${f.dupOnly ? "checked" : ""}> Duplicates only</label></div>
      <div class="filter-field"><button class="btn" id="f-reset">Reset filters</button></div>
    `;
    document.getElementById("f-seller").value = f.seller;
    document.getElementById("f-offplan").value = f.offplan;
    document.getElementById("f-rooms").value = f.rooms;
    document.getElementById("f-building").value = f.building;
    document.getElementById("f-section").value = f.section;
    document.getElementById("f-agency").value = f.agency;

    const bind = (id, key, checkbox = false) => document.getElementById(id).addEventListener("input", (e) => {
      f[key] = checkbox ? e.target.checked : e.target.value;
      state.page = 1;
      renderListingsTab();
    });
    ["search", "priceMin", "priceMax", "sizeMin", "sizeMax", "psqmMin", "psqmMax", "floorMin", "floorMax"]
      .forEach((k) => bind(`f-${k}`, k));
    ["rooms", "building", "section", "agency", "seller", "offplan"].forEach((k) => bind(`f-${k}`, k));
    bind("f-dupOnly", "dupOnly", true);
    document.getElementById("f-reset").addEventListener("click", () => {
      Object.assign(f, { priceMin: "", priceMax: "", sizeMin: "", sizeMax: "", psqmMin: "", psqmMax: "", floorMin: "", floorMax: "", rooms: "", building: "", agency: "", section: "", seller: "all", offplan: "all", dupOnly: false, search: "" });
      renderFiltersBar();
      renderListingsTab();
    });
  }

  // ---------- listings table ----------
  const TABLE_COLUMNS = [
    ["title", "Title"], ["price_eur", "Price"], ["price_per_sqm_eur", "€/m²"], ["size_sqm", "m²"],
    ["rooms_raw", "Rooms"], ["floor_raw", "Floor"], ["building", "Building"], ["agency_name", "Agency / Owner"],
    ["off_plan", "Off-plan"], ["is_duplicate", "Dup"], ["scraped_at", "Scraped"],
  ];

  function renderListingsTable() {
    let filtered = applyFilters(state.sale);
    filtered = sortList(filtered, state.sort);
    document.getElementById("listings-count").textContent = `${filtered.length} listings match current filters`;

    const thead = document.querySelector("#listings-table thead");
    thead.innerHTML = "<tr>" + TABLE_COLUMNS.map(([key, label]) => {
      const sorted = state.sort.key === key;
      return `<th data-key="${key}" class="${sorted ? "sorted" : ""}" data-dir="${sorted ? (state.sort.dir === "asc" ? "▲" : "▼") : ""}">${label}</th>`;
    }).join("") + "</tr>";
    thead.querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (state.sort.key === key) state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
      else state.sort = { key, dir: "desc" };
      renderListingsTable();
    }));

    const pageSize = state.pageSize;
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    state.page = Math.min(state.page, totalPages);
    const pageItems = filtered.slice((state.page - 1) * pageSize, state.page * pageSize);

    const tbody = document.querySelector("#listings-table tbody");
    if (!pageItems.length) {
      tbody.innerHTML = `<tr><td colspan="${TABLE_COLUMNS.length}" class="empty-state">No listings match the current filters.</td></tr>`;
    } else {
      tbody.innerHTML = pageItems.map((l) => `
        <tr class="${l.is_duplicate ? "dup-row" : ""}">
          <td><a class="listing-link" href="${l.url}" target="_blank" rel="noopener">${(l.title || "Untitled").slice(0, 70)}</a></td>
          <td>${fmtEUR(l.price_eur)}</td>
          <td>${fmtEUR(l.price_per_sqm_eur)}</td>
          <td>${fmtNum(l.size_sqm, 1)}</td>
          <td>${l.rooms_raw || "—"}</td>
          <td>${l.floor_raw || "—"}</td>
          <td>${l.building || l.section || "—"}</td>
          <td>${l.is_owner ? '<span class="badge owner">Owner</span>' : `<span class="badge agency">${l.agency_name || "Agency"}</span>`}</td>
          <td>${l.off_plan === true ? '<span class="badge offplan">Off-plan</span>' : l.off_plan === false ? '<span class="badge resale">Resale</span>' : "—"}</td>
          <td>${l.is_duplicate ? `<span class="badge dup">×${l.duplicate_count}</span>` : "—"}</td>
          <td>${l.scraped_at ? new Date(l.scraped_at).toLocaleDateString() : "—"}</td>
        </tr>
      `).join("");
    }

    document.getElementById("pager").innerHTML = `
      <button class="btn" id="pg-prev" ${state.page <= 1 ? "disabled" : ""}>‹ Prev</button>
      <span class="small muted">Page ${state.page} / ${totalPages}</span>
      <button class="btn" id="pg-next" ${state.page >= totalPages ? "disabled" : ""}>Next ›</button>
    `;
    document.getElementById("pg-prev")?.addEventListener("click", () => { state.page--; renderListingsTable(); });
    document.getElementById("pg-next")?.addEventListener("click", () => { state.page++; renderListingsTable(); });

    state._filteredForExport = filtered;
  }

  function renderListingsTab() {
    renderFiltersBar();
    renderListingsTable();
  }

  function toCSV(rows, columns) {
    const esc = (v) => {
      if (v == null) return "";
      const s = String(v).replace(/"/g, '""');
      return /[",\n]/.test(s) ? `"${s}"` : s;
    };
    const header = columns.map(([, label]) => esc(label)).join(",");
    const lines = rows.map((r) => columns.map(([key]) => esc(typeof key === "function" ? key(r) : r[key])).join(","));
    return [header, ...lines].join("\n");
  }

  function downloadBlob(filename, content, type) {
    const blob = new Blob([content], { type });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function wireExports() {
    document.getElementById("export-csv").addEventListener("click", () => {
      const rows = state._filteredForExport || [];
      const csv = toCSV(rows, TABLE_COLUMNS.concat([["url", "URL"]]));
      downloadBlob("bw_listings.csv", csv, "text/csv");
    });
    document.getElementById("export-xlsx").addEventListener("click", () => {
      const rows = state._filteredForExport || [];
      const cols = TABLE_COLUMNS.concat([["url", "URL"]]);
      const data = [cols.map((c) => c[1]), ...rows.map((r) => cols.map((c) => r[c[0]]))];
      const ws = XLSX.utils.aoa_to_sheet(data);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, "Listings");
      XLSX.writeFile(wb, "bw_listings.xlsx");
    });
    document.getElementById("export-roi-csv").addEventListener("click", () => {
      const rows = state._roiForExport || [];
      const csv = toCSV(rows, ROI_COLUMNS);
      downloadBlob("bw_yield_roi.csv", csv, "text/csv");
    });
  }

  // ---------- by-layout grouping ----------
  function renderLayoutGroups() {
    const filtered = applyFilters(state.sale);
    const groups = {};
    for (const l of filtered) (groups[l.layout_group || "Unspecified"] = groups[l.layout_group || "Unspecified"] || []).push(l);

    const html = LAYOUT_ORDER.filter((k) => groups[k]?.length).map((k) => {
      const items = groups[k].sort((a, b) => (a.price_eur ?? Infinity) - (b.price_eur ?? Infinity));
      const medPrice = median(items.map((i) => i.price_eur));
      const medPsqm = median(items.map((i) => i.price_per_sqm_eur));
      return `
        <div class="layout-group">
          <h4>${k} <span class="count">${items.length} listings · median ${fmtEUR(medPrice)} · median ${fmtEUR(medPsqm)}/m²</span></h4>
          <div class="mini-card-grid">
            ${items.slice(0, 24).map((l) => `
              <div class="mini-card">
                <div class="title">${(l.title || "Untitled").slice(0, 50)}</div>
                <div class="price">${fmtEUR(l.price_eur)}</div>
                <div class="sub">${fmtNum(l.size_sqm, 0)} m² · ${l.floor_raw || "—"} · ${l.building || l.section || "BW"}</div>
                <div class="sub"><a class="listing-link" href="${l.url}" target="_blank" rel="noopener">View listing ↗</a></div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }).join("") || `<div class="empty-state">No listings match the current filters.</div>`;
    document.getElementById("layout-groups").innerHTML = html;
  }

  // ---------- duplicates ----------
  function renderDuplicates() {
    const groups = {};
    for (const l of state.sale) {
      if (!l.is_duplicate) continue;
      (groups[l.duplicate_group_id] = groups[l.duplicate_group_id] || []).push(l);
    }
    const groupList = Object.values(groups);
    if (!groupList.length) {
      document.getElementById("duplicates-list").innerHTML = `<div class="empty-state">No duplicate listings detected in the current dataset.</div>`;
      return;
    }
    document.getElementById("duplicates-list").innerHTML = groupList.map((members) => `
      <div class="dup-group">
        <h4>${members[0].building || members[0].section || "Belgrade Waterfront"} · ${fmtNum(members[0].size_sqm, 0)} m² · floor ${members[0].floor_raw || "—"} <span class="muted small">(${members.length} listings)</span></h4>
        <table>
          <thead><tr><th>Agency / Owner</th><th>Price</th><th>€/m²</th><th>Title</th><th></th></tr></thead>
          <tbody>
            ${members.map((l) => `
              <tr>
                <td>${l.is_owner ? '<span class="badge owner">Owner</span>' : (l.agency_name || "Agency")}</td>
                <td>${fmtEUR(l.price_eur)}</td>
                <td>${fmtEUR(l.price_per_sqm_eur)}</td>
                <td>${(l.title || "").slice(0, 60)}</td>
                <td><a class="listing-link" href="${l.url}" target="_blank" rel="noopener">View ↗</a></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `).join("");
  }

  // ---------- agency leaderboard ----------
  function renderAgencyLeaderboard() {
    const lb = state.leaderboard || {};
    const sections = Object.keys(lb);
    if (!sections.length) {
      document.getElementById("agency-leaderboard").innerHTML = `<div class="empty-state">Not enough agency-attributed listings yet.</div>`;
      return;
    }
    document.getElementById("agency-leaderboard").innerHTML = sections.map((section) => {
      const rows = lb[section].slice(0, 8);
      const max = rows[0]?.count || 1;
      return `
        <div class="leaderboard-section">
          <h4>${section} <span class="muted small">— top agency: ${rows[0]?.agency || "—"} (${rows[0]?.count || 0} listings)</span></h4>
          ${rows.map((r) => `
            <div class="leaderboard-bar-row">
              <div class="name">${r.agency}</div>
              <div class="bar" style="width:${Math.max(6, (r.count / max) * 240)}px"></div>
              <div class="val">${r.count}</div>
            </div>
          `).join("")}
        </div>
      `;
    }).join("");
    renderBuildingsChart();
  }

  // ---------- activity (new/removed) ----------
  function renderActivity() {
    const h = state.history || {};
    const newToday = h.new_today || [];
    const removed = h.removed_vs_7d || [];
    document.getElementById("new-today-count").textContent = `(${newToday.length})`;
    document.getElementById("removed-count").textContent = `(${removed.length})`;

    const row = (l) => `
      <div class="mini-list-row">
        <span>${l.is_owner ? '<span class="badge owner">Owner</span>' : (l.agency_name || "Agency")} · ${l.building || l.section || "BW"} · ${fmtNum(l.size_sqm, 0)} m²</span>
        <span>${fmtEUR(l.price_eur)}</span>
      </div>`;
    document.getElementById("new-today-list").innerHTML = newToday.length ? newToday.map(row).join("") : `<div class="empty-state">No new listings recorded since the previous scrape.</div>`;
    document.getElementById("removed-list").innerHTML = removed.length ? removed.map(row).join("") : `<div class="empty-state">No listings have dropped off in the last 7 days (or not enough history yet).</div>`;
  }

  // ---------- ROI calculator ----------
  const ROI_COLUMNS = [
    ["title", "Title"], ["building", "Building"], ["rooms_raw", "Rooms"], ["size_sqm", "m²"],
    ["price_eur", "Price"], ["comps", "Rent comps"], ["est_monthly_rent", "Est. monthly rent"],
    ["gross_yield_pct", "Gross yield %"], ["net_yield_pct", "Net yield %"],
    ["annual_net_income", "Annual net income"], ["roi_pct", "ROI %"], ["payback_years", "Payback (yrs)"],
  ];

  function findRentComps(sale, rentPool, tolerancePct) {
    if (sale.size_sqm == null) return [];
    const tol = tolerancePct / 100;
    return rentPool.filter((r) => {
      if (r.size_sqm == null || r.rent_monthly_eur == null) return false;
      if (r.size_sqm < sale.size_sqm * (1 - tol) || r.size_sqm > sale.size_sqm * (1 + tol)) return false;
      if (sale.rooms_category && r.rooms_category && sale.rooms_category !== r.rooms_category) return false;
      if (sale.building && r.building) return sale.building === r.building;
      if (sale.section && r.section) return sale.section === r.section;
      return true; // both unresolved to a building/section: fall back to size+rooms match only
    });
  }

  function computeROI(saleList, rentPool, cfg) {
    return saleList.map((s) => {
      let comps = findRentComps(s, rentPool, cfg.sizeTolerance);
      if (!comps.length) comps = findRentComps(s, rentPool, cfg.sizeTolerance * 1.5);
      if (!comps.length || !s.price_eur) {
        return { ...s, comps: comps.length, est_monthly_rent: null, gross_yield_pct: null, net_yield_pct: null, annual_net_income: null, roi_pct: null, payback_years: null };
      }
      const rentPerSqm = median(comps.map((c) => c.rent_monthly_eur / c.size_sqm));
      const estMonthlyRent = rentPerSqm * s.size_sqm;
      const grossAnnual = estMonthlyRent * 12;
      const grossYield = (grossAnnual / s.price_eur) * 100;
      const vacancyLoss = grossAnnual * (cfg.vacancy / 100);
      const mgmtCost = grossAnnual * (cfg.mgmtFee / 100);
      const maintenanceCost = s.price_eur * (cfg.maintenance / 100);
      const netIncome = grossAnnual - vacancyLoss - mgmtCost - maintenanceCost - cfg.otherAnnual;
      const netYield = (netIncome / s.price_eur) * 100;
      const payback = netIncome > 0 ? s.price_eur / netIncome : null;
      return {
        ...s, comps: comps.length, est_monthly_rent: Math.round(estMonthlyRent),
        gross_yield_pct: grossYield, net_yield_pct: netYield,
        annual_net_income: Math.round(netIncome), roi_pct: netYield, payback_years: payback,
      };
    });
  }

  function renderROIControls() {
    const c = state.roi;
    document.getElementById("roi-controls").innerHTML = `
      <div class="filter-field"><label>Vacancy rate %/yr</label><input id="r-vacancy" type="number" value="${c.vacancy}"></div>
      <div class="filter-field"><label>Mgmt fee % of rent</label><input id="r-mgmtFee" type="number" value="${c.mgmtFee}"></div>
      <div class="filter-field"><label>Maintenance % of price/yr</label><input id="r-maintenance" type="number" value="${c.maintenance}" step="0.1"></div>
      <div class="filter-field"><label>Other costs €/yr</label><input id="r-otherAnnual" type="number" value="${c.otherAnnual}"></div>
      <div class="filter-field"><label>Comp size tolerance ±%</label><input id="r-sizeTolerance" type="number" value="${c.sizeTolerance}"></div>
    `;
    ["vacancy", "mgmtFee", "maintenance", "otherAnnual", "sizeTolerance"].forEach((k) => {
      document.getElementById(`r-${k}`).addEventListener("input", (e) => {
        state.roi[k] = +e.target.value;
        renderROITable();
      });
    });
  }

  function renderROITable() {
    const filteredSale = applyFilters(state.sale);
    const results = computeROI(filteredSale, state.rent, state.roi)
      .filter((r) => r.comps > 0)
      .sort((a, b) => (state.roiSort.dir === "asc" ? 1 : -1) * ((a[state.roiSort.key] ?? -Infinity) - (b[state.roiSort.key] ?? -Infinity)));

    document.getElementById("roi-count").textContent = `${results.length} sale listings have matching rental comps (of ${filteredSale.length} filtered)`;
    state._roiForExport = results;

    const thead = document.querySelector("#roi-table thead");
    thead.innerHTML = "<tr>" + ROI_COLUMNS.map(([key, label]) => {
      const sorted = state.roiSort.key === key;
      return `<th data-key="${key}" class="${sorted ? "sorted" : ""}" data-dir="${sorted ? (state.roiSort.dir === "asc" ? "▲" : "▼") : ""}">${label}</th>`;
    }).join("") + "</tr>";
    thead.querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (state.roiSort.key === key) state.roiSort.dir = state.roiSort.dir === "asc" ? "desc" : "asc";
      else state.roiSort = { key, dir: "desc" };
      renderROITable();
    }));

    const tbody = document.querySelector("#roi-table tbody");
    tbody.innerHTML = results.length ? results.slice(0, 200).map((r) => `
      <tr>
        <td><a class="listing-link" href="${r.url}" target="_blank" rel="noopener">${(r.title || "Untitled").slice(0, 55)}</a></td>
        <td>${r.building || r.section || "—"}</td>
        <td>${r.rooms_raw || "—"}</td>
        <td>${fmtNum(r.size_sqm, 1)}</td>
        <td>${fmtEUR(r.price_eur)}</td>
        <td>${r.comps}</td>
        <td>${fmtEUR(r.est_monthly_rent)}</td>
        <td>${fmtPct(r.gross_yield_pct)}</td>
        <td>${fmtPct(r.net_yield_pct)}</td>
        <td>${fmtEUR(r.annual_net_income)}</td>
        <td>${fmtPct(r.roi_pct)}</td>
        <td>${r.payback_years ? fmtNum(r.payback_years, 1) : "—"}</td>
      </tr>
    `).join("") : `<tr><td colspan="${ROI_COLUMNS.length}" class="empty-state">No sale listings have enough comparable rentals yet — widen the size tolerance or check back once more rental data has been scraped.</td></tr>`;
  }

  function renderROITab() {
    renderROIControls();
    renderROITable();
  }

  // ---------- tabs ----------
  function wireTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
      });
    });
  }

  function wireTheme() {
    const btn = document.getElementById("theme-toggle");
    btn.addEventListener("click", () => {
      const root = document.documentElement;
      const current = root.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      renderOverviewCharts();
      renderBuildingsChart();
    });
  }

  async function main() {
    wireTabs();
    wireTheme();
    wireExports();
    await loadAll();
    renderKPIs();
    renderOverviewCharts();
    renderListingsTab();
    renderLayoutGroups();
    renderDuplicates();
    renderAgencyLeaderboard();
    renderActivity();
    renderROITab();
  }

  main();
})();
