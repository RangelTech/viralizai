/* Viralizaí: app de uma página (spec 47b). Sem framework: hash na URL = tela. */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const tela = $("#tela");
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mmss = (s) => { s = Math.round(s || 0); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return h ? `${h}h${String(m).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`; };
let CONTA = null, PLANOS = null, sondagem = null;
const EXEMPLO = "https://www.youtube.com/watch?v=YV9u_1VzZDQ"; // live de GTA RP escolhida para o 1º corte guiado

// ---------------------------------------------------------------- API
async function api(caminho, opt = {}) {
  const o = { method: opt.method || (opt.json !== undefined || opt.body ? "POST" : "GET"), headers: {}, credentials: "same-origin" };
  if (opt.json !== undefined) { o.headers["content-type"] = "application/json"; o.body = JSON.stringify(opt.json); }
  if (opt.body) { o.body = opt.body; Object.assign(o.headers, opt.headers || {}); }
  const r = await fetch(caminho, o);
  let j = null;
  try { j = await r.json(); } catch { j = {}; }
  if (r.status === 401 && !caminho.startsWith("/api/entrar") && !caminho.startsWith("/api/cadastro")) { location.hash = "#/entrar"; throw new Error("entre na sua conta"); }
  if (r.status === 402) { const d = j.detail || {}; paywall(typeof d === "string" ? d : d.mensagem, d.plano, d.moedas); throw new Error("__paywall"); }
  if (!r.ok) { const d = j.detail; throw new Error(typeof d === "string" ? d : (d && d.mensagem) || "Não deu certo agora. Tenta de novo."); }
  return j;
}
function toast(msg, erro = false) {
  if (msg === "__paywall") return;
  const t = $("#toast"); t.textContent = msg; t.className = "toast ver" + (erro ? " erro" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.className = "toast"), 3200);
}
async function conta(recarregar = false) {
  if (!CONTA || recarregar) { CONTA = await api("/api/conta"); }
  $("#moedas span").textContent = CONTA.moedas;
  const n = $("#sino i"); n.textContent = CONTA.avisos; n.classList.toggle("oculto", !CONTA.avisos);
  return CONTA;
}

// ---------------------------------------------------------------- folha (paywall, criar, moedas)
function abrirFolha(html, montar) {
  $("#folha-conteudo").innerHTML = html; $("#veu").classList.add("aberto"); $("#folha").classList.add("aberta");
  if (montar) montar($("#folha-conteudo"));
}
function fecharFolha() { $("#veu").classList.remove("aberto"); $("#folha").classList.remove("aberta"); }
$("#veu").onclick = fecharFolha;

