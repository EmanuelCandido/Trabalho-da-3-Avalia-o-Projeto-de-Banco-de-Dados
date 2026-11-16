/* Motor de montagem: cada quadro é uma função do tempo t (segundos).
   - seek(t) desenha o quadro e resolve quando as imagens estão decodificadas;
   - sons() devolve a lista de efeitos sonoros (tempo, tipo, volume) para o montar.py mixar.
   As cenas e a ordem do vídeo ficam em cenas.js. */
"use strict";

const W = 1920, H = 1080;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, u) => a + (b - a) * u;
const prog = (t, t0, dur) => clamp((t - t0) / dur);
const E = {
  lin: (u) => u,
  out: (u) => 1 - Math.pow(1 - u, 3),
  out5: (u) => 1 - Math.pow(1 - u, 5),
  in: (u) => u * u * u,
  inOut: (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2),
  mola: (u, s = 1.15) => (u >= 1 ? 1 : 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2)),
};

function el(tag, cls, html, pai) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  if (pai) pai.appendChild(e);
  return e;
}
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

/* ------------------------------------------------------------------ texto palavra a palavra */
// `trecho` vira um bloco monoespaçado; **trecho** vira negrito. Cada palavra é um <span class="w">.
function palavras(pai, texto) {
  const partes = [];
  const re = /`([^`]+)`(\S*)|\*\*([^*]+)\*\*(\S*)|(\S+)/g;
  let m;
  while ((m = re.exec(texto))) {
    if (m[1]) partes.push(`<span class="mono">${esc(m[1])}</span>${esc(m[2])}`);
    else if (m[3]) partes.push(`<b style="font-weight:650">${esc(m[3])}</b>${esc(m[4])}`);
    else partes.push(esc(m[5]));
  }
  pai.innerHTML = partes.map((p) => `<span class="w">${p}</span>`).join(" ");
  return [...pai.querySelectorAll(".w")];
}

// Entrada com desfoque → nitidez (assinatura da referência) e saída com desfoque.
function animarPalavras(spans, t, t0, { passo = 0.07, dur = 0.34, saida = Infinity, desfoque = 14, sobe = 10 } = {}) {
  spans.forEach((s, i) => {
    const p = E.out(prog(t, t0 + i * passo, dur));
    const q = E.inOut(prog(t, saida + i * 0.025, 0.28));
    const op = p * (1 - q);
    s.style.opacity = op.toFixed(3);
    const b = desfoque * (1 - p) + 12 * q;
    s.style.filter = b > 0.05 ? `blur(${b.toFixed(2)}px)` : "none";
    s.style.transform = `translateY(${((1 - p) * sobe - q * 8).toFixed(2)}px)`;
  });
}

/* ------------------------------------------------------------------ dados da captura */
const D = { abas: {}, marcas: {}, whats: null, cap: null };

function bsearch(arr, v) { // último índice com arr[i] <= v
  let lo = 0, hi = arr.length - 1, r = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (arr[m] <= v) { r = m; lo = m + 1; } else hi = m - 1; }
  return r;
}

function prepararCaptura(cap) {
  D.cap = cap;
  for (const [nome, a] of Object.entries(cap.abas)) {
    D.abas[nome] = {
      nome, url: a.url, qt: a.quadros.map((q) => q[0]), qf: a.quadros.map((q) => q[1]),
      mt: [], mx: [], my: [], ft: [], ff: [], ct: [], cx: [], cy: [], kt: [], focos: [], areas: {}, ut: [], uu: [], rt: [],
    };
  }
  for (const e of cap.eventos) {
    const a = D.abas[e.aba];
    if (e.tipo === "marca") D.marcas[e.nome] = e.t;
    else if (e.tipo === "mouse") { a.mt.push(e.t); a.mx.push(e.x); a.my.push(e.y); }
    else if (e.tipo === "cursor") { a.ft.push(e.t); a.ff.push(e.forma); }
    else if (e.tipo === "clique") { a.ct.push(e.t); a.cx.push(e.x); a.cy.push(e.y); }
    else if (e.tipo === "tecla") a.kt.push(e.t);
    else if (e.tipo === "foco") a.focos.push(e);
    else if (e.tipo === "area") (a.areas[e.nome] = a.areas[e.nome] || []).push({ t: e.t, caixa: e.caixa });
    else if (e.tipo === "url") { a.ut.push(e.t); a.uu.push(e.url); }
    else if (e.tipo === "rolar") a.rt.push(e.t);
    else if (e.tipo === "whatsapp") D.whats = e;
  }
}
const M = (nome, desloc = 0) => {
  if (!(nome in D.marcas)) throw new Error("marca ausente: " + nome);
  return D.marcas[nome] + desloc;
};

function quadroEm(aba, t) {
  const a = D.abas[aba];
  const i = Math.max(0, bsearch(a.qt, t));
  return a.url + a.qf[i];
}
function mouseEm(aba, t) {
  const a = D.abas[aba];
  if (!a.mt.length) return { x: 1440 * 0.62, y: 900 * 0.72 };
  const i = bsearch(a.mt, t);
  if (i < 0) return { x: a.mx[0], y: a.my[0] };
  if (i >= a.mt.length - 1) return { x: a.mx[i], y: a.my[i] };
  const u = clamp((t - a.mt[i]) / Math.max(1e-4, a.mt[i + 1] - a.mt[i]));
  // amostras de 60 Hz: se o próximo ponto está longe no tempo, o mouse estava parado
  if (a.mt[i + 1] - a.mt[i] > 0.1) return { x: a.mx[i], y: a.my[i] };
  return { x: lerp(a.mx[i], a.mx[i + 1], u), y: lerp(a.my[i], a.my[i + 1], u) };
}
function formaEm(aba, t) {
  const a = D.abas[aba];
  const i = bsearch(a.ft, t);
  return i < 0 ? "seta" : a.ff[i];
}
function cliqueEm(aba, t) { // segundos desde o último clique
  const a = D.abas[aba];
  const i = bsearch(a.ct, t);
  return i < 0 ? 99 : t - a.ct[i];
}
function urlEm(aba, t) {
  const a = D.abas[aba];
  const i = bsearch(a.ut, t);
  return i < 0 ? "" : a.uu[i];
}
// instante do foco com esse nome (o roteiro da captura dá nome a cada enquadramento)
function FO(aba, nome, desloc = 0) {
  const f = D.abas[aba].focos.find((x) => x.nome === nome);
  if (!f) throw new Error("foco ausente: " + nome);
  return f.t + desloc;
}
// área com esse nome no instante t (a mais recente; antes da primeira, a primeira)
function areaEm(aba, nome, t) {
  const l = D.abas[aba].areas[nome];
  if (!l) throw new Error("área ausente: " + nome);
  let r = l[0];
  for (const x of l) if (x.t <= t) r = x;
  return r.caixa;
}
function focosEntre(aba, t0, t1) { return D.abas[aba].focos.filter((f) => f.t >= t0 - 1e-6 && f.t <= t1); }
function ultimoFoco(aba, t) { const f = D.abas[aba].focos.filter((x) => x.t <= t); return f[f.length - 1] || null; }

/* ------------------------------------------------------------------ mapa de tempo de um trecho gravado */
// Converte tempo local do trecho <-> tempo da captura, com partes aceleradas: [[capIni, capFim, velocidade], ...]
class Mapa {
  constructor(c0, c1, rapidos = []) {
    this.c0 = c0; this.c1 = c1; this.p = [];
    let c = c0, l = 0;
    const r = rapidos.filter(([a, b]) => b > a + 0.05 && b > c0 && a < c1).map(([a, b, v]) => [Math.max(a, c0), Math.min(b, c1), v]).sort((x, y) => x[0] - y[0]);
    for (const [a, b, v] of r) {
      if (a > c) { this.p.push({ c0: c, c1: a, v: 1, l0: l }); l += a - c; }
      this.p.push({ c0: a, c1: b, v, l0: l }); l += (b - a) / v; c = b;
    }
    if (c < c1) { this.p.push({ c0: c, c1, v: 1, l0: l }); l += c1 - c; }
    this.dur = l;
  }
  cap(l) {
    for (const s of this.p) { const d = (s.c1 - s.c0) / s.v; if (l <= s.l0 + d || s === this.p[this.p.length - 1]) return s.c0 + (l - s.l0) * s.v; }
    return this.c1;
  }
  loc(c) {
    for (const s of this.p) if (c <= s.c1) return s.l0 + (Math.max(c, s.c0) - s.c0) / s.v;
    return this.dur;
  }
  vel(l) { for (const s of this.p) if (l <= s.l0 + (s.c1 - s.c0) / s.v) return s.v; return 1; }
}

/* ------------------------------------------------------------------ janela do navegador */
const BARRA = 46;           // altura da barra da janela, em px da página gravada
const VW = 1440, VH = 900;  // tamanho da página gravada (px CSS)
const espera = [];          // imagens a decodificar antes da foto do quadro

class Janela {
  constructor(aba) {
    this.aba = aba;
    this.e = el("div", "janela", null, $("#mundo"));
    this.e.style.width = VW + "px"; this.e.style.height = VH + BARRA + "px";
    const sombra = el("div", "janela__sombra", null, this.e);
    this.corpo = el("div", "janela__corpo", null, sombra);
    const barra = el("div", "janela__barra", "<i></i><i></i><i></i>", this.corpo);
    barra.style.height = BARRA + "px";
    this.url = el("div", "janela__url", "", barra);
    const tela = el("div", "janela__tela", null, this.corpo);
    tela.style.top = BARRA + "px";
    this.img = el("img", null, null, tela);
    this.src = ""; this.urlTxt = null;
    this.e.style.display = "none";
  }
  // x, y: canto superior esquerdo no palco; s: escala; recorte: [cima, direita, baixo, esquerda] em px da janela
  set({ x, y, s, capT, recorte = null, raio = 16, opacidade = 1, desfoque = 0 }) {
    this.e.style.display = "block";
    this.e.style.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) scale(${s.toFixed(5)})`;
    this.e.style.opacity = opacidade.toFixed(3);
    this.e.style.filter = desfoque > 0.05 ? `blur(${desfoque.toFixed(2)}px)` : "none";
    this.corpo.style.clipPath = recorte ? `inset(${recorte.map((v) => v.toFixed(1) + "px").join(" ")} round ${raio.toFixed(1)}px)` : "none";
    const src = quadroEm(this.aba, capT);
    if (src !== this.src) { this.src = src; this.img.src = src; espera.push(this.img.decode().catch(() => {})); }
    const u = urlEm(this.aba, capT);
    if (u !== this.urlTxt) {
      this.urlTxt = u;
      try {
        const p = new URL(u);
        const host = p.hostname === "127.0.0.1" || p.hostname === "localhost" ? `${p.hostname}:${p.port}` : p.hostname;
        const resto = decodeURIComponent((p.pathname === "/" ? "" : p.pathname) + p.search).replace(/\+/g, " ");
        this.url.innerHTML = `<b>${esc(host)}</b>${esc(resto)}`;
      } catch { this.url.textContent = u; }
    }
  }
  esconder() { this.e.style.display = "none"; }
  // ponto da página gravada (px CSS) -> palco, dado o estado aplicado
  ponto(px, py, est, cam) {
    const wx = est.x + px * est.s, wy = est.y + (BARRA + py) * est.s;
    return { x: cam.tx + wx * cam.z, y: cam.ty + wy * cam.z };
  }
}

