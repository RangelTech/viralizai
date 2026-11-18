import React from "react";
import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import type { Props } from "./tipos";
import { Arroba, Gancho, Progresso, Sons, TelaFinal, tema } from "./pecas";
import { Conversa, Curiosidade, Historia, Impacto, NoticiaF, QuizF, Top5, VersusF } from "./formatos";

const MAPA = { historia: Historia, conversa: Conversa, top5: Top5, curiosidade: Curiosidade, quiz: QuizF, impacto: Impacto, noticia: NoticiaF, versus: VersusF };
const FINAL_S = 2.5;

export const Video: React.FC<Props> = (p) => {
  const { fps, durationInFrames } = useVideoConfig();
  const t = tema(p.variacao, p.cor);
  const F = MAPA[p.formato] || Curiosidade;
  const fimFinal = Math.round(FINAL_S * fps);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <F p={p} />
      {p.formato !== "conversa" && p.formato !== "impacto" ? (
        <Sequence durationInFrames={Math.round(2.6 * fps)}><Gancho texto={p.gancho} t={t} /></Sequence>
      ) : null}
      <Arroba arroba={p.arroba} t={t} />
      <Progresso t={t} />
      <Sequence from={durationInFrames - fimFinal}><TelaFinal texto={p.final} arroba={p.arroba} t={t} /></Sequence>
      <Sons sfx={p.sfx} voz={p.voz} />
    </AbsoluteFill>
  );
};
