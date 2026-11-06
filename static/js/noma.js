/* NOMA — interações e animações da loja (JavaScript puro, sem frameworks) */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const CSRF = $('meta[name="csrf-token"]')?.content || "";
  const leve = document.documentElement.classList.contains("leve");     // aparelho fraco ou rede lenta
  const poucosDados = document.documentElement.classList.contains("dados");  // 2G ou economia de dados
  const reduzir = leve || matchMedia("(prefers-reduced-motion: reduce)").matches;
  const brl = (v) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v || 0).replace(/ /g, " ");
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icone = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;

  async function api(url, { metodo = "GET", dados } = {}) {
    const resp = await fetch(url, {
      method: metodo,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF, "X-Requested-With": "fetch" },
      body: dados ? JSON.stringify(dados) : undefined,
      credentials: "same-origin",
    });
    let json = {};
    try { json = await resp.json(); } catch { /* resposta sem JSON */ }
    if (!resp.ok) { const e = new Error(json.erro || "Algo deu errado. Tente de novo."); e.dados = json; e.status = resp.status; throw e; }
    return json;
  }

  /* ------------------------------------------------ toasts */
  function toast(msg, tipo = "ok", link) {
    const caixa = $("[data-toasts]");
    if (!caixa) return;
    const t = document.createElement("div");
    t.className = `toast ${tipo === "erro" ? "toast--erro" : ""}`;
    t.setAttribute("role", tipo === "erro" ? "alert" : "status");
    t.innerHTML = `${icone(tipo === "erro" ? "alerta" : "check")}<span>${esc(msg)}</span>${link ? `<a href="#" data-acao>${esc(link.texto)}</a>` : ""}`;
    if (link) t.querySelector("[data-acao]").addEventListener("click", (e) => { e.preventDefault(); link.acao(); fechar(); });
    caixa.append(t);
    const fechar = () => { t.classList.add("saindo"); setTimeout(() => t.remove(), 350); };
    setTimeout(fechar, tipo === "erro" ? 4800 : 3200);
  }
  window.nomaToast = toast;
  try { JSON.parse($("#flash")?.textContent || "[]").forEach(([tipo, msg]) => toast(msg, tipo)); } catch { /* sem avisos */ }

  /* ------------------------------------------------ ondinha nos botões */
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".botao");
    if (!b || b.disabled || reduzir) return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height);
    const o = document.createElement("span");
    o.className = "onda";
    o.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
    b.append(o);
    setTimeout(() => o.remove(), 650);
  });

  /* ------------------------------------------------ revelar ao rolar */
  const observador = "IntersectionObserver" in window ? new IntersectionObserver((entradas) => {
    entradas.forEach((en) => { if (en.isIntersecting) { en.target.classList.add("visivel"); observador.unobserve(en.target); } });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }) : null;
  const revelar = (raiz = document) => $$(".revelar:not(.visivel), .avaliacoes__caixa", raiz).forEach((el) => observador ? observador.observe(el) : el.classList.add("visivel"));
  revelar();

  /* ------------------------------------------------ topo que muda ao rolar */
  const topo = $("#topo");
  addEventListener("scroll", () => topo?.classList.toggle("rolou", scrollY > 10), { passive: true });

  /* ------------------------------------------------ contagem regressiva da faixa */
  const faixa = $(".faixa");
  if (faixa) {
    let fim = Date.parse(faixa.dataset.termina || "");
    if (!fim || fim < Date.now()) { const d = new Date(); d.setHours(23, 59, 59, 0); fim = d.getTime(); }
    const partes = { h: $("[data-h]", faixa), m: $("[data-m]", faixa), s: $("[data-s]", faixa) };
    const atualizar = () => {
      let resto = Math.max(0, Math.floor((fim - Date.now()) / 1000));
      const v = { h: Math.floor(resto / 3600), m: Math.floor((resto % 3600) / 60), s: resto % 60 };
      for (const k in v) {
        const txt = String(v[k]).padStart(2, "0");
        if (partes[k].textContent !== txt) { partes[k].textContent = txt; partes[k].classList.remove("tique"); void partes[k].offsetWidth; partes[k].classList.add("tique"); }
      }
    };
    atualizar(); setInterval(atualizar, 1000);
  }

  /* ------------------------------------------------ menu do celular */
  const nav = $("[data-menu]");
  $("[data-abrir-menu]")?.addEventListener("click", () => {
    nav.classList.add("aberto"); nav.setAttribute("aria-hidden", "false");
    mostrarVeu(() => { nav.classList.remove("aberto"); nav.setAttribute("aria-hidden", "true"); });
    setTimeout(() => $("[data-fechar-menu]", nav)?.focus(), 200);
  });
  addEventListener("resize", () => { if (innerWidth > 860 && nav?.classList.contains("aberto")) esconderVeu(); });
  $("[data-fechar-menu]")?.addEventListener("click", () => esconderVeu());

  /* ------------------------------------------------ véu compartilhado (gaveta e menu) */
  const veu = $("[data-veu]");
  let aoFecharVeu = null;
  function mostrarVeu(aoFechar) {
    aoFecharVeu = aoFechar; veu.hidden = false; document.body.classList.add("travado");
    requestAnimationFrame(() => veu.classList.add("ativo"));
  }
  function esconderVeu() {
    veu.classList.remove("ativo"); document.body.classList.remove("travado");
    aoFecharVeu?.(); aoFecharVeu = null;
    setTimeout(() => { if (!veu.classList.contains("ativo")) veu.hidden = true; }, 350);
  }
  veu?.addEventListener("click", esconderVeu);

  /* ------------------------------------------------ carrossel do topo */
  const carrossel = $("[data-carrossel]");
  if (carrossel) {
    const slides = $$(".hero__slide", carrossel), pontos = $$("[data-ponto]", carrossel);
    let atual = 0, timer;
    const DUR = 6500;
    carrossel.style.setProperty("--duracao", DUR + "ms");
    // Banners fora da primeira tela guardam o endereço em data-*: só baixam quando forem usados.
    const carregarSlide = (slide) => {
      $$("[data-srcset]", slide).forEach((el) => { el.srcset = el.dataset.srcset; delete el.dataset.srcset; });
      $$("[data-src]", slide).forEach((el) => { el.src = el.dataset.src; delete el.dataset.src; });
    };
    const automatico = !poucosDados;
    const ir = (n) => {
      slides[atual].classList.remove("ativo"); pontos[atual].classList.remove("ativo");
      atual = (n + slides.length) % slides.length;
      carregarSlide(slides[atual]);
      slides[atual].classList.add("ativo"); pontos[atual].classList.add("ativo");
      clearTimeout(timer); if (automatico) timer = setTimeout(() => ir(atual + 1), DUR);
    };
    // Depois que a página terminou de carregar, adianta o próximo banner em segundo plano.
    if (automatico) addEventListener("load", () => (window.requestIdleCallback || setTimeout)(() => slides.forEach(carregarSlide)));
    pontos.forEach((p) => p.addEventListener("click", () => ir(+p.dataset.ponto)));
    let x0 = null;
    carrossel.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; }, { passive: true });
    carrossel.addEventListener("touchend", (e) => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 40) ir(atual + (dx < 0 ? 1 : -1)); x0 = null; });
    if (automatico) timer = setTimeout(() => ir(1), DUR);
    else carrossel.classList.add("parado");
  }

  /* ------------------------------------------------ trilho (vistos recentemente) */
  function ligarTrilhos(raiz = document) {
    $$("[data-trilho]", raiz).forEach((t) => {
      const faixa = $("[data-trilho-faixa]", t), ant = $("[data-trilho-ant]", t), prox = $("[data-trilho-prox]", t);
      const atualizar = () => {
        ant.classList.toggle("some", faixa.scrollLeft < 8);
        prox.classList.toggle("some", faixa.scrollLeft + faixa.clientWidth >= faixa.scrollWidth - 8);
      };
      ant.onclick = () => faixa.scrollBy({ left: -faixa.clientWidth * 0.75 });
      prox.onclick = () => faixa.scrollBy({ left: faixa.clientWidth * 0.75 });
      faixa.addEventListener("scroll", atualizar, { passive: true });
      atualizar();
    });
  }
  ligarTrilhos();
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-limpar-vistos]");
    if (!b) return;
    try {
      await api("/api/vistos/limpar", { metodo: "POST" });
      const sec = b.closest("[data-vistos]");
      sec.style.transition = "opacity .4s, transform .4s"; sec.style.opacity = "0"; sec.style.transform = "translateY(10px)";
      setTimeout(() => sec.remove(), 400);
      toast("Histórico de vistos apagado do Redis.");
    } catch (err) { toast(err.message, "erro"); }
  });

  /* ------------------------------------------------ sanfonas com altura animada */
  document.addEventListener("click", (e) => {
    const sum = e.target.closest(".sanfona > summary");
    if (!sum || reduzir) return;
    e.preventDefault();
    const det = sum.parentNode, corpo = $(".sanfona__corpo", det);
    if (det.open) {
      corpo.animate([{ height: corpo.offsetHeight + "px", opacity: 1 }, { height: "0px", opacity: 0 }], { duration: 300, easing: "cubic-bezier(.22,1,.36,1)" })
        .onfinish = () => { det.open = false; };
      det.classList.add("fechando");
    } else {
      det.open = true;
      corpo.animate([{ height: "0px", opacity: 0 }, { height: corpo.offsetHeight + "px", opacity: 1 }], { duration: 380, easing: "cubic-bezier(.22,1,.36,1)" });
    }
  });

  /* ------------------------------------------------ modais genéricos */
  let modalAberto = null;
  function abrirModal(nome) {
    const m = $(`[data-modal="${nome}"]`);
    if (!m) return;
    fecharModal();
    m.hidden = false; document.body.classList.add("travado");
    requestAnimationFrame(() => m.classList.add("ativo"));
    modalAberto = m;
    setTimeout(() => $("input, textarea, button:not([data-fechar-modal])", m)?.focus({ preventScroll: true }), 250);
  }
  function fecharModal() {
    const m = modalAberto;
    if (!m) return;
    m.classList.remove("ativo"); modalAberto = null;
    if (!$("[data-gaveta].aberta")) document.body.classList.remove("travado");
    setTimeout(() => { m.hidden = true; }, 300);
  }
  document.addEventListener("click", (e) => {
    const abrir = e.target.closest("[data-abrir-modal]");
    if (abrir) abrirModal(abrir.dataset.abrirModal);
    if (e.target.closest("[data-fechar-modal]") || e.target.classList.contains("modal")) fecharModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if ($("[data-zoom-caixa].ativo")) return fecharZoom();
    if (modalAberto) return fecharModal();
    if (!$("[data-busca]").hidden) return fecharBusca();
    if ($("[data-gaveta].aberta")) return fecharCarrinho();
    if (nav?.classList.contains("aberto")) esconderVeu();
  });

  /* ================================================ CARRINHO ================================================ */
  const gaveta = $("[data-gaveta]");
  const contador = $("[data-contador]");
  let carrinho = { itens: [], total: 0, qtd: 0 };
  let totalMostrado = 0;

  if (gaveta) gaveta.inert = true;  // fechada: fora do alcance do Tab
  function abrirCarrinho() {
    gaveta.classList.add("aberta"); gaveta.setAttribute("aria-hidden", "false"); gaveta.inert = false;
    mostrarVeu(() => { gaveta.classList.remove("aberta"); gaveta.setAttribute("aria-hidden", "true"); gaveta.inert = true; });
    setTimeout(() => $("[data-fechar-carrinho]", gaveta)?.focus({ preventScroll: true }), 300);
    $$(".item", gaveta).forEach((el) => { el.classList.remove("entrar"); void el.offsetWidth; el.classList.add("entrar"); });
  }
  function fecharCarrinho() { esconderVeu(); }
  $$("[data-abrir-carrinho]").forEach((b) => b.addEventListener("click", async () => { abrirCarrinho(); await carregarCarrinho(); }));
  $$("[data-fechar-carrinho]", gaveta).forEach((b) => b.addEventListener("click", fecharCarrinho));

  async function carregarCarrinho() {
    try { desenhar(await api("/api/carrinho"), { entrar: true }); } catch (err) { toast(err.message, "erro"); }
  }

  function animarNumero(el, de, para) {
    if (reduzir || de === para) { el.textContent = brl(para); return; }
    const t0 = performance.now(), dur = 550;
    const passo = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = brl(de + (para - de) * e);
      if (k < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  }

  function atualizarContador(qtd, pular = true) {
    if (!contador) return;
    contador.textContent = qtd;
    contador.classList.toggle("tem", qtd > 0);
    if (pular) { contador.classList.remove("pulou"); void contador.offsetWidth; contador.classList.add("pulou"); }
  }

  function htmlItem(it, i) {
    const variacao = [it.cor, it.tamanho && it.tamanho !== "Único" ? `Tamanho ${it.tamanho}` : ""].filter(Boolean).join(" · ");
    return `<article class="item" data-chave="${esc(it.chave)}" style="--i:${i}">
      <a class="item__foto" href="${esc(it.url)}"><img src="${esc(it.imagem)}" alt="${esc(it.nome)}" loading="lazy"></a>
      <div>
        <a class="item__nome" href="${esc(it.url)}">${esc(it.nome)}</a>
        ${variacao ? `<p class="item__var">${esc(variacao)}</p>` : ""}
        <p class="item__preco">${it.preco_original_fmt ? `<s>${esc(it.preco_original_fmt)}</s>` : ""}${esc(it.preco_fmt)}</p>
        ${it.sem_estoque ? `<p class="item__alerta">Só ${it.estoque} em estoque — ajuste a quantidade.</p>` : ""}
        <div class="qtd">
          <button type="button" class="qtd__btn" data-item-menos aria-label="Diminuir">${icone("menos")}</button>
          <output>${it.quantidade}</output>
          <button type="button" class="qtd__btn" data-item-mais aria-label="Aumentar" ${it.quantidade >= it.estoque ? "disabled" : ""}>${icone("mais")}</button>
        </div>
      </div>
      <button type="button" class="item__remover" data-item-remover aria-label="Remover ${esc(it.nome)}">${icone("lixeira")}</button>
    </article>`;
  }

  function desenhar(c, { entrar = false, destacar = null, pular = false } = {}) {
    const anterior = carrinho;
    carrinho = c;
    const lista = $("[data-itens]", gaveta), vazio = $("[data-vazio]", gaveta), rodape = $("[data-rodape]", gaveta);
    const vazioAgora = !c.itens.length;
    vazio.hidden = !vazioAgora; rodape.hidden = vazioAgora; lista.hidden = vazioAgora;
    // Reaproveita os itens que já estão na tela para animar só o que mudou.
    const existentes = new Map($$(".item", lista).map((el) => [el.dataset.chave, el]));
    const novaOrdem = c.itens.map((it, i) => {
      const atual = existentes.get(it.chave);
      const tmp = document.createElement("div"); tmp.innerHTML = htmlItem(it, i);
      const el = tmp.firstElementChild;
      if (atual) {
        const qAntes = $("output", atual).textContent;
        atual.replaceWith(el);
        if (qAntes !== String(it.quantidade)) { const o = $("output", el); o.classList.add("mudou"); }
      } else if (entrar || destacar === it.chave) el.classList.add(entrar ? "entrar" : "destaque");
      existentes.delete(it.chave);
      return el;
    });
    existentes.forEach((el) => el.remove());
    lista.replaceChildren(...novaOrdem);
    if (destacar) $(`.item[data-chave="${CSS.escape(destacar)}"]`, lista)?.classList.add("destaque");
    animarNumero($("[data-total]", gaveta), totalMostrado, c.total);
    totalMostrado = c.total;
    const eco = $("[data-economia]", gaveta);
    eco.hidden = !(c.economia > 0);
    if (c.economia > 0) eco.textContent = `Você está economizando ${brl(c.economia)} 🎉`;
    atualizarContador(c.qtd, pular || (anterior.qtd !== c.qtd && anterior !== null));
  }

  gaveta?.addEventListener("click", async (e) => {
    const item = e.target.closest(".item");
    if (!item) return;
    const chave = item.dataset.chave;
    const it = carrinho.itens.find((x) => x.chave === chave);
    try {
      if (e.target.closest("[data-item-remover]")) {
        item.classList.add("saindo");
        const c = await api("/api/carrinho", { metodo: "DELETE", dados: { chave } });
        setTimeout(() => desenhar(c), 380);
        toast(`${it?.nome || "Item"} removido.`, "ok", { texto: "Desfazer", acao: () => desfazer(it) });
      } else if (e.target.closest("[data-item-mais]")) {
        desenhar(await api("/api/carrinho", { metodo: "PATCH", dados: { chave, quantidade: it.quantidade + 1 } }));
      } else if (e.target.closest("[data-item-menos]")) {
        if (it.quantidade <= 1) { item.classList.add("saindo"); }
        const c = await api("/api/carrinho", { metodo: "PATCH", dados: { chave, quantidade: it.quantidade - 1 } });
        setTimeout(() => desenhar(c), it.quantidade <= 1 ? 380 : 0);
      }
    } catch (err) {
      item.classList.remove("saindo");
      if (err.dados?.itens) desenhar(err.dados);
      toast(err.message, "erro");
    }
  });

  async function desfazer(it) {
    if (!it) return;
    try {
      const c = await api("/api/carrinho", { metodo: "POST", dados: { produto_id: it.produto_id, cor: it.cor, tamanho: it.tamanho === "Único" ? "" : it.tamanho, quantidade: it.quantidade } });
      desenhar(c, { destacar: it.chave });
    } catch (err) { toast(err.message, "erro"); }
  }

  /* foto que voa até o carrinho */
  function voarAteCarrinho(img) {
    const alvo = $("[data-abrir-carrinho]");
    if (!img || !alvo || reduzir) return Promise.resolve();
    const r = img.getBoundingClientRect(), a = alvo.getBoundingClientRect();
    const tam = Math.min(r.width, 160);
    const clone = img.cloneNode();
    clone.className = "voando";
    Object.assign(clone.style, { left: `${r.left + r.width / 2 - tam / 2}px`, top: `${r.top + r.height / 2 - tam * 0.6}px`, width: `${tam}px`, height: `${tam * 1.2}px` });
    document.body.append(clone);
    const dx = a.left + a.width / 2 - (r.left + r.width / 2), dy = a.top + a.height / 2 - (r.top + r.height / 2);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      clone.style.transform = `translate(${dx}px, ${dy}px) scale(.12) rotate(-12deg)`;
      clone.style.opacity = ".4"; clone.style.borderRadius = "50%";
    }));
    return new Promise((ok) => setTimeout(() => {
      clone.remove();
      alvo.classList.remove("balancou"); void alvo.offsetWidth; alvo.classList.add("balancou");
      ok();
    }, 800));
  }

  /* ------------------------------------------------ página do produto */
  const pagProduto = $("[data-produto]");
  if (pagProduto) {
    const form = $("[data-compra]", pagProduto);
    const qtdEl = $("[data-qtd] [data-valor]", pagProduto);
    const botao = $("[data-adicionar]", pagProduto);
    const max = +(botao?.dataset.max || 1);
    let qtd = 1;
    const mudarQtd = (n) => {
      qtd = Math.max(1, Math.min(max, Math.min(20, n)));
      qtdEl.textContent = qtd; qtdEl.classList.remove("mudou"); void qtdEl.offsetWidth; qtdEl.classList.add("mudou");
    };
    $("[data-qtd] [data-menos]", pagProduto)?.addEventListener("click", () => mudarQtd(qtd - 1));
    $("[data-qtd] [data-mais]", pagProduto)?.addEventListener("click", () => {
      if (qtd >= max) toast(`Só temos ${max} unidade(s) em estoque.`, "erro"); else mudarQtd(qtd + 1);
    });
    form?.addEventListener("change", (e) => {
      if (e.target.name === "cor") $("[data-cor-nome]", form).textContent = e.target.value;
      if (e.target.name === "tamanho") {
        const nome = $("[data-tam-nome]", form); if (nome) nome.textContent = e.target.value;
        $("[data-aviso-tamanho]", form).hidden = true;
      }
    });
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!botao || botao.classList.contains("carregando")) return;
      const grupoTam = $('[data-grupo="tamanho"]', form);
      const tamanho = $('input[name="tamanho"]:checked', form)?.value || "";
      if (grupoTam && !tamanho) {
        grupoTam.classList.remove("tremeu"); void grupoTam.offsetWidth; grupoTam.classList.add("tremeu");
        $("[data-aviso-tamanho]", form).hidden = false;
        grupoTam.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      const cor = $('input[name="cor"]:checked', form)?.value || "";
      botao.classList.add("carregando");
      try {
        const c = await api("/api/carrinho", { metodo: "POST", dados: { produto_id: pagProduto.dataset.produto, cor, tamanho, quantidade: qtd } });
        botao.classList.remove("carregando"); botao.classList.add("ok");
        await voarAteCarrinho($(".galeria__foto img", pagProduto));
        const chave = `${pagProduto.dataset.produto}|${cor}|${tamanho || (c.itens.find((i) => i.produto_id === pagProduto.dataset.produto && i.tamanho === "Único") ? "Único" : "")}`;
        desenhar(c, { destacar: chave, pular: true });
        setTimeout(() => { abrirCarrinho(); }, 150);
        setTimeout(() => botao.classList.remove("ok"), 1800);
      } catch (err) {
        botao.classList.remove("carregando");
        if (err.dados?.campo === "tamanho") { $("[data-aviso-tamanho]", form).hidden = false; }
        toast(err.message, "erro");
      }
    });

    /* zoom da galeria */
    const zoom = $("[data-zoom-caixa]");
    $$("[data-zoom]", pagProduto).forEach((b) => b.addEventListener("click", () => {
      $("[data-zoom-img]", zoom).src = b.dataset.zoom;
      zoom.hidden = false; requestAnimationFrame(() => zoom.classList.add("ativo"));
    }));
    zoom?.addEventListener("click", fecharZoom);

    /* filtro das avaliações por nota */
    $$("[data-abas-notas] .aba", pagProduto).forEach((aba) => aba.addEventListener("click", () => {
      $$("[data-abas-notas] .aba", pagProduto).forEach((a) => a.classList.toggle("ativa", a === aba));
      $$("[data-nota-item]", pagProduto).forEach((li) => {
        const mostrar = aba.dataset.nota === "todas" || li.dataset.notaItem === aba.dataset.nota;
        li.classList.toggle("oculta", !mostrar);
        if (mostrar && !reduzir) li.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 300 });
      });
    }));

    /* escrever avaliação */
    const formAv = $("[data-form-avaliar]");
    let nota = 0;
    const estrelas = $$("[data-avaliar-estrelas] button");
    const pintar = (n) => estrelas.forEach((b) => b.classList.toggle("acesa", +b.dataset.n <= n));
    estrelas.forEach((b) => {
      b.addEventListener("mouseenter", () => pintar(+b.dataset.n));
      b.addEventListener("click", () => { nota = +b.dataset.n; estrelas.forEach((x) => x.setAttribute("aria-checked", x === b)); pintar(nota); $('[data-erro="nota"]', formAv).hidden = true; });
    });
    $("[data-avaliar-estrelas]")?.addEventListener("mouseleave", () => pintar(nota));
    formAv?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const dados = Object.fromEntries(new FormData(formAv)); dados.nota = nota;
      $$(".campo__erro", formAv).forEach((x) => { x.hidden = true; x.closest(".campo")?.classList.remove("erro"); });
      const enviar = $('button[type="submit"]', formAv);
      enviar.classList.add("carregando");
      try {
        await api(`/api/produto/${pagProduto.dataset.slug}/avaliacao`, { metodo: "POST", dados });
        sessionStorage.setItem("noma:avaliou", "1");
        toast("Obrigado! Sua avaliação foi salva no MongoDB.");
        setTimeout(() => location.reload(), 700);
      } catch (err) {
        enviar.classList.remove("carregando");
        Object.entries(err.dados?.campos || {}).forEach(([campo, msg]) => {
          const el = $(`[data-erro="${campo}"]`, formAv); if (!el) return;
          el.textContent = msg; el.hidden = false;
          const caixa = el.closest(".campo"); caixa.classList.add("erro");
          if (campo === "nota") { const g = $("[data-avaliar-estrelas]"); g.classList.remove("tremeu"); void g.offsetWidth; g.classList.add("tremeu"); }
        });
        if (!err.dados?.campos) toast(err.message, "erro");
      }
    });
    try {
      if (sessionStorage.getItem("noma:avaliou")) {
        sessionStorage.removeItem("noma:avaliou");
        const primeiro = $(".opiniao", pagProduto);
        $("#avaliacoes").scrollIntoView({ behavior: "smooth" });
        primeiro?.classList.add("nova");
      }
    } catch { /* armazenamento indisponível */ }
  }
  function fecharZoom() {
    const zoom = $("[data-zoom-caixa]");
    if (!zoom) return;
    zoom.classList.remove("ativo"); setTimeout(() => { zoom.hidden = true; }, 300);
  }

  /* ------------------------------------------------ finalizar pedido */
  const modalFin = $('[data-modal="finalizar"]');
  let previaTimer;
  async function atualizarPrevia() {
    const dados = { nome: $("[data-fin-nome]").value, observacao: $("[data-fin-obs]").value };
    try {
      const r = await api("/api/mensagem", { metodo: "POST", dados });
      const balao = $("[data-fin-previa]");
      if (balao.textContent !== r.mensagem) {
        balao.textContent = r.mensagem;
        if (!reduzir) balao.animate([{ transform: "scale(.98)", opacity: .6 }, { transform: "none", opacity: 1 }], { duration: 250 });
      }
    } catch { /* prévia é só ilustrativa */ }
  }
  $("[data-finalizar]")?.addEventListener("click", () => {
    if (!carrinho.itens.length) return;
    const lista = $("[data-fin-itens]");
    lista.innerHTML = carrinho.itens.map((it, i) => `<li style="--i:${i}"><img src="${esc(it.imagem)}" alt=""><div>${it.quantidade}x ${esc(it.nome)}<small>${esc([it.cor, it.tamanho !== "Único" ? it.tamanho : ""].filter(Boolean).join(" · "))}</small></div><b>${esc(it.subtotal_fmt)}</b></li>`).join("");
    $("[data-fin-total]").textContent = brl(carrinho.total);
    $("[data-fin]").hidden = false; $("[data-sucesso]", modalFin).hidden = true;
    $("[data-fin-erro]").hidden = true;
    atualizarPrevia();
    fecharCarrinho();
    abrirModal("finalizar");
  });
  $$("[data-fin-nome], [data-fin-obs]").forEach((c) => c.addEventListener("input", () => { clearTimeout(previaTimer); previaTimer = setTimeout(atualizarPrevia, 250); }));
  $("[data-enviar-pedido]")?.addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.classList.add("carregando");
    $("[data-fin-erro]").hidden = true;
    try {
      const r = await api("/api/pedido", { metodo: "POST", dados: { nome: $("[data-fin-nome]").value, observacao: $("[data-fin-obs]").value } });
      $("[data-fin]").hidden = true;
      const ok = $("[data-sucesso]", modalFin);
      $("[data-codigo]", ok).textContent = r.codigo;
      $("[data-link-whats]", ok).href = r.url;
      ok.hidden = false;
      desenhar({ itens: [], total: 0, qtd: 0, economia: 0 }, { pular: true });
      setTimeout(() => { location.href = r.url; }, 2000);
    } catch (err) {
      const el = $("[data-fin-erro]"); el.textContent = err.message; el.hidden = false;
    } finally { b.classList.remove("carregando"); }
  });

  /* ------------------------------------------------ busca ao vivo */
  const busca = $("[data-busca]"), entrada = $("[data-busca-input]"), resultados = $("[data-busca-resultados]");
  const dicaInicial = resultados?.innerHTML;
  let buscaTimer, foco = -1, ultimaBusca = "";
  function abrirBusca() {
    if (nav?.classList.contains("aberto")) esconderVeu();
    busca.hidden = false; document.body.classList.add("travado");
    requestAnimationFrame(() => busca.classList.add("ativo"));
    setTimeout(() => entrada.focus(), 120);
  }
  function fecharBusca() {
    busca.classList.remove("ativo"); document.body.classList.remove("travado");
    setTimeout(() => { busca.hidden = true; }, 350);
  }
  $$("[data-abrir-busca]").forEach((b) => b.addEventListener("click", abrirBusca));
  $("[data-fechar-busca]")?.addEventListener("click", fecharBusca);
  busca?.addEventListener("click", (e) => { if (e.target === busca) fecharBusca(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement.tagName)) { e.preventDefault(); abrirBusca(); }
  });
  const marcar = (txt, q) => esc(txt).replace(new RegExp(`(${esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig"), "<mark>$1</mark>");
  entrada?.addEventListener("input", () => {
    clearTimeout(buscaTimer);
    const q = entrada.value.trim();
    if (q.length < 2) { resultados.innerHTML = dicaInicial; return; }
    buscaTimer = setTimeout(async () => {
      ultimaBusca = q;
      try {
        const r = await api(`/api/busca?q=${encodeURIComponent(q)}`);
        if (q !== ultimaBusca) return;
        foco = -1;
        resultados.innerHTML = r.itens.length
          ? r.itens.map((it, i) => `<a class="sugestao" style="--i:${i}" href="/produto/${esc(it.slug)}"><img src="${esc(it.imagem)}" alt=""><span>${marcar(it.nome, q)}<small>${esc(it.categoria)}</small></span><b>${esc(it.preco)}</b></a>`).join("")
            + `<a class="sugestao__ver" href="/busca?q=${encodeURIComponent(q)}">Ver todos os resultados ${icone("seta")}</a>`
          : `<p class="busca__dica">Nada encontrado para “${esc(q)}”. Tente “linho”, “camiseta” ou “bolsa”.</p>`;
      } catch (err) { resultados.innerHTML = `<p class="busca__dica">${esc(err.message)}</p>`; }
    }, 200);
  });
  entrada?.addEventListener("keydown", (e) => {
    const itens = $$(".sugestao", resultados);
    if (!itens.length || !["ArrowDown", "ArrowUp", "Enter"].includes(e.key)) return;
    if (e.key === "Enter" && foco < 0) return;
    e.preventDefault();
    if (e.key === "Enter") { location.href = itens[foco].href; return; }
    foco = (foco + (e.key === "ArrowDown" ? 1 : -1) + itens.length) % itens.length;
    itens.forEach((el, i) => el.classList.toggle("foco", i === foco));
  });

  /* ------------------------------------------------ listagem: filtros sem recarregar a página */
  const pagLista = $("[data-pagina-lista]");
  if (pagLista) {
    document.addEventListener("click", (e) => {
      const botao = e.target.closest("[data-filtro-botao]");
      $$("[data-filtro].aberto").forEach((f) => { if (!botao || f !== botao.parentNode) { f.classList.remove("aberto"); $("[data-filtro-botao]", f).setAttribute("aria-expanded", "false"); } });
      if (botao) { const f = botao.parentNode; const abre = !f.classList.contains("aberto"); f.classList.toggle("aberto", abre); botao.setAttribute("aria-expanded", abre); }
    });
    async function navegar(url, empilhar = true) {
      const lista = $("[data-lista]");
      lista.classList.add("trocando");
      try {
        const html = await (await fetch(url, { headers: { "X-Requested-With": "fetch" } })).text();
        const nova = new DOMParser().parseFromString(html, "text/html").querySelector("[data-lista]");
        if (!nova) throw new Error();
        lista.replaceWith(nova);
        if (empilhar) history.pushState({}, "", url);
        revelar(nova); ligarListagem();
      } catch { location.href = url; }
    }
    function ligarListagem() {
      $$("[data-navegar]").forEach((a) => a.onclick = (e) => { e.preventDefault(); navegar(a.href); });
      const sel = $("[data-ordenar]"); if (sel) sel.onchange = () => navegar(sel.value);
      const mais = $("[data-ver-mais]");
      if (mais) mais.onclick = async () => {
        mais.classList.add("carregando");
        const pagina = +mais.dataset.pagina + 1;
        const url = new URL(mais.dataset.url, location.origin);
        url.searchParams.set("pagina", pagina); url.searchParams.set("parcial", "1");
        try {
          const r = await (await fetch(url, { headers: { "X-Requested-With": "fetch" } })).json();
          const grade = $("[data-grade]"), tmp = document.createElement("div");
          tmp.innerHTML = r.html;
          const novos = [...tmp.children]; grade.append(...novos); novos.forEach((n) => revelar(n.parentNode));
          mais.dataset.pagina = pagina;
          if (!r.tem_mais) mais.parentNode.remove();
        } catch { toast("Não foi possível carregar mais produtos.", "erro"); }
        mais.classList.remove("carregando");
      };
    }
    ligarListagem();
    addEventListener("popstate", () => navegar(location.href, false));
  }

  /* contador inicial (sem animação) */
  if (contador) contador.classList.toggle("tem", +contador.textContent > 0);
})();