/* ------------------------------------------------------------------ cursor */
const SVG_SETA = `<svg width="30" height="40" viewBox="-2 -2 22 32"><path d="M0 0 L0 23.6 L5.6 18.5 L9.5 27.4 L13.6 25.6 L9.8 16.9 L17.2 16.9 Z" fill="#111" stroke="#fff" stroke-width="1.9" stroke-linejoin="round"/></svg>`;
const SVG_MAO = `<svg width="34" height="38" viewBox="-1 -1 28 32"><path d="M8.6 1.2c1.4 0 2.5 1.1 2.5 2.5v7.4l.9-.1c.4-1.1 1.4-1.8 2.6-1.8 1.2 0 2.2.8 2.5 1.9.5-.3 1-.4 1.6-.4 1.3 0 2.4.9 2.6 2.1.4-.2.8-.3 1.3-.3 1.5 0 2.6 1.2 2.6 2.6v5.4c0 4.6-3.4 8.2-8 8.2h-2.4c-2.5 0-4.4-1-5.9-3L2 19.1c-.8-1.1-.6-2.6.5-3.4 1-.8 2.5-.6 3.3.4l.3.4V3.7c0-1.4 1.1-2.5 2.5-2.5z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/><path d="M14.1 12.2v5.4M17.7 13.6v4.2M21.3 15v3.2" stroke="#111" stroke-width="1.3" stroke-linecap="round"/></svg>`;
const SVG_TEXTO = `<svg width="16" height="34" viewBox="-1 -1 12 30"><path d="M1 1h3c.6 0 1 .4 1 1v24c0 .6-.4 1-1 1H1M9 1H6c-.6 0-1 .4-1 1v24c0 .6.4 1 1 1h3" fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/><path d="M1 1h3c.6 0 1 .4 1 1v24c0 .6-.4 1-1 1H1M9 1H6c-.6 0-1 .4-1 1v24c0 .6.4 1 1 1h3" fill="none" stroke="#111" stroke-width="1.6" stroke-linecap="round"/></svg>`;
const PONTA = { seta: [2.7, 2.7], mao: [9.7, 2.4], texto: [8, 17] };

