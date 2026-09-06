(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];

  const dialog = $('#exercise-dialog');
  const form = $('#exercise-form');
  let imagemBase64 = null;
  let removerImagem = false;

  const escMsg = (txt) => String(txt || '');
  const msg = (txt, erro = true) => {
    const el = $('#exercise-msg');
    if (el) el.innerHTML = `<div class="status-msg ${erro ? 'status-msg--erro' : 'status-msg--ok'}">${escMsg(txt)}</div>`;
  };

  const previewPadrao = () => { const p=$('#exercise-preview'); if (p) p.innerHTML='▦'; };
  const limpar = () => {
    form?.reset();
    $('#exercise-id').value = '';
    $('#exercise-dialog-title').textContent = 'Novo exercício';
    $('#exercise-ativo').checked = true;
    $('#exercise-tipo').value = 'FORCA';
    imagemBase64 = null;
    removerImagem = false;
    previewPadrao();
    const m=$('#exercise-msg'); if(m)m.innerHTML='';
  };
  const fechar = () => dialog?.close();

  $('#novo-exercicio')?.addEventListener('click', () => { limpar(); dialog?.showModal(); });
  $('#exercise-fechar')?.addEventListener('click', fechar);
  $('#exercise-cancelar')?.addEventListener('click', fechar);

  $('#exercise-imagem')?.addEventListener('change', (ev) => {
    const f = ev.target.files?.[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { msg('A imagem deve ter no máximo 5 MB.'); return; }
    const r = new FileReader();
    r.onload = () => {
      imagemBase64 = r.result;
      removerImagem = false;
      const p=$('#exercise-preview');
      if(p)p.innerHTML=`<img src="${r.result}" alt="">`;
    };
    r.readAsDataURL(f);
  });

  $('#exercise-remover-imagem')?.addEventListener('click', () => {
    imagemBase64 = null;
    removerImagem = true;
    previewPadrao();
  });

  $$('.editar-exercicio').forEach(btn => btn.addEventListener('click', async () => {
    limpar();
    btn.disabled = true;
    try {
      const res = await fetch(`/api/exercicios/${btn.dataset.id}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.sucesso) throw new Error(data.erro || 'Não foi possível abrir o exercício.');
      const e = data.exercicio;
      $('#exercise-id').value = e.id;
      $('#exercise-dialog-title').textContent = 'Editar exercício';
      $('#exercise-nome').value = e.nome || '';
      $('#exercise-grupo').value = e.grupo_muscular || '';
      $('#exercise-equipamento').value = e.equipamento || '';
      $('#exercise-tipo').value = e.tipo || 'FORCA';
      $('#exercise-dificuldade').value = e.dificuldade || '';
      $('#exercise-instrucoes').value = e.instrucoes || '';
      $('#exercise-video').value = e.video_url || '';
      $('#exercise-observacoes').value = e.observacoes || '';
      $('#exercise-ativo').checked = !!e.ativo;
      const p=$('#exercise-preview');
      if (p) p.innerHTML = e.imagem_path ? `<img src="/static/${e.imagem_path}" alt="">` : '▦';
      removerImagem = false;
      dialog?.showModal();
    } catch (err) {
      alert(err.message || 'Erro ao abrir exercício.');
    } finally {
      btn.disabled = false;
    }
  }));

  form?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const id = $('#exercise-id').value;
    const salvar = $('#exercise-salvar');
    salvar.disabled = true;
    const payload = {
      nome: $('#exercise-nome').value.trim(),
      grupo_muscular: $('#exercise-grupo').value.trim(),
      equipamento: $('#exercise-equipamento').value.trim(),
      tipo: $('#exercise-tipo').value,
      dificuldade: $('#exercise-dificuldade').value || null,
      instrucoes: $('#exercise-instrucoes').value.trim(),
      video_url: $('#exercise-video').value.trim(),
      observacoes: $('#exercise-observacoes').value.trim(),
      ativo: $('#exercise-ativo').checked
    };
    if (imagemBase64) payload.imagem_base64 = imagemBase64;
    if (removerImagem) payload.remover_imagem = true;

    try {
      const res = await fetch(id ? `/api/exercicios/${id}` : '/api/exercicios', {
        method: id ? 'PUT' : 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.sucesso) throw new Error(data.erro || 'Não foi possível salvar.');
      location.reload();
    } catch (err) {
      msg(err.message || 'Erro de conexão.');
      salvar.disabled = false;
    }
  });

  const aplicarFiltros = () => {
    const q = ($('#busca-exercicio')?.value || '').toLowerCase().trim();
    const grupo = $('#filtro-grupo')?.value || '';
    const tipo = $('#filtro-tipo')?.value || '';
    const status = $('#filtro-status')?.value || 'ativo';
    let visiveis = 0;
    $$('.exercise-card-v54').forEach(card => {
      const okQ = !q || card.dataset.search.includes(q);
      const okGrupo = !grupo || card.dataset.grupo === grupo;
      const okTipo = !tipo || card.dataset.tipo === tipo;
      const ativo = card.dataset.ativo === '1';
      const okStatus = status === 'todos' || (status === 'ativo' && ativo) || (status === 'inativo' && !ativo);
      card.hidden = !(okQ && okGrupo && okTipo && okStatus);
      if (!card.hidden) visiveis++;
    });
    const vazio = $('#exercise-empty-filter');
    if (vazio) vazio.hidden = visiveis > 0;
  };

  ['#busca-exercicio','#filtro-grupo','#filtro-tipo','#filtro-status'].forEach(sel => {
    $(sel)?.addEventListener(sel === '#busca-exercicio' ? 'input' : 'change', aplicarFiltros);
  });
  aplicarFiltros();
})();
