const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const statusDisplay = document.getElementById("status-display");
const statusIcon = document.getElementById("status-icon");
const statusEyebrow = document.getElementById("status-eyebrow");
const statusTexto = document.getElementById("status-texto");
const statusNome = document.getElementById("status-nome");
const stateChip = document.getElementById("state-chip");
const personCard = document.getElementById("person-card");
const foto = document.getElementById("status-foto");
const personNome = document.getElementById("person-nome");
const personCpf = document.getElementById("person-cpf");
const personMatricula = document.getElementById("person-matricula");
const personPlano = document.getElementById("person-plano");
const personVencimento = document.getElementById("person-vencimento");
const countdown = document.getElementById("result-countdown");
const gatePulse = document.getElementById("gate-pulse");
const cameraState = document.getElementById("camera-state");
const cameraHint = document.getElementById("camera-hint");
const historico = document.getElementById("catraca-historico");
const standbyOverlay = document.getElementById("standby-overlay");
const operationState = document.getElementById("operation-state");
const livenessState = document.getElementById("liveness-state");
const sleepScreen = document.getElementById("sleep-screen");
const sleepClock = document.getElementById("sleep-clock");
const sleepDate = document.getElementById("sleep-date");
const sleepPresenceText = document.getElementById("sleep-presence-text");

const CONFIG = window.CATRACA_CONFIG || {};
const CAT_ID = CONFIG.catraca?.id || null;
const INTERVALO_MS = Math.max(500, Number(CONFIG.intervalo_ms || 850));
const TEMPO_RESULTADO_MS = Math.max(1500, Number(CONFIG.tempo_resultado_ms || 3000));
const STANDBY_MS = Math.max(5000, Number(CONFIG.standby_sem_presenca_ms ?? 30000));
const WAKE_DELAY_MS = Math.max(0, Number(CONFIG.atraso_apos_presenca_ms || 700));
const COOLDOWN_MS = Math.max(0, Number(CONFIG.cooldown_proxima_pessoa_ms ?? 1000));
const AUSENCIA_REARMAR_MS = Math.max(0, Number(CONFIG.ausencia_rearmar_ms ?? 1200));
const MAX_ESPERA_SAIDA_MS = Math.max(0, Number(CONFIG.max_espera_saida_ms ?? 0));
const MODO_PRESENCA = ["sempre", "inteligente", "sensor"].includes(CONFIG.presenca_modo) ? CONFIG.presenca_modo : "inteligente";
const SENSIBILIDADE = ["baixa", "media", "alta"].includes(CONFIG.sensibilidade_presenca) ? CONFIG.sensibilidade_presenca : "media";
const SOM_ATIVO = CONFIG.som_ativo !== false;
const LIVENESS_ATIVO = CONFIG.liveness_ativo !== false;
const ERRO_RECUPERACAO_MS = Math.max(500, Number(CONFIG.erro_recuperacao_ms ?? 2500));
const INTERVALO_DETECTOR_PRESENCA_MS = Math.max(100, Number(CONFIG.intervalo_detector_presenca_ms ?? 500));
const INTERVALO_HISTORICO_MS = Math.max(1000, Number(CONFIG.intervalo_historico_ms ?? 5000));

const ESTADOS = Object.freeze({
  INICIANDO: "INICIANDO",
  PRONTO: "PRONTO",
  DESCANSO: "DESCANSO",
  PRESENCA: "PRESENÇA DETECTADA",
  IDENTIFICANDO: "IDENTIFICANDO",
  PROVA_VIDA: "PROVA DE VIDA",
  RESULTADO: "RESULTADO",
  COOLDOWN: "COOLDOWN",
  AGUARDANDO_SAIDA: "AGUARDANDO SAÍDA",
  ERRO: "ERRO"
});

let estado = ESTADOS.INICIANDO;
let verificando = false;
let semRostoDesde = performance.now();
let ausenciaDesde = null;
let esperaSaidaDesde = null;
let leiturasSemPresenca = 0;
let baselineMovimento = null;
let movimentoConsecutivo = 0;
let tokenFluxo = 0;
let timerResultado = null;
let timerReconhecimento = null;
let timerHistorico = null;
let timerMovimento = null;
let timerSaida = null;
let timerRelogio = null;
let timerCooldown = null;
let timerRecuperacao = null;

