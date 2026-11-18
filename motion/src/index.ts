import React from "react";
import { Composition, registerRoot } from "remotion";
import { Video } from "./Video";
import type { Props } from "./tipos";

const EXEMPLO: Props = {
  formato: "top5", variacao: 0, gancho: "5 COISAS DO GTA VI", duracao: 20, arroba: "viralizai",
  cenas: [{ inicio: 0, fim: 20, fala: "", destaque: "GTA VI", emoji: "🎮" }], palavras: [], sfx: [],
  ranking: [{ n: 5, titulo: "Mapa gigante", t: 3, icone: "🗺️" }, { n: 4, titulo: "Polícia esperta", t: 6, icone: "🚓" },
    { n: 3, titulo: "Vice City", t: 9, icone: "🌴" }, { n: 2, titulo: "Dois protagonistas", t: 12, icone: "👫" }, { n: 1, titulo: "Online novo", t: 15, icone: "🔥" }],
};

const Raiz: React.FC = () =>
  React.createElement(Composition<Props, any>, {
    id: "Viral",
    component: Video as any,
    width: 1080,
    height: 1920,
    fps: 30,
    durationInFrames: 600,
    defaultProps: EXEMPLO,
    calculateMetadata: ({ props }: { props: Props }) => ({ durationInFrames: Math.max(60, Math.round((props.duracao + 2.5) * 30)) }),
  });

registerRoot(Raiz);
