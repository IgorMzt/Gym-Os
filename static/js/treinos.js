(() => {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const dialog=$('#workout-dialog'), picker=$('#exercise-picker-v55'), builder=$('#treinos-builder');
  let treinos=[], pickerTreino=null;

  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const msg=(s,erro=true)=>{$('#workout-msg').innerHTML=`<div class="status-msg ${erro?'status-msg--erro':'status-msg--ok'}">${esc(s)}</div>`};

  function render(){
    builder.innerHTML=treinos.map((t,ti)=>`
      <section class="workout-block-v55">
        <div class="workout-block-head-v55">
          <input class="treino-nome-v55" data-ti="${ti}" value="${esc(t.nome)}" maxlength="80" placeholder="Treino A">
          <div>
            <button type="button" class="btn btn--secundario btn--mini add-ex-v55" data-ti="${ti}">+ Exercício</button>
            <button type="button" class="link-danger-v53 del-treino-v55" data-ti="${ti}">Remover treino</button>
          </div>
        </div>
        <textarea class="treino-obs-v55" data-ti="${ti}" rows="1" maxlength="1000" placeholder="Observações do treino">${esc(t.observacoes||'')}</textarea>
        <div class="workout-exercises-v55">
          ${t.exercicios.length?t.exercicios.map((e,ei)=>`
            <article class="workout-exercise-row-v55">
              <div class="workout-exercise-name-v55"><b>${ei+1}</b><span><strong>${esc(e.exercicio_nome)}</strong><small>${esc(e.grupo_muscular||'')}</small></span></div>
              <div class="workout-fields-v55">
                <label>Séries<input type="number" min="1" max="99" data-ti="${ti}" data-ei="${ei}" data-f="series" value="${esc(e.series??'')}"></label>
                <label>Repetições<input maxlength="40" data-ti="${ti}" data-ei="${ei}" data-f="repeticoes" value="${esc(e.repeticoes||'')}" placeholder="8-12"></label>
                <label>Carga<input maxlength="40" data-ti="${ti}" data-ei="${ei}" data-f="carga" value="${esc(e.carga||'')}" placeholder="kg / livre"></label>
                <label>Descanso (s)<input type="number" min="0" max="3600" data-ti="${ti}" data-ei="${ei}" data-f="descanso_segundos" value="${esc(e.descanso_segundos??'')}"></label>
              </div>
              <input class="exercise-note-v55" maxlength="1000" data-ti="${ti}" data-ei="${ei}" data-f="observacoes" value="${esc(e.observacoes||'')}" placeholder="Observação específica">
              <div class="workout-row-actions-v55">
                <button type="button" data-ti="${ti}" data-ei="${ei}" class="move-up-v55" ${ei===0?'disabled':''}>↑</button>
                <button type="button" data-ti="${ti}" data-ei="${ei}" class="move-down-v55" ${ei===t.exercicios.length-1?'disabled':''}>↓</button>
                <button type="button" data-ti="${ti}" data-ei="${ei}" class="del-ex-v55">×</button>
              </div>
            </article>`).join(''):`<div class="empty-builder-v55">Adicione exercícios da biblioteca.</div>`}
        </div>
      </section>`).join('');

    $$('.treino-nome-v55').forEach(x=>x.oninput=()=>treinos[+x.dataset.ti].nome=x.value);
    $$('.treino-obs-v55').forEach(x=>x.oninput=()=>treinos[+x.dataset.ti].observacoes=x.value);
    $$('[data-f]').forEach(x=>x.oninput=()=>treinos[+x.dataset.ti].exercicios[+x.dataset.ei][x.dataset.f]=x.value);
    $$('.add-ex-v55').forEach(x=>x.onclick=()=>{pickerTreino=+x.dataset.ti; $('#picker-search').value=''; filtrarPicker(); picker.showModal()});
    $$('.del-treino-v55').forEach(x=>x.onclick=()=>{treinos.splice(+x.dataset.ti,1);render()});
    $$('.del-ex-v55').forEach(x=>x.onclick=()=>{treinos[+x.dataset.ti].exercicios.splice(+x.dataset.ei,1);render()});
    $$('.move-up-v55').forEach(x=>x.onclick=()=>mover(+x.dataset.ti,+x.dataset.ei,-1));
    $$('.move-down-v55').forEach(x=>x.onclick=()=>mover(+x.dataset.ti,+x.dataset.ei,1));
  }
  function mover(ti,ei,d){const a=treinos[ti].exercicios,n=ei+d;if(n<0||n>=a.length)return;[a[ei],a[n]]=[a[n],a[ei]];render()}
  function addTreino(){treinos.push({nome:`Treino ${String.fromCharCode(65+treinos.length)}`,observacoes:'',exercicios:[]});render()}
  function reset(){
    $('#workout-form').reset(); $('#ficha-id').value=''; $('#workout-title').textContent='Nova ficha'; $('#ficha-ativa').checked=true;
    $('#workout-msg').innerHTML=''; treinos=[]; addTreino();
  }

  $('#nova-ficha')?.addEventListener('click',()=>{reset();dialog.showModal()});
  $('#add-treino')?.addEventListener('click',addTreino);
  $('#workout-close')?.addEventListener('click',()=>dialog.close());
  $('#workout-cancel')?.addEventListener('click',()=>dialog.close());
  $('#picker-close')?.addEventListener('click',()=>picker.close());

  function filtrarPicker(){
    const q=($('#picker-search').value||'').toLowerCase().trim();
    $$('.picker-item-v55').forEach(x=>x.hidden=!!q&&!x.dataset.search.includes(q));
  }
  $('#picker-search')?.addEventListener('input',filtrarPicker);
  $$('.picker-item-v55').forEach(x=>x.addEventListener('click',()=>{
    if(pickerTreino===null)return;
    if(treinos[pickerTreino].exercicios.some(e=>e.exercicio_id===+x.dataset.id)){alert('Este exercício já está neste treino.');return}
    treinos[pickerTreino].exercicios.push({
      exercicio_id:+x.dataset.id,exercicio_nome:x.dataset.nome,grupo_muscular:x.dataset.grupo,
      series:3,repeticoes:'8-12',carga:'',descanso_segundos:60,observacoes:''
    });
    picker.close();render();
  }));

  $$('.editar-ficha').forEach(btn=>btn.addEventListener('click',async()=>{
    btn.disabled=true;
    try{
      const r=await fetch(`/api/fichas-treino/${btn.dataset.id}`),d=await r.json().catch(()=>({}));
      if(!r.ok||!d.sucesso)throw new Error(d.erro||'Não foi possível abrir a ficha.');
      const f=d.ficha;
      $('#ficha-id').value=f.id;$('#workout-title').textContent='Editar ficha';
      $('#ficha-aluno').value=f.pessoa_id;$('#ficha-professor').value=f.professor_id||'';
      $('#ficha-nome').value=f.nome||'';$('#ficha-objetivo').value=f.objetivo||'';
      $('#ficha-inicio').value=f.data_inicio||'';$('#ficha-fim').value=f.data_fim||'';
      $('#ficha-observacoes').value=f.observacoes||'';$('#ficha-ativa').checked=!!f.ativo;
      treinos=(f.treinos||[]).map(t=>({nome:t.nome,observacoes:t.observacoes||'',exercicios:(t.exercicios||[]).map(e=>({...e}))}));
      if(!treinos.length)addTreino();else render();
      $('#workout-msg').innerHTML='';dialog.showModal();
    }catch(e){alert(e.message)}finally{btn.disabled=false}
  }));

  $('#workout-form')?.addEventListener('submit',async ev=>{
    ev.preventDefault();
    const id=$('#ficha-id').value, save=$('#workout-save');save.disabled=true;
    const payload={
      pessoa_id:$('#ficha-aluno').value,professor_id:$('#ficha-professor').value||null,
      nome:$('#ficha-nome').value.trim(),objetivo:$('#ficha-objetivo').value.trim(),
      data_inicio:$('#ficha-inicio').value||null,data_fim:$('#ficha-fim').value||null,
      observacoes:$('#ficha-observacoes').value.trim(),ativo:$('#ficha-ativa').checked,treinos
    };
    try{
      const r=await fetch(id?`/api/fichas-treino/${id}`:'/api/fichas-treino',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const d=await r.json().catch(()=>({}));if(!r.ok||!d.sucesso)throw new Error(d.erro||'Não foi possível salvar a ficha.');
      location.reload();
    }catch(e){msg(e.message)}finally{save.disabled=false}
  });

  const dupDialog=$('#duplicate-workout-v591');let dupId=null;
  $$('.duplicar-ficha-v591').forEach(b=>b.addEventListener('click',()=>{dupId=b.dataset.id;$('#duplicate-name-v591').textContent=`Criar uma cópia de "${b.dataset.nome}" para outro aluno.`;$('#duplicate-student-v591').value='';$('#duplicate-msg-v591').innerHTML='';dupDialog.showModal()}));
  $('#duplicate-close-v591')?.addEventListener('click',()=>dupDialog.close());$('#duplicate-cancel-v591')?.addEventListener('click',()=>dupDialog.close());
  $('#duplicate-confirm-v591')?.addEventListener('click',async()=>{const b=$('#duplicate-confirm-v591'),pid=$('#duplicate-student-v591').value;if(!pid){$('#duplicate-msg-v591').innerHTML='<div class="status-msg status-msg--erro">Selecione o aluno.</div>';return}b.disabled=true;try{const r=await fetch(`/api/fichas-treino/${dupId}/duplicar`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pessoa_id:pid})}),d=await r.json();if(!r.ok||!d.sucesso)throw new Error(d.erro||'Não foi possível duplicar.');location.reload()}catch(e){$('#duplicate-msg-v591').innerHTML=`<div class="status-msg status-msg--erro">${esc(e.message)}</div>`}finally{b.disabled=false}});

  function filtros(){
    const q=($('#busca-ficha')?.value||'').toLowerCase().trim(),s=$('#status-ficha')?.value||'ativa';let n=0;
    $$('.workout-card-v55').forEach(c=>{const a=c.dataset.ativo==='1';c.hidden=!( (!q||c.dataset.search.includes(q)) && (s==='todas'||(s==='ativa'&&a)||(s==='inativa'&&!a)) );if(!c.hidden)n++});
    $('#ficha-empty').hidden=n>0;
  }
  $('#busca-ficha')?.addEventListener('input',filtros);$('#status-ficha')?.addEventListener('change',filtros);filtros();
})();
