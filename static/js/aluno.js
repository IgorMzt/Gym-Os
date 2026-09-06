const pessoaId = window.ALUNO_ID;
const pessoaNome = window.ALUNO_NOME || "este aluno";
const alunoCfg = window.ALUNO_CONFIG || {};
const PREP_BIO = Math.max(0, Number(alunoCfg.preparacaoCapturaMs ?? 550));
const INTERVALO_BIO = Math.max(0, Number(alunoCfg.intervaloCapturaMs ?? 450));
const msg = document.getElementById("perfil-mensagem");
const cpf = document.getElementById("cpf");
const bioVideo = document.getElementById("bio-video");
const bioCanvas = document.getElementById("bio-canvas");
const bioBtn = document.getElementById("btn-biometria");
const bioMsg = document.getElementById("bio-mensagem");
const bioCount = document.getElementById("biometria-contador");
const bioHint = document.getElementById("bio-hint");
const modal = document.getElementById("perfil-confirm-modal");
const modalTitle = document.getElementById("perfil-confirm-title");
const modalText = document.getElementById("perfil-confirm-text");
const modalAction = document.getElementById("perfil-confirm-action");
let acaoPendente = null;

const esc = valor => String(valor ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
function mostrar(texto, tipo="sucesso") { if (msg) msg.innerHTML = `<div class="status-msg status-msg--${tipo}">${esc(texto)}</div>`; }
function abrirModal(titulo, texto, acao, perigo=false) { acaoPendente=acao; modalTitle.textContent=titulo; modalText.textContent=texto; modalAction.textContent=perigo?"Remover":"Confirmar"; modalAction.className=`btn ${perigo?"btn--perigo":"btn--primario"}`; modal.classList.remove("hidden"); }
function fecharModal(){ modal.classList.add("hidden"); acaoPendente=null; }

document.querySelectorAll("[data-profile-modal-close]").forEach(el=>el.addEventListener("click",fecharModal));
window.addEventListener("keydown",e=>{if(e.key==="Escape")fecharModal();});

cpf?.addEventListener("input", () => {
  let v = cpf.value.replace(/\D/g, "").slice(0, 11);
  if(v.length>9)v=v.replace(/(\d{3})(\d{3})(\d{3})(\d{1,2}).*/, '$1.$2.$3-$4'); else if(v.length>6)v=v.replace(/(\d{3})(\d{3})(\d{1,3}).*/, '$1.$2.$3'); else if(v.length>3)v=v.replace(/(\d{3})(\d{1,3}).*/, '$1.$2');
  cpf.value=v;
});
function somarDias(iso, dias) { const d = new Date(`${iso}T12:00:00`); d.setDate(d.getDate()+Number(dias)); return d.toISOString().slice(0,10); }
document.getElementById("plano_id")?.addEventListener("change", e => { const o=e.target.selectedOptions[0]; const inicio=document.getElementById("data_inicio"); const venc=document.getElementById("data_vencimento"); if(o?.dataset.dias && inicio.value) venc.value=somarDias(inicio.value,o.dataset.dias); });
document.getElementById("data_inicio")?.addEventListener("change",()=>document.getElementById("plano_id")?.dispatchEvent(new Event("change")));

document.getElementById("btn-salvar")?.addEventListener("click", async () => {
  const btn=document.getElementById("btn-salvar"); btn.disabled=true; const original=btn.textContent; btn.textContent="Salvando...";
  const payload={nome:document.getElementById("nome").value,cpf:cpf.value,data_nascimento:document.getElementById("data_nascimento").value,sexo:document.getElementById("sexo").value,telefone:document.getElementById("telefone").value,email:document.getElementById("email").value,plano_id:document.getElementById("plano_id").value,data_inicio:document.getElementById("data_inicio").value,data_vencimento:document.getElementById("data_vencimento").value,status_financeiro:document.getElementById("status_financeiro").value,observacoes:document.getElementById("observacoes").value,liberado:document.getElementById("liberado").checked};
  try { const r=await fetch(`/api/pessoas/${pessoaId}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); const d=await r.json().catch(()=>({})); if(!r.ok||!d.sucesso)throw new Error(d.erro||"Não foi possível salvar."); mostrar(d.mensagem||"Cadastro atualizado."); }
  catch(e){mostrar(e.message||"Erro de conexão com o servidor.","erro");}
  finally{btn.disabled=false;btn.textContent=original;}
});

document.getElementById("btn-renovar")?.addEventListener("click",()=>abrirModal("Renovar plano",`Renovar o plano atual de ${pessoaNome}? O novo vencimento será calculado automaticamente.`,"renovar"));
document.getElementById("btn-toggle-acesso")?.addEventListener("click",e=>{const acao=e.currentTarget.dataset.acao;abrirModal(acao==="bloquear"?"Bloquear acesso":"Desbloquear acesso",acao==="bloquear"?`Bloquear manualmente o acesso de ${pessoaNome}?`:`Remover o bloqueio manual de ${pessoaNome}?`,acao);});
document.getElementById("btn-remover-aluno")?.addEventListener("click",()=>abrirModal("Remover aluno",`Remover definitivamente o cadastro e a biometria de ${pessoaNome}? O histórico de acessos será preservado.`,"remover",true));

modalAction?.addEventListener("click",async()=>{
  if(!acaoPendente)return; const acao=acaoPendente; modalAction.disabled=true;
  try{
    if(acao==="renovar"){
      const r=await fetch(`/api/pessoas/${pessoaId}/renovar`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plano_id:document.getElementById("plano_id").value})}); const d=await r.json().catch(()=>({})); if(!r.ok||!d.sucesso)throw new Error(d.erro||"Falha ao renovar."); document.getElementById("data_vencimento").value=d.data_vencimento; document.getElementById("status_financeiro").value="EM_DIA"; fecharModal(); mostrar(`Plano renovado até ${new Date(`${d.data_vencimento}T12:00:00`).toLocaleDateString("pt-BR")}.`);
    }else{
      const r=await fetch(`/api/pessoas/${pessoaId}/${acao}`,{method:"POST"}); const d=await r.json().catch(()=>({})); if(!r.ok||!d.sucesso)throw new Error(d.erro||"Não foi possível concluir."); fecharModal(); if(acao==="remover"){window.location.href="/gerenciar";return;} const toggle=document.getElementById("btn-toggle-acesso"); const bloqueado=acao==="bloquear"; document.getElementById("liberado").checked=!bloqueado; toggle.dataset.acao=bloqueado?"liberar":"bloquear"; toggle.textContent=bloqueado?"Desbloquear acesso":"Bloquear acesso"; toggle.classList.toggle("btn--sucesso",bloqueado); mostrar(bloqueado?"Acesso bloqueado.":"Bloqueio manual removido.");
    }
  }catch(e){mostrar(e.message||"Erro de conexão.","erro");}
  finally{modalAction.disabled=false;}
});

document.getElementById("btn-foco-biometria")?.addEventListener("click",()=>document.getElementById("secao-biometria")?.scrollIntoView({behavior:"smooth",block:"center"}));

ligarCamera(bioVideo).catch(() => { if(bioBtn)bioBtn.disabled=true; if(bioHint)bioHint.textContent="Câmera indisponível"; });
bioBtn?.addEventListener("click", async()=>{
  bioBtn.disabled=true; const imagens=[]; bioHint.textContent="Centralize o rosto e mova levemente a cabeça";
  try{
    for(let i=1;i<=5;i++){bioCount.textContent=`${i-1} / 5`;await dormir(PREP_BIO);imagens.push(capturarFrame(bioVideo,bioCanvas,.74));bioCount.textContent=`${i} / 5`;await dormir(INTERVALO_BIO);}
    const r=await fetch(`/api/pessoas/${pessoaId}/biometria`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({imagens})});const d=await r.json().catch(()=>({}));if(!r.ok||!d.sucesso)throw new Error(d.erro||"Não foi possível atualizar a biometria.");bioMsg.innerHTML=`<div class="status-msg status-msg--sucesso">${esc(d.mensagem)}</div>`;bioHint.textContent="Biometria atualizada";
  }catch(e){bioMsg.innerHTML=`<div class="status-msg status-msg--erro">${esc(e.message||"Não foi possível atualizar a biometria.")}</div>`;bioCount.textContent="0 / 5";bioHint.textContent="Capture novamente";}finally{bioBtn.disabled=false;}
});


document.getElementById("btn-copiar-pix-atual")?.addEventListener("click", async () => {
  const payload=document.getElementById("pix-payload-atual")?.value || "";
  await navigator.clipboard.writeText(payload);
  mostrar("PIX copia e cola copiado.");
});

document.getElementById("btn-gerar-pix")?.addEventListener("click", async (e) => {
  const btn=e.currentTarget, box=document.getElementById("pix-resultado"); btn.disabled=true; const old=btn.textContent; btn.textContent="Gerando...";
  try {
    const r=await fetch(`/api/pessoas/${pessoaId}/cobrancas/pix`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    const d=await r.json().catch(()=>({})); if(!r.ok||!d.sucesso) throw new Error(d.erro||"Falha ao gerar PIX.");
    const img=d.encodedImage?`<img class="pix-qr-v51" alt="QR Code PIX" src="data:image/png;base64,${d.encodedImage}">`:"";
    box.innerHTML=`<div class="pix-box-v51">${img}<strong>PIX gerado</strong><small>Vencimento ${esc(d.vencimento)}</small><textarea id="pix-payload" readonly>${esc(d.payload||"")}</textarea><button class="btn btn--outline btn--full" type="button" id="btn-copiar-pix">Copiar PIX</button></div>`;
    document.getElementById("btn-copiar-pix")?.addEventListener("click",async()=>{await navigator.clipboard.writeText(d.payload||""); mostrar("PIX copia e cola copiado.");});
  } catch(err) { box.innerHTML=`<div class="status-msg status-msg--erro">${esc(err.message||"Erro ao gerar cobrança.")}</div>`; }
  finally { btn.disabled=false; btn.textContent=old; }
});


// Gerenciamento de acesso ao PWA do aluno (Admin)
document.getElementById('btn-salvar-app-v58')?.addEventListener('click', async () => {
  const btn = document.getElementById('btn-salvar-app-v58');
  const msg = document.getElementById('app-access-msg-v58');
  btn.disabled = true;
  try {
    const response = await fetch(`/api/pessoas/${window.ALUNO_ID}/acesso-app`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        login: document.getElementById('app-login-v58').value.trim(),
        senha: document.getElementById('app-senha-v58').value,
        ativo: document.getElementById('app-ativo-v58').checked
      })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.sucesso) throw new Error(data.erro || 'Não foi possível salvar o acesso.');
    msg.innerHTML = '<div class="status-msg status-msg--ok">Acesso do aluno atualizado.</div>';
    document.getElementById('app-senha-v58').value = '';
  } catch (e) {
    msg.innerHTML = `<div class="status-msg status-msg--erro">${String(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
});
