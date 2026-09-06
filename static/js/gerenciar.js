const busca = document.getElementById("busca-aluno");
const contador = document.getElementById("contador-resultados");
const filtroBar = document.getElementById("student-filterbar");
const vazio = document.getElementById("student-empty-filter");
const msg = document.getElementById("student-action-message");
const modal = document.getElementById("student-confirm-modal");
const modalTitle = document.getElementById("student-confirm-title");
const modalText = document.getElementById("student-confirm-text");
const modalAction = document.getElementById("student-confirm-action");
let filtroAtual = "todos";
let acaoPendente = null;

const escapeHtmlLocal = (valor) => String(valor ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);

function entradas(tipo = null) {
  return [...document.querySelectorAll(".student-entry")].filter(el => !tipo || el.dataset.kind === tipo);
}
function correspondeFiltro(el) {
  if (filtroAtual === "todos") return true;
  return el.dataset[filtroAtual] === "1";
}
function aplicarFiltros() {
  const termo = (busca?.value || "").toLowerCase().trim();
  let visiveis = 0;
  entradas("row").forEach(el => {
    const ok = (!termo || el.dataset.search.includes(termo)) && correspondeFiltro(el);
    el.hidden = !ok;
    if (ok) visiveis += 1;
  });
  entradas("card").forEach(el => {
    const ok = (!termo || el.dataset.search.includes(termo)) && correspondeFiltro(el);
    el.hidden = !ok;
  });
  if (contador) contador.textContent = `${visiveis} aluno(s)`;
  vazio?.classList.toggle("hidden", visiveis !== 0);
}
function selecionarFiltro(filtro) {
  filtroAtual = filtro;
  document.querySelectorAll("[data-filtro]").forEach(btn => btn.classList.toggle("is-active", btn.dataset.filtro === filtro));
  aplicarFiltros();
}
function mostrarMensagem(texto, tipo = "sucesso") {
  if (!msg) return;
  msg.innerHTML = `<div class="status-msg status-msg--${tipo}">${escapeHtmlLocal(texto)}</div>`;
  window.setTimeout(() => { if (msg) msg.innerHTML = ""; }, 4200);
}
function abrirConfirmacao(config) {
  acaoPendente = config;
  modalTitle.textContent = config.titulo;
  modalText.textContent = config.texto;
  modalAction.textContent = config.confirmar || "Confirmar";
  modalAction.className = `btn ${config.perigo ? "btn--perigo" : "btn--primario"}`;
  modal.classList.remove("hidden");
}
function fecharConfirmacao() {
  modal?.classList.add("hidden");
  acaoPendente = null;
}
function atualizarEntradas(id, mutacao) {
  document.querySelectorAll(`.student-entry[data-id="${id}"]`).forEach(mutacao);
}
function atualizarBloqueio(id, bloqueado) {
  atualizarEntradas(id, el => {
    el.dataset.bloqueados = bloqueado ? "1" : "0";
    if (bloqueado) el.dataset.ativos = "0";
    const badge = el.querySelector(".student-status");
    if (badge) {
      badge.textContent = bloqueado ? "BLOQUEADO" : "ATIVO";
      badge.className = `student-status status--${bloqueado ? "bloqueado" : "ativo"}`;
    }
    const btn = el.querySelector('button[data-acao="bloquear"],button[data-acao="liberar"]');
    if (btn) {
      btn.dataset.acao = bloqueado ? "liberar" : "bloquear";
      btn.textContent = bloqueado ? "Desbloquear" : "Bloquear";
      btn.classList.toggle("btn--sucesso", bloqueado);
    }
  });
  aplicarFiltros();
}
function atualizarRenovacao(id, vencimento) {
  atualizarEntradas(id, el => {
    el.dataset.vencidos = "0";
    el.dataset.vencendo = "0";
    el.dataset.inadimplentes = "0";
    if (el.dataset.bloqueados !== "1") el.dataset.ativos = "1";
    el.querySelectorAll(".student-expiry").forEach(cel => {
      cel.textContent = new Date(`${vencimento}T12:00:00`).toLocaleDateString("pt-BR");
      cel.dataset.vencimento = vencimento;
    });
    const badge = el.querySelector(".student-status");
    if (badge && el.dataset.bloqueados !== "1") {
      badge.textContent = "ATIVO";
      badge.className = "student-status status--ativo";
    }
  });
  aplicarFiltros();
}

busca?.addEventListener("input", aplicarFiltros);
filtroBar?.addEventListener("click", ev => {
  const btn = ev.target.closest("[data-filtro]");
  if (btn) selecionarFiltro(btn.dataset.filtro);
});
document.querySelectorAll("[data-filter-shortcut]").forEach(btn => btn.addEventListener("click", () => selecionarFiltro(btn.dataset.filterShortcut)));
document.querySelectorAll("[data-modal-close]").forEach(el => el.addEventListener("click", fecharConfirmacao));
window.addEventListener("keydown", ev => { if (ev.key === "Escape") fecharConfirmacao(); });

document.addEventListener("click", ev => {
  const btn = ev.target.closest("button[data-acao]");
  if (!btn) return;
  const { acao, id, nome, planoId } = btn.dataset;
  if (acao === "renovar") {
    abrirConfirmacao({titulo:"Renovar plano", texto:`Renovar o plano atual de ${nome}? O novo vencimento será calculado a partir do vencimento atual ou de hoje.`, confirmar:"Renovar", acao, id, planoId});
  } else if (acao === "bloquear") {
    abrirConfirmacao({titulo:"Bloquear acesso", texto:`Bloquear manualmente o acesso de ${nome}? O aluno não será liberado na catraca até ser desbloqueado.`, confirmar:"Bloquear", perigo:true, acao, id});
  } else if (acao === "liberar") {
    abrirConfirmacao({titulo:"Desbloquear acesso", texto:`Remover o bloqueio manual de ${nome}? As regras de plano e financeiro continuarão valendo.`, confirmar:"Desbloquear", acao, id});
  }
});

modalAction?.addEventListener("click", async () => {
  if (!acaoPendente) return;
  const atual = {...acaoPendente};
  modalAction.disabled = true;
  const original = modalAction.textContent;
  modalAction.textContent = "Processando...";
  try {
    let url = `/api/pessoas/${atual.id}/${atual.acao}`;
    const opts = {method:"POST", headers:{"Content-Type":"application/json"}};
    if (atual.acao === "renovar") opts.body = JSON.stringify({plano_id: atual.planoId || null});
    const r = await fetch(url, opts);
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.sucesso) throw new Error(d.erro || "Não foi possível concluir a ação.");
    fecharConfirmacao();
    if (atual.acao === "renovar") atualizarRenovacao(atual.id, d.data_vencimento);
    else atualizarBloqueio(atual.id, atual.acao === "bloquear");
    mostrarMensagem(d.mensagem || "Alteração realizada com sucesso.");
  } catch (e) {
    mostrarMensagem(e.message || "Erro de conexão com o servidor.", "erro");
  } finally {
    modalAction.disabled = false;
    modalAction.textContent = original;
  }
});

aplicarFiltros();