const motionCanvas = document.createElement("canvas");
motionCanvas.width = 48;
motionCanvas.height = 36;
const motionCtx = motionCanvas.getContext("2d", {alpha: false, willReadFrequently: true});

function safeClass(el, action, classe) {
  if (el?.classList && typeof el.classList[action] === "function") el.classList[action](classe);
}
function setText(el, texto) {
  if (el) el.textContent = texto;
}
function setEstado(novo) {
  estado = novo;
  setText(stateChip, novo);
  setText(operationState, novo);
}
function limparTimersDeFluxo() {
  clearInterval(timerResultado);
  clearInterval(timerSaida);
  clearTimeout(timerCooldown);
  clearTimeout(timerRecuperacao);
}
function cancelarFluxoAtual() {
  tokenFluxo += 1;
  limparTimersDeFluxo();
}
function renderEstado(classe, eyebrow, titulo, mensagem, pessoa = null) {
  if (statusDisplay) statusDisplay.className = `result-card result-card--${classe}`;
  setText(statusIcon, classe === "liberado" ? "✓" : ["bloqueado", "negado"].includes(classe) ? "×" : "•");
  setText(statusEyebrow, eyebrow);
  setText(statusTexto, titulo);
  setText(statusNome, mensagem || "");
  safeClass(personCard, pessoa ? "remove" : "add", "hidden");
  safeClass(gatePulse, "add", "hidden");
  safeClass(countdown, "add", "hidden");

  if (pessoa) {
    if (foto) foto.src = pessoa.foto || "";
    safeClass(foto, pessoa.foto ? "remove" : "add", "hidden");
    setText(personNome, pessoa.nome || "—");
    setText(personCpf, `CPF ${pessoa.cpf || "—"}`);
    setText(personMatricula, `Matrícula ${pessoa.matricula || "—"}`);
    setText(personPlano, `Plano ${pessoa.plano || "—"}`);
    setText(personVencimento, `Vencimento ${pessoa.data_vencimento || "—"}`);
  }
}

function atualizarRelogio() {
  const agora = new Date();
  setText(sleepClock, agora.toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"}));
  setText(sleepDate, agora.toLocaleDateString("pt-BR", {
    weekday: "long", day: "2-digit", month: "long"
  }).toUpperCase());
}

function mostrarTelaDescanso(visivel) {
  safeClass(sleepScreen, visivel ? "remove" : "add", "hidden");
  document.body.classList.toggle("catraca-em-descanso", !!visivel);
  if (visivel) atualizarRelogio();
}

function renderPronto() {
  cancelarFluxoAtual();
  setEstado(ESTADOS.PRONTO);
  mostrarTelaDescanso(false);
  safeClass(standbyOverlay, "add", "hidden");
  renderEstado("aguardando", "PRONTO", "Aproxime-se", "Pronto para identificar o próximo aluno");
  setText(cameraHint, "Centralize o rosto");
  setText(cameraState, "Pronta");
}

function renderIdentificando() {
  setEstado(ESTADOS.IDENTIFICANDO);
  renderEstado("prova", "IDENTIFICAÇÃO", "Identificando...", "Mantenha o rosto centralizado por um instante");
  setText(cameraHint, "Mantenha o rosto centralizado");
  setText(cameraState, "Lendo");
}

function renderProvaVida(motivo) {
  setEstado(ESTADOS.PROVA_VIDA);
  renderEstado("prova", "PROVA DE VIDA", "Mova a cabeça", motivo || "Faça um movimento leve para continuar");
  setText(cameraHint, "Movimente levemente a cabeça");
  setText(cameraState, "Validando");
}

function entrarDescanso() {
  if (MODO_PRESENCA === "sempre") return;
  cancelarFluxoAtual();
  setEstado(ESTADOS.DESCANSO);
  baselineMovimento = null;
  movimentoConsecutivo = 0;
  safeClass(standbyOverlay, "remove", "hidden");
  renderEstado("aguardando", "DESCANSO", "Aguardando presença", "O reconhecimento facial está em repouso");
  setText(cameraHint, "Aproxime-se");
  setText(cameraState, "Descanso");
  setText(sleepPresenceText, "Aguardando presença");
  mostrarTelaDescanso(true);
}

function deveEntrarDescanso() {
  return MODO_PRESENCA !== "sempre" &&
    estado === ESTADOS.PRONTO &&
    performance.now() - semRostoDesde >= STANDBY_MS;
}

function limiarMovimento() {
  return {baixa: 16, media: 11, alta: 7}[SENSIBILIDADE] || 11;
}

function medirMovimento() {
  if (video.readyState < 2 || estado !== ESTADOS.DESCANSO) return false;
  motionCtx.drawImage(video, 0, 0, motionCanvas.width, motionCanvas.height);
  const data = motionCtx.getImageData(0, 0, motionCanvas.width, motionCanvas.height).data;
  const atual = new Uint8Array(motionCanvas.width * motionCanvas.height);

  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    atual[p] = (data[i] * 3 + data[i + 1] * 6 + data[i + 2]) / 10;
  }

  if (!baselineMovimento) {
    baselineMovimento = atual;
    return false;
  }

  let soma = 0;
  for (let i = 0; i < atual.length; i++) soma += Math.abs(atual[i] - baselineMovimento[i]);
  const media = soma / atual.length;
  baselineMovimento = atual;

  movimentoConsecutivo = media >= limiarMovimento()
    ? movimentoConsecutivo + 1
    : Math.max(0, movimentoConsecutivo - 1);

  return movimentoConsecutivo >= 2;
}

