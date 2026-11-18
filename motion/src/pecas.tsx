// Peças que todo molde usa (47d §4): fundo animado, legenda cinética, gancho, ênfase, emoji, progresso, tela final, sons.
import React from "react";
import { AbsoluteFill, Audio, interpolate, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { loadFont as anton } from "@remotion/google-fonts/Anton";
import { loadFont as montserrat } from "@remotion/google-fonts/Montserrat";
import { loadFont as bebas } from "@remotion/google-fonts/BebasNeue";
import type { Palavra, Sfx } from "./tipos";

const A = anton().fontFamily;
const M = montserrat("normal", { weights: ["800", "900"] }).fontFamily;
const B = bebas().fontFamily;

export type Tema = { fundo: [string, string, string]; destaque: string; texto: string; fonteTitulo: string; fonteCorpo: string; legenda: string };
export const TEMAS: Tema[] = [
  { fundo: ["#05070a", "#0b2a1a", "#0d3d24"], destaque: "#2bff88", texto: "#ffffff", fonteTitulo: A, fonteCorpo: M, legenda: "#2bff88" },
  { fundo: ["#0a0510", "#2a0b3a", "#4a0d4d"], destaque: "#ffd23d", texto: "#ffffff", fonteTitulo: B, fonteCorpo: M, legenda: "#ffd23d" },
  { fundo: ["#0b0605", "#3a120b", "#5c1a0a"], destaque: "#ff6a00", texto: "#ffffff", fonteTitulo: A, fonteCorpo: M, legenda: "#ffb000" },
];

export const tema = (variacao: number, cor?: string): Tema => {
  const t = TEMAS[Math.abs(variacao) % TEMAS.length];
  return cor ? { ...t, destaque: cor, legenda: cor } : t;
};

// ---------------------------------------------------------------- fundo vivo (nunca tela parada)
export const Fundo: React.FC<{ t: Tema; estilo?: "grade" | "orbes" | "raios" }> = ({ t, estilo = "orbes" }) => {
  const f = useCurrentFrame();
  const ang = (f / 3) % 360;
  return (
    <AbsoluteFill style={{ background: `linear-gradient(${160 + Math.sin(f / 90) * 20}deg, ${t.fundo[0]}, ${t.fundo[1]} 55%, ${t.fundo[2]})`, overflow: "hidden" }}>
      {estilo === "grade" && (
        <AbsoluteFill style={{ backgroundImage: `linear-gradient(${t.destaque}22 2px, transparent 2px), linear-gradient(90deg, ${t.destaque}22 2px, transparent 2px)`,
          backgroundSize: "90px 90px", backgroundPosition: `0 ${(f * 2) % 90}px`, transform: "perspective(900px) rotateX(55deg) scale(2.2)", transformOrigin: "50% 100%", opacity: 0.6 }} />
      )}
      {estilo === "raios" && (
        <AbsoluteFill style={{ background: `repeating-conic-gradient(from ${ang}deg at 50% 45%, ${t.destaque}14 0deg 10deg, transparent 10deg 20deg)` }} />
      )}
      {estilo === "orbes" && [0, 1, 2, 3].map((i) => (
        <div key={i} style={{ position: "absolute", width: 700, height: 700, borderRadius: "50%", filter: "blur(120px)", opacity: 0.35,
          background: i % 2 ? t.destaque : t.fundo[2],
          left: 540 + Math.sin(f / (70 + i * 13) + i * 2) * 420 - 350, top: 960 + Math.cos(f / (90 + i * 11) + i) * 700 - 350 }} />
      ))}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,.65) 100%)" }} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- legenda cinética (palavra falada destacada)
export const Legenda: React.FC<{ palavras: Palavra[]; t: Tema; y?: number; tamanho?: number }> = ({ palavras, t, y = 1180, tamanho = 84 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  // grupos de até 3 palavras (ou quebra em pontuação/pausa)
  const grupos: Palavra[][] = [];
  let g: Palavra[] = [];
  palavras.forEach((p, i) => {
    g.push(p);
    const prox = palavras[i + 1];
    if (g.length >= 3 || /[.!?,]$/.test(p.w) || !prox || prox.t0 - p.t1 > 0.5) {
      grupos.push(g);
      g = [];
    }
  });
  const atual = grupos.find((x) => s >= x[0].t0 - 0.05 && s <= x[x.length - 1].t1 + 0.25);
  if (!atual) return null;
  const entrada = spring({ frame: f - Math.round(atual[0].t0 * fps), fps, config: { damping: 12, stiffness: 220 } });
  return (
    <div style={{ position: "absolute", top: y, left: 60, right: 60, display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "10px 22px",
      transform: `scale(${0.85 + 0.15 * entrada})` }}>
      {atual.map((p, i) => {
        const falando = s >= p.t0 && s <= p.t1 + 0.05;
        return (
          <span key={i} style={{ fontFamily: t.fonteCorpo, fontWeight: 900, fontSize: tamanho, textTransform: "uppercase", lineHeight: 1.05,
            color: falando ? t.legenda : t.texto, transform: falando ? "scale(1.12) rotate(-2deg)" : "none",
            WebkitTextStroke: "4px #000", paintOrder: "stroke fill", textShadow: "0 8px 24px rgba(0,0,0,.6)" }}>
            {p.w.replace(/[.,;:]+$/, "")}
          </span>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- gancho (2 primeiros segundos)
export const Gancho: React.FC<{ texto: string; t: Tema }> = ({ texto, t }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const soco = spring({ frame: f, fps, config: { damping: 8, stiffness: 260 } });
  const sai = interpolate(f, [fps * 2.2, fps * 2.6], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const flash = interpolate(f, [0, 4], [0.9, 0], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: sai, padding: 70 }}>
      <AbsoluteFill style={{ background: "#fff", opacity: flash }} />
      <div style={{ fontFamily: t.fonteTitulo, fontSize: 132, lineHeight: 0.98, color: t.texto, textAlign: "center", textTransform: "uppercase",
        transform: `scale(${0.4 + 0.6 * soco}) rotate(${(1 - soco) * -6}deg)`, textShadow: `0 0 60px ${t.destaque}88, 0 10px 0 #000` }}>
        {texto.split(" ").map((w, i) => (
          <span key={i} style={{ color: i % 3 === 1 ? t.destaque : t.texto }}>{w} </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- texto grande da cena com zoom-soco
export const Destaque: React.FC<{ texto: string; t: Tema; inicioFrame: number; y?: number; tamanho?: number }> = ({ texto, t, inicioFrame, y = 520, tamanho = 120 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const e = spring({ frame: f - inicioFrame, fps, config: { damping: 10, stiffness: 200 } });
  return (
    <div style={{ position: "absolute", top: y, left: 50, right: 50, textAlign: "center", fontFamily: t.fonteTitulo, fontSize: tamanho, lineHeight: 1,
      color: t.texto, textTransform: "uppercase", transform: `translateY(${(1 - e) * 80}px) scale(${0.7 + 0.3 * e})`, opacity: e,
      textShadow: `0 0 50px ${t.destaque}66, 0 8px 0 #000` }}>
      {texto}
    </div>
  );
};

export const Emoji: React.FC<{ e: string; inicioFrame: number; x?: number; y?: number; tamanho?: number }> = ({ e, inicioFrame, x = 540, y = 360, tamanho = 220 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: f - inicioFrame, fps, config: { damping: 7, stiffness: 180 } });
  const bob = Math.sin((f - inicioFrame) / 8) * 10;
  return (
    <div style={{ position: "absolute", left: x - tamanho / 2, top: y - tamanho / 2 + bob, fontSize: tamanho, transform: `scale(${s}) rotate(${(1 - s) * 40}deg)`,
      filter: "drop-shadow(0 20px 30px rgba(0,0,0,.5))" }}>{e}</div>
  );
};

// tremida curta nos impactos
export const useTremida = (momentos: number[], forca = 14) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = f / fps;
  const m = momentos.find((x) => s >= x && s < x + 0.25);
  if (m === undefined) return "none";
  const k = 1 - (s - m) / 0.25;
  return `translate(${Math.sin(f * 7) * forca * k}px, ${Math.cos(f * 9) * forca * k}px)`;
};

export const Progresso: React.FC<{ t: Tema }> = ({ t }) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <div style={{ position: "absolute", top: 0, left: 0, height: 12, width: `${(100 * f) / durationInFrames}%`, background: t.destaque, boxShadow: `0 0 20px ${t.destaque}` }} />
  );
};

export const Arroba: React.FC<{ arroba?: string; t: Tema; embaixo?: boolean }> = ({ arroba, t, embaixo }) =>
  arroba ? (
    <div style={{ position: "absolute", ...(embaixo ? { bottom: 200 } : { top: 120 }), width: "100%", textAlign: "center", fontFamily: t.fonteCorpo, fontWeight: 800, fontSize: 38, color: "#ffffffcc",
      textShadow: "0 2px 8px #000" }}>@{arroba.replace(/^@/, "")}</div>
  ) : null;

export const TelaFinal: React.FC<{ texto?: string; arroba?: string; t: Tema }> = ({ texto, arroba, t }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const e = spring({ frame: f, fps, config: { damping: 12 } });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", background: "rgba(0,0,0,.9)", opacity: e }}>
      <div style={{ fontFamily: t.fonteTitulo, fontSize: 110, color: t.texto, textAlign: "center", padding: 60, transform: `scale(${0.8 + 0.2 * e})`, lineHeight: 1 }}>
        {texto || "SEGUE PRA PARTE 2"}
      </div>
      {arroba ? <div style={{ fontFamily: t.fonteCorpo, fontWeight: 900, fontSize: 64, color: t.destaque, marginTop: 30 }}>@{arroba.replace(/^@/, "")}</div> : null}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- sons
export const Sons: React.FC<{ sfx: Sfx[]; voz?: string }> = ({ sfx, voz }) => {
  const { fps } = useVideoConfig();
  return (
    <>
      {voz ? <Audio src={staticFile(voz)} /> : null}
      {sfx.map((x, i) => (
        <Sequence key={i} from={Math.max(0, Math.round(x.t * fps))} durationInFrames={Math.round(fps * 2.5)}>
          <Audio src={staticFile(`sfx/${x.tipo}.mp3`)} volume={x.tipo === "riser" ? 0.35 : 0.55} />
        </Sequence>
      ))}
    </>
  );
};

export const entra = (f: number, ini: number, dur = 8) =>
  interpolate(f, [ini, ini + dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
