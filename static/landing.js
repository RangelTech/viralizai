// Landing (Rangel Tech e Fael): vitrine pública, planos ao vivo, calculadora, entrada suave ao rolar.
(async () => {
  const $ = (s) => document.querySelector(s);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const brl = (v) => "R$ " + v.toFixed(2).replace(".", ",");
  // entrada ao rolar
  const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && e.target.classList.add("ver")), { threshold: 0.15 });
  document.querySelectorAll(".aparece").forEach((el) => io.observe(el));
  // calculadora (estimativa honesta, com a conta à mostra)
  const vpd = $("#vpd"), vw = $("#vw");
  const calc = () => {
    const videos = +vpd.value, views = +vw.value;
    $("#vpd-v").textContent = videos; $("#vw-v").textContent = views >= 1000 ? (views / 1000) + " mil" : views;
    const rpm = 2.5; // R$ por mil views qualificadas (vídeos de 1 min+), média aproximada
    const mes = videos * 30 * (views / 1000) * rpm;
    $("#res").textContent = "R$ " + Math.round(mes).toLocaleString("pt-BR");
  };
  if (vpd) { vpd.oninput = vw.oninput = calc; calc(); }
  // vitrine pública (prova)
  try {
    const r = await fetch("/api/publico/vitrine?limite=15").then((x) => x.json());
    if (r.itens && r.itens.length) {
      $("#prova").innerHTML = r.itens.map((b) => `<div class="vid" data-video="${b.previa_url || ""}" data-tipo="corte" data-titulo="${esc(b.gancho || b.titulo)}">${b.capa_url ? `<img src="${b.capa_url}" alt="" loading="lazy">` : ""}
        ${b.previa_url ? `<video muted playsinline loop preload="none" data-src="${b.previa_url}" style="position:absolute;inset:0"></video>` : ""}
        <span><u-i class=i-flame></u-i> ${b.nota}</span><b>${esc(b.gancho || b.titulo)}</b></div>`).join("");
      const vio = new IntersectionObserver((es) => es.forEach((e) => { const v = e.target; if (e.isIntersecting) { if (!v.src) v.src = v.dataset.src; v.play().catch(() => {}); } else v.pause(); }), { threshold: 0.5 });
      document.querySelectorAll("#prova video").forEach((v) => vio.observe(v));
    }
  } catch {}
  // exemplos de animação
  try {
    const e = await fetch("/api/publico/exemplos").then((x) => x.json());
    if (e.itens && e.itens.length) {
      $("#anims").innerHTML = e.itens.map((x) => `<div class="vid" data-video="${x.url}" data-tipo="animacao" data-titulo="${esc(x.titulo)}">${x.capa_url ? `<img src="${x.capa_url}" alt="" loading="lazy">` : ""}
        <video muted playsinline loop preload="none" data-src="${x.url}" style="position:absolute;inset:0"></video><b>${esc(x.titulo)}</b></div>`).join("");
      const aio = new IntersectionObserver((es) => es.forEach((en) => { const v = en.target; if (en.isIntersecting) { if (!v.src) v.src = v.dataset.src; v.play().catch(() => {}); } else v.pause(); }), { threshold: 0.5 });
      document.querySelectorAll("#anims video").forEach((v) => aio.observe(v));
    } else { const s = document.getElementById("animacoes"); if (s) s.style.display = "none"; }
  } catch {}
  // planos ao vivo (preço e checkout vêm do servidor)
  try {
    const p = await fetch("/api/planos").then((x) => x.json());
    $("#planos").innerHTML = p.planos.map((x) => `<div class="pl ${x.destaque ? "dest" : ""}">${x.destaque ? '<span class="tag">MAIS ESCOLHIDO</span>' : ""}
      <h3>${esc(x.nome)}</h3>${x.lancamento ? `<div class="de">${brl(x.preco)}</div>` : ""}<div class="p">${brl(x.lancamento || x.preco).replace(",90", '<small>,90</small>').replace(",00", "")}<small>/mês</small></div>
      <ul>${x.itens.map((i) => `<li>${esc(i)}</li>`).join("")}</ul><a class="btn ${x.destaque ? "pulsa" : "sec"}" href="${x.direto && x.checkout ? esc(x.checkout) : "/entrar?plano=" + x.codigo}">${x.direto ? "Assinar agora" : "Começar agora"}</a></div>`).join("");
    if (!p.moedas.length) { const m = $("#moedas"); if (m) m.style.display = "none"; } else
    $("#moedas").innerHTML = `<div><b><u-i class=i-bot></u-i> Vídeo com IA</b><br><span style="color:var(--txt2)">Pacotes de moedas, 1 moeda = 1 vídeo de 10 s</span></div>` +
      p.moedas.map((m) => `<span><b>${m.moedas} vídeos</b> ${brl(m.preco)}</span>`).join("");
  } catch {}

  // vídeo completo num modal, com som, e o caminho pra assinar
  const modal = document.createElement("div");
  modal.className = "modal-video";
  modal.innerHTML = `<div class="mv-caixa"><button class="mv-fechar" aria-label="Fechar">✕</button><video playsinline controls></video>
    <b class="mv-titulo"></b><a class="btn pulsa mv-cta1" href="/entrar"><u-i class=i-send></u-i> QUERO POSTAR ESSE VÍDEO NO MEU CANAL AGORA</a>
    <a class="btn sec mv-cta2" href="/entrar"><u-i class=i-sparkles></u-i> Quero fazer vídeos assim</a><small>Teste grátis: 1 corte com o seu @, sem cartão.</small></div>`;
  if (location.hostname.includes("fael")) {  // landing do Fael: tudo leva aos planos (checkout direto)
    modal.querySelectorAll('a[href="/entrar"]').forEach((x) => (x.href = "#planos-sec"));
    const nota = modal.querySelector("small"); if (nota) nota.textContent = "Escolhe o plano, paga e o acesso chega no seu e-mail.";
    modal.querySelectorAll("a").forEach((x) => x.addEventListener("click", () => fechar()));
  }
  document.body.appendChild(modal);
  const mv = modal.querySelector("video");
  const fechar = () => { modal.classList.remove("aberto"); mv.pause(); mv.removeAttribute("src"); mv.load(); document.body.style.overflow = ""; };
  modal.querySelector(".mv-fechar").onclick = fechar;
  modal.onclick = (e) => { if (e.target === modal) fechar(); };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fechar(); });
  document.addEventListener("click", (e) => {
    const card = e.target.closest(".vid[data-video]");
    if (!card || !card.dataset.video) return;
    const anim = card.dataset.tipo === "animacao";
    modal.querySelector(".mv-titulo").textContent = card.dataset.titulo || "";
    modal.querySelector(".mv-cta2").textContent = anim ? " Quero criar animações assim" : " Quero gerar cortes assim";
    mv.src = card.dataset.video; mv.muted = false;
    modal.classList.add("aberto"); document.body.style.overflow = "hidden";
    mv.play().catch(() => { mv.muted = true; mv.play().catch(() => {}); });
  });
})();