async function acordarPorPresenca() {
  if (estado !== ESTADOS.DESCANSO) return;
  const meuToken = ++tokenFluxo;
  setEstado(ESTADOS.PRESENCA);
  setText(sleepPresenceText, "Presença detectada");
  safeClass(standbyOverlay, "add", "hidden");

  // Mantemos a tela de descanso por um instante enquanto a câmera estabiliza.
  await dormir(WAKE_DELAY_MS);
  if (meuToken !== tokenFluxo || estado !== ESTADOS.PRESENCA) return;

  mostrarTelaDescanso(false);
  semRostoDesde = performance.now();
  renderIdentificando();

  // O próximo ciclo de reconhecimento transforma IDENTIFICANDO em PRONTO/PROVA/RESULTADO.
}

function renderAguardandoSaida() {
  setEstado(ESTADOS.AGUARDANDO_SAIDA);
  mostrarTelaDescanso(false);
  renderEstado("aguardando", "PRÓXIMA PESSOA", "Aguardando saída", "Afaste-se da câmera para liberar a próxima leitura");
  setText(cameraState, "Pausa");
  setText(cameraHint, "Aguarde a pessoa anterior sair");
}

function tocarSom(status) {
  try {
    const audio = new AudioContext();
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.frequency.value = status === "LIBERADO" ? 880 : 220;
    gain.gain.value = 0.06;
    osc.start();
    osc.stop(audio.currentTime + 0.12);
  } catch (_) {}
}

function renderResultado(dados) {
  cancelarFluxoAtual();
  setEstado(ESTADOS.RESULTADO);

  const classe = dados.status === "LIBERADO"
    ? "liberado"
    : dados.status === "BLOQUEADO" ? "bloqueado" : "negado";
  const pessoa = dados.pessoa || null;
  const titulo = dados.status === "LIBERADO"
    ? "ACESSO LIBERADO"
    : dados.status === "BLOQUEADO" ? "ACESSO BLOQUEADO"
    : dados.status === "ERRO" ? "CATRACA INDISPONÍVEL"
    : "ACESSO NEGADO";
  const eyebrow = dados.status === "LIBERADO"
    ? "ENTRADA AUTORIZADA"
    : dados.status === "ERRO" ? "FALHA NO DISPOSITIVO"
    : "ACESSO RECUSADO";
  const mensagem = pessoa?.motivo || dados.motivo || (pessoa ? pessoa.nome : "Pessoa não reconhecida");

  renderEstado(classe, eyebrow, titulo, mensagem, pessoa);
  if (dados.status === "LIBERADO") safeClass(gatePulse, "remove", "hidden");
  safeClass(countdown, "remove", "hidden");
  setText(cameraState, dados.status === "LIBERADO" ? "Liberada" : "Pausa");

  let restante = TEMPO_RESULTADO_MS;
  const atualizarCountdown = () => setText(
    countdown,
    restante > 0 ? `Próxima etapa em ${Math.ceil(restante / 1000)}s` : "Preparando próxima pessoa..."
  );
  atualizarCountdown();

  const inicio = performance.now();
  timerResultado = setInterval(() => {
    restante = Math.max(0, TEMPO_RESULTADO_MS - (performance.now() - inicio));
    atualizarCountdown();
  }, 200);

  const meuToken = tokenFluxo;
  setTimeout(() => {
    if (meuToken !== tokenFluxo || estado !== ESTADOS.RESULTADO) return;
    clearInterval(timerResultado);
    iniciarCooldown();
  }, TEMPO_RESULTADO_MS);

  if (SOM_ATIVO) tocarSom(dados.status);
  atualizarHistorico();
}

