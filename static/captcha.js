// Captcha invisível (Cloudflare Turnstile) para telas de login próprias (spec 57 §5A). Fonte única: produtos-core.
// Uso: <script src="/s/captcha.js"></script>; RTCaptcha.preparar() ao abrir o formulário; no envio,
// corpo.captcha = await RTCaptcha.token(). Sem chave no servidor (/api/acesso/config vazio) devolve '' e o servidor não cobra.
;(() => {
  let SITE = null, wid = null, pend = null, carregando = null, caixa = null, voando = null, pronto = null
  const config = fetch('/api/acesso/config').then((r) => r.json()).then((j) => (SITE = j.turnstile || '')).catch(() => (SITE = ''))
  const carregar = () => carregando || (carregando = new Promise((ok, falha) => {
    const s = document.createElement('script')
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    s.async = true; s.onload = ok; s.onerror = falha
    document.head.append(s)
  }))
  const entregar = (t) => { const f = pend; pend = null; if (f) f(t) }
  async function gerar() {
    await config
    if (!SITE) return ''
    try {
      await carregar()
      if (!caixa) { caixa = document.createElement('div'); caixa.style.cssText = 'position:fixed;bottom:8px;right:8px;z-index:99999'; document.body.append(caixa) }
      return await new Promise((ok) => {
        pend = ok
        if (wid === null) {
          wid = window.turnstile.render(caixa, { sitekey: SITE, execution: 'execute', appearance: 'interaction-only',
            callback: entregar, 'error-callback': () => entregar(''), 'timeout-callback': () => entregar('') })
        } else window.turnstile.reset(wid)
        window.turnstile.execute(wid)
        setTimeout(() => { if (pend === ok) entregar('') }, 15000)
      })
    } catch { return '' }
  }
  const pedir = () => { if (!voando) voando = gerar().finally(() => { voando = null }); return voando }
  const preparar = () => { if (!pronto) pronto = { quando: Date.now(), token: pedir() } }
  async function token() {
    const p = pronto && Date.now() - pronto.quando < 240000 ? pronto.token : pedir()
    pronto = null
    const t = await p
    setTimeout(preparar, 500)
    return t
  }
  window.RTCaptcha = { preparar, token }
})()
