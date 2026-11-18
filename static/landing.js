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
    const r = await fetch("/api/publico/vitrine").then((x) => x.json());
    if (r.itens && r.itens.length) {
      $("#prova").innerHTML = r.itens.map((b) => `<div class="vid">${b.capa_url ? `<img src="${b.capa_url}" alt="" loading="lazy">` : ""}
        ${b.previa_url ? `<video muted playsinline loop preload="none" data-src="${b.previa_url}" style="position:absolute;inset:0"></video>` : ""}
        <span>🔥 ${b.nota}</span><b>${esc(b.gancho || b.titulo)}</b></div>`).join("");
      const vio = new IntersectionObserver((es) => es.forEach((e) => { const v = e.target; if (e.isIntersecting) { if (!v.src) v.src = v.dataset.src; v.play().catch(() => {}); } else v.pause(); }), { threshold: 0.5 });
      document.querySelectorAll("#prova video").forEach((v) => vio.observe(v));
    }
  } catch {}
  // planos ao vivo (preço e checkout vêm do servidor)
  try {
    const p = await fetch("/api/planos").then((x) => x.json());
    $("#planos").innerHTML = p.planos.map((x) => `<div class="pl ${x.destaque ? "dest" : ""}">${x.destaque ? '<span class="tag">MAIS ESCOLHIDO</span>' : ""}
      <h3>${esc(x.nome)}</h3>${x.lancamento ? `<div class="de">${brl(x.preco)}</div>` : ""}<div class="p">${brl(x.lancamento || x.preco).replace(",90", '<small>,90</small>').replace(",00", "")}<small>/mês</small></div>
      <ul>${x.itens.map((i) => `<li>${esc(i)}</li>`).join("")}</ul><a class="btn ${x.destaque ? "pulsa" : "sec"}" href="/entrar?plano=${x.codigo}">Começar agora</a></div>`).join("");
    $("#moedas").innerHTML = `<div><b>🤖 Vídeo com IA</b><br><span style="color:var(--txt2)">Pacotes de moedas, 1 moeda = 1 vídeo de 10 s</span></div>` +
      p.moedas.map((m) => `<span><b>${m.moedas} vídeos</b> ${brl(m.preco)}</span>`).join("");
  } catch {}
})();
