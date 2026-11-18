// Os 8 formatos virais do lançamento (47d §3). Cada um recebe Props e escolhe o visual pela `variacao`.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig, Img, OffthreadVideo, staticFile } from "remotion";
import type { Cena, Props } from "./tipos";
import { Destaque, Emoji, entra, Fundo, Legenda, tema, Tema, useTremida } from "./pecas";

const cenaAtual = (cenas: Cena[], s: number) => cenas.find((c) => s >= c.inicio && s < c.fim) || cenas[cenas.length - 1];
const enfases = (p: Props) => p.palavras.filter((w) => p.cenas.some((c) => (c.enfase || []).some((e) => w.w.toLowerCase().includes(e.toLowerCase())))).map((w) => w.t0);

const BRoll: React.FC<{ arq?: string }> = ({ arq }) => {
  const f = useCurrentFrame();
  if (!arq) return null;
  const z = 1.05 + f / 3000;
  const st = { width: "100%", height: "100%", objectFit: "cover" as const, transform: `scale(${z})` };
  return (
    <AbsoluteFill style={{ opacity: 0.55 }}>
      {/\.(mp4|webm|mov)$/i.test(arq) ? <OffthreadVideo src={staticFile(arq)} muted style={st} /> : <Img src={staticFile(arq)} style={st} />}
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(0,0,0,.55), rgba(0,0,0,.15) 40%, rgba(0,0,0,.75))" }} />
    </AbsoluteFill>
  );
};

// 1. História narrada + fundo "satisfatório" (gameplay de fundo vira animação hipnótica, sem licença de terceiros)
export const Historia: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = tema(p.variacao, p.cor);
  const c = cenaAtual(p.cenas, f / fps);
  return (
    <AbsoluteFill style={{ transform: useTremida(enfases(p), 10) }}>
      <Fundo t={t} estilo="orbes" />
      <AbsoluteFill style={{ top: 1100 }}><Satisfatorio t={t} /></AbsoluteFill>
      <BRoll arq={c?.broll} />
      {c ? <Destaque key={c.inicio} texto={c.destaque} t={t} inicioFrame={Math.round(c.inicio * fps)} y={330} tamanho={96} /> : null}
      {c?.emoji ? <Emoji key={"e" + c.inicio} e={c.emoji} inicioFrame={Math.round(c.inicio * fps) + 6} y={700} tamanho={180} /> : null}
      <Legenda palavras={p.palavras} t={t} y={880} tamanho={92} />
    </AbsoluteFill>
  );
};

const Satisfatorio: React.FC<{ t: Tema }> = ({ t }) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "#000" }}>
      {Array.from({ length: 14 }).map((_, i) => {
        const y = ((f * (4 + (i % 4)) + i * 140) % 1100) - 200;
        return (
          <div key={i} style={{ position: "absolute", left: 40 + ((i * 73) % 1000), top: y, width: 90 + (i % 3) * 30, height: 90 + (i % 3) * 30,
            borderRadius: i % 2 ? "50%" : 22, background: i % 3 ? t.destaque : t.fundo[2], opacity: 0.85, transform: `rotate(${f * (i % 2 ? 3 : -2)}deg)`,
            boxShadow: `0 0 40px ${t.destaque}` }} />
        );
      })}
      <div style={{ position: "absolute", left: 0, right: 0, top: 380, height: 16, background: t.destaque, boxShadow: `0 0 30px ${t.destaque}` }} />
    </AbsoluteFill>
  );
};