async function planos() { if (!PLANOS) PLANOS = await api("/api/planos"); return PLANOS; }
async function paywall(motivo, plano = "corte", moedas = false) {
  if (moedas) return folhaMoedas(motivo);
  const p = await planos();
  abrirFolha(`<h2 style="margin-top:0">${esc(motivo || "Escolha um plano pra continuar 🔥")}</h2>
    <div id="pl">${p.planos.map((x) => `<div class="plano ${x.codigo === plano ? "sel" : ""}" data-c="${x.codigo}">${x.destaque ? '<span class="tag">mais escolhido</span>' : ""}
      <b>${esc(x.nome)}</b><div class="preco">R$ ${(x.lancamento || x.preco).toFixed(2).replace(".", ",")}<small>/mês${x.lancamento ? ` · depois R$ ${x.preco.toFixed(2).replace(".", ",")}` : ""}</small></div>
      <ul>${x.itens.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>`).join("")}</div>
    <button class="btn pri bloco pulsa" id="assinar">Assinar com Pix</button>
    <p class="ajuda" style="text-align:center;margin-top:10px">Garantia de 7 dias. Cancela quando quiser.</p>`, (el) => {
    let sel = plano;
    $$(".plano", el).forEach((d) => (d.onclick = () => { sel = d.dataset.c; $$(".plano", el).forEach((x) => x.classList.toggle("sel", x === d)); }));
    $("#assinar", el).onclick = () => irCheckout(p.planos.find((x) => x.codigo === sel));
  });
}
async function folhaMoedas(motivo) {
  const p = await planos();
  abrirFolha(`<h2 style="margin-top:0">${esc(motivo || "Comprar moedas 🪙")}</h2><p class="sub">1 moeda = 1 vídeo com IA de 10 segundos.</p>
    ${p.moedas.map((x) => `<div class="plano" data-c="${x.codigo}">${x.destaque ? `<span class="tag">${esc(x.destaque)}</span>` : ""}
      <b>${x.moedas} vídeos</b><div class="preco">R$ ${x.preco.toFixed(2).replace(".", ",")} <small>· R$ ${(x.preco / x.moedas).toFixed(2).replace(".", ",")} cada</small></div></div>`).join("")}`,
    (el) => $$(".plano", el).forEach((d) => (d.onclick = () => irCheckout(p.moedas.find((x) => x.codigo === d.dataset.c)))));
}
function irCheckout(item) {
  if (!item || !item.checkout) return toast("O pagamento abre em instantes. Tenta de novo daqui a pouco.", true);
  const u = new URL(item.checkout);
  if (CONTA) { u.searchParams.set("email", CONTA.email); if (CONTA.nome) u.searchParams.set("name", CONTA.nome); }
  location.href = u.toString();
}
function folhaCriar() {
  abrirFolha(`<h2 style="margin-top:0">O que vamos criar?</h2><div class="opcoes">
    <button class="opcao" data-h="#/cortar"><span class="ic">✂️</span><span><b>Cortar live ou vídeo</b><small>Cole um link e receba os melhores momentos</small></span><span class="tag">no plano</span></button>
    <button class="opcao" data-h="#/animacao"><span class="ic">✨</span><span><b>Criar animação</b><small>Escreva uma ideia, a gente anima</small></span></button>
    <button class="opcao" data-h="#/ia"><span class="ic">🤖</span><span><b>Vídeo com IA</b><small>Bichos, objetos e cenas que viralizam</small></span><span class="tag">🪙 1</span></button>
    <button class="opcao" data-h="#/editar"><span class="ic">🎬</span><span><b>Editar meu vídeo</b><small>Suba um vídeo e deixe com sua cara</small></span><span class="tag">grátis</span></button></div>`,
    (el) => $$(".opcao", el).forEach((b) => (b.onclick = () => { fecharFolha(); location.hash = b.dataset.h; })));
}
$("#mais").onclick = folhaCriar;
$("#moedas").onclick = () => folhaMoedas();
$("#sino").onclick = async () => {
  const a = await api("/api/avisos"); CONTA.avisos = 0; conta();
  abrirFolha(`<h2 style="margin-top:0">Avisos</h2>${a.avisos.length ? a.avisos.map((x) => `<a class="opcao" href="${esc(x.link || "#/")}" style="margin-bottom:8px"><span>${esc(x.texto)}<br><small>${new Date(x.quando * 1000).toLocaleString("pt-BR")}</small></span></a>`).join("")
    : '<div class="vazio"><div class="ic">🔔</div>Nada por aqui ainda.</div>'}`, (el) => $$("a", el).forEach((x) => (x.onclick = fecharFolha)));
};
$("#ajuda").onclick = () => abrirFolha(`<h2 style="margin-top:0">Precisa de ajuda?</h2>
  <details class="card" style="margin-bottom:8px"><summary><b>Como eu ganho dinheiro no TikTok?</b></summary><p class="sub">O TikTok paga por vídeos com mais de 1 minuto (programa de recompensas). Por isso o padrão aqui é "Ganhar no TikTok": cortes de 61 a 90 segundos. Poste todo dia, responda os comentários na 1ª hora.</p></details>
  <details class="card" style="margin-bottom:8px"><summary><b>Posso postar corte de live dos outros?</b></summary><p class="sub">Use só vídeos públicos e sempre dê o crédito ao canal original (a legenda pronta já vem com o crédito).</p></details>
  <details class="card" style="margin-bottom:8px"><summary><b>Funciona no celular?</b></summary><p class="sub">Sim, foi feito pra celular. Você pode fechar o app: te avisamos quando ficar pronto.</p></details>
  <a class="btn bloco" href="https://wa.me/5562999671998?text=Oi%2C%20preciso%20de%20ajuda%20no%20Viraliza%C3%AD" target="_blank" rel="noopener">Falar com uma pessoa no WhatsApp</a>`);

// ---------------------------------------------------------------- roteador
const ROTAS = [
  [/^#\/entrar$/, telaEntrar], [/^#\/bemvindo(?:\/(\d))?$/, telaBemvindo], [/^#\/?$/, telaInicio], [/^#\/criar$/, () => { telaInicio(); folhaCriar(); }],
  [/^#\/cortar$/, telaCortar], [/^#\/pedido\/(\w+)$/, telaPedido], [/^#\/video\/(\w+)\/(\d+)$/, telaVideo], [/^#\/videos$/, telaVideos],
  [/^#\/vitrine$/, telaVitrine], [/^#\/animacao$/, telaAnimacao], [/^#\/ia$/, telaIA], [/^#\/editar$/, telaEditar], [/^#\/postagens$/, telaPostagens],
  [/^#\/perfil$/, telaPerfil], [/^#\/estilo$/, telaEstilo], [/^#\/planos$/, () => { telaInicio(); paywall("Escolha seu plano 🔥"); }],
];
async function rotear() {
  clearInterval(sondagem); sondagem = null; fecharFolha();
  const h = location.hash || "#/";
  const publica = h === "#/entrar", foco = publica || h.startsWith("#/bemvindo");
  $("#topo").classList.toggle("oculto", publica); $("#barra").classList.toggle("oculto", foco); $(".lateral").classList.toggle("oculto", foco);
  $("#ajuda").classList.toggle("oculto", foco);
  $("#app").classList.toggle("sem-menu", foco);
  if (!publica) {
    try { await conta(); } catch { return; }
    if (!CONTA.onboarding && !h.startsWith("#/bemvindo") && !h.startsWith("#/pedido")) { location.hash = "#/bemvindo/1"; return; }
  }
  const r = h.split("?")[0];
  $$("[data-r]").forEach((a) => a.classList.toggle("ativo", (a.dataset.r === "inicio" && r === "#/") || r.startsWith("#/" + a.dataset.r)));
  for (const [rx, f] of ROTAS) { const m = r.match(rx); if (m) { tela.innerHTML = ""; window.scrollTo(0, 0); try { await f(...m.slice(1)); } catch (e) { toast(e.message, true); }
    $("#ajuda").classList.toggle("oculto", foco || !!$(".acao-fixa")); return; } }
  location.hash = "#/";
}
window.addEventListener("hashchange", rotear);

// ---------------------------------------------------------------- entrar / criar conta
function telaEntrar() {
  const q = new URLSearchParams(location.search);
  let aba = (q.get("entrar") || (() => { try { return sessionStorage.getItem("aba"); } catch { return ""; } })() === "entrar") ? "entrar" : "criar"; try { sessionStorage.removeItem("aba"); } catch {}
  const desenhar = () => {
    tela.innerHTML = `<div class="entrar"><div class="logo"><span class="gota"></span><span>Viraliz<b>aí</b></span></div>
      <div class="abas"><button data-a="criar" class="${aba === "criar" ? "sel" : ""}">Criar conta</button><button data-a="entrar" class="${aba === "entrar" ? "sel" : ""}">Entrar</button></div>
      ${CONTA_GOOGLE ? '<a class="btn bloco" href="/api/google"><b style="color:#4285f4">G</b> Continuar com Google</a><div class="ou">ou</div>' : ""}
      <form id="f" novalidate>${aba === "criar" ? `
        <label class="campo">Seu nome<input class="input" name="nome" autocomplete="given-name" required></label>
        <label class="campo">E-mail<input class="input" name="email" type="email" autocomplete="email" required></label>
        <label class="campo">Senha<div class="olho"><input class="input" name="senha" type="password" minlength="8" autocomplete="new-password" required><button type="button" aria-label="Mostrar senha">👁</button></div><span class="ajuda">Pelo menos 8 letras ou números.</span></label>
        <label class="campo">WhatsApp <span class="ajuda">(opcional: pra te avisar quando o vídeo ficar pronto)</span><input class="input" name="whatsapp" inputmode="tel" placeholder="(62) 99999-9999"></label>
        <label class="check"><input type="checkbox" name="aceite" required> Aceito os <a href="/termos" target="_blank">termos e a privacidade</a></label>
        <div class="erro-txt" id="err"></div><button class="btn pri bloco">CRIAR MINHA CONTA</button>
        <p class="ajuda" style="text-align:center">Já tem conta? <a href="#" data-a="entrar">Entrar</a></p>` : `
        <label class="campo">E-mail<input class="input" name="email" type="email" autocomplete="email" required></label>
        <label class="campo">Senha<div class="olho"><input class="input" name="senha" type="password" autocomplete="current-password" required><button type="button" aria-label="Mostrar senha">👁</button></div></label>
        <div class="erro-txt" id="err"></div><button class="btn pri bloco">ENTRAR</button>
        <p class="ajuda" style="text-align:center"><a href="#" id="esqueci">Esqueci a senha</a></p>`}</form></div>`;
    $$("[data-a]").forEach((b) => (b.onclick = (e) => { e.preventDefault(); aba = b.dataset.a; desenhar(); }));
    $$(".olho button").forEach((b) => (b.onclick = () => { const i = b.previousElementSibling; i.type = i.type === "password" ? "text" : "password"; }));
    const esq = $("#esqueci"); if (esq) esq.onclick = (e) => { e.preventDefault(); esqueci(); };
    $("#f").onsubmit = async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target)); d.aceite = !!d.aceite;
      const falta = aba === "criar" ? (!d.nome ? "Como você se chama?" : !/^\S+@\S+\.\S+$/.test(d.email || "") ? "Esse e-mail não parece certo." : (d.senha || "").length < 8 ? "A senha precisa de pelo menos 8 letras ou números." : !d.aceite ? "Pra criar a conta, aceite os termos." : "")
        : (!d.email || !d.senha ? "Preencha e-mail e senha." : "");
      if (falta) { $("#err").textContent = falta; return; }
      const btn = $("#f .btn.pri"); btn.disabled = true; $("#err").textContent = "";
      try {
        await api(aba === "criar" ? "/api/cadastro" : "/api/entrar/senha", { json: d });
        CONTA = null; location.hash = "#/";
      } catch (er) {
        $("#err").innerHTML = esc(er.message) + (/já tem conta/.test(er.message) ? ' <a href="#" id="ir-entrar">Entrar</a>' : "");
        const ir = $("#ir-entrar"); if (ir) ir.onclick = (ev) => { ev.preventDefault(); aba = "entrar"; desenhar(); };
      } finally { btn.disabled = false; }
    };
  };
  desenhar();
}
let CONTA_GOOGLE = false;
function esqueci() {
  abrirFolha(`<h2 style="margin-top:0">Esqueci a senha</h2><form id="fe"><label class="campo">Seu e-mail<input class="input" name="email" type="email" required></label>
    <div id="passo2" class="oculto"><label class="campo">Código que chegou no e-mail<input class="input" name="codigo" inputmode="numeric" maxlength="6"></label>
    <label class="campo">Nova senha<input class="input" name="senha" type="password" minlength="8"></label></div>
    <div class="erro-txt" id="erre"></div><button class="btn pri bloco">Mandar código</button></form>`, (el) => {
    let passo = 1;
    $("#fe", el).onsubmit = async (e) => {
      e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
      try {
        if (passo === 1) { await api("/api/senha/esqueci", { json: { email: d.email } }); passo = 2; $("#passo2", el).classList.remove("oculto"); $("#fe .btn", el).textContent = "Trocar senha e entrar"; toast("Se o e-mail tiver conta, o código chegou 📩"); }
        else { await api("/api/senha/redefinir", { json: d }); fecharFolha(); CONTA = null; location.hash = "#/"; }
      } catch (er) { $("#erre", el).textContent = er.message; }
    };
  });
}

// ---------------------------------------------------------------- onboarding "Meu estilo"
const MOLDURAS = { neon: "#2bff88", fogo: "#ff6a00", rosa: "#ff3d6e", ouro: "#ffc53d", gelo: "#3dd6ff", roxo: "#9b5cff" };
async function telaBemvindo(passo = "1") {
  passo = +passo; const e = CONTA.estilo;
  const pulos = `<div class="passos">${[1, 2, 3, 4].map((i) => `<i class="${i <= passo ? "on" : ""}"></i>`).join("")}</div>`;
  const pular = `<button class="btn fantasma bloco" id="pular">Pular por agora</button>`;
  if (passo === 1) {
    tela.innerHTML = `${pulos}<h1>Onde você vai postar?</h1><p class="sub">Escolha uma ou mais.</p>
      <div class="opcoes" id="redes">${[["tiktok", "🎵", "TikTok"], ["instagram", "📸", "Instagram Reels"], ["youtube", "▶️", "YouTube Shorts"]].map(([c, i, n]) =>
        `<button class="opcao ${e.redes.includes(c) ? "sel" : ""}" data-c="${c}"><span class="ic">${i}</span><b>${n}</b></button>`).join("")}</div>
      <label class="campo" style="margin-top:16px">Seu @ (vai aparecer no vídeo)<input class="input" id="arroba" placeholder="@seuperfil" value="${esc(e.arroba ? "@" + e.arroba : "")}"></label>
      <div class="acao-fixa"><button class="btn pri bloco" id="seg">Continuar</button>${pular}</div>`;
    $$("#redes .opcao").forEach((b) => (b.onclick = () => b.classList.toggle("sel")));
    $("#seg").onclick = async () => {
      const redes = $$("#redes .sel").map((b) => b.dataset.c);
      if (!redes.length) return toast("Escolhe pelo menos uma rede", true);
      CONTA = await api("/api/estilo", { json: { redes, arroba: $("#arroba").value } }); location.hash = "#/bemvindo/2";
    };
  } else if (passo === 2) {
    tela.innerHTML = `${pulos}<h1>Escolha seu estilo</h1><p class="sub">É a cor do gancho e da legenda em todos os seus vídeos.</p>
      <div class="moldura" id="mold">${Object.entries(MOLDURAS).map(([k, c]) => `<button data-m="${k}" class="${e.moldura === k ? "sel" : ""}" style="background:linear-gradient(160deg,#111,#000)">
        <span style="background:${c};color:#000">O MELHOR CORTE 🔥</span><em>@${esc(e.arroba || "seuperfil")}</em></button>`).join("")}</div>
      <div class="acao-fixa"><button class="btn pri bloco" id="seg">Continuar</button>${pular}</div>`;
    let m = e.moldura;
    $$("#mold button").forEach((b) => (b.onclick = () => { m = b.dataset.m; $$("#mold button").forEach((x) => x.classList.toggle("sel", x === b)); }));
    $("#seg").onclick = async () => { CONTA = await api("/api/estilo", { json: { moldura: m } }); location.hash = "#/bemvindo/3"; };
  } else if (passo === 3) {
    tela.innerHTML = `${pulos}<h1>Quer que a gente te avise?</h1><p class="sub">Quando o vídeo ficar pronto, mandamos no seu WhatsApp. Pode fechar o app.</p>
      <label class="campo">WhatsApp<input class="input" id="zap" inputmode="tel" value="${esc(CONTA.whatsapp || "")}" placeholder="(62) 99999-9999"></label>
      <div class="acao-fixa"><button class="btn pri bloco" id="seg">Continuar</button>${pular}</div>`;
    $("#seg").onclick = async () => { if ($("#zap").value) CONTA = await api("/api/conta", { json: { whatsapp: $("#zap").value } }); location.hash = "#/bemvindo/4"; };
  } else {
    tela.innerHTML = `${pulos}<h1>Bora fazer seu 1º vídeo? 🔥</h1><p class="sub">Já colamos uma live de GTA pra você. Em uns 2 minutos sai o corte com o seu @.</p>
      <div class="card"><div class="link-info" style="margin:0;border:none;padding:0"><div style="font-size:42px">🎮</div><div><b>Live de GTA RP</b><small>✓ escolhida a dedo pra viralizar</small></div></div></div>
      <div class="acao-fixa"><button class="btn pri bloco pulsa" id="seg">✂️ Fazer meu 1º corte</button><button class="btn fantasma bloco" id="depois">Quero colar outro link</button></div>`;
    const fim = async () => { CONTA = await api("/api/conta", { json: { onboarding: true } }); };
    $("#seg").onclick = async () => { await fim(); try { const p = await api("/api/cortes", { json: { url: EXEMPLO, objetivo: "tiktok", quantos: 1 } }); location.hash = "#/pedido/" + p.id; } catch (er) { toast(er.message, true); } };
    $("#depois").onclick = async () => { await fim(); location.hash = "#/cortar"; };
  }
  const p = $("#pular"); if (p) p.onclick = async () => { CONTA = await api("/api/conta", { json: { onboarding: true } }); location.hash = "#/"; };
}

// ---------------------------------------------------------------- início
async function telaInicio() {
  const c = await conta(true);
  const meta = c.plano === "teste" ? null : Math.min(c.uso.cortes, 10);
  tela.innerHTML = `<h1>Fala, ${esc((c.nome || "criador").split(" ")[0])}! 👊</h1>
    ${c.plano === "teste" ? `<div class="dica"><span style="font-size:24px">🎁</span><div><b>${c.teste_usado ? "Sua prévia grátis já foi." : "Você tem 1 corte grátis pra testar."}</b><br>
      ${c.teste_usado ? "Gostou? Assina e corta à vontade." : "Cola uma live e vê a mágica."}<br><button class="btn peq pri" style="margin-top:8px" id="ver-planos">${c.teste_usado ? "Ver planos" : "Usar meu corte grátis"}</button></div></div>`
      : `<div class="card meta"><div class="linha"><span>Meta da semana: 10 vídeos de 1 min</span><span>${meta}/10</span></div><div class="barrinha"><i style="width:${meta * 10}%"></i></div>
      <span class="ajuda">${c.plano_nome} · ${c.restam_cortes} cortes sobrando no mês</span></div>`}
    <h2>O que vamos criar hoje?</h2>
    <div class="ferramentas">
      <button class="ferr" data-h="#/cortar"><span class="ic">✂️</span><b>Cortar live</b><span>Melhores momentos com nota de viral</span></button>
      <button class="ferr" data-h="#/animacao"><span class="ic">✨</span><b>Animação</b><span>Escreve a ideia, a gente anima</span></button>
      <button class="ferr" data-h="#/ia"><span class="selo">🪙 1</span><span class="ic">🤖</span><b>Vídeo com IA</b><span>Bichos e cenas que viralizam</span></button>
      <button class="ferr" data-h="#/editar"><span class="ic">🎬</span><b>Editar meu vídeo</b><span>Seu @, legenda e 1 min</span></button>
    </div>
    <div id="andamento"></div>
    <div class="secao-topo"><h2>🔥 Prontos pra postar agora</h2><a href="#/vitrine">Ver todos</a></div><div class="rolar" id="vit"><div class="esqueleto" style="width:150px;height:300px"></div></div>
    <div class="secao-topo"><h2>Seus últimos vídeos</h2><a href="#/videos">Ver todos</a></div><div class="grade" id="ult"></div>
    <div class="dica" style="margin-top:22px"><span style="font-size:22px">💡</span><div><b>Dica do dia</b><br>Poste o corte de nota mais alta entre 18h e 21h e responda os comentários na 1ª hora: o TikTok entrega mais.</div></div>`;
  $$(".ferr").forEach((b) => (b.onclick = () => (location.hash = b.dataset.h)));
  const vp = $("#ver-planos"); if (vp) vp.onclick = () => (c.teste_usado ? paywall() : (location.hash = "#/cortar"));
  const [ped, vit] = await Promise.all([api("/api/pedidos"), api("/api/vitrine").catch(() => ({ secoes: [] }))]);
  if (!$("#andamento")) return; // a pessoa já mudou de tela
  const and = ped.pedidos.filter((p) => !["pronto", "erro"].includes(p.estado));
  $("#andamento").innerHTML = and.length ? `<h2>Em andamento</h2>${and.map((p) => `<a class="card" href="#/pedido/${p.id}" style="display:block;margin-bottom:10px;color:var(--txt)">
    <b>${esc(nomePedido(p))}</b><div class="ajuda" style="margin:4px 0 8px">${esc(p.etapa || "Começando")} · ${esc(p.estimativa)}</div><div class="barrinha"><i style="width:${Math.round(p.progresso * 100)}%"></i></div></a>`).join("")}` : "";
  const itens = (vit.secoes && vit.secoes[0] && vit.secoes[0].itens) || [];
  $("#vit").innerHTML = itens.length ? itens.map(cartaoVitrine).join("") : '<div class="ajuda">Os cortes prontos aparecem aqui assim que alguém cortar uma live 🔥</div>';
  ligarVitrine($("#vit"));
  const vids = videosDe(ped.pedidos).slice(0, 4);
  $("#ult").innerHTML = vids.length ? vids.map(cartaoVideo).join("") : `<div class="vazio" style="grid-column:1/-1"><div class="ic">🎬</div>Bora fazer seu 1º vídeo<br><a class="btn pri" style="margin-top:12px" href="#/cortar">✂️ Cortar uma live</a></div>`;
  if (and.length) sondagem = setInterval(() => { if (location.hash === "#/" || location.hash === "") rotear(); }, 8000);
}
const nomePedido = (p) => ({ cortes: "Cortes", vitrine: "Corte pronto", animacao: "Animação", video_ia: "Vídeo com IA", editar: "Vídeo editado" }[p.tipo] || "Vídeo") +
  ((p.resultado && p.resultado.video && p.resultado.video.titulo) ? ": " + p.resultado.video.titulo : "");
function videosDe(pedidos) {
  const out = [];
  for (const p of pedidos) for (const c of (p.resultado && p.resultado.cortes) || []) if (c.estado === "pronto" && c.url) out.push({ ...c, pid: p.id, tipo: p.tipo, criado: p.criado });
  return out;
}
const TIPO = { cortes: "✂️ Corte", vitrine: "✂️ Corte", animacao: "✨ Animação", video_ia: "🤖 IA", editar: "🎬 Editado" };
const cartaoVideo = (v) => `<a class="vcard" href="#/video/${v.pid}/${v.k}"><div class="tela">${v.capa_url ? `<img src="${v.capa_url}" alt="" loading="lazy">` : ""}
  ${v.nota ? `<span class="nota ${v.nota >= 85 ? "alta" : ""}">🔥 ${v.nota}</span>` : ""}<span class="tipo">${TIPO[v.tipo] || ""}</span><span class="dur">${mmss(v.duracao)}</span></div>
  <div class="info"><b>${esc(v.gancho || v.titulo || "Vídeo")}</b></div></a>`;
const cartaoVitrine = (b) => `<div class="vcard" data-id="${b.id}"><div class="tela">${b.capa_url ? `<img src="${b.capa_url}" alt="" loading="lazy">` : ""}
  ${b.previa_url ? `<video muted playsinline loop preload="none" data-src="${b.previa_url}"></video>` : ""}
  <span class="nota ${b.nota >= 85 ? "alta" : ""}">🔥 ${b.nota}</span><span class="dur">${mmss(b.duracao)}</span></div>
  <div class="info"><b>${esc(b.gancho || b.titulo)}</b><small>de: ${esc(b.canal || "canal original")}${b.usos ? ` · usado ${b.usos}×` : ""}</small></div></div>`;
function ligarVitrine(el) {
  const io = new IntersectionObserver((es) => es.forEach((e) => { const v = e.target; if (e.isIntersecting) { if (!v.src) v.src = v.dataset.src; v.play().catch(() => {}); } else v.pause(); }), { threshold: 0.6 });
  $$("video[data-src]", el).forEach((v) => io.observe(v));
  $$(".vcard[data-id]", el).forEach((c) => (c.onclick = () => usarVitrine(c.dataset.id, c)));
}
async function usarVitrine(id, card) {
  const b = card.querySelector("b").textContent;
  abrirFolha(`<h2 style="margin-top:0">${esc(b)}</h2><div class="player" style="max-width:260px;margin-bottom:14px"><video src="/api/vitrine/${id}/previa.mp4" autoplay muted loop playsinline controls></video></div>
    <p class="ajuda">A gente coloca seu @, sua cor e uma variação pra não ficar igual ao de ninguém.</p>
    <button class="btn pri bloco" id="usar">Usar esse corte</button>`, (el) => {
    $("#usar", el).onclick = async () => { try { const p = await api(`/api/vitrine/${id}/usar`, { method: "POST" }); fecharFolha(); location.hash = "#/pedido/" + p.id; } catch (e) { toast(e.message, true); } };
  });
}

// ---------------------------------------------------------------- cortar
async function telaCortar() {
  let objetivo = "tiktok", quantos = CONTA.plano === "teste" ? 1 : 3, link = null, arquivo = null;
  const lim = CONTA.plano === "teste" ? 1 : CONTA.restam_cortes;
  tela.innerHTML = `<h1>Cortar live ou vídeo</h1><p class="sub">Cola o link e a IA acha os melhores momentos.</p>
    <label class="campo">Cole o link<div class="grupo"><input class="input" id="url" inputmode="url" placeholder="youtube.com/… · twitch.tv/… · kick.com/…"><button class="btn" id="colar">Colar</button></div></label>
    <div id="info"></div>
    <p class="ajuda" style="margin:6px 0 18px">ou <a href="#" id="subir">subir um vídeo do celular</a><input type="file" id="arq" accept="video/*" class="oculto"></p>
    <h2>Pra que é esse corte?</h2><div class="opcoes" id="obj">
      <button class="opcao sel" data-o="tiktok"><span class="ic">💰</span><span><b>Ganhar no TikTok</b><small>61 a 90 segundos (o TikTok paga vídeo de 1 min+)</small></span><span class="tag">recomendado</span></button>
      <button class="opcao" data-o="viral"><span class="ic">⚡</span><span><b>Viralizar rápido</b><small>20 a 40 segundos</small></span></button>
      <button class="opcao" data-o="reels"><span class="ic">📱</span><span><b>Reels / Shorts</b><small>até 60 segundos</small></span></button></div>
    <h2>Quantos cortes?</h2><div class="pilulas" id="qtd">${[1, 3, 5, 10].map((n) => `<button class="pilula ${n === quantos ? "sel" : ""}" data-n="${n}" ${n > Math.max(1, lim) ? "data-cad=1" : ""}>${n}${n > Math.max(1, lim) ? '<span class="cad">🔒</span>' : ""}</button>`).join("")}</div>
    <h2>Seu estilo</h2><div class="card" style="display:flex;align-items:center;gap:12px"><span style="width:34px;height:34px;border-radius:10px;background:${esc(CONTA.estilo.cor)}"></span>
      <div style="flex:1"><b>@${esc(CONTA.estilo.arroba || "sem @")}</b><div class="ajuda">${CONTA.estilo.redes.join(" · ")}</div></div><a class="btn peq" href="#/estilo">Trocar</a></div>
    <div class="acao-fixa"><button class="btn pri bloco pulsa" id="ir">✂️ Cortar agora</button></div>`;
  const url = $("#url");
  const ver = async () => {
    const v = url.value.trim(); link = null; if (!/^https?:\/\//.test(v)) { $("#info").innerHTML = ""; return; }
    $("#info").innerHTML = '<div class="esqueleto" style="height:74px;margin-top:10px"></div>';
    try {
      const i = await api("/api/link", { json: { url: v } }); link = v;
      $("#info").innerHTML = `<div class="link-info">${i.capa ? `<img src="${esc(i.capa)}" alt="">` : ""}<div><b>${esc(i.titulo)}</b><small>${esc(i.canal || "")} · ${mmss(i.duracao)} ✓</small></div></div>
        ${i.ao_vivo ? '<div class="dica" style="margin-top:10px">🔴 <div>Essa live está ao vivo agora. Manda o link quando ela terminar (o Vigia ao Vivo, que corta enquanto acontece, chega em breve).</div></div>' : ""}`;
    } catch (e) { $("#info").innerHTML = `<div class="erro-txt" style="margin-top:8px">${esc(e.message)} <a href="#" onclick="document.getElementById('arq').click();return false">Subir o vídeo</a></div>`; }
  };
  url.addEventListener("change", ver); url.addEventListener("paste", () => setTimeout(ver, 50));
  $("#colar").onclick = async () => { try { url.value = await navigator.clipboard.readText(); ver(); } catch { url.focus(); toast("Segura no campo e toca em Colar"); } };
  $("#subir").onclick = (e) => { e.preventDefault(); $("#arq").click(); };
  $("#arq").onchange = () => { arquivo = $("#arq").files[0]; if (arquivo) $("#info").innerHTML = `<div class="link-info"><div style="font-size:32px">📁</div><div><b>${esc(arquivo.name)}</b><small>${(arquivo.size / 1e6).toFixed(0)} MB ✓</small></div></div>`; };
  $$("#obj .opcao").forEach((b) => (b.onclick = () => { objetivo = b.dataset.o; $$("#obj .opcao").forEach((x) => x.classList.toggle("sel", x === b)); }));
  $$("#qtd .pilula").forEach((b) => (b.onclick = () => { if (b.dataset.cad) return paywall(CONTA.plano === "teste" ? "No teste grátis é 1 corte. Assina pra cortar até 10 de uma vez 🔥" : "Esse tanto de cortes passa do seu limite do mês."); quantos = +b.dataset.n; $$("#qtd .pilula").forEach((x) => x.classList.toggle("sel", x === b)); }));
  $("#ir").onclick = async () => {
    const btn = $("#ir"); btn.disabled = true;
    try {
      let p;
      if (arquivo) {
        btn.textContent = "Enviando o vídeo…";
        p = await api(`/api/cortes/upload?objetivo=${objetivo}&quantos=${quantos}`, { body: arquivo, headers: { "x-arquivo": arquivo.name } });
      } else {
        if (!url.value.trim()) throw new Error("Cola o link da live ou do vídeo.");
        p = await api("/api/cortes", { json: { url: url.value.trim(), objetivo, quantos } });
      }
      location.hash = "#/pedido/" + p.id;
    } catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = "✂️ Cortar agora"; }
  };
}

// ---------------------------------------------------------------- pedido (andamento + resultado)
let festejado = {};
async function telaPedido(id) {
  const p = await api("/api/pedidos/" + id);
  const res = p.resultado || {}, cortes = res.cortes || [];
  const etapas = p.tipo === "cortes" ? ["Li o vídeo", "Achei os melhores momentos", "Montando seus cortes"] : p.tipo === "animacao" ? ["Escrevi o roteiro", "Gravando a narração", "Animando as cenas"]
    : p.tipo === "video_ia" ? ["Entendi o pedido", "Criando seu vídeo", "Colocando seu @"] : ["Recebi o vídeo", "Editando", "Finalizando"];
  const fase = p.estado === "pronto" ? 3 : p.estado === "montando" ? 2 : p.progresso >= 0.35 ? 1 : 0;
  const prontos = cortes.filter((c) => c.estado === "pronto");
  const titulo = res.video && res.video.titulo ? res.video.titulo : res.titulo || "";
  tela.innerHTML = `<a href="#/videos" class="ajuda">← Meus vídeos</a>
    <h1>${p.estado === "pronto" ? (p.tipo === "cortes" || p.tipo === "vitrine" ? "Seus cortes 🔥" : "Pronto 🔥") : p.estado === "erro" ? "Não deu certo" : "Fazendo seu vídeo…"}</h1>
    ${titulo ? `<p class="sub">${esc(titulo)}${res.video && res.video.canal ? " · " + esc(res.video.canal) : ""}</p>` : ""}
    ${p.estado === "erro" ? `<div class="card"><p>${esc(p.erro)}</p><a class="btn pri" href="#/cortar">Tentar de novo</a></div>` : ""}
    ${p.estado !== "pronto" && p.estado !== "erro" ? `<div class="etapas">${etapas.map((e, i) => `<div class="etapa ${i < fase ? "feita" : i === fase ? "agora" : ""}"><span class="b">${i < fase ? "✓" : ""}</span>${e}${i === fase && p.etapa && i === 2 && /de/.test(p.etapa) ? ` · ${esc(p.etapa)}` : ""}</div>`).join("")}</div>
      <p class="ajuda">⏱ ${esc(p.estimativa || "uns 2 minutinhos")}</p>
      <div class="zap"><span>📲 Pode fechar, te aviso no WhatsApp${CONTA.whatsapp ? "" : " (coloca seu número no Perfil)"}</span><button class="tg ${CONTA.estilo.avisar_whatsapp && CONTA.whatsapp ? "on" : ""}" id="tgzap" aria-label="Avisar no WhatsApp"></button></div>` : ""}
    ${res.previa && prontos.length ? `<div class="dica" style="margin-bottom:14px">🎁 <div><b>Essa é sua prévia grátis.</b> Gostou? Pra baixar, postar e cortar mais, escolhe um plano.<br><button class="btn peq pri" style="margin-top:8px" onclick="paywall('Seu 1º vídeo viral está pronto 🔥 Pra baixar e postar, escolha um plano')">Ver planos</button></div></div>` : ""}
    <div id="cortes">${cortes.map((c, i) => cartaoCorte(p, c, i === 0 && cortes.length > 1)).join("")}</div>
    ${p.estado === "pronto" && p.tipo === "cortes" && !res.previa ? `<button class="btn bloco" id="mais-cortes">Quero mais cortes dessa live</button>` : ""}
    ${p.estado === "pronto" && p.tipo === "video_ia" && cortes[0] && cortes[0].pode_refazer ? `<button class="btn bloco" id="refazer">Não ficou bom? Refazer grátis</button>` : ""}`;
  const tg = $("#tgzap"); if (tg) tg.onclick = async () => { if (!CONTA.whatsapp) return (location.hash = "#/perfil"); tg.classList.toggle("on"); CONTA = await api("/api/estilo", { json: { avisar_whatsapp: tg.classList.contains("on") } }); };
  const mc = $("#mais-cortes"); if (mc) mc.onclick = async () => { try { const n = await api(`/api/pedidos/${id}/mais`, { json: { quantos: 3 } }); location.hash = "#/pedido/" + n.id; } catch (e) { toast(e.message, true); } };
  const rf = $("#refazer"); if (rf) rf.onclick = () => toast("Abre o Vídeo com IA e gera de novo: esse refazer é grátis.");
  ligarCortes(p);
  if (prontos.length && !festejado[id] && (p.estado === "pronto" || prontos.length === 1)) { festejado[id] = 1; festa(); }
  if (!["pronto", "erro"].includes(p.estado)) sondagem = setInterval(async () => {
    const n = await api("/api/pedidos/" + id).catch(() => null);
    if (n && (n.estado !== p.estado || n.etapa !== p.etapa || JSON.stringify((n.resultado || {}).cortes || []).length !== JSON.stringify(cortes).length)) rotear();
  }, 3500);
}
function cartaoCorte(p, c, melhor) {
  if (c.estado !== "pronto") return `<div class="corte quase"><div class="tela esqueleto"></div><div><div class="topo-c">${c.estado === "erro" ? "😕" : "⏳"} ${c.estado === "erro" ? "Pulei esse" : "quase lá…"}</div>
    <div class="gancho">${esc(c.gancho || "")}</div><div class="porque">${c.estado === "erro" ? esc(c.erro || "") : "Montando com o seu estilo"}</div></div></div>`;
  return `<div class="corte"><a class="tela" href="#/video/${p.id}/${c.k}">${melhor ? '<span class="melhor">Melhor</span>' : ""}<video src="${c.url}#t=1" poster="${c.capa_url || ""}" muted playsinline preload="none"></video></a>
    <div><div class="topo-c">${c.nota ? `<span class="fogo">🔥 ${c.nota}</span>` : ""}<span class="ajuda">· ${mmss(c.duracao)}</span></div>
    <div class="gancho">"${esc(c.gancho || c.titulo || "")}"</div>${c.porque ? `<div class="porque">Por quê: ${esc(c.porque)}</div>` : ""}
    <div class="acoes"><a class="btn peq" href="#/video/${p.id}/${c.k}">Editar</a><button class="btn peq" data-postar="${p.id}/${c.k}">Postar</button><button class="btn peq pri" data-baixar="${c.url}">⤓ Baixar</button></div></div></div>`;
}
function ligarCortes(p) {
  $$("[data-baixar]").forEach((b) => (b.onclick = () => baixar(b.dataset.baixar)));
  $$("[data-postar]").forEach((b) => (b.onclick = () => postar(b.dataset.postar)));
  $$(".corte video").forEach((v) => { v.onmouseenter = () => v.play().catch(() => {}); v.onmouseleave = () => v.pause(); });
}
async function baixar(url) {
  const r = await fetch(url + "?baixar=1", { method: "HEAD" }).catch(() => null);
  if (r && r.status === 402) return paywall("Gostou? Pra baixar e postar, escolha um plano 🔥", "corte");
  const a = document.createElement("a"); a.href = url + "?baixar=1"; a.download = ""; document.body.appendChild(a); a.click(); a.remove();
}
function postar(ref) {
  if (!CONTA.limites.postar) return abrirFolha(`<h2 style="margin-top:0">Postar sozinho é do plano Viral</h2><p class="sub">No Viral a gente posta e agenda no TikTok e no Instagram por você.</p>
    <button class="btn pri bloco" onclick="paywall('Postar sozinho é do plano Viral 🔥','viral')">Ver plano Viral</button>
    <button class="btn bloco" style="margin-top:8px" id="eu-mesmo">Baixar e postar eu mesmo</button>`, (el) => ($("#eu-mesmo", el).onclick = () => { fecharFolha(); location.hash = "#/video/" + ref; }));
  location.hash = "#/postagens";
}
function festa() {
  const f = document.createElement("div"); f.className = "festa";
  for (let i = 0; i < 60; i++) { const c = document.createElement("i"); c.style.left = Math.random() * 100 + "%"; c.style.background = ["#2bff88", "#ffc53d", "#ff6a00", "#fff"][i % 4]; c.style.animationDelay = Math.random() * 0.6 + "s"; f.appendChild(c); }
  document.body.appendChild(f); setTimeout(() => f.remove(), 2600);
}

// ---------------------------------------------------------------- detalhe do vídeo + editor simples
async function telaVideo(pid, k) {
  const p = await api("/api/pedidos/" + pid);
  const c = ((p.resultado || {}).cortes || []).find((x) => x.k === +k);
  if (!c || !c.url) { tela.innerHTML = '<div class="vazio"><div class="ic">🎬</div>Esse vídeo não está mais aqui.</div>'; return; }
  const leg = [c.legenda || "", (c.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
  const editavel = p.tipo === "cortes" || p.tipo === "vitrine";
  tela.innerHTML = `<a href="#/pedido/${pid}" class="ajuda">← Voltar</a><div class="duas" style="margin-top:12px">
    <div><div class="player"><video src="${c.url}" controls playsinline autoplay muted loop poster="${c.capa_url || ""}"></video></div>
      <div class="acoes3" style="max-width:420px;margin:12px auto 0"><button class="btn" id="ed-abrir">Editar</button><button class="btn" id="postar">Postar</button><button class="btn pri" id="baixar">⤓ Baixar</button></div></div>
    <div><h1 style="font-size:28px">${esc(c.gancho || c.titulo || "Seu vídeo")}</h1>
      <p class="sub">${c.nota ? `🔥 ${c.nota} · ` : ""}${mmss(c.duracao)}${c.porque ? " · " + esc(c.porque) : ""}</p>
      <label class="campo">Legenda do post<div class="copiar"><textarea class="input" id="leg" rows="5">${esc(leg)}</textarea><button class="btn peq" id="copiar">Copiar</button></div></label>
      ${p.resultado.video && p.resultado.video.url ? `<p class="ajuda">Original: <a href="${esc(p.resultado.video.url)}" target="_blank" rel="noopener">${esc(p.resultado.video.canal || "ver vídeo")}</a> (dê o crédito na legenda)</p>` : ""}
      <div id="editor" class="card oculto" style="margin-top:16px"><h2 style="margin-top:0">Editar</h2>
        ${editavel ? `<label class="campo">Título no topo (gancho)<input class="input" id="g" maxlength="60" value="${esc(c.gancho || "")}"></label>
        <div class="grupo"><label class="campo" style="flex:1">Tirar do começo (s)<input class="input" id="ai" type="number" min="0" max="30" value="0"></label>
        <label class="campo" style="flex:1">Tirar do fim (s)<input class="input" id="af" type="number" min="0" max="30" value="0"></label></div>
        <label class="check"><input type="checkbox" id="lg" checked> Legenda ligada</label>
        <button class="btn pri bloco" id="salvar">Salvar</button>` : `<p class="sub">Pra colocar legenda, título, @ ou esticar pra 1 minuto, abre no editor.</p><a class="btn pri bloco" href="#/editar?de=${pid}&k=${k}">Abrir no Editar meu vídeo</a>`}
      </div></div></div>`;
  $("#baixar").onclick = () => baixar(c.url);
  $("#postar").onclick = () => postar(`${pid}/${k}`);
  $("#copiar").onclick = async () => { try { await navigator.clipboard.writeText($("#leg").value); toast("Legenda copiada ✓"); } catch { $("#leg").select(); } };
  $("#ed-abrir").onclick = () => { $("#editor").classList.toggle("oculto"); $("#editor").scrollIntoView({ behavior: "smooth" }); };
  const s = $("#salvar");
  if (s) s.onclick = async () => {
    s.disabled = true; s.textContent = "Preparando seu vídeo…";
    try { await api(`/api/pedidos/${pid}/cortes/${k}/editar`, { json: { gancho: $("#g").value, aparar_inicio: +$("#ai").value || 0, aparar_fim: +$("#af").value || 0, legenda: $("#lg").checked } }); toast("Salvo ✓"); rotear(); }
    catch (e) { toast(e.message, true); s.disabled = false; s.textContent = "Salvar"; }
  };
}

// ---------------------------------------------------------------- meus vídeos
async function telaVideos() {
  const ped = await api("/api/pedidos");
  let filtro = "todos";
  const vids = videosDe(ped.pedidos);
  const and = ped.pedidos.filter((p) => !["pronto", "erro"].includes(p.estado));
  const desenhar = () => {
    const lista = vids.filter((v) => filtro === "todos" || (filtro === "cortes" ? ["cortes", "vitrine"].includes(v.tipo) : v.tipo === filtro));
    tela.innerHTML = `<h1>Meus vídeos</h1><div class="pilulas rolar" style="margin-bottom:14px">${[["todos", "Todos"], ["cortes", "Cortes"], ["animacao", "Animações"], ["video_ia", "Vídeo IA"], ["editar", "Editados"]]
      .map(([c, n]) => `<button class="pilula ${filtro === c ? "sel" : ""}" data-f="${c}">${n}</button>`).join("")}</div>
      ${and.map((p) => `<a class="card" href="#/pedido/${p.id}" style="display:block;margin-bottom:10px;color:var(--txt)"><b>⏳ ${esc(nomePedido(p))}</b><div class="ajuda">${esc(p.etapa || "Começando")}</div></a>`).join("")}
      <div class="grade">${lista.length ? lista.map(cartaoVideo).join("") : `<div class="vazio" style="grid-column:1/-1"><div class="ic">🎬</div>Bora fazer seu 1º vídeo<br><a class="btn pri" style="margin-top:12px" href="#/cortar">✂️ Cortar uma live</a></div>`}</div>
      <p class="ajuda" style="margin-top:16px">Seus vídeos ficam guardados por 30 dias. Baixe os que quiser guardar.</p>`;
    $$("[data-f]").forEach((b) => (b.onclick = () => { filtro = b.dataset.f; desenhar(); }));
  };
  desenhar();
}

// ---------------------------------------------------------------- vitrine
async function telaVitrine() {
  let tema = "";
  tela.innerHTML = `<h1>Prontos pra postar</h1><p class="sub">Cortes que já bombaram. Escolhe um e a gente coloca a sua cara.</p>
    <label class="campo"><input class="input" id="busca" placeholder="🔍 Buscar (ex.: polícia, GTA, podcast)"></label>
    <div class="pilulas rolar" id="temas" style="margin-bottom:12px">${[["", "🔥 Em alta"], ["gta", "🎮 GTA"], ["podcast", "🎙 Podcasts"], ["humor", "😂 Humor"], ["futebol", "⚽ Futebol"], ["games", "🕹 Games"], ["novos", "🆕 Novos"]]
      .map(([c, n]) => `<button class="pilula ${c === tema ? "sel" : ""}" data-t="${c}">${n}</button>`).join("")}</div><div id="lista"></div>`;
  const carregar = async () => {
    const q = $("#busca").value.trim();
    $("#lista").innerHTML = '<div class="grade">' + '<div class="esqueleto" style="aspect-ratio:9/16"></div>'.repeat(4) + "</div>";
    const r = await api(`/api/vitrine?tema=${encodeURIComponent(tema)}&q=${encodeURIComponent(q)}`);
    const secoes = r.secoes || [{ titulo: "", itens: r.itens }];
    const tot = secoes.reduce((a, s) => a + s.itens.length, 0);
    $("#lista").innerHTML = tot ? secoes.filter((s) => s.itens.length).map((s) => `${s.titulo ? `<h2>${esc(s.titulo)}</h2>` : ""}<div class="grade">${s.itens.map(cartaoVitrine).join("")}</div>`).join("")
      : '<div class="vazio"><div class="ic">🎮</div>Ainda não tem cortes desse tema.<br>Corte uma live e seja o 1º!<br><a class="btn pri" style="margin-top:12px" href="#/cortar">✂️ Cortar uma live</a></div>';
    ligarVitrine($("#lista"));
  };
  $$("#temas .pilula").forEach((b) => (b.onclick = () => { tema = b.dataset.t; $$("#temas .pilula").forEach((x) => x.classList.toggle("sel", x === b)); carregar(); }));
  let t; $("#busca").oninput = () => { clearTimeout(t); t = setTimeout(carregar, 400); };
  carregar();
}

// ---------------------------------------------------------------- animação
async function telaAnimacao() {
  const f = await api("/api/animacao/formatos");
  let formato = "auto", voz = "masculina", seg = 61, roteiro = null;
  const travado = CONTA.limites.animacoes_mes === 0;
  tela.innerHTML = `<h1>Criar animação ✨</h1><p class="sub">Escreve a ideia. A gente faz o roteiro, a voz e a animação.</p>
    ${travado ? '<div class="dica" style="margin-bottom:14px">🔒 <div>Animação é do plano <b>Corte + Animação</b>. Dá pra montar o roteiro e ver como fica.</div></div>' : ""}
    <label class="campo">Sobre o que é o vídeo?<textarea class="input" id="ideia" placeholder="ex.: 5 coisas que ninguém te conta sobre o GTA 6"></textarea></label>
    <div class="pilulas" id="ideias">${["curiosidade de GTA", "dica de dinheiro", "história de terror", "top 5 carros", "quiz de futebol"].map((x) => `<button class="pilula">${x}</button>`).join("")}</div>
    <h2>Escolha o visual</h2><div class="rolar" id="fmt"><button class="opcao sel" data-f="auto" style="width:170px"><span><b>✨ Escolhe pra mim</b><small>a IA decide</small></span></button>
      ${f.formatos.map((x) => `<button class="opcao" data-f="${x.codigo}" style="width:190px"><span><b>${esc(x.nome)}</b><small>${esc(x.frase)}</small></span></button>`).join("")}</div>
    <h2>Escolha a voz</h2><div class="rolar" id="voz">${f.vozes.map((v) => `<button class="opcao ${v.codigo === voz ? "sel" : ""}" data-v="${v.codigo}" style="width:170px">
      <span><b>${esc(v.nome)}</b><small>${esc(v.descricao)}</small></span>${v.amostra ? `<span class="tag ouvir" data-a="${v.amostra}">▶ ouvir</span>` : ""}</button>`).join("")}</div>
    <h2>Duração</h2><div class="pilulas" id="dur">${[[30, "30 s"], [61, "61 s · ganhar no TikTok"], [90, "90 s"]].map(([s, n]) => `<button class="pilula ${s === seg ? "sel" : ""}" data-s="${s}">${n}</button>`).join("")}</div>
    <div id="rot"></div>
    <div class="acao-fixa"><button class="btn pri bloco pulsa" id="ir">✨ Ver o roteiro</button></div>`;
  $$("#ideias .pilula").forEach((b) => (b.onclick = () => ($("#ideia").value = b.textContent)));
  const sel = (id, attr, cb) => $$(`#${id} [data-${attr}]`).forEach((b) => (b.onclick = () => { $$(`#${id} [data-${attr}]`).forEach((x) => x.classList.toggle("sel", x === b)); cb(b.dataset[attr]); }));
  sel("fmt", "f", (v) => (formato = v)); sel("voz", "v", (v) => (voz = v)); sel("dur", "s", (v) => (seg = +v));
  let tocando = null;
  $$("#voz .ouvir").forEach((o) => (o.onclick = (e) => { e.stopPropagation(); if (tocando) tocando.pause(); tocando = new Audio(o.dataset.a); tocando.play().catch(() => {}); }));
  $("#ir").onclick = async () => {
    const b = $("#ir");
    if (!roteiro) {
      if ($("#ideia").value.trim().length < 6) return toast("Conta em uma frase sobre o que é o vídeo", true);
      b.disabled = true; b.textContent = "Escrevendo o roteiro…";
      try {
        roteiro = await api("/api/animacao/roteiro", { json: { ideia: $("#ideia").value, formato, segundos: seg } });
        $("#rot").innerHTML = `<h2>Roteiro (${esc(f.formatos.find((x) => x.codigo === roteiro.formato)?.nome || roteiro.formato)})</h2><div class="card">
          <b>${esc(roteiro.gancho || roteiro.titulo)}</b>${roteiro.cenas.filter((c) => c.fala).map((c, i) => `<p style="margin:10px 0 0"><span class="ajuda">Cena ${i + 1}${c.destaque ? " · " + esc(c.destaque) : ""}</span><br>${esc(c.emoji || "")} ${esc(c.fala)}</p>`).join("")}
          ${roteiro.conversa ? roteiro.conversa.mensagens.map((m) => `<p style="margin:6px 0;text-align:${m.de === "eu" ? "right" : "left"}"><span class="pilula" style="display:inline-block;min-height:0;padding:6px 12px">${esc(m.texto)}</span></p>`).join("") : ""}
          ${roteiro.quiz ? `<p><b>${esc(roteiro.quiz.pergunta)}</b><br>${roteiro.quiz.opcoes.map((o, i) => (i === roteiro.quiz.certa ? "✅ " : "▫️ ") + esc(o)).join("<br>")}</p>` : ""}</div>
          <button class="btn bloco" id="ajustar" style="margin-top:10px">Ajustar (fazer outro roteiro)</button>`;
        $("#ajustar").onclick = () => { roteiro = null; $("#rot").innerHTML = ""; $("#ir").textContent = "✨ Ver o roteiro"; $("#ir").click(); };
        b.textContent = travado ? "🔒 Criar animação" : "Tá ótimo, criar ✨";
      } catch (e) { toast(e.message, true); b.textContent = "✨ Ver o roteiro"; }
      b.disabled = false; return;
    }
    b.disabled = true;
    try { const p = await api("/api/animacao", { json: { roteiro, voz } }); location.hash = "#/pedido/" + p.id; } catch (e) { toast(e.message, true); b.disabled = false; }
  };
}

// ---------------------------------------------------------------- vídeo com IA
async function telaIA() {
  const m = await api("/api/video_ia/moldes");
  let molde = "bicho", prev = null;
  tela.innerHTML = `<h1>Vídeo com IA 🤖</h1><p class="sub">Você tem <b>🪙 ${CONTA.moedas}</b> ${CONTA.moedas === 1 ? "moeda" : "moedas"}. Cada vídeo de 10 s custa 1. A prévia é grátis.</p>
    <div class="rolar" id="moldes">${m.moldes.map((x) => `<button class="opcao ${x.codigo === molde ? "sel" : ""}" data-m="${x.codigo}" style="width:180px"><span><b>${esc(x.nome)}</b><small>${esc(x.dica)}</small></span></button>`).join("")}</div>
    <label class="campo" style="margin-top:16px">Me conta o que você quer ver<textarea class="input" id="ped" placeholder="${esc(m.moldes[0].exemplo)}"></textarea></label>
    <div id="pv"></div>
    <div class="acao-fixa"><button class="btn pri bloco" id="ir">👀 Ver prévia (grátis)</button></div>`;
  $$("#moldes .opcao").forEach((b) => (b.onclick = () => { molde = b.dataset.m; $$("#moldes .opcao").forEach((x) => x.classList.toggle("sel", x === b)); $("#ped").placeholder = m.moldes.find((x) => x.codigo === molde).exemplo; }));
  const gerarPrevia = async (ajuste = "") => {
    const b = $("#ir"); b.disabled = true; b.textContent = "Desenhando a cena…";
    try {
      prev = await api("/api/video_ia/previa", { json: { pedido: $("#ped").value || $("#ped").placeholder, molde, ajuste } });
      $("#pv").innerHTML = `<h2>Ficou bom?</h2>${prev.imagem_url ? `<div class="player" style="max-width:300px;aspect-ratio:2/3"><img src="${prev.imagem_url}" alt="Prévia da cena" style="width:100%;height:100%;object-fit:cover"></div>` : '<p class="ajuda">A prévia em imagem não saiu agora, mas o roteiro está pronto.</p>'}
        <div class="pilulas" style="margin-top:12px">${["mais engraçado", "outro cenário", "outra cor", "mais realista"].map((a) => `<button class="pilula" data-aj="${a}">${a}</button>`).join("")}</div>`;
      $$("[data-aj]").forEach((x) => (x.onclick = () => gerarPrevia(x.dataset.aj)));
      b.textContent = "✓ Gerar vídeo · 🪙 1";
    } catch (e) { toast(e.message, true); b.textContent = "👀 Ver prévia (grátis)"; }
    b.disabled = false;
  };
  $("#ir").onclick = async () => {
    if (!prev) return gerarPrevia();
    if (CONTA.moedas < 1) return folhaMoedas("Você está sem moedas 🪙 Pega um pacote e cria na hora.");
    $("#ir").disabled = true;
    try { const p = await api("/api/video_ia", { json: { prompt: prev.prompt, imagem: prev.imagem, legenda: prev.legenda, molde } }); CONTA = null; location.hash = "#/pedido/" + p.id; }
    catch (e) { toast(e.message, true); $("#ir").disabled = false; }
  };
}

// ---------------------------------------------------------------- editar meu vídeo
async function telaEditar() {
  const q = new URLSearchParams((location.hash.split("?")[1]) || "");
  const de = q.get("de"), k = q.get("k") || "1";
  let arquivo = null;
  tela.innerHTML = `<h1>Editar meu vídeo 🎬</h1><p class="sub">Seu @, legenda automática, título no topo e "esticar pra 1 min" pra ganhar no TikTok.</p>
    ${de ? '<div class="card">✓ Usando o vídeo que você escolheu</div>' : `<button class="btn bloco" id="esc">📁 Escolher vídeo do celular</button><input type="file" id="arq" accept="video/*" class="oculto"><div id="info"></div>`}
    <h2>Atalhos</h2><div class="pilulas" id="at"><button class="pilula sel" data-p="tiktok">TikTok 1 min</button><button class="pilula" data-p="reels">Reels</button><button class="pilula" data-p="leg">Só legenda</button></div>
    <label class="campo" style="margin-top:16px">Título no topo (gancho)<input class="input" id="g" maxlength="60" placeholder="ex.: ELE NÃO ESPERAVA ISSO 😱"></label>
    <label class="check"><input type="checkbox" id="lg" checked> Legenda automática</label>
    <label class="check"><input type="checkbox" id="es" checked> Esticar pra passar de 1 minuto</label>
    <h2>Velocidade</h2><div class="pilulas" id="vel">${["0.75", "1", "1.25", "1.5"].map((v) => `<button class="pilula ${v === "1" ? "sel" : ""}" data-v="${v}">${v}×</button>`).join("")}</div>
    <div class="acao-fixa"><button class="btn pri bloco" id="ir">Salvar e preparar</button></div>`;
  let vel = "1";
  $$("#vel .pilula").forEach((b) => (b.onclick = () => { vel = b.dataset.v; $$("#vel .pilula").forEach((x) => x.classList.toggle("sel", x === b)); }));
  $$("#at .pilula").forEach((b) => (b.onclick = () => { $$("#at .pilula").forEach((x) => x.classList.toggle("sel", x === b)); $("#es").checked = b.dataset.p === "tiktok"; $("#lg").checked = true; }));
  if (!de) { $("#esc").onclick = () => $("#arq").click(); $("#arq").onchange = () => { arquivo = $("#arq").files[0]; if (arquivo) $("#info").innerHTML = `<div class="link-info"><div style="font-size:30px">🎞</div><div><b>${esc(arquivo.name)}</b><small>${(arquivo.size / 1e6).toFixed(0)} MB ✓</small></div></div>`; }; }
  $("#ir").onclick = async () => {
    if (!de && !arquivo) return toast("Escolhe um vídeo primeiro", true);
    const b = $("#ir"); b.disabled = true; b.textContent = "Enviando…";
    const qs = new URLSearchParams({ gancho: $("#g").value, legenda: $("#lg").checked ? "1" : "0", esticar: $("#es").checked ? "1" : "0", velocidade: vel, ...(de ? { de, k } : {}) });
    try { const p = await api("/api/editar?" + qs, de ? { method: "POST" } : { body: arquivo, headers: { "x-arquivo": arquivo.name } }); location.hash = "#/pedido/" + p.id; }
    catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Salvar e preparar"; }
  };
}

// ---------------------------------------------------------------- postagens
async function telaPostagens() {
  const p = await api("/api/postagens");
  tela.innerHTML = `<h1>Postagens 📅</h1><div class="pilulas" style="margin-bottom:16px"><button class="pilula sel">Calendário</button><button class="pilula">Contas</button><button class="pilula">Histórico</button></div>
    ${p.pode_postar ? `<div class="card"><h2 style="margin-top:0">Contas conectadas</h2>
      <div class="opcao" style="margin-bottom:8px"><span class="ic">🎵</span><span><b>TikTok</b><small>Conecte pelo QR code</small></span><a class="btn peq pri" style="margin-left:auto" href="${esc(p.posta_url)}" target="_blank" rel="noopener">Conectar</a></div>
      <div class="opcao"><span class="ic">📸</span><span><b>Instagram</b><small>Usuário e senha, passo a passo do código</small></span><a class="btn peq pri" style="margin-left:auto" href="${esc(p.posta_url)}" target="_blank" rel="noopener">Conectar</a></div></div>
      <div class="vazio"><div class="ic">🗓</div>Nada agendado ainda.<br>Abre um vídeo pronto e toca em <b>Postar</b>.</div>`
      : `<div class="vazio"><div class="ic">🚀</div><b>Postar sozinho é do plano Viral</b><br>A gente posta e agenda no TikTok e no Instagram por você, no melhor horário.<br>
      <button class="btn pri" style="margin-top:14px" onclick="paywall('Postar sozinho é do plano Viral 🔥','viral')">Ver plano Viral</button><br><span class="ajuda">Enquanto isso: baixe o vídeo e poste você mesmo.</span></div>`}`;
}

// ---------------------------------------------------------------- perfil e estilo
async function telaPerfil() {
  const c = await conta(true);
  tela.innerHTML = `<h1>Perfil</h1><div class="card" style="display:flex;gap:14px;align-items:center;margin-bottom:16px"><div style="width:56px;height:56px;border-radius:50%;background:var(--card2);display:grid;place-items:center;font-size:26px">👤</div>
    <div><b>${esc(c.nome || "Sem nome")}</b><div class="ajuda">${esc(c.email)}</div></div></div>
    <div class="opcoes">
      <a class="opcao" href="#/estilo"><span class="ic">🎨</span><span><b>Meu estilo</b><small>@${esc(c.estilo.arroba || "—")} · ${c.estilo.redes.join(", ")}</small></span></a>
      <button class="opcao" id="plano"><span class="ic">💳</span><span><b>Plano e moedas</b><small>${esc(c.plano_nome)} · 🪙 ${c.moedas} · ${c.uso.cortes} cortes este mês</small></span></button>
      <a class="opcao" href="#/postagens"><span class="ic">🔗</span><span><b>Contas conectadas</b><small>TikTok e Instagram</small></span></a>
      <button class="opcao" id="avisos"><span class="ic">📲</span><span><b>Avisos</b><small>${c.whatsapp ? "WhatsApp " + esc(c.whatsapp) : "Coloque seu WhatsApp"}</small></span></button>
      <button class="opcao" id="ajuda2"><span class="ic">❓</span><span><b>Ajuda</b><small>Perguntas e falar com uma pessoa</small></span></button>
      <a class="opcao" href="/termos" target="_blank"><span class="ic">🔒</span><span><b>Dados e privacidade</b><small>Termos, seus dados</small></span></a>
      <button class="opcao" id="sair"><span class="ic">🚪</span><span><b>Sair</b></span></button></div>`;
  $("#plano").onclick = () => abrirFolha(`<h2 style="margin-top:0">Plano e moedas</h2><div class="card meta"><div class="linha"><span>Plano</span><span>${esc(c.plano_nome)}</span></div>
    ${c.plano !== "teste" ? `<div class="linha"><span>Cortes no mês</span><span>${c.uso.cortes}/${c.limites.cortes_mes}</span></div><div class="barrinha"><i style="width:${Math.min(100, (100 * c.uso.cortes) / c.limites.cortes_mes)}%"></i></div>
    ${c.limites.animacoes_mes ? `<div class="linha"><span>Animações</span><span>${c.uso.animacoes}/${c.limites.animacoes_mes}</span></div>` : ""}
    <div class="linha"><span>Renova em</span><span>${new Date(c.ativo_ate * 1000).toLocaleDateString("pt-BR")}</span></div>` : ""}
    <div class="linha"><span>Moedas IA</span><span>🪙 ${c.moedas}</span></div></div>
    <button class="btn pri bloco" style="margin-top:12px" onclick="paywall('Trocar de plano')">Trocar plano</button><button class="btn bloco" style="margin-top:8px" onclick="folhaMoedas()">Comprar moedas</button>`);
  $("#avisos").onclick = () => abrirFolha(`<h2 style="margin-top:0">Avisos</h2><label class="campo">WhatsApp<input class="input" id="z" inputmode="tel" value="${esc(c.whatsapp)}"></label>
    <button class="btn pri bloco" id="sz">Salvar</button>`, (el) => ($("#sz", el).onclick = async () => { CONTA = await api("/api/conta", { json: { whatsapp: $("#z", el).value } }); fecharFolha(); toast("Salvo ✓"); rotear(); }));
  $("#ajuda2").onclick = () => $("#ajuda").click();
  $("#sair").onclick = async () => { await api("/api/sair", { method: "POST" }); CONTA = null; location.hash = "#/entrar"; };
}
async function telaEstilo() {
  const e = CONTA.estilo;
  tela.innerHTML = `<a href="#/perfil" class="ajuda">← Perfil</a><h1>Meu estilo</h1><p class="sub">Vale pra todos os vídeos novos.</p>
    <label class="campo">Seu @<input class="input" id="arroba" value="${esc(e.arroba ? "@" + e.arroba : "")}"></label>
    <h2>Onde você posta</h2><div class="pilulas" id="redes">${[["tiktok", "TikTok"], ["instagram", "Instagram"], ["youtube", "YouTube Shorts"]].map(([c, n]) => `<button class="pilula ${e.redes.includes(c) ? "sel" : ""}" data-c="${c}">${n}</button>`).join("")}</div>
    <h2>Cor</h2><div class="moldura" id="mold">${Object.entries(MOLDURAS).map(([k, c]) => `<button data-m="${k}" class="${e.moldura === k ? "sel" : ""}"><span style="background:${c};color:#000">GANCHO 🔥</span><em>@${esc(e.arroba || "seuperfil")}</em></button>`).join("")}</div>
    <label class="check" style="margin-top:16px"><input type="checkbox" id="leg" ${e.legenda ? "checked" : ""}> Legenda palavra a palavra</label>
    <div class="acao-fixa"><button class="btn pri bloco" id="salvar">Salvar estilo</button></div>`;
  let m = e.moldura;
  $$("#redes .pilula").forEach((b) => (b.onclick = () => b.classList.toggle("sel")));
  $$("#mold button").forEach((b) => (b.onclick = () => { m = b.dataset.m; $$("#mold button").forEach((x) => x.classList.toggle("sel", x === b)); }));
  $("#salvar").onclick = async () => {
    try { CONTA = await api("/api/estilo", { json: { arroba: $("#arroba").value, redes: $$("#redes .sel").map((b) => b.dataset.c), moldura: m, legenda: $("#leg").checked } }); toast("Estilo salvo ✓"); history.back(); }
    catch (er) { toast(er.message, true); }
  };
}

window.paywall = paywall; window.folhaMoedas = folhaMoedas; window.fecharFolha = fecharFolha;
if (location.pathname === "/entrar" && !location.hash) {
  try { if (location.search.includes("entrar=1")) sessionStorage.setItem("aba", "entrar"); } catch {}
  history.replaceState(null, "", "/app#/entrar");
}
rotear();