function iniciarCooldown() {
  setEstado(ESTADOS.COOLDOWN);
  renderEstado("aguardando", "INTERVALO ENTRE PESSOAS", "Aguarde", "Preparando a catraca para a próxima pessoa");
  setText(cameraState, "Pausa");
  setText(cameraHint, "Aguarde");

  const meuToken = tokenFluxo;
  if (COOLDOWN_MS <= 0) {
    iniciarEsperaSaida();
    return;
  }

  timerCooldown = setTimeout(() => {
    if (meuToken === tokenFluxo && estado === ESTADOS.COOLDOWN) iniciarEsperaSaida();
  }, COOLDOWN_MS);
}

function finalizarEsperaSaida() {
  clearInterval(timerSaida);
  ausenciaDesde = null;
  esperaSaidaDesde = null;
  leiturasSemPresenca = 0;
  semRostoDesde = performance.now();
  renderPronto();
}

function iniciarEsperaSaida() {
  ausenciaDesde = null;
  esperaSaidaDesde = performance.now();
  leiturasSemPresenca = 0;
  renderAguardandoSaida();
  clearInterval(timerSaida);
  timerSaida = setInterval(verificarAreaLivre, Math.max(650, INTERVALO_MS));
  verificarAreaLivre();
}

async function verificarAreaLivre() {
  if (estado !== ESTADOS.AGUARDANDO_SAIDA || verificando || video.readyState < 2) return;
  verificando = true;

  try {
    const imagem = capturarFrame(video, canvas, 0.45);
    const resposta = await fetch("/api/presenca", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({imagem}),
      cache: "no-store"
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok || !dados.sucesso) throw new Error(dados.erro || "Falha ao verificar área");

    const agora = performance.now();
    const tempoEsperando = esperaSaidaDesde ? agora - esperaSaidaDesde : 0;

    if (dados.presenca) {
      ausenciaDesde = null;
      leiturasSemPresenca = 0;
      setText(statusNome,
        MAX_ESPERA_SAIDA_MS > 0
          ? `Pessoa detectada · limite automático em ${Math.max(0, Math.ceil((MAX_ESPERA_SAIDA_MS - tempoEsperando) / 1000))}s`
          : "Ainda há uma pessoa diante da câmera"
      );
    } else {
      leiturasSemPresenca += 1;
      if (ausenciaDesde === null) ausenciaDesde = agora;
      const tempoLivre = agora - ausenciaDesde;
      const faltam = Math.max(0, AUSENCIA_REARMAR_MS - tempoLivre);

      setText(statusNome, faltam > 0 ? "Área livre. Confirmando saída..." : "Área liberada");

      if (faltam <= 0 && leiturasSemPresenca >= 2) {
        finalizarEsperaSaida();
        return;
      }
    }

    if (MAX_ESPERA_SAIDA_MS > 0 && tempoEsperando >= MAX_ESPERA_SAIDA_MS) {
      finalizarEsperaSaida();
    }
  } catch (erro) {
    console.error("Falha ao confirmar saída:", erro);
    const tempoEsperando = esperaSaidaDesde ? performance.now() - esperaSaidaDesde : 0;

    // Se há limite configurado, ele também funciona como failsafe para falha da API.
    if (MAX_ESPERA_SAIDA_MS > 0 && tempoEsperando >= MAX_ESPERA_SAIDA_MS) {
      finalizarEsperaSaida();
    } else {
      setText(statusNome, "Confirmando área livre...");
    }
  } finally {
    verificando = false;
  }
}