// 2. Conversa de WhatsApp
export const Conversa: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  const conv = p.conversa || { nome: "Contato", mensagens: [] };
  const vis = conv.mensagens.filter((m) => s >= m.t);
  const prox = conv.mensagens.find((m) => s < m.t && m.t - s < 1.4 && m.de === "outro");
  const fundo = ["#0b141a", "#111b21", "#0d1418"][p.variacao % 3];
  const deslize = Math.max(0, vis.length - 7) * 150;
  return (
    <AbsoluteFill style={{ background: fundo }}>
      <div style={{ height: 210, background: "#202c33", display: "flex", alignItems: "center", gap: 28, padding: "70px 40px 0", fontFamily: "Arial", color: "#e9edef" }}>
        <div style={{ width: 96, height: 96, borderRadius: "50%", background: "#6a7175", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 54 }}>👤</div>
        <div><div style={{ fontSize: 44, fontWeight: 700 }}>{conv.nome}</div><div style={{ fontSize: 30, color: "#8696a0" }}>{prox ? "digitando..." : "online"}</div></div>
      </div>
      <div style={{ position: "absolute", top: 240, left: 0, right: 0, bottom: 260, overflow: "hidden" }}>
        <div style={{ transform: `translateY(${-deslize}px)`, padding: "0 34px", display: "flex", flexDirection: "column", gap: 22 }}>
          {vis.map((m, i) => {
            const e = spring({ frame: f - Math.round(m.t * fps), fps, config: { damping: 14, stiffness: 240 } });
            const eu = m.de === "eu";
            return (
              <div key={i} style={{ alignSelf: eu ? "flex-end" : "flex-start", maxWidth: "78%", background: eu ? "#005c4b" : "#202c33", color: "#e9edef",
                borderRadius: 26, padding: "22px 30px", fontSize: 46, fontFamily: "Arial", lineHeight: 1.25, transform: `scale(${e})`,
                transformOrigin: eu ? "100% 100%" : "0 100%", boxShadow: "0 4px 10px rgba(0,0,0,.3)" }}>
                {m.texto}
                <span style={{ fontSize: 24, color: "#8696a0", marginLeft: 16 }}>{eu ? "✓✓" : ""}</span>
              </div>
            );
          })}
          {prox ? <div style={{ alignSelf: "flex-start", background: "#202c33", borderRadius: 26, padding: "26px 34px", fontSize: 50, color: "#8696a0" }}>
            {"•••".slice(0, 1 + (Math.floor(f / 6) % 3))}</div> : null}
        </div>
      </div>
      <Legenda palavras={p.palavras} t={tema(p.variacao, p.cor)} y={1680} tamanho={64} />
    </AbsoluteFill>
  );
};

// 3. Top 5 / ranking (contagem regressiva, nº 1 com revelação)
export const Top5: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  const t = tema(p.variacao, p.cor);
  const itens = p.ranking || [];
  const atual = s < 2.6 ? null : [...itens].reverse().find((i) => s >= Math.max(i.t, 2.6)) || null;
  const ini = atual ? Math.round(Math.max(atual.t, 2.6) * fps) : 0;
  const e = spring({ frame: f - ini, fps, config: { damping: 9, stiffness: 160 } });
  const c = cenaAtual(p.cenas, s);
  return (
    <AbsoluteFill style={{ transform: useTremida(itens.map((i) => i.t), 16) }}>
      <Fundo t={t} estilo="raios" />
      <BRoll arq={c?.broll} />
      <div style={{ position: "absolute", top: 240, left: 60, fontFamily: t.fonteCorpo, fontWeight: 900, fontSize: 52, color: t.destaque, textTransform: "uppercase" }}>
        {p.gancho}
      </div>
      {atual ? (
        <>
          <div style={{ position: "absolute", top: 380, width: "100%", textAlign: "center", fontFamily: t.fonteTitulo, fontSize: 420, lineHeight: 1,
            color: atual.n === 1 ? t.destaque : t.texto, transform: `scale(${0.3 + 0.7 * e})`, textShadow: `0 0 80px ${t.destaque}` }}>
            #{atual.n}
          </div>
          {atual.icone ? <Emoji key={atual.n} e={atual.icone} inicioFrame={ini + 4} y={1000} tamanho={170} /> : null}
          <div style={{ position: "absolute", top: 1120, left: 60, right: 60, textAlign: "center", fontFamily: t.fonteTitulo, fontSize: 96, color: t.texto,
            opacity: entra(f, ini + 6), textTransform: "uppercase", lineHeight: 1 }}>{atual.titulo}</div>
        </>
      ) : null}
      <div style={{ position: "absolute", bottom: 380, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 18 }}>
        {[...itens].sort((a, b) => b.n - a.n).map((i) => (
          <div key={i.n} style={{ width: 70, height: 70, borderRadius: 18, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: t.fonteCorpo,
            fontWeight: 900, fontSize: 36, background: atual && i.n === atual.n ? t.destaque : "rgba(255,255,255,.12)", color: atual && i.n === atual.n ? "#000" : "#fff" }}>{i.n}</div>
        ))}
      </div>
      <Legenda palavras={p.palavras} t={t} y={1560} tamanho={66} />
    </AbsoluteFill>
  );
};

