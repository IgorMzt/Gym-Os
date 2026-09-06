(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const dialog = $('#professor-dialog');
  const form = $('#professor-form');
  let fotoBase64 = null;
  let removerFoto = false;

  const showMsg = (txt, erro=true) => { const el=$('#prof-msg'); if(el) el.innerHTML=`<div class="status-msg ${erro?'status-msg--erro':'status-msg--ok'}">${String(txt||'')}</div>`; };
  const close = () => dialog?.close();
  $('#novo-professor')?.addEventListener('click',()=>{ form?.reset(); fotoBase64=null; removerFoto=false; const p=$('#prof-preview'); if(p){p.innerHTML='P';} dialog?.showModal(); });
  $('#editar-professor')?.addEventListener('click',()=>dialog?.showModal());
  $('#prof-fechar')?.addEventListener('click',close); $('#prof-cancelar')?.addEventListener('click',close);

  $('#prof-foto')?.addEventListener('change',(e)=>{ const f=e.target.files?.[0]; if(!f)return; if(f.size>5*1024*1024){showMsg('A foto deve ter no máximo 5 MB.');return;} const r=new FileReader(); r.onload=()=>{fotoBase64=r.result;removerFoto=false;const p=$('#prof-preview');if(p)p.innerHTML=`<img src="${r.result}" alt="">`;}; r.readAsDataURL(f); });
  $('#remover-foto')?.addEventListener('click',()=>{removerFoto=true;fotoBase64=null;const p=$('#prof-preview');if(p)p.innerHTML=($('#prof-nome')?.value||'P').slice(0,1).toUpperCase();});

  form?.addEventListener('submit',async(e)=>{ e.preventDefault(); const id=$('#prof-id')?.value||''; const payload={nome:$('#prof-nome').value.trim(),cpf:$('#prof-cpf').value.trim(),cref:$('#prof-cref').value.trim(),telefone:$('#prof-telefone').value.trim(),email:$('#prof-email').value.trim(),especialidade:$('#prof-especialidade').value.trim(),usuario_id:$('#prof-usuario').value||null,observacoes:$('#prof-observacoes').value.trim(),ativo:$('#prof-ativo').checked}; if(fotoBase64)payload.foto_base64=fotoBase64;if(removerFoto)payload.remover_foto=true; const res=await fetch(id?`/api/professores/${id}`:'/api/professores',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const data=await res.json().catch(()=>({})); if(!res.ok||!data.sucesso){showMsg(data.erro||'Não foi possível salvar.');return;} location.href=data.redirect_url||location.href; });

  $('#busca-professor')?.addEventListener('input',e=>{const q=e.target.value.toLowerCase().trim();$$('#prof-grid [data-search]').forEach(x=>x.hidden=q&&!x.dataset.search.includes(q));});
  $('#busca-vinculados')?.addEventListener('input',e=>{const q=e.target.value.toLowerCase().trim();$$('#lista-vinculados [data-search]').forEach(x=>x.hidden=q&&!x.dataset.search.includes(q));});
  $('#busca-disponiveis')?.addEventListener('input',e=>{const q=e.target.value.toLowerCase().trim();$$('#lista-disponiveis [data-search]').forEach(x=>x.hidden=q&&!x.dataset.search.includes(q));});

  $$('.btn-vincular').forEach(btn=>btn.addEventListener('click',async()=>{btn.disabled=true;const res=await fetch(`/api/professores/${window.PROFESSOR_ID}/alunos/${btn.dataset.aluno}`,{method:'POST'});const d=await res.json().catch(()=>({}));if(res.ok&&d.sucesso)location.reload();else{btn.disabled=false;alert(d.erro||'Não foi possível vincular.');}}));
  $$('.btn-desvincular').forEach(btn=>btn.addEventListener('click',async()=>{if(!confirm(`Desvincular ${btn.dataset.nome} deste professor?`))return;btn.disabled=true;const res=await fetch(`/api/professores/${window.PROFESSOR_ID}/alunos/${btn.dataset.aluno}`,{method:'DELETE'});const d=await res.json().catch(()=>({}));if(res.ok&&d.sucesso)location.reload();else{btn.disabled=false;alert(d.erro||'Não foi possível desvincular.');}}));
})();
