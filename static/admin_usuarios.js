// Aba "Usuários" do /admin padrão (spec 57 §5.1). Fonte única: produtos-core/produtos_core/static/admin_usuarios.js
// (cada produto serve uma cópia em /s/admin_usuarios.js). Listar, trocar plano, dar dias e apagar (o QA não apaga).
;(() => {
  const $ = (s, r = document) => r.querySelector(s)
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  const data = (t) => (t ? new Date(t * 1000).toLocaleDateString('pt-BR') : '—')
  const api = async (url, opt = {}) => {
    const r = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opt })
    let j = {}; try { j = await r.json() } catch {}
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Não deu certo (' + r.status + ')')
    return j
  }
  const nav = $('nav.abas'), main = $('main')
  if (!nav || !main) return
  nav.insertAdjacentHTML('beforeend', '<button data-aba="usuarios" aria-selected="false">Usuários</button>')
  main.insertAdjacentHTML('beforeend', `<section data-p="usuarios" hidden>
    <input class="busca" id="u-busca" placeholder="Buscar por e-mail">
    <div class="msg" id="u-msg" role="status"></div>
    <div class="lista" id="u-lista"></div></section>`)
  let q = '', tempo = null
  async function carregar() {
    const el = $('#u-lista'); el.innerHTML = '<p class="msg">Carregando…</p>'
    try {
      const j = await api('/api/painel/usuarios?q=' + encodeURIComponent(q))
      el.innerHTML = (j.usuarios.length ? '' : '<p class="msg">Nenhum usuário.</p>') + j.usuarios.map((u) => `
        <div class="item" data-u="${u.id}" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 0;border-bottom:1px solid var(--bd)">
          <b style="flex:1;min-width:200px">${esc(u.email)}${u.qa ? ' <small>(QA)</small>' : ''}</b>
          <small style="width:150px">${u.ativo ? 'ativo até ' + data(u.ativo_ate) : 'sem plano ativo'}</small>
          <input data-campo="plano" value="${esc(u.plano || '')}" placeholder="plano" style="width:110px">
          <input data-campo="dias" type="number" min="0" max="3650" placeholder="dias" style="width:80px">
          <button class="btn" data-acao="salvar">Salvar</button>
          ${u.qa ? '' : '<button class="btn" data-acao="apagar">Apagar</button>'}
          ${u.canais ? `<div style="flex-basis:100%;display:grid;gap:6px;padding-left:16px">${u.canais.map((k) => `
            <div data-canal="${esc(k.canal)}" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
              <small style="width:90px">canal <b>${esc(k.canal)}</b></small>
              <small style="width:150px">${k.ativo ? 'ativo até ' + data(k.ativo_ate) : 'sem plano ativo'}</small>
              <input data-campo="plano" value="${esc(k.plano || '')}" placeholder="plano" style="width:110px">
              <input data-campo="dias" type="number" min="0" max="3650" placeholder="dias" style="width:80px">
              <button class="btn" data-acao="salvar-canal">Salvar canal</button></div>`).join('')}</div>` : ''}
        </div>`).join('') + `<p class="msg">${j.total} usuário(s)</p>`
    } catch (e) { el.innerHTML = '<p class="msg erro">' + esc(e.message) + '</p>' }
  }
  const msg = (t, erro) => { const m = $('#u-msg'); m.textContent = t; m.className = 'msg' + (erro ? ' erro' : ' ok') }
  // o admin liga as abas no carregamento, antes deste botão existir: a troca para "Usuários" é feita aqui
  nav.addEventListener('click', (e) => {
    const b = e.target.closest('[data-aba="usuarios"]'); if (!b) return
    document.querySelectorAll('[data-aba]').forEach((x) => x.setAttribute('aria-selected', String(x === b)))
    document.querySelectorAll('[data-p]').forEach((p) => (p.hidden = p.dataset.p !== 'usuarios'))
    carregar()
  })
  main.addEventListener('input', (e) => { if (e.target.id === 'u-busca') { clearTimeout(tempo); tempo = setTimeout(() => { q = e.target.value.trim(); carregar() }, 300) } })
  main.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-acao]'); if (!b) return
    const linha = b.closest('[data-u]'), id = linha.dataset.u, email = $('b', linha).textContent
    try {
      if (b.dataset.acao === 'salvar-canal') {
        const cx = b.closest('[data-canal]'), corpo = { canal: cx.dataset.canal, plano: $('[data-campo=plano]', cx).value.trim() }
        const d = $('[data-campo=dias]', cx).value; if (d !== '') corpo.dias = Number(d)
        await api('/api/painel/usuarios/' + id, { method: 'PUT', body: JSON.stringify(corpo) }); msg('Salvo: ' + email + ' (' + corpo.canal + ')')
      } else if (b.dataset.acao === 'salvar') {
        const corpo = { plano: $('[data-campo=plano]', linha).value.trim() }
        const d = $('[data-campo=dias]', linha).value; if (d !== '') corpo.dias = Number(d)
        await api('/api/painel/usuarios/' + id, { method: 'PUT', body: JSON.stringify(corpo) }); msg('Salvo: ' + email)
      } else if (confirm('Apagar ' + email + ' e todos os dados dele neste produto? Não tem volta.')) {
        const j = await api('/api/painel/usuarios/' + id, { method: 'DELETE' }); msg('Apagado: ' + j.email)
      } else return
      carregar()
    } catch (err) { msg(err.message, true) }
  })
})()
