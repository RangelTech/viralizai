// Animação programada (motor cinema, 47e §3): o roteiro vira um script JS (motor + planos + compositor) que desenha cada quadro
// num canvas. O bundle do Remotion fica fixo; o filme vem da pasta pública do trabalho (filme.js), então nada é recompilado.
import React, { useEffect, useRef, useState } from "react";
import { AbsoluteFill, Audio, Sequence, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont } from "@remotion/google-fonts/Poppins";

loadFont("normal", { weights: ["700"], subsets: ["latin"] });

export type CinemaProps = {
  duracao: number;
  voz?: string;
  musica?: string;
  musicaVol?: number;
  sfx?: [number, string, number?][];
  palavras: { w: string; s: number; e: number }[];
  imagens?: Record<string, string>;
  legenda?: boolean;
};

type Filme = { renderFrame: (f: number) => void; TOTAL_FRAMES: number; DUR: number };

export const Cinema: React.FC<CinemaProps> = (p) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [filme, setFilme] = useState<Filme | null>(null);
  const [handle] = useState(() => delayRender("carregando filme.js"));

  useEffect(() => {
    let vivo = true;
    (async () => {
      const codigo = await (await fetch(staticFile("filme.js"))).text();
      const imgs: Record<string, HTMLImageElement> = {};
      await Promise.all(Object.entries(p.imagens || {}).map(([k, u]) => new Promise<void>((ok) => {
        const im = new Image(); im.onload = () => ok(); im.onerror = () => ok(); im.src = u.startsWith("http") ? u : staticFile(u); imgs[k] = im;
      })));
      await document.fonts.load("700 40px Poppins");
      // eslint-disable-next-line no-new-func
      const montar = new Function("WORDS", "IMG", "OPCOES", `${codigo}\nreturn montar;`)(p.palavras || [], imgs, { legenda: p.legenda !== false });
      if (!vivo || !canvas.current) return;
      setFilme(montar(canvas.current));
      continueRender(handle);
    })().catch((e) => { console.error(e); continueRender(handle); });
    return () => { vivo = false; };
  }, []);

  useEffect(() => { if (filme) filme.renderFrame(frame); }, [filme, frame]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <canvas ref={canvas} width={width} height={height} style={{ width: "100%", height: "100%" }} />
      {p.voz ? <Audio src={staticFile(p.voz)} /> : null}
      {p.musica ? <Audio src={staticFile(p.musica)} volume={p.musicaVol ?? 0.12} loop /> : null}
      {(p.sfx || []).map(([t, nome, vol], i) => (
        <Sequence key={i} from={Math.max(0, Math.round(t * 30))} durationInFrames={90}><Audio src={staticFile(`sfx/${nome}.mp3`)} volume={vol ?? 0.4} /></Sequence>
      ))}
    </AbsoluteFill>
  );
};