// 4. Curiosidade com apoio visual (B-roll quando houver; senão ícones grandes)
export const Curiosidade: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = tema(p.variacao, p.cor);
  const c = cenaAtual(p.cenas, f / fps);
  const ini = Math.round((c?.inicio || 0) * fps);
  const zoom = interpolate(f - ini, [0, 120], [1.15, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ transform: useTremida(enfases(p), 8) }}>
      <Fundo t={t} estilo={p.variacao % 2 ? "grade" : "orbes"} />
      <BRoll arq={c?.broll} />
      <AbsoluteFill style={{ transform: `scale(${zoom})` }}>
        {c?.icone || c?.emoji ? <Emoji key={c.inicio} e={c.icone || c.emoji || ""} inicioFrame={ini} y={560} tamanho={340} /> : null}
      </AbsoluteFill>
      {c ? <Destaque key={"d" + c.inicio} texto={c.destaque} t={t} inicioFrame={ini + 4} y={240} tamanho={100} /> : null}
      <Legenda palavras={p.palavras} t={t} y={1240} tamanho={86} />
    </AbsoluteFill>
  );
};

// 5. Quiz / adivinhe (contador de 5 s e revelação)
export const QuizF: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  const t = tema(p.variacao, p.cor);
  const q = p.quiz;
  if (!q) return <Curiosidade p={p} />;
  const revelou = s >= q.t_revela;
  const faltam = Math.max(0, Math.ceil(q.t_revela - s));
  const letras = ["A", "B", "C", "D"];
  return (
    <AbsoluteFill>
      <Fundo t={t} estilo="grade" />
      <div style={{ position: "absolute", top: 260, left: 60, right: 60, textAlign: "center", fontFamily: t.fonteTitulo, fontSize: 92, color: t.texto, lineHeight: 1.05,
        opacity: entra(f, q.t_pergunta * fps) }}>{q.pergunta}</div>
      <div style={{ position: "absolute", top: 760, left: 70, right: 70, display: "flex", flexDirection: "column", gap: 34 }}>
        {q.opcoes.map((o, i) => {
          const certa = i === q.certa;
          const e = entra(f, (q.t_pergunta + 0.6 + i * 0.35) * fps);
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 28, padding: "30px 36px", borderRadius: 28, fontFamily: t.fonteCorpo, fontWeight: 900,
              fontSize: 54, opacity: revelou && !certa ? 0.35 : e, transform: `translateX(${(1 - e) * -120}px) scale(${revelou && certa ? 1.06 : 1})`,
              background: revelou ? (certa ? "#22c55e" : "#3f1d1d") : "rgba(255,255,255,.1)", color: "#fff", border: `4px solid ${revelou && certa ? "#fff" : "transparent"}` }}>
              <span style={{ width: 80, height: 80, borderRadius: 20, background: t.destaque, color: "#000", display: "flex", alignItems: "center", justifyContent: "center" }}>{letras[i]}</span>
              {o}{revelou && certa ? " ✅" : ""}
            </div>
          );
        })}
      </div>
      {!revelou && faltam <= 5 ? (
        <div style={{ position: "absolute", top: 1280, width: "100%", textAlign: "center", fontFamily: t.fonteTitulo, fontSize: 220, color: t.destaque,
          transform: `scale(${1 + 0.15 * Math.sin(f / 3)})`, textShadow: `0 0 60px ${t.destaque}` }}>{faltam}</div>
      ) : null}
      {revelou || faltam > 5 ? <Legenda palavras={p.palavras} t={t} y={1600} tamanho={60} /> : null}
    </AbsoluteFill>
  );
};

