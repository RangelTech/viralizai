// Dados que o diretor (IA) preenche. A IA nunca escreve código: só este JSON, validado no Python antes do render.
export type Palavra = { t0: number; t1: number; w: string };
export type Sfx = { t: number; tipo: "whoosh" | "pop" | "impacto" | "ding" | "riser" | "notif" | "tic" | "erro" };
export type Cena = {
  inicio: number;
  fim: number;
  fala: string;
  destaque: string; // 2 a 5 palavras grandes na tela
  emoji?: string;
  enfase?: string[]; // palavras que levam zoom-soco
  icone?: string; // emoji grande de apoio
  broll?: string; // arquivo de vídeo/imagem de apoio (opcional)
};
export type Mensagem = { de: "eu" | "outro"; texto: string; t: number };
export type ItemRanking = { n: number; titulo: string; desc?: string; icone?: string; t: number };
export type Quiz = { pergunta: string; opcoes: string[]; certa: number; t_pergunta: number; t_revela: number };
export type Versus = { a: string; b: string; ia?: string; ib?: string; itens: { rotulo: string; va: number; vb: number; t: number }[]; vencedor: "a" | "b" };
export type Noticia = { faixa: string; manchete: string; numeros?: { rotulo: string; valor: string; t: number }[] };

export type Props = {
  formato: "historia" | "conversa" | "top5" | "curiosidade" | "quiz" | "impacto" | "noticia" | "versus";
  variacao: number; // 0, 1 ou 2: cores, fontes e transições diferentes
  gancho: string;
  duracao: number; // segundos
  cenas: Cena[];
  palavras: Palavra[];
  voz?: string; // arquivo de áudio da narração (na pasta pública do render)
  sfx: Sfx[];
  arroba?: string;
  cor?: string;
  final?: string; // chamada da tela final
  conversa?: { nome: string; mensagens: Mensagem[] };
  ranking?: ItemRanking[];
  quiz?: Quiz;
  versus?: Versus;
  noticia?: Noticia;
};
