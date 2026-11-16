/* Cenas e ordem do vídeo (roteiro em docs/VIDEO.md, seção 4).
   Gramática da referência: fundo branco, palavras que entram com desfoque, objetos com mola,
   Dock como "mapa", interface isolada que se expande, chicote vertical entre capítulos. */
"use strict";

const S0 = 1280 / VW;                             // escala base da janela gravada no palco
const BASE = { x: (W - VW * S0) / 2, y: 160, s: S0 };
const CX = 960, CY = 590;                         // ponto da tela onde a câmera centraliza o foco
let F = {};                                       // fotos (montar.py passa os endereços)

/* ------------------------------------------------------------------ ícones (desenhados aqui, sem logotipos oficiais) */
const ICONES = {
  loja: `<svg viewBox="0 0 88 88"><rect width="88" height="88" rx="22" fill="#111"/><text x="44" y="58" text-anchor="middle" font-family="Inter" font-weight="700" font-size="40" fill="#fff">N</text></svg>`,
  painel: `<svg viewBox="0 0 88 88"><rect width="88" height="88" rx="22" fill="#fff"/><rect x="17" y="21" width="54" height="40" rx="7" fill="none" stroke="#111" stroke-width="5"/><path d="M33 70h22M44 61v9" stroke="#111" stroke-width="5" stroke-linecap="round"/><path d="M27 51l10-11 8 7 13-14" fill="none" stroke="#2463eb" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  mongo: `<svg viewBox="0 0 88 88"><rect width="88" height="88" rx="22" fill="#023430"/><path d="M44 14c-8 12-15 21-15 33 0 10 6 17 15 25 9-8 15-15 15-25 0-12-7-21-15-33z" fill="#00ed64"/><path d="M44 30v50" stroke="#023430" stroke-width="3" stroke-linecap="round"/></svg>`,
  supabase: `<svg viewBox="0 0 88 88"><rect width="88" height="88" rx="22" fill="#1c1c1c"/><path d="M49 14L22 52h21l-4 22 27-38H45z" fill="#3ecf8e"/></svg>`,
  redis: `<svg viewBox="0 0 88 88"><rect width="88" height="88" rx="22" fill="#dc382d"/><path d="M44 22l24 10-24 10-24-10z" fill="#fff"/><path d="M20 44l24 10 24-10M20 56l24 10 24-10" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/></svg>`,
  whats: `<svg viewBox="0 0 88 88"><rect width="88" height="88" rx="22" fill="#25d366"/><path d="M44 19a25 25 0 0 0-21.6 37.6L19 69l12.8-3.3A25 25 0 1 0 44 19z" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round"/><circle cx="34" cy="44" r="3.4" fill="#fff"/><circle cx="44" cy="44" r="3.4" fill="#fff"/><circle cx="54" cy="44" r="3.4" fill="#fff"/></svg>`,
  check: `<svg viewBox="0 0 20 20"><path d="M4.5 10.5l3.6 3.6 7.4-8" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};
const APPS = [["loja", "Loja NOMA"], ["painel", "Painel admin"], ["mongo", "MongoDB"], ["supabase", "Supabase"], ["redis", "Redis"], ["whats", "WhatsApp"]];

/* ------------------------------------------------------------------ utilidades das cenas */
const camada = () => { const c = el("div", "abs", null, $("#mg")); c.style.inset = "0"; c.style.display = "none"; return c; };
function colocar(e, x, y, ancora = "centro") {
  e.style.left = x + "px"; e.style.top = y + "px";
  const tx = ancora === "dir" ? "-100%" : ancora === "esq" ? "0" : "-50%";
  e.dataset.base = `translate(${tx}, -50%)`;
  e.style.transform = e.dataset.base;
}
function texto(pai, conteudo, cls, x, y, ancora) {
  const e = el("div", "abs " + cls, null, pai);
  colocar(e, x, y, ancora);
  e.spans = palavras(e, conteudo);
  return e;
}
// pop com mola: escala, opacidade e desfoque
function pop(e, t, t0, { dur = 0.55, de = 0.6, saida = Infinity, extra = "" } = {}) {
  const p = clamp((t - t0) / dur), q = E.inOut(prog(t, saida, 0.3));
  const k = lerp(de, 1, E.mola(p)) * (1 - 0.06 * q);
  e.style.opacity = (clamp(p * 3) * (1 - q)).toFixed(3);
  const b = 12 * (1 - clamp(p * 2.2)) + 10 * q;
  e.style.filter = b > 0.05 ? `blur(${b.toFixed(2)}px)` : "none";
  e.style.transform = `${e.dataset.base || ""} ${extra} scale(${k.toFixed(4)})`;
}
// chicote vertical: a camada sobe (ou desce) uma tela com desfoque
function chicote(c, t, t0, dur = 0.45, dir = -1) {
  const u = prog(t, t0, dur);
  if (u <= 0) return 0;
  const k = E.in(u);
  c.style.transform = `translateY(${(dir * 1150 * k).toFixed(1)}px)`;
  c.style.filter = `blur(${(Math.sin(Math.PI * Math.min(1, u * 1.2)) * 10).toFixed(2)}px)`;
  return u;
}
function entraDeBaixo(c, t, t0, dur = 0.55) {
  const u = prog(t, t0, dur);
  const k = E.out5(u);
  c.style.transform = `translateY(${((1 - k) * 1150).toFixed(1)}px)`;
  const b = (1 - clamp(u * 1.4)) * 10;
  c.style.filter = b > 0.05 ? `blur(${b.toFixed(2)}px)` : "none";
}

// cursor das cenas animadas: quadros-chave {t, x, y, forma?, clique?}
function cursorMG(kf, t, opacidade = 1) {
  const pos = (tt) => {
    if (tt <= kf[0].t) return { x: kf[0].x, y: kf[0].y };
    for (let i = 0; i < kf.length - 1; i++) {
      const a = kf[i], b = kf[i + 1];
      if (tt < b.t) { const u = E.inOut(prog(tt, a.t, b.t - a.t)); return { x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u) }; }
    }
    const z = kf[kf.length - 1]; return { x: z.x, y: z.y };
  };
  const p = pos(t);
  let forma = "seta", clique = null;
  for (const k of kf) if (k.t <= t) { if (k.forma) forma = k.forma; if (k.clique) clique = t - k.t; }
  cursor.set({ x: p.x, y: p.y, forma, clique, opacidade, rastro: [pos(t - 0.009), pos(t - 0.018), pos(t - 0.027)] });
}
const sonsCursor = (ini, kf) => kf.forEach((k) => k.clique && som(ini + k.t, "clique"));

/* ------------------------------------------------------------------ Dock */
class Dock {
  constructor(pai) {
    this.e = el("div", "dock", null, pai);
    this.itens = APPS.map(([id, nome]) => {
      const it = el("div", "dock__item", ICONES[id], this.e);
      it.nome = el("div", "dock__nome", nome, it);
      it.ponto = el("div", "dock__ponto", null, it);
      return it;
    });
    this.largura = 16 * 2 + 88 * 6 + 14 * 5;
  }
  centroIcone(i, x, y, s = 1) { return { x: x + s * (-this.largura / 2 + 16 + 44 + i * 102), y: y + s * 0 }; }
  // x, y: centro do Dock; hover: índice sob o cursor; salto: {i, t} (pulo de "abrindo")
  set({ x, y, s = 1, opacidade = 1, desfoque = 0, hover = -1, salto = null, t = 0 }) {
    this.e.style.left = x - this.largura / 2 + "px"; this.e.style.top = y - 58 + "px";
    this.e.style.transform = `scale(${s.toFixed(4)})`;
    this.e.style.transformOrigin = "50% 50%";
    this.e.style.opacity = opacidade.toFixed(3);
    this.e.style.filter = desfoque > 0.05 ? `blur(${desfoque.toFixed(2)}px)` : "none";
    this.itens.forEach((it, i) => {
      const d = hover < 0 ? 9 : Math.abs(i - hover);
      const k = d === 0 ? 1.16 : d === 1 ? 1.05 : 1;
      let pulo = 0;
      if (salto && salto.i === i) { const u = t - salto.t; if (u > 0 && u < 0.9) pulo = -Math.abs(Math.sin(u * Math.PI / 0.45)) * 26 * (1 - u / 0.9); }
      it.style.transform = `translateY(${pulo.toFixed(2)}px) scale(${k})`;
      it.nome.style.opacity = d === 0 ? 1 : 0;
      it.ponto.style.opacity = salto && salto.i === i && t > salto.t ? 1 : 0;
    });
  }
}

/* ------------------------------------------------------------------ cena: abertura ("Meet Goose") */
function cenaAbertura() {
  const c = camada();
  const cartas = F.abertura.map((src) => { const d = el("div", "cartao-foto", `<img src="${src}">`, c); d.style.left = 960 - 115 + "px"; d.style.top = 520 - 144 + "px"; return d; });
  const ordem = [0, 4, 1, 3, 2]; // a do meio por cima
  ordem.forEach((i, z) => { cartas[i].style.zIndex = z; });
  const a1 = texto(c, "Conheça", "titulo", 930, 520, "dir");
  const a2 = texto(c, "a NOMA", "titulo", 990, 520, "esq");
  const b1 = texto(c, "Uma loja de", "titulo", 640, 492, "dir");
  const b1b = texto(c, "roupas", "titulo", 640, 556, "dir");
  const b2 = texto(c, "com três bancos", "titulo", 1280, 492, "esq");
  const b2b = texto(c, "de dados", "titulo", 1280, 556, "esq");
  const sub = texto(c, "Projeto de Banco de Dados · 3ª avaliação", "sub", 960, 760, "centro");
  const dur = 8.4;
  const s = seg("abertura", dur, (tl) => {
    c.style.display = "block";
    c.style.transform = ""; c.style.filter = "none";
    const k = 1 + 0.035 * (tl / dur);
    // palavras do "Conheça a NOMA": abrem espaço quando os cartões nascem
    const abre = E.inOut(prog(tl, 0.55, 0.7));
    a1.style.left = lerp(930, 640, abre) + "px"; a2.style.left = lerp(990, 1280, abre) + "px";
    animarPalavras(a1.spans, tl, 0.08, { saida: 2.45 });
    animarPalavras(a2.spans, tl, 0.16, { saida: 2.5 });
    animarPalavras(b1.spans, tl, 2.7, { passo: 0.09 });
    animarPalavras(b1b.spans, tl, 2.95);
    animarPalavras(b2.spans, tl, 3.45, { passo: 0.09 });
    animarPalavras(b2b.spans, tl, 3.8);
    animarPalavras(sub.spans, tl, 5.0, { passo: 0.05, desfoque: 10 });
    // leque de cartões
    const leque = [[-128, -15], [-64, -7.5], [0, 0], [64, 7.5], [128, 15]];
    cartas.forEach((d, i) => {
      const meio = i === 2;
      const p = clamp((tl - (meio ? 0.6 : 0.9 + Math.abs(i - 2) * 0.06)) / 0.6);
      const ab = E.mola(clamp((tl - 0.95) / 0.75), 1.0);
      const [dx, rot] = leque[i];
      const esc = meio ? lerp(0.15, 1, E.mola(p)) : lerp(0.5, 0.92, E.out(p));
      d.style.opacity = (meio ? clamp(p * 3) : clamp(p * 2)).toFixed(3);
      d.style.transform = `translateX(${(dx * ab).toFixed(1)}px) rotate(${(rot * ab).toFixed(2)}deg) scale(${(esc * (meio ? 1.04 : 1)).toFixed(4)})`;
      const b = 10 * (1 - clamp(p * 2));
      d.style.filter = b > 0.05 ? `blur(${b.toFixed(1)}px)` : "none";
    });
    c.style.transform = `scale(${k.toFixed(4)})`; c.style.transformOrigin = "960px 540px";
    chicote(c, tl, dur - 0.45);
    if (tl > dur - 0.45) c.style.transform = c.style.transform + ` scale(${k.toFixed(4)})`;
  }, { esconder: () => { c.style.display = "none"; } });
  som(s.ini + 0.08, "tique", 0.7); som(s.ini + 0.6, "pop"); som(s.ini + 0.95, "whoosh", 0.45);
  som(s.ini + 2.7, "tique", 0.6); som(s.ini + 3.45, "tique", 0.6); som(s.ini + dur - 0.5, "whoosh");
  return s;
}

/* ------------------------------------------------------------------ cena: Dock + arquitetura */
function cenaArquitetura() {
  const c = camada();
  const dock = new Dock(c);
  const titulo1 = texto(c, "Três bancos, cada um no que faz melhor", "titulo titulo--meio", 960, 150);
  const titulo2 = texto(c, "Tudo ligado por uma API em **Flask**", "titulo titulo--meio", 960, 150);
  const dados = [
    ["mongo", "MongoDB", "Catálogo flexível: cada produto tem os seus campos", ["produtos", "GridFS", "banners"]],
    ["supabase", "Supabase", "Login do admin, auditoria e pedidos (PostgreSQL)", ["Auth", "acessos_admin", "pedidos"]],
    ["redis", "Redis", "Rápido e com validade (TTL)", ["cache", "carrinho", "vistos", "ranking"]],
  ];
  const blocos = dados.map(([id, nome, papel, chips], i) => {
    const b = el("div", "bloco", `<div class="bloco__icone">${ICONES[id]}</div><div><div class="bloco__nome">${nome}</div><div class="bloco__papel">${papel}</div><div class="chips">${chips.map((x) => `<span class="chip">${x}</span>`).join("")}</div></div>`, c);
    b.style.width = "540px"; b.querySelector(".bloco__papel").style.whiteSpace = "normal";
    colocar(b, 380 + i * 580, 520);
    b.chips = [...b.querySelectorAll(".chip")];
    return b;
  });
  const flask = el("div", "chip", "Flask · Python", c);
  flask.style.cssText += "position:absolute;font-size:24px;padding:14px 22px;border-radius:16px;background:#111;color:#fff;";
  colocar(flask, 960, 286);
  const svg = el("div", "linhas", `<svg width="1920" height="1080"><g fill="none" stroke="#c9c9cf" stroke-width="2.5" stroke-linecap="round">
    <path id="l0" d="M960 312 C 960 360, 380 340, 380 388"/><path id="l1" d="M960 312 L 960 388"/><path id="l2" d="M960 312 C 960 360, 1540 340, 1540 388"/></g>
    <g fill="#111"><circle id="p0" r="6"/><circle id="p1" r="6"/><circle id="p2" r="6"/></g></svg>`, c);
  const linhas = [0, 1, 2].map((i) => svg.querySelector("#l" + i));
  const pontos = [0, 1, 2].map((i) => svg.querySelector("#p" + i));
  const comp = linhas.map((l) => l.getTotalLength());

  const dur = 27;
  const ic = (i, s = 1, y = 900) => dock.centroIcone(i, 960, y, s);
  const kf = [
    { t: 0.0, x: 2010, y: 760 }, { t: 1.2, x: 1260, y: 700 },
    { t: 2.5, x: ic(2).x, y: 905 }, { t: 2.75, x: ic(2).x, y: 905, forma: "mao", clique: true },
    { t: 6.4, x: ic(3).x + 4, y: 908 }, { t: 6.65, x: ic(3).x + 4, y: 908, forma: "mao", clique: true },
    { t: 10.6, x: ic(4).x, y: 906 }, { t: 10.85, x: ic(4).x, y: 906, forma: "mao", clique: true },
    { t: 13.8, x: 1500, y: 990, forma: "seta" }, { t: 26, x: 1560, y: 1010 },
  ];
  const cliques = [2.75, 6.65, 10.85];
  const s = seg("arquitetura", dur, (tl) => {
    c.style.display = "block"; c.style.transform = ""; c.style.filter = "none";
    entraDeBaixo(c, tl, 0);
    const desce = E.inOut(prog(tl, 1.3, 0.9));
    const y = lerp(560, 900, desce);
    let hover = -1;
    const cx = cursor_x(kf, tl);
    const sobreDock = tl > 2.2 && tl < 11.6;
    if (sobreDock) hover = Math.round((cx - (960 - dock.largura / 2 + 60)) / 102);
    dock.set({ x: 960, y, hover: sobreDock ? hover : -1, t: tl, salto: null });
    animarPalavras(titulo1.spans, tl, 0.9, { saida: 14.6 });
    animarPalavras(titulo2.spans, tl, 15.0, { saida: dur - 0.9 });
    blocos.forEach((b, i) => {
      pop(b, tl, cliques[i] + 0.1, { dur: 0.6 });
      b.chips.forEach((ch, j) => {
        const p = E.out(prog(tl, cliques[i] + 0.7 + j * 0.16, 0.3));
        ch.style.opacity = p.toFixed(3); ch.style.filter = p < 1 ? `blur(${(8 * (1 - p)).toFixed(2)}px)` : "none";
        ch.style.transform = `translateY(${(6 * (1 - p)).toFixed(1)}px)`;
      });
    });
    pop(flask, tl, 15.4, { dur: 0.5 });
    linhas.forEach((l, i) => {
      const p = E.inOut(prog(tl, 15.8 + i * 0.15, 0.9));
      l.style.strokeDasharray = comp[i]; l.style.strokeDashoffset = (comp[i] * (1 - p)).toFixed(1);
      const viagem = ((tl - 17.2 - i * 0.5) % 1.6) / 1.6;
      if (tl > 17.2 + i * 0.5 && tl < dur - 1) {
        const pt = l.getPointAtLength(comp[i] * E.inOut(viagem));
        pontos[i].setAttribute("cx", pt.x); pontos[i].setAttribute("cy", pt.y); pontos[i].style.opacity = Math.sin(Math.PI * viagem).toFixed(3);
      } else pontos[i].style.opacity = 0;
    });
    cursorMG(kf, tl, 1 - prog(tl, 13.0, 1.2));
    chicote(c, tl, dur - 0.45);
  }, { sobrepor: 0.45, esconder: () => { c.style.display = "none"; } });
  sonsCursor(s.ini, kf);
  cliques.forEach((t) => som(s.ini + t + 0.12, "pop"));
  som(s.ini + 0.9, "tique", 0.6); som(s.ini + 15.0, "tique", 0.6); som(s.ini + 15.8, "whoosh", 0.35);
  som(s.ini + dur - 0.5, "whoosh");
  return s;
}
function cursor_x(kf, t) { // posição x do cursor de quadros-chave (para o hover do Dock)
  for (let i = 0; i < kf.length - 1; i++) if (t < kf[i + 1].t) return lerp(kf[i].x, kf[i + 1].x, E.inOut(prog(t, kf[i].t, kf[i + 1].t - kf[i].t)));
  return kf[kf.length - 1].x;
}

/* ------------------------------------------------------------------ cena: título de capítulo + Dock */
// Termina com o clique num app do Dock; o trecho gravado seguinte nasce do ícone.
function capitulo(num, titulo, app, { dur = 4.2, sub = null } = {}) {
  const c = camada();
  const idx = APPS.findIndex(([id]) => id === app);
  const ind = texto(c, num, "indice", 960, 368);
  const tit = texto(c, titulo, "titulo", 960, 430);
  const st = sub ? texto(c, sub, "sub", 960, 494) : null;
  const dock = new Dock(c);
  const alvo = dock.centroIcone(idx, 960, 700);
  const tClique = 2.6;
  const kf = [{ t: 0.9, x: 2010, y: 880 }, { t: tClique - 0.3, x: alvo.x + 3, y: alvo.y + 6 }, { t: tClique, x: alvo.x + 3, y: alvo.y + 6, forma: "mao", clique: true }, { t: dur, x: alvo.x + 3, y: alvo.y + 6, forma: "mao" }];
  const s = seg("cap" + num, dur, (tl) => {
    c.style.display = "block"; c.style.transform = ""; c.style.filter = "none";
    entraDeBaixo(c, tl, 0);
    animarPalavras(ind.spans, tl, 0.2, { saida: tClique + 0.35 });
    animarPalavras(tit.spans, tl, 0.3, { passo: 0.08, saida: tClique + 0.35 });
    if (st) animarPalavras(st.spans, tl, 0.7, { passo: 0.05, desfoque: 10, saida: tClique + 0.35 });
    const sai = E.inOut(prog(tl, tClique + 0.35, 0.6));
    const hover = tl > tClique - 0.6 ? idx : -1;
    dock.set({ x: 960, y: 700, s: 1 - 0.04 * sai, opacidade: 1 - sai, desfoque: 8 * sai, hover, salto: { i: idx, t: tClique + 0.05 }, t: tl });
    cursorMG(kf, tl, 1 - prog(tl, tClique + 0.3, 0.35));
  }, { sobrepor: 0.45, esconder: () => { c.style.display = "none"; } });
  sonsCursor(s.ini, kf);
  som(s.ini + 0.25, "tique", 0.6);
  s.icone = alvo; s.tClique = tClique;
  return s;
}

/* ------------------------------------------------------------------ trecho gravado (janela flutuante + câmera + cursor) */
const ID = { k: 1, tx: 0, ty: 0 };
const compor = (a, b) => ({ k: a.k * b.k, tx: a.k * b.tx + a.tx, ty: a.k * b.ty + a.ty });
const aplicarT = (T, p) => ({ x: T.tx + T.k * p.x, y: T.ty + T.k * p.y });
const camParaT = (c) => ({ k: c.z, tx: CX - c.cx * c.z, ty: CY - c.cy * c.z });
const CAM0 = { z: 1, cx: CX, cy: CY };

function alvoCamera(f, livre) {
  if (!f || !f.caixa) return CAM0;
  const [bx, by, bw, bh] = f.caixa;
  const wx = BASE.x + bx * S0, wy = BASE.y + (BARRA + by) * S0, ww = bw * S0, wh = bh * S0;
  const z = clamp(Math.min(1780 / ww, 860 / wh), 1, f.zoom_max || 2);
  let cx = wx + ww / 2, cy = wy + wh / 2;
  if (!livre && z > 1) {
    const L = BASE.x, R = BASE.x + VW * S0, T = BASE.y, B = BASE.y + (VH + BARRA) * S0;
    // a janela ampliada não pode mostrar menos do que cobria antes (sem "buracos" brancos)
    let tx = CX - cx * z, ty = CY - cy * z;
    tx = clamp(tx, R * (1 - z), L * (1 - z)); ty = clamp(ty, B * (1 - z), T * (1 - z));
    cx = (CX - tx) / z; cy = (CY - ty) / z;
  }
  if (z === 1 && !livre) return CAM0;
  return { z, cx, cy };
}
function misturaCam(a, b, u) {
  return { z: Math.exp(lerp(Math.log(a.z), Math.log(b.z), u)), cx: lerp(a.cx, b.cx, u), cy: lerp(a.cy, b.cy, u) };
}

function recorteDe(area) { // área da página -> recorte (inset) na janela
  const [x, y, w, h] = area;
  return [BARRA + y, VW - (x + w), (VH + BARRA) - (BARRA + y + h), x];
}

function gravacao(nome, o) {
  const aba = o.aba, j = janelas[aba];
  const mapa = new Mapa(o.de, o.ate, o.rapidos || []);
  const isolar = o.isolar || [];
  const isolado = (c) => isolar.some((x) => c >= (x.entra ?? x.de) - 0.6 && c <= x.ate + 0.9);
  // câmera: estado inicial = último foco antes do trecho; focos logo no início valem na hora
  const focos = D.abas[aba].focos;
  let inicial = null;
  for (const f of focos) if (f.t <= o.de + 0.6) inicial = f;
  const trans = [];
  let atual = alvoCamera(inicial, inicial && isolado(inicial.t));
  const cam0 = atual;
  for (const f of focos) {
    if (f.t <= o.de + 0.6 || f.t > o.ate) continue;
    const t0 = Math.max(0, mapa.loc(f.t) - 0.12);
    trans.push({ t0, para: alvoCamera(f, isolado(f.t)) });
  }
  const DUR_CAM = 0.95;
  const camEm = (tl) => {
    let c = cam0;
    for (let i = 0; i < trans.length; i++) {
      const tr = trans[i];
      if (tl < tr.t0) break;
      c = misturaCam(c, tr.para, E.inOut(prog(tl, tr.t0, DUR_CAM)));
    }
    return c;
  };
  const recorteEm = (capT) => {
    for (const x of isolar) {
      const a = recorteDe(areaEm(aba, x.area, capT)), zero = [0, 0, 0, 0];
      if (x.entra != null && capT >= x.entra && capT < x.de) { const u = E.inOut(prog(capT, x.entra, x.de - x.entra)); return { r: a.map((v, i) => lerp(zero[i], v, u)), raio: lerp(16, 12, u), iso: u }; }
      if (capT >= x.de - 1e-6 && capT <= x.ate) return { r: a, raio: 12, iso: 1 };
      if (capT > x.ate && capT < x.ate + 0.9) { const u = E.inOut(prog(capT, x.ate, 0.9)); return { r: a.map((v, i) => lerp(v, zero[i], u)), raio: lerp(12, 16, u), iso: 1 - u }; }
    }
    return { r: null, raio: 16, iso: 0 };
  };
  const ent = o.entrada || { tipo: "sobe" }, sai = o.saida || { tipo: "nada" };
  const DUR_E = ent.dur || (ent.tipo === "icone" ? 0.75 : 0.6), DUR_S = sai.dur || 0.45;
  const dur = mapa.dur;
  const s = seg(nome, dur, (tl) => {
    const capT = mapa.cap(tl);
    // entrada/saída como transformação do palco
    let T = ID, op = 1, blur = 0;
    if (ent.tipo === "sobe" && tl < DUR_E) { const u = prog(tl, 0, DUR_E); T = { k: 1, tx: 0, ty: (1 - E.out5(u)) * 1150 }; blur = (1 - clamp(u * 1.4)) * 10; }
    if (ent.tipo === "icone" && tl < DUR_E) {
      const u = E.out5(prog(tl, 0, DUR_E)), P = ent.ponto, C = { x: CX, y: CY };
      const k = lerp(0.06, 1, u);
      T = { k, tx: lerp(P.x, C.x, u) - k * C.x, ty: lerp(P.y, C.y, u) - k * C.y };
      op = clamp(prog(tl, 0, DUR_E) * 4); blur = (1 - u) * 6;
    }
    if (sai.tipo === "sobe" && tl > dur - DUR_S) { const u = prog(tl, dur - DUR_S, DUR_S); T = { k: 1, tx: 0, ty: -E.in(u) * 1150 }; blur = Math.sin(Math.PI * Math.min(1, u * 1.2)) * 10; }
    if (sai.tipo === "some" && tl > dur - DUR_S) { const u = E.inOut(prog(tl, dur - DUR_S, DUR_S)); op = 1 - u; blur = 10 * u; T = { k: 1 - 0.04 * u, tx: CX * 0.04 * u, ty: CY * 0.04 * u }; }
    if (o.empurrar) { const k = 1 + o.empurrar * (tl / dur); T = compor(T, { k, tx: CX * (1 - k), ty: CY * (1 - k) }); }
    const cam = camEm(tl);
    const MT = compor(T, camParaT(cam));
    const mundo = $("#mundo");
    mundo.style.transform = `translate(${MT.tx.toFixed(2)}px, ${MT.ty.toFixed(2)}px) scale(${MT.k.toFixed(5)})`;
    mundo.style.filter = blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : "none";
    mundo.style.opacity = op.toFixed(3);
    const rec = recorteEm(capT);
    const est = { x: BASE.x, y: BASE.y, s: S0 };
    j.set({ ...est, capT, recorte: rec.r, raio: rec.raio });
    if (o.cortina) desenharCortina(capT, o.cortina);
    // cursor
    const m = mouseEm(aba, capT);
    const pt = (q) => aplicarT(MT, { x: est.x + q.x * est.s, y: est.y + (BARRA + q.y) * est.s });
    const v = mapa.vel(tl);
    const rastro = [1, 2, 3].map((k) => pt(mouseEm(aba, capT - k * 0.009 * v)));
    const p = pt(m);
    cursor.set({ x: p.x, y: p.y, forma: formaEm(aba, capT), clique: cliqueEm(aba, capT), rastro, escala: 1 + 0.22 * (cam.z - 1), opacidade: op * (o.semCursor ? 0 : 1) });
    legenda.pilula = rec.iso > 0.5 ? 0 : clamp((cam.z - 1.02) / 0.12);
    if (o.extra) o.extra(tl, capT, s);
  }, { sobrepor: o.sobrepor || 0, esconder: () => { if (o.cortina) $("#cortina").style.transform = "translateX(100%)"; } });
  s.mapa = mapa;
  s.emT = (capT) => s.ini + mapa.loc(capT);
  // sons: cliques e teclas da gravação
  const a = D.abas[aba];
  a.ct.forEach((t) => { if (t >= o.de && t <= o.ate) som(s.emT(t), "clique"); });
  let pular = false;
  a.kt.forEach((t) => {
    if (t < o.de || t > o.ate) return;
    const v = mapa.vel(mapa.loc(t));
    if (v > 1.5) { pular = !pular; if (pular) return; }
    som(s.emT(t), "tecla");
  });
  if (ent.tipo === "sobe") som(s.ini, "whoosh", 0.8);
  if (ent.tipo === "icone") som(s.ini + 0.05, "whoosh", 0.55);
  if (sai.tipo === "sobe") som(s.fim - 0.5, "whoosh");
  (o.legendas || []).forEach(([capT, txt, d], i, arr) => {
    const t0 = s.emT(capT);
    const prox = arr[i + 1] ? s.emT(arr[i + 1][0]) - 0.15 : s.fim - 0.3;
    legenda.add(t0, d ? Math.min(prox, t0 + d) : prox, txt);
  });
  return s;
}

function desenharCortina(capT, c) {
  const u = E.out5(prog(capT, c.de, 0.75));
  const v = c.ate != null ? E.inOut(prog(capT, c.ate, 0.6)) : 0;
  $("#cortina").style.transform = `translateX(${((1 - u) * 100 + v * 100).toFixed(2)}%)`;
}

/* ------------------------------------------------------------------ cartões flutuantes (o que aconteceu nos bancos) */
function avisos(lista) {
  // lista: [{t0, t1, x, y, icone, titulo, linha}]  (tempos no vídeo)
  const c = el("div", "abs", null, $("#sobre")); c.style.inset = "0";
  const cards = lista.map((a) => {
    const e = el("div", "aviso-card", `${ICONES[a.icone]}<div><b>${esc(a.titulo)}</b><span>${esc(a.linha)}</span></div>`, c);
    colocar(e, a.x, a.y, a.ancora || "esq");
    som(a.t0, "pop");
    return e;
  });
  LINHA.push({
    nome: "avisos", ini: Math.min(...lista.map((a) => a.t0)), fim: Math.max(...lista.map((a) => a.t1)) + 0.4,
    desenhar: (tl, t) => { c.style.display = "block"; lista.forEach((a, i) => pop(cards[i], t, a.t0, { dur: 0.55, saida: a.t1 })); },
    esconder: () => { c.style.display = "none"; },
  });
}

/* ------------------------------------------------------------------ tela dividida: painel × loja */
function telaDividida(nome, { de, ate, legendas = [] }) {
  const mapa = new Mapa(de, ate);
  const ja = janelas.admin, jl = janelas.loja;
  const sEsq = { x: 70, y: 300, s: 0.6 }, sDir = { x: 1850 - VW * 0.6, y: 300, s: 0.6 };
  const fimLayout = { x: BASE.x, y: BASE.y, s: S0 };
  const dur = mapa.dur;
  const tJunta = 1.0;      // o painel encolhe para a esquerda e a loja aparece
  const tSolta = dur - 1.1; // a loja ocupa a tela
  const s = seg(nome, dur, (tl) => {
    const capT = mapa.cap(tl);
    $("#mundo").style.transform = "none"; $("#mundo").style.filter = "none"; $("#mundo").style.opacity = 1;
    const u = E.inOut(prog(tl, 0, tJunta)), v = E.inOut(prog(tl, tSolta, 1.1));
    const ea = { x: lerp(BASE.x, sEsq.x, u) - v * 900, y: lerp(BASE.y, sEsq.y, u), s: lerp(S0, sEsq.s, u) };
    ja.set({ ...ea, capT, opacidade: 1 - v, desfoque: 8 * v });
    const el2 = { x: lerp(sDir.x + 700 * (1 - u), fimLayout.x, v), y: lerp(sDir.y, fimLayout.y, v), s: lerp(sDir.s, fimLayout.s, v) };
    jl.set({ ...el2, capT, opacidade: clamp(u * 1.5) });
    const ativo = tl < tSolta - 0.3 && tl > tJunta + 0.6 ? "loja" : null;
    if (ativo) {
      const m = mouseEm("loja", capT), p = { x: el2.x + m.x * el2.s, y: el2.y + (BARRA + m.y) * el2.s };
      cursor.set({ x: p.x, y: p.y, forma: formaEm("loja", capT), clique: cliqueEm("loja", capT), opacidade: clamp(prog(tl, tJunta + 0.6, 0.3)) * (1 - prog(tl, tSolta - 0.6, 0.3)) });
    }
  });
  s.emT = (capT) => s.ini + mapa.loc(capT);
  som(s.ini + 0.1, "whoosh", 0.5); som(s.fim - 1.1, "whoosh", 0.4);
  legendas.forEach(([capT, txt], i, arr) => legenda.add(s.emT(capT), arr[i + 1] ? s.emT(arr[i + 1][0]) - 0.15 : s.fim - 0.25, txt));
  return s;
}

/* ------------------------------------------------------------------ cena: o celular com a mensagem do WhatsApp */
function cenaCelular() {
  const c = camada();
  const msg = (D.whats && D.whats.texto) || "Olá, gostaria de pedir: …";
  const codigo = (msg.match(/Pedido:\s*(\S+)/) || [])[1] || "";
  const total = (msg.match(/Total:\s*(R\$\s?[\d.,]+)/) || [])[1] || "";
  const cel = el("div", "celular", `<div class="celular__tela"><div class="celular__ilha"></div><div class="celular__status"><span>9:41</span><span>●●● ᯤ ▮</span></div>
    <div class="zap__topo"><div class="zap__avatar">N</div><div class="zap__nome">NOMA<small>conta comercial</small></div></div>
    <div class="zap__corpo"><div class="zap__balao">${esc(msg)}<small>agora ✓✓</small></div></div><div class="zap__campo"></div></div>`, c);
  cel.style.left = 960 - 215 + "px"; cel.style.top = 100 + "px";
  const balao = cel.querySelector(".zap__balao");
  const e1 = texto(c, "O pedido chega", "titulo titulo--meio", 690, 470, "dir");
  const e2 = texto(c, "pronto no WhatsApp", "titulo titulo--meio", 690, 530, "dir");
  const d1 = texto(c, codigo ? `Pedido ${codigo}` : "", "titulo titulo--meio", 1230, 470, "esq");
  const d2 = texto(c, total ? `Total ${total}` : "", "titulo titulo--meio", 1230, 530, "esq");
  [e1, e2, d1, d2].forEach((x) => { x.style.color = "#fff"; });
  const selo = texto(c, "Ilustração com a mensagem real do pedido gravado", "selo-ilustra", 960, 1030);
  selo.style.color = "rgba(255,255,255,.75)";
  const dur = 9.6;
  const s = seg("celular", dur, (tl) => {
    c.style.display = "block"; c.style.transform = ""; c.style.filter = "none";
    $("#cortina").style.transform = "translateX(0)";
    const u = E.out5(prog(tl, 0.1, 0.8));
    cel.style.transform = `translateY(${((1 - u) * 1000).toFixed(1)}px)`;
    const p = clamp((tl - 1.3) / 0.5);
    balao.style.opacity = clamp(p * 3).toFixed(3);
    balao.style.transform = `scale(${lerp(0.7, 1, E.mola(p)).toFixed(4)})`;
    balao.style.filter = p < 0.5 ? `blur(${(10 * (1 - p * 2)).toFixed(2)}px)` : "none";
    animarPalavras(e1.spans, tl, 2.2); animarPalavras(e2.spans, tl, 2.5);
    animarPalavras(d1.spans, tl, 3.1); animarPalavras(d2.spans, tl, 3.4);
    animarPalavras(selo.spans, tl, 4.0, { passo: 0.03, desfoque: 8 });
    c.style.transform = `scale(${(1 + 0.03 * tl / dur).toFixed(4)})`; c.style.transformOrigin = "960px 540px";
    if (chicote(c, tl, dur - 0.45) > 0) $("#cortina").style.transform = `translateY(${(-1150 * E.in(prog(tl, dur - 0.45, 0.45))).toFixed(1)}px)`;
  }, { sobrepor: 0.2, esconder: () => { c.style.display = "none"; } });
  som(s.ini + 0.15, "whoosh", 0.6); som(s.ini + 1.35, "pop", 1.1); som(s.ini + 2.2, "tique", 0.5); som(s.fim - 0.5, "whoosh");
  return s;
}

/* ------------------------------------------------------------------ cena: o que cada banco fez */
function cenaResumo() {
  const c = camada();
  const tit = texto(c, "O que cada banco fez neste vídeo", "titulo titulo--meio", 960, 190);
  const cols = [
    ["mongo", "MongoDB", ["`insert` do Suéter em `produtos`", "2 fotos no `GridFS` (WebP)", "`find` no catálogo e na busca", "`$inc` de vendidos e estoque"]],
    ["supabase", "Supabase", ["Auth conferiu o login", "2 linhas em `acessos_admin`", "`registrar_pedido()` numa transação", "`vw_resumo_vendas` no dashboard"]],
    ["redis", "Redis", ["`INCR` falhas de login (TTL)", "`INCR` versão do cache", "`HINCRBY` no carrinho", "`LPUSH` vistos · `ZINCRBY` ranking"]],
  ];
  const blocos = cols.map(([id, nome, itens], i) => {
    const x = 380 + i * 580;
    const cab = el("div", "bloco", `<div class="bloco__icone">${ICONES[id]}</div><div class="bloco__nome">${nome}</div>`, c);
    cab.style.width = "520px"; cab.style.padding = "20px 24px";
    colocar(cab, x, 340);
    const linhas = itens.map((txt, j) => {
      const e = el("div", "abs", null, c);
      e.style.cssText += "font:500 25px/1.3 Inter,sans-serif;white-space:nowrap;display:flex;align-items:center;gap:14px;";
      colocar(e, x - 255, 478 + j * 104, "esq");
      e.innerHTML = `<span class="check" style="margin:0;width:32px;height:32px;flex:none">${ICONES.check}</span><span class="txt resumo-txt"></span>`;
      e.spans = palavras(e.querySelector(".txt"), txt);
      e.chk = e.querySelector(".check");
      return e;
    });
    return { cab, linhas };
  });
  const dur = 17;
  const s = seg("resumo", dur, (tl) => {
    c.style.display = "block"; c.style.transform = ""; c.style.filter = "none";
    entraDeBaixo(c, tl, 0);
    animarPalavras(tit.spans, tl, 0.5);
    blocos.forEach((b, i) => {
      pop(b.cab, tl, 1.0 + i * 0.25, { dur: 0.55 });
      b.linhas.forEach((e, j) => {
        const t0 = 2.0 + j * 2.6 + i * 0.7;
        pop(e.chk, tl, t0, { dur: 0.45, de: 0.2 });
        animarPalavras(e.spans, tl, t0 + 0.1, { passo: 0.05 });
      });
    });
    chicote(c, tl, dur - 0.45);
  }, { sobrepor: 0.45, esconder: () => { c.style.display = "none"; } });
  som(s.ini + 0.15, "whoosh", 0.7); som(s.ini + 0.5, "tique", 0.6);
  [0, 1, 2].forEach((i) => som(s.ini + 1.0 + i * 0.25, "pop", 0.7));
  for (let j = 0; j < 4; j++) for (let i = 0; i < 3; i++) som(s.ini + 2.0 + j * 2.6 + i * 0.7, "tique", 0.8);
  som(s.fim - 0.5, "whoosh");
  return s;
}

/* ------------------------------------------------------------------ cena: encerramento */
function cenaFim() {
  const c = camada();
  const frases = ["Login seguro pelo Supabase.", "Cadastro flexível no MongoDB.", "Catálogo atualizado na hora.", "Pedido pronto no WhatsApp."];
  const linhas = frases.map((f, i) => {
    const e = el("div", "abs titulo titulo--meio", null, c);
    colocar(e, 690, 330 + i * 110, "esq");
    e.innerHTML = `<span class="check">${ICONES.check}</span><span class="txt"></span>`;
    e.spans = palavras(e.querySelector(".txt"), f);
    e.chk = e.querySelector(".check");
    return e;
  });
  const cartas = F.fim.map((src) => { const d = el("div", "cartao-foto", `<img src="${src}">`, c); d.style.left = 960 - 115 + "px"; d.style.top = 470 - 144 + "px"; return d; });
  [0, 4, 1, 3, 2].forEach((i, z) => { cartas[i].style.zIndex = z; });
  const logo = texto(c, "N O M A", "titulo", 960, 720);
  logo.style.letterSpacing = ".2em"; logo.style.fontWeight = "600";
  const sub = texto(c, "MongoDB · Supabase · Redis", "sub", 960, 790);
  const sub2 = texto(c, "Projeto de Banco de Dados · 3ª avaliação", "sub", 960, 836);
  const dur = 13;
  const s = seg("fim", dur, (tl) => {
    c.style.display = "block"; c.style.transform = ""; c.style.filter = "none";
    entraDeBaixo(c, tl, 0);
    linhas.forEach((e, i) => {
      const t0 = 0.6 + i * 0.75;
      animarPalavras(e.spans, tl, t0 + 0.12, { saida: 5.6 + i * 0.08 });
      pop(e.chk, tl, t0, { dur: 0.45, de: 0.2, saida: 5.6 + i * 0.08 });
    });
    const leque = [[-128, -15], [-64, -7.5], [0, 0], [64, 7.5], [128, 15]];
    cartas.forEach((d, i) => {
      const p = clamp((tl - 6.3 - Math.abs(i - 2) * 0.07) / 0.6);
      const ab = E.mola(clamp((tl - 6.6) / 0.8), 1.0);
      const [dx, rot] = leque[i];
      d.style.opacity = clamp(p * 2.5).toFixed(3);
      d.style.transform = `translateX(${(dx * ab).toFixed(1)}px) rotate(${(rot * ab).toFixed(2)}deg) scale(${lerp(0.4, i === 2 ? 0.98 : 0.9, E.mola(p)).toFixed(4)})`;
      d.style.filter = p < 0.5 ? `blur(${(10 * (1 - p * 2)).toFixed(1)}px)` : "none";
    });
    animarPalavras(logo.spans, tl, 7.2, { passo: 0.08 });
    animarPalavras(sub.spans, tl, 8.0, { passo: 0.06, desfoque: 10 });
    animarPalavras(sub2.spans, tl, 8.5, { passo: 0.05, desfoque: 10 });
    const fade = E.inOut(prog(tl, dur - 1.0, 0.9));
    c.style.opacity = (1 - fade).toFixed(3);
    c.style.transform = `scale(${(1 + 0.025 * tl / dur).toFixed(4)})`; c.style.transformOrigin = "960px 540px";
  }, { sobrepor: 0.45, esconder: () => { c.style.display = "none"; } });
  frases.forEach((_, i) => som(s.ini + 0.6 + i * 0.75, "pop", 0.8));
  som(s.ini + 6.3, "whoosh", 0.4); som(s.ini + 7.2, "tique", 0.6);
  return s;
}

/* ------------------------------------------------------------------ ordem do vídeo */
function montarLinha() {
  janelas = { admin: new Janela("admin"), loja: new Janela("loja") };
  const teste = D.cap.teste;

  cenaAbertura();
  cenaArquitetura();

  // ---------------------------------------------------------------- 01 · login
  let cap = capitulo("01", "Login do administrador", "painel", { sub: "Supabase Auth + Redis contra força bruta" });
  const login = gravacao("login", {
    aba: "admin", de: M("login_inicio"), ate: M("dashboard_fim"), sobrepor: cap.dur - cap.tClique - 0.05,
    entrada: { tipo: "icone", ponto: cap.icone }, saida: { tipo: "sobe" },
    isolar: [{ area: "form_login", de: M("login_inicio"), ate: M("login_expandir") }],
    rapidos: [[M("login_entrar_errado", 0.5), M("login_erro", -0.1), 2], [M("login_entrar_certo", 0.6), M("dashboard", -0.2), 2.5]],
    legendas: [
      [M("login_inicio", 0.2), "Área restrita do painel"],
      [M("login_senha_errada"), "Primeiro, uma senha **errada**…"],
      [M("login_erro"), "Tentativa negada: gravada no Supabase e contada no Redis"],
      [M("login_senha_certa", -0.6), "Agora com a senha certa"],
      [M("dashboard", 0.3), "Supabase Auth confirmou: sessão nova e proteção CSRF"],
      [M("dashboard", 2.0), "Status e latência dos três bancos, ao vivo"],
      [M("dashboard", 5.0), "Totais vindos do MongoDB, do Supabase e do Redis"],
      [M("dashboard_fim", -4.4), "Auditoria: cada tentativa fica em `acessos_admin`"],
    ],
  });

  // ---------------------------------------------------------------- 02 · cadastro
  cap = capitulo("02", "Cadastro de um produto", "painel", { sub: "Documento flexível no MongoDB" });
  const cad = gravacao("cadastro", {
    aba: "admin", de: M("dashboard_fim", 0.2), ate: M("cadastro_fim", 0.4), sobrepor: cap.dur - cap.tClique - 0.05,
    entrada: { tipo: "icone", ponto: cap.icone }, saida: { tipo: "some", dur: 0.6 },
    rapidos: [[M("salvar", 0.6), M("produto_salvo", -0.1), 2.2]],
    legendas: [
      [M("dashboard_fim", 0.6), "Os produtos ficam na coleção `produtos` do MongoDB"],
      [M("form_inicio", 0.2), "Novo produto: Suéter Tricô Vinho"],
      [FO("admin", "form_preco"), "Preço, promoção e estoque"],
      [FO("admin", "form_atributos"), "Atributos livres: cada produto tem os seus campos"],
      [FO("admin", "form_fotos"), "As fotos vão para o **GridFS**, convertidas em WebP"],
      [FO("admin", "form_cores"), "Cor, tamanhos e vitrine"],
      [M("salvar", -3.2), "Prévia do card como vai aparecer na loja"],
      [M("produto_salvo"), "Salvo no MongoDB, e o cache do Redis foi invalidado"],
      [M("documento"), "O documento real, como ficou gravado no MongoDB"],
    ],
  });
  avisos([
    { t0: cad.emT(M("produto_salvo", 0.5)), t1: cad.emT(M("produto_salvo", 4.6)), x: 70, y: 690, icone: "mongo", titulo: "MongoDB", linha: "insert_one → produtos" },
    { t0: cad.emT(M("produto_salvo", 1.0)), t1: cad.emT(M("produto_salvo", 4.8)), x: 70, y: 810, icone: "redis", titulo: "Redis", linha: "INCR noma:cache:versao" },
  ]);

  // ---------------------------------------------------------------- 03 · catálogo
  cap = capitulo("03", "O catálogo do cliente, na hora", "loja", { sub: "Sem reiniciar nada" });
  const div = telaDividida("dividida", {
    de: M("loja_antes", -1.3), ate: M("loja_produto_visivel", 2.2),
    legendas: [[M("loja_antes", -1.1), "À esquerda o painel, à direita a loja do cliente"], [M("loja_recarregar", 0.1), "O cliente abre Novidades: o Suéter já está lá, em primeiro"]],
  });
  div.ini = Math.max(0, cap.fim - (cap.dur - cap.tClique - 0.05)); div.fim = div.ini + div.dur; fimLinha = div.fim;
  gravacao("catalogo", {
    aba: "loja", de: M("loja_produto_visivel", 2.2), ate: M("loja_fim"), entrada: { tipo: "nada" }, saida: { tipo: "sobe" },
    legendas: [
      [M("loja_produto_visivel", 2.2), "Passando o mouse, a segunda foto aparece"],
      [M("busca"), "A busca ao vivo também já encontra o produto"],
      [M("pagina_produto", 0.2), "Página do produto lida do MongoDB, com cache no Redis"],
      [M("loja_fim", -3.4), "Os atributos livres aparecem em Características"],
    ],
  });

  // ---------------------------------------------------------------- 04 · compra
  cap = capitulo("04", "Simulação de compra", "loja", { sub: "Carrinho no Redis, pedido no Supabase, mensagem no WhatsApp" });
  const compra = gravacao("compra", {
    aba: "loja", de: M("compra_inicio"), ate: M("compra_fim"), sobrepor: cap.dur - cap.tClique - 0.05,
    entrada: { tipo: "icone", ponto: cap.icone }, saida: { tipo: "nada" },
    isolar: [{ area: "botao_finalizar", entra: M("finalizar_clique", -1.5), de: M("finalizar_clique", -0.7), ate: M("finalizar_clique", 0.55) }],
    cortina: { de: M("finalizar_clique", 0.35) },
    rapidos: [[M("enviar_pedido", 0.5), M("pedido_ok", -0.1), 2], [M("pedido_ok", 2.4), M("whatsapp", -0.1), 2.5]],
    legendas: [
      [M("compra_inicio", 0.2), "Tamanho M, duas unidades"],
      [M("adicionou_1", 0.3), "O carrinho fica no Redis: um HASH por visitante"],
      [M("acessorios"), "Mais um item: o cinto de couro"],
      [M("vistos"), "Vistos recentemente: uma LIST no Redis"],
      [FO("loja", "compra_cinto"), "Cinto no carrinho também"],
      [M("carrinho_qtd"), "Quantidade e total mudam na hora"],
      [M("finalizar_clique", -1.4), "Finalizar compra"],
      [M("finalizar_modal", 0.2), "Nome, observação e prévia da mensagem"],
      [M("enviar_pedido", -0.3), "Enviar: o pedido é gravado no Supabase"],
      [M("pedido_ok", 0.2), "Pedido registrado com código"],
      [M("whatsapp", 0.1), "Redirecionado ao WhatsApp com a mensagem pronta"],
    ],
  });
  som(compra.emT(M("pedido_ok", 0.05)), "sucesso");
  cenaCelular();

  // ---------------------------------------------------------------- 05 · pedido no painel
  cap = capitulo("05", "O pedido no painel", "painel", { sub: "Gravado no PostgreSQL do Supabase" });
  gravacao("pedidos", {
    aba: "admin", de: M("pedidos_inicio"), ate: M("fim"), sobrepor: cap.dur - cap.tClique - 0.05,
    entrada: { tipo: "icone", ponto: cap.icone }, saida: { tipo: "sobe" },
    legendas: [
      [M("pedidos_inicio", 0.3), "`registrar_pedido()` grava pedido e itens numa transação"],
      [M("dashboard_final", -3.0), "Itens, total e a mensagem enviada ao WhatsApp"],
      [M("dashboard_final", 1.0), "O dashboard já conta o pedido novo"],
      [M("redis_final"), "Mais vistos: um ranking (ZSET) no Redis"],
      [FO("admin", "comandos_redis", -0.2), "Comandos do Redis: acerto (HIT) e falta (MISS) do cache"],
    ],
  });
  cenaResumo();
  cenaFim();
}

function iniciar(dados) {
  prepararCaptura(dados.captura);
  F = dados.fotos;
  cursor.init(); legenda.init();
  montarLinha();
  return { duracao: duracao(), segmentos: LINHA.map((s) => [s.nome, +s.ini.toFixed(2), +s.fim.toFixed(2)]) };
}
