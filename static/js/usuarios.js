(() => {
  const escapeHtmlLocal = (valor) => String(valor ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const dialog = document.querySelector('#usuario-dialog');
  if (!dialog) return;
  const form = document.querySelector('#usuario-form');
  const msg = document.querySelector('#usuario-msg');
  const idEl = document.querySelector('#usuario-id');
  const nome = document.querySelector('#usuario-nome');
  const login = document.querySelector('#usuario-login');
  const papel = document.querySelector('#usuario-papel');
  const senha = document.querySelector('#usuario-senha');
  const ativo = document.querySelector('#usuario-ativo');
  const titulo = document.querySelector('#usuario-dialog-titulo');
  const campoSenha = document.querySelector('#campo-senha');

  function abrirNovo(){
    form.reset(); idEl.value=''; ativo.checked=true; campoSenha.hidden=false; senha.required=true;
    titulo.textContent='Novo usuário'; msg.innerHTML=''; dialog.showModal();
  }
  function abrirEditar(tr){
    idEl.value=tr.dataset.id; nome.value=tr.dataset.nome; login.value=tr.dataset.login;
    papel.value=tr.dataset.papel; ativo.checked=tr.dataset.ativo==='1'; senha.value=''; senha.required=false;
    campoSenha.hidden=false; titulo.textContent='Editar usuário'; msg.innerHTML=''; dialog.showModal();
  }
  document.querySelector('#novo-usuario')?.addEventListener('click', abrirNovo);
  document.querySelectorAll('.btn-editar-usuario').forEach(btn=>btn.addEventListener('click',()=>abrirEditar(btn.closest('tr'))));
  document.querySelector('#fechar-dialog')?.addEventListener('click',()=>dialog.close());
  document.querySelector('#cancelar-dialog')?.addEventListener('click',()=>dialog.close());

  form.addEventListener('submit', async (ev)=>{
    ev.preventDefault();
    const id=idEl.value;
    const payload={nome:nome.value.trim(), login:login.value.trim(), papel:papel.value, ativo:ativo.checked};
    if (senha.value) payload.senha=senha.value;
    const url=id ? `/api/usuarios/${id}` : '/api/usuarios';
    const method=id ? 'PUT' : 'POST';
    const res=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await res.json().catch(()=>({}));
    if(!res.ok||!data.sucesso){msg.innerHTML=`<div class="status-msg status-msg--erro">${escapeHtmlLocal(data.erro||'Não foi possível salvar.')}</div>`;return;}
    location.reload();
  });
})();