// 6. Texto cinético de impacto (frases explodindo no ritmo)
export const Impacto: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  const t = tema(p.variacao, p.cor);
  const w = [...p.palavras].reverse().find((x) => s >= x.t0);
  const ini = w ? Math.round(w.t0 * fps) : 0;
  const e = spring({ frame: f - ini, fps, config: { damping: 7, stiffness: 300 } });
  const grande = w && (w.w.length > 5 || p.cenas.some((c) => (c.enfase || []).includes(w.w.toLowerCase())));
  return (
    <AbsoluteFill style={{ transform: useTremida(enfases(p), 20) }}>
      <Fundo t={t} estilo="raios" />
      {w ? (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <div style={{ fontFamily: t.fonteTitulo, fontSize: grande ? 230 : 170, color: grande ? t.destaque : t.texto, textTransform: "uppercase", textAlign: "center",
            transform: `scale(${0.2 + 0.8 * e}) rotate(${(ini % 3 - 1) * 4}deg)`, textShadow: `0 0 90px ${t.destaque}88, 0 12px 0 #000`, padding: 40, lineHeight: 0.95 }}>
            {w.w.replace(/[.,;:!?]+$/, "")}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

// 7. Notícia urgente
export const NoticiaF: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  const t = tema(p.variacao, p.cor);
  const n = p.noticia || { faixa: "URGENTE", manchete: p.gancho };
  const pisca = Math.floor(f / 10) % 2 === 0;
  const c = cenaAtual(p.cenas, s);
  return (
    <AbsoluteFill>
      <Fundo t={{ ...t, fundo: ["#05060a", "#0b1230", "#141f4d"] }} estilo="grade" />
      <BRoll arq={c?.broll} />
      <div style={{ position: "absolute", top: 230, left: 0, right: 0, height: 120, background: "#d90429", display: "flex", alignItems: "center", gap: 24, padding: "0 50px",
        transform: `translateX(${(1 - entra(f, 0, 10)) * -1100}px)` }}>
        <span style={{ width: 36, height: 36, borderRadius: "50%", background: pisca ? "#fff" : "transparent", border: "4px solid #fff" }} />
        <span style={{ fontFamily: t.fonteTitulo, fontSize: 80, color: "#fff" }}>{n.faixa}</span>
      </div>
      <div style={{ position: "absolute", top: 400, left: 50, right: 50, fontFamily: t.fonteTitulo, fontSize: 104, lineHeight: 1, color: "#fff", textTransform: "uppercase",
        opacity: entra(f, 12, 12) }}>{n.manchete}</div>
      {(n.numeros || []).filter((x) => s >= x.t).map((x, i) => (
        <div key={i} style={{ position: "absolute", top: 820 + i * 170, left: 50, right: 50, display: "flex", justifyContent: "space-between", alignItems: "center",
          background: "rgba(255,255,255,.08)", borderLeft: `12px solid ${t.destaque}`, padding: "24px 34px", borderRadius: 16, opacity: entra(f, x.t * fps) }}>
          <span style={{ fontFamily: t.fonteCorpo, fontWeight: 800, fontSize: 44, color: "#cfd6ff" }}>{x.rotulo}</span>
          <span style={{ fontFamily: t.fonteTitulo, fontSize: 84, color: t.destaque }}>{x.valor}</span>
        </div>
      ))}
      <div style={{ position: "absolute", bottom: 300, left: 0, right: 0, height: 80, background: "#0a0a0a", overflow: "hidden", display: "flex", alignItems: "center" }}>
        <div style={{ whiteSpace: "nowrap", fontFamily: t.fonteCorpo, fontWeight: 800, fontSize: 40, color: "#fff", transform: `translateX(${1080 - (f * 6) % 4000}px)` }}>
          {(p.cenas.map((c) => c.destaque).join("   •   ") + "   •   ").repeat(3)}
        </div>
      </div>
      <Legenda palavras={p.palavras} t={t} y={1360} tamanho={70} />
    </AbsoluteFill>
  );
};

// 8. X contra Y
export const VersusF: React.FC<{ p: Props }> = ({ p }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  const t = tema(p.variacao, p.cor);
  const v = p.versus;
  if (!v) return <Curiosidade p={p} />;
  const fimItens = v.itens.length ? v.itens[v.itens.length - 1].t + 2.5 : 999;
  const venceu = s >= fimItens;
  const lado = (nome: string, icone: string | undefined, cor: string, esq: boolean) => {
    const ganhou = venceu && ((v.vencedor === "a") === esq);
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 20, background: cor,
        transform: `scale(${ganhou ? 1.04 : 1})`, opacity: venceu && !ganhou ? 0.4 : 1 }}>
        <div style={{ fontSize: 170 }}>{icone || (esq ? "🅰️" : "🅱️")}</div>
        <div style={{ fontFamily: t.fonteTitulo, fontSize: 84, color: "#fff", textAlign: "center", padding: "0 20px", lineHeight: 1 }}>{nome}</div>
        {ganhou ? <div style={{ fontSize: 120 }}>👑</div> : null}
      </div>
    );
  };
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <div style={{ position: "absolute", top: 180, height: 720, left: 0, right: 0, display: "flex" }}>
        {lado(v.a, v.ia, "#1d3fbf", true)}
        {lado(v.b, v.ib, "#bf1d3a", false)}
        <div style={{ position: "absolute", left: 540 - 90, top: 270, width: 180, height: 180, borderRadius: "50%", background: t.destaque, display: "flex", alignItems: "center",
          justifyContent: "center", fontFamily: t.fonteTitulo, fontSize: 96, color: "#000", transform: `scale(${spring({ frame: f - 6, fps, config: { damping: 6 } })})` }}>VS</div>
      </div>
      <div style={{ position: "absolute", top: 940, left: 50, right: 50, display: "flex", flexDirection: "column", gap: 26 }}>
        {v.itens.filter((x) => s >= x.t).map((x, i) => {
          const e = entra(f, x.t * fps, 18);
          const tot = Math.max(1, x.va + x.vb);
          return (
            <div key={i}>
              <div style={{ fontFamily: t.fonteCorpo, fontWeight: 900, fontSize: 40, color: "#fff", textAlign: "center", marginBottom: 8 }}>{x.rotulo}</div>
              <div style={{ display: "flex", height: 54, borderRadius: 27, overflow: "hidden", background: "#222" }}>
                <div style={{ width: `${(50 + (x.va / tot - 0.5) * 100 * e)}%`, background: "#2f5bff", color: "#fff", fontFamily: t.fonteCorpo, fontWeight: 900, fontSize: 34,
                  display: "flex", alignItems: "center", paddingLeft: 20 }}>{Math.round(x.va * e)}</div>
                <div style={{ flex: 1, background: "#ff2f55", color: "#fff", fontFamily: t.fonteCorpo, fontWeight: 900, fontSize: 34, display: "flex", alignItems: "center",
                  justifyContent: "flex-end", paddingRight: 20 }}>{Math.round(x.vb * e)}</div>
              </div>
            </div>
          );
        })}
      </div>
      <Legenda palavras={p.palavras} t={t} y={1600} tamanho={62} />
    </AbsoluteFill>
  );
};
