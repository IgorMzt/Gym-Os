function aplicarTema(tema) {
  const valido = ['light', 'system', 'dark'].includes(tema) ? tema : 'system';
  document.documentElement.dataset.tema = valido;
  localStorage.setItem('panobianco-tema', valido);
  atualizarBotoesTema(valido);
  const meta = document.getElementById('meta-theme-color');
  if (meta) {
    const escuro = valido === 'dark' || (valido === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches);
    meta.setAttribute('content', escuro ? '#111111' : '#ffffff');
  }
}

function atualizarBotoesTema(tema) {
  document.querySelectorAll('[data-tema]').forEach((botao) => {
    if (!botao.classList.contains('theme-btn')) return;
    botao.classList.toggle('ativo', botao.dataset.tema === tema);
    botao.setAttribute('aria-pressed', botao.dataset.tema === tema ? 'true' : 'false');
  });
}

(function iniciarTema() {
  const legado = { claro: 'light', sistema: 'system', escuro: 'dark' };
  const bruto = localStorage.getItem('panobianco-tema');
  const salvo = legado[bruto] || bruto || window.TEMA_PADRAO || 'system';
  document.documentElement.dataset.tema = salvo;
  document.addEventListener('DOMContentLoaded', () => {
    atualizarBotoesTema(salvo);
    document.querySelectorAll('.theme-btn').forEach((botao) => {
      botao.addEventListener('click', () => aplicarTema(botao.dataset.tema));
    });
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    media?.addEventListener?.('change', () => {
      if ((localStorage.getItem('panobianco-tema') || window.TEMA_PADRAO || 'system') === 'system') aplicarTema('system');
    });
    aplicarTema(salvo);
  });
})();

function atualizarRelogio() {
  const el = document.getElementById("relogio");
  if (!el) return;
  el.textContent = new Date().toLocaleTimeString("pt-BR");
}
setInterval(atualizarRelogio, 1000);
atualizarRelogio();

function desligarCamera(elementoVideo) {
  const stream = elementoVideo?.srcObject;
  if (stream && typeof stream.getTracks === "function") {
    stream.getTracks().forEach((track) => track.stop());
  }
  if (elementoVideo) elementoVideo.srcObject = null;
}

async function ligarCamera(elementoVideo) {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Seu navegador não permite acesso à câmera neste endereço.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
    audio: false,
  });
  elementoVideo.srcObject = stream;
  return stream;
}

function capturarFrame(video, canvas, qualidade = 0.76) {
  const ctx = canvas.getContext("2d", { alpha: false });
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", qualidade);
}

function dormir(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatarDataLocal(valor) {
  if (!valor) return "—";
  const iso = valor.replace(" ", "T") + (valor.endsWith("Z") ? "" : "Z");
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return valor;
  return data.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
}

document.querySelectorAll(".date-local").forEach((el) => {
  el.textContent = formatarDataLocal(el.dataset.utc);
});


// Proteção CSRF transparente para operações administrativas.
(() => {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const metodo = String(init.method || "GET").toUpperCase();
    const url = typeof input === "string" ? input : (input?.url || "");
    const mesmaOrigem = !/^https?:\/\//i.test(url) || url.startsWith(window.location.origin);
    if (mesmaOrigem && ["POST", "PUT", "PATCH", "DELETE"].includes(metodo) && window.CSRF_TOKEN) {
      const headers = new Headers(init.headers || {});
      if (!headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", window.CSRF_TOKEN);
      init = {...init, headers};
    }
    return originalFetch(input, init);
  };
})();


// Sidebar responsiva do painel administrativo.
(() => {
  const side = document.getElementById("admin-sidebar");
  const btn = document.getElementById("sidebar-toggle");
  const bg = document.getElementById("sidebar-backdrop");
  if (!side || !btn || !bg) return;
  const fechar = () => { side.classList.remove("is-open"); bg.classList.remove("is-open"); };
  btn.addEventListener("click", () => {
    side.classList.toggle("is-open");
    bg.classList.toggle("is-open");
  });
  bg.addEventListener("click", fechar);
  side.querySelectorAll("a").forEach(a => a.addEventListener("click", fechar));
})();

(()=>{const input=document.getElementById('global-search-v591'),box=document.getElementById('global-results-v591');if(!input||!box)return;let timer;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));input.addEventListener('input',()=>{clearTimeout(timer);const q=input.value.trim();if(q.length<2){box.hidden=true;return}timer=setTimeout(async()=>{try{const r=await fetch('/api/busca-global?q='+encodeURIComponent(q)),d=await r.json();box.innerHTML=(d.resultados||[]).map(x=>`<a href="/alunos/${x.id}"><strong>${esc(x.nome)}</strong><span>${esc(x.matricula||'—')} · ${esc(x.plano||'Sem plano')}</span></a>`).join('')||'<div class="global-empty-v591">Nenhum aluno encontrado.</div>';box.hidden=false}catch{}},180)});document.addEventListener('click',e=>{if(!e.target.closest('.global-search-v591'))box.hidden=true})})();