const cursor = {
  e: null, pedido: null,
  init() {
    this.e = $("#cursor");
    this.rastros = [0, 1, 2].map(() => el("div", "c", "", this.e));
    this.anel = el("div", "anel", null, this.e);
    this.c = el("div", "c", "", this.e);
    this.forma = null;
  },
  // {x, y, forma, escala, clique (s desde o clique), rastro: [{x,y}], opacidade}
  set(p) { this.pedido = p; },
  aplicar() {
    const p = this.pedido;
    this.pedido = null;
    if (!p || p.opacidade === 0) { this.e.style.display = "none"; return; }
    this.e.style.display = "block";
    if (p.forma !== this.forma) {
      this.forma = p.forma;
      const svg = p.forma === "mao" ? SVG_MAO : p.forma === "texto" ? SVG_TEXTO : SVG_SETA;
      [this.c, ...this.rastros].forEach((n) => { n.innerHTML = svg; });
    }
    const esc = (p.escala || 1) * 1.18;
    const k = p.clique != null && p.clique < 0.28 ? 1 - 0.18 * Math.sin(Math.PI * clamp(p.clique / 0.24)) : 1;
    const [ox, oy] = PONTA[p.forma] || PONTA.seta;
    const tf = (x, y, s) => `translate(${(x - ox * s).toFixed(2)}px, ${(y - oy * s).toFixed(2)}px) scale(${s.toFixed(4)})`;
    this.c.style.transform = tf(p.x, p.y, esc * k);
    this.c.style.opacity = p.opacidade ?? 1;
    const r = p.rastro || [];
    this.rastros.forEach((n, i) => {
      const q = r[i];
      if (!q || Math.hypot(q.x - p.x, q.y - p.y) < 6) { n.style.opacity = 0; return; }
      n.style.opacity = ((0.2 - i * 0.06) * (p.opacidade ?? 1)).toFixed(3);
      n.style.transform = tf(q.x, q.y, esc * k);
    });
    if (p.clique != null && p.clique < 0.5) {
      const u = clamp(p.clique / 0.45);
      this.anel.style.opacity = (0.9 * (1 - u)).toFixed(3);
      this.anel.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px) scale(${(0.4 + 0.9 * E.out(u)).toFixed(3)})`;
    } else this.anel.style.opacity = 0;
  },
};

/* ------------------------------------------------------------------ legendas */
const legenda = {
  lista: [], atual: null, spans: [],
  init() { this.caixa = $(".legenda__caixa"); },
  add(t0, t1, texto) { this.lista.push({ t0, t1, texto }); },
  pilula: 0,
  aplicar(t) {
    const l = this.lista.find((x) => t >= x.t0 && t < x.t1 + 0.35);
    if (!l) { this.caixa.style.display = "none"; this.atual = null; return; }
    this.caixa.style.display = "block";
    if (l !== this.atual) { this.atual = l; this.spans = palavras(this.caixa, l.texto); }
    animarPalavras(this.spans, t, l.t0, { passo: 0.06, saida: l.t1 - 0.05 });
    const a = clamp(this.pilula) * clamp(1 - prog(t, l.t1, 0.3)) * clamp(prog(t, l.t0, 0.25));
    this.caixa.style.background = `rgba(255,255,255,${(0.94 * a).toFixed(3)})`;
    this.caixa.style.boxShadow = `0 14px 40px rgba(17,17,20,${(0.12 * a).toFixed(3)})`;
    this.pilula = 0;
  },
};

/* ------------------------------------------------------------------ linha do tempo */
const LINHA = [];
const SONS = [];
let fimLinha = 0;

// Acrescenta um segmento. sobrepor: quanto ele começa antes do fim do anterior (transições cruzadas).
function seg(nome, dur, desenhar, { sobrepor = 0, sons = null, esconder = null } = {}) {
  const ini = Math.max(0, fimLinha - sobrepor);
  const s = { nome, ini, fim: ini + dur, dur, desenhar, esconder, sons };
  LINHA.push(s);
  fimLinha = s.fim;
  return s;
}
const som = (t, tipo, vol = 1) => SONS.push({ t: +t.toFixed(4), tipo, vol });

let janelas = {};
async function seek(t) {
  espera.length = 0;
  Object.values(janelas).forEach((j) => j.esconder());
  $("#mundo").style.transform = "none";
  for (const s of LINHA) {
    const ativo = t >= s.ini && t < s.fim;
    if (ativo) s.desenhar(t - s.ini, t, s);
    else if (s.esconder) s.esconder();
  }
  legenda.aplicar(t);
  cursor.aplicar();
  await Promise.all(espera);
  // espera o Chrome pintar (texto recém-mostrado é rasterizado num quadro seguinte)
  await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
}
function duracao() { return fimLinha; }
function sons() { return SONS.slice().sort((a, b) => a.t - b.t); }
