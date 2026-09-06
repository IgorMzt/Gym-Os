(() => {
  const root = document.getElementById("v5-dashboard");
  if (!root) return;

  let snapshot = window.DASHBOARD_V5 || {};
  const refreshMs = Math.max(3000, Number(root.dataset.refresh || snapshot.atualizacao_ms || 10000));
  const indicator = document.getElementById("refresh-indicator");

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  })[c]);

  const localTime = (v) => {
    if (!v) return "—";
    try {
      const normalized = String(v).includes("T") ? String(v) : String(v).replace(" ", "T");
      const d = new Date(normalized);
      if (Number.isNaN(d.getTime())) return v;
      return d.toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"});
    } catch (_) { return v; }
  };

  function updateKpis(kpis = {}) {
    document.querySelectorAll("[data-kpi]").forEach(el => {
      const k = el.dataset.kpi;
      if (Object.prototype.hasOwnProperty.call(kpis, k)) el.textContent = kpis[k];
    });
  }

  function updateChart(data) {
    const box = document.getElementById("v5-chart");
    if (!box) return;
    const max = Math.max(1, ...data.map(p => Number(p.quantidade || 0)));
    box.innerHTML = data.map(p => {
      const pct = Math.max(2, Number(p.quantidade || 0) / max * 100);
      const label = Number(p.hora) % 3 === 0 ? p.rotulo : "";
      return `<div class="v5-chart__col" title="${esc(p.rotulo)} · ${Number(p.quantidade || 0)} entrada(s)">
        <div class="v5-chart__value">${p.quantidade || ""}</div>
        <div class="v5-chart__track"><div class="v5-chart__bar" style="height:${pct.toFixed(1)}%"></div></div>
        <span>${esc(label)}</span>
      </div>`;
    }).join("");
  }

  function updateAlerts(alertas = []) {
    const box = document.getElementById("v5-alerts");
    if (!box) return;
    box.innerHTML = alertas.length ? alertas.map(a =>
      a.pessoa_id
        ? `<a class="v5-alert v5-alert--${esc(a.nivel)}" href="/alunos/${Number(a.pessoa_id)}">
            <i></i><div><strong>${esc(a.titulo)}</strong><span>${esc(a.texto)}</span></div><b>›</b>
          </a>`
        : `<div class="v5-alert v5-alert--${esc(a.nivel)}">
            <i></i><div><strong>${esc(a.titulo)}</strong><span>${esc(a.texto)}</span></div>
          </div>`
    ).join("") : `<div class="v5-empty">Nenhum alerta prioritário neste momento.</div>`;
  }

  function updatePresence(itens = []) {
    const box = document.getElementById("v5-presence-list");
    if (!box) return;
    box.innerHTML = itens.length ? itens.map(p => {
      const avatar = p.foto_url
        ? `<img src="${esc(p.foto_url)}" alt="">`
        : `<span>${esc(String(p.nome || "?").slice(0,1).toUpperCase())}</span>`;
      if (p.pessoa_id) {
        return `<a class="v5-person" href="/alunos/${Number(p.pessoa_id)}">
          <div class="v5-avatar">${avatar}</div>
          <div class="v5-person__main"><strong>${esc(p.nome || "Aluno")}</strong><span>${esc(p.plano || "Sem plano")} · ${esc(p.catraca_nome || "Catraca")}</span></div>
          <time>${esc(localTime(p.data_hora))}</time>
        </a>`;
      }
      return `<div class="v5-person">
        <div class="v5-avatar">${avatar}</div>
        <div class="v5-person__main"><strong>${esc(p.nome || "Aluno removido")}</strong><span>${esc(p.catraca_nome || "Catraca")} · histórico preservado</span></div>
        <time>${esc(localTime(p.data_hora))}</time>
      </div>`;
    }).join("") : `<div class="v5-empty">Nenhum acesso liberado dentro da janela atual.</div>`;
  }

  function updateFeed(itens = []) {
    const box = document.getElementById("v5-feed");
    if (!box) return;
    box.innerHTML = itens.length ? itens.map(log => {
      const status = String(log.status || "").toLowerCase();
      const icon = log.status === "LIBERADO" ? "✓" : "×";
      return `<div class="v5-feed__item">
        <span class="v5-feed__status v5-feed__status--${esc(status)}">${icon}</span>
        <div><strong>${esc(log.nome || "Pessoa não identificada")}</strong><span>${esc(log.motivo || log.status || "—")} · ${esc(log.catraca_nome || "Catraca")}</span></div>
        <time>${esc(localTime(log.data_hora))}</time>
      </div>`;
    }).join("") : `<div class="v5-empty">Nenhuma movimentação registrada.</div>`;
  }

  const money = (centavos) => new Intl.NumberFormat("pt-BR", {style:"currency", currency:"BRL"}).format(Number(centavos || 0) / 100);

  function updateFinance(fin = {}) {
    document.querySelectorAll("[data-finance]").forEach(el => {
      const k = el.dataset.finance;
      if (!Object.prototype.hasOwnProperty.call(fin, k)) return;
      el.textContent = el.dataset.money === "0" ? Number(fin[k] || 0) : money(fin[k]);
    });
    const box = document.getElementById("v5-finance-recent");
    if (!box) return;
    const itens = fin.pagamentos_recentes || [];
    box.innerHTML = itens.length ? itens.map(pg =>
      pg.pessoa_id
        ? `<a href="/alunos/${Number(pg.pessoa_id)}"><span><strong>${esc(pg.nome || "Aluno")}</strong><small>${esc(localTime(pg.data_pagamento))}</small></span><b>${esc(money(pg.valor_centavos))}</b></a>`
        : `<div class="v5-finance-history-row"><span><strong>${esc(pg.nome || "Aluno removido")}</strong><small>${esc(localTime(pg.data_pagamento))} · histórico preservado</small></span><b>${esc(money(pg.valor_centavos))}</b></div>`
    ).join("") : `<div class="v5-empty">Nenhum pagamento confirmado ainda.</div>`;
  }

  function updateDevices(itens = []) {
    const box = document.getElementById("v5-devices");
    if (!box) return;
    box.innerHTML = itens.length ? itens.map(c =>
      `<div class="v5-device">
        <div class="v5-device__status ${c.ativa ? "is-active" : ""}"><i></i>${c.ativa ? "ATIVA" : "INATIVA"}</div>
        <strong>${esc(c.nome)}</strong><span>${esc(c.local || "Local não definido")} · ${esc(c.modo)}</span>
        <small>${c.ultimo_evento ? `Último evento: ${esc(localTime(c.ultimo_evento))}` : "Sem eventos registrados"}</small>
      </div>`
    ).join("") : `<div class="v5-empty">Nenhuma catraca configurada.</div>`;
  }

  async function refresh() {
    indicator?.classList.add("is-refreshing");
    try {
      const r = await fetch("/api/dashboard", {cache:"no-store"});
      const d = await r.json();
      if (!r.ok || !d.sucesso) throw new Error(d.erro || "Dashboard indisponível");
      snapshot = d.dashboard;
      updateKpis(snapshot.kpis);
      updateChart(snapshot.chart || []);
      updateAlerts(snapshot.alertas || []);
      updatePresence(snapshot.presenca || []);
      updateFeed(snapshot.feed || []);
      updateDevices(snapshot.catracas || []);
      updateFinance(snapshot.financeiro || {});
      const ph = document.getElementById("pico-hora");
      const pq = document.getElementById("pico-qtd");
      if (ph) ph.textContent = snapshot.pico?.hora || "—";
      if (pq) pq.textContent = snapshot.pico?.quantidade ?? 0;
    } catch (e) {
      console.error("Atualização do dashboard:", e);
    } finally {
      indicator?.classList.remove("is-refreshing");
    }
  }

  setInterval(refresh, refreshMs);
})();