async function verificarFrame() {
  if (verificando || video.readyState < 2) return;
  if (![ESTADOS.PRONTO, ESTADOS.IDENTIFICANDO, ESTADOS.PROVA_VIDA].includes(estado)) return;

  verificando = true;
  try {
    if (estado === ESTADOS.PRONTO) setEstado(ESTADOS.IDENTIFICANDO);

    const imagem = capturarFrame(video, canvas, 0.70);
    const resposta = await fetch("/api/verificar", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({imagem, catraca_id: CAT_ID}),
      cache: "no-store"
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok || !dados.sucesso) throw new Error(dados.erro || "Falha na verificação");

    if (dados.status === "SEM_ROSTO") {
      if (estado !== ESTADOS.PRONTO) {
        setEstado(ESTADOS.PRONTO);
        renderEstado("aguardando", "PRONTO", "Aproxime-se", "Pronto para identificar o próximo aluno");
        setText(cameraState, "Pronta");
        setText(cameraHint, "Centralize o rosto");
      }
      if (deveEntrarDescanso()) entrarDescanso();
    } else if (dados.status === "PROVA_VIDA") {
      semRostoDesde = performance.now();
      renderProvaVida(dados.motivo);
    } else if (dados.status === "AGUARDANDO") {
      semRostoDesde = performance.now();
      renderIdentificando();
    } else if (["LIBERADO", "BLOQUEADO", "NEGADO", "ERRO"].includes(dados.status)) {
      semRostoDesde = performance.now();
      renderResultado(dados);
    }
  } catch (erro) {
    console.error("Falha na leitura da catraca:", erro);
    cancelarFluxoAtual();
    setEstado(ESTADOS.ERRO);
    renderEstado("negado", "SISTEMA INDISPONÍVEL", "Falha na leitura", "Não foi possível validar o acesso. Tente novamente em instantes.");
    setText(cameraState, "Erro");

    const meuToken = tokenFluxo;
    timerRecuperacao = setTimeout(() => {
      if (meuToken !== tokenFluxo || estado !== ESTADOS.ERRO) return;
      semRostoDesde = performance.now();
      renderPronto();
    }, ERRO_RECUPERACAO_MS);
  } finally {
    verificando = false;
  }
}

function escapeLocal(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[c]);
}

async function atualizarHistorico() {
  try {
    const resposta = await fetch("/api/historico", {cache: "no-store"});
    if (!resposta.ok) return;
    const dados = await resposta.json();
    if (!historico) return;

    historico.innerHTML = "";
    (dados.logs || []).slice(0, 8).forEach(log => {
      const tr = document.createElement("tr");
      let horario = "—";
      try {
        horario = new Date(log.data_hora.replace(" ", "T") + "Z").toLocaleTimeString("pt-BR");
      } catch (_) {}

      tr.innerHTML =
        `<td class="mono">${escapeLocal(horario)}</td>` +
        `<td><strong>${escapeLocal(log.nome || "Não identificado")}</strong></td>` +
        `<td><span class="badge badge--${escapeLocal(String(log.status || "").toLowerCase())}">${escapeLocal(log.status)}</span></td>` +
        `<td>${escapeLocal(log.motivo || "—")}</td>`;
      historico.appendChild(tr);
    });
  } catch (_) {}
}

ligarCamera(video).then(() => {
  setText(cameraState, "Pronta");
  setText(livenessState, LIVENESS_ATIVO ? "Prova de vida ativa" : "Prova de vida desativada");

  if (MODO_PRESENCA === "sensor") {
    console.warn("Sensor externo ainda não conectado; usando presença inteligente como fallback.");
  }

  semRostoDesde = performance.now();
  renderPronto();
  atualizarHistorico();
  atualizarRelogio();

  timerReconhecimento = setInterval(verificarFrame, INTERVALO_MS);
  timerHistorico = setInterval(atualizarHistorico, INTERVALO_HISTORICO_MS);
  timerRelogio = setInterval(atualizarRelogio, 1000);

  timerMovimento = setInterval(() => {
    if (estado === ESTADOS.DESCANSO && medirMovimento()) acordarPorPresenca();
  }, INTERVALO_DETECTOR_PRESENCA_MS);
}).catch(erro => {
  console.error("Não foi possível iniciar a câmera:", erro);
  cancelarFluxoAtual();
  setEstado(ESTADOS.ERRO);
  setText(cameraState, "Erro");
  renderEstado("negado", "CÂMERA INDISPONÍVEL", "Verifique a câmera", "Autorize o acesso à câmera no navegador e recarregue a página.");
});

window.addEventListener("beforeunload", () => {
  clearInterval(timerReconhecimento);
  clearInterval(timerHistorico);
  clearInterval(timerMovimento);
  clearInterval(timerSaida);
  clearInterval(timerRelogio);
  clearTimeout(timerCooldown);
  clearTimeout(timerRecuperacao);
  desligarCamera(video);
});
