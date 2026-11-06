/* NOMA — interações do painel administrativo */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const CSRF = $('meta[name="csrf-token"]')?.content || "";
  const reduzir = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const brl = (v) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v || 0).replace(/ /g, " ");
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icone = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;

  async function api(url, { metodo = "GET", dados } = {}) {
    const r = await fetch(url, { method: metodo, credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF, "X-Requested-With": "fetch" },
      body: dados ? JSON.stringify(dados) : undefined });
    let json = {};
    try { json = await r.json(); } catch { /* sem corpo */ }
    if (r.status === 401) { location.href = "/admin/login"; throw new Error("Sessão expirada."); }
    if (!r.ok) throw new Error(json.erro || "Algo deu errado.");
    return json;
  }

  function toast(msg, tipo = "ok") {
    const t = document.createElement("div");
    t.className = `toast ${tipo === "erro" ? "toast--erro" : ""}`;
    t.setAttribute("role", "status");
    t.innerHTML = `${icone(tipo === "erro" ? "alerta" : "check")}<span>${esc(msg)}</span>`;
    $("[data-toasts]").append(t);
    setTimeout(() => { t.classList.add("saindo"); setTimeout(() => t.remove(), 300); }, 3400);
  }
  try { JSON.parse($("#flash")?.textContent || "[]").forEach(([tipo, msg]) => toast(msg, tipo)); } catch { /* nada */ }

  /* ondinha nos botões */
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".botao");
    if (!b || b.disabled || reduzir) return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height), o = document.createElement("span");
    o.className = "onda"; o.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
    b.append(o); setTimeout(() => o.remove(), 650);
  });

  /* menu lateral no celular */
  const lateral = $("[data-lateral]");
  $("[data-abrir-lateral]")?.addEventListener("click", (e) => { e.stopPropagation(); lateral.classList.toggle("aberta"); });
  document.addEventListener("click", (e) => { if (lateral?.classList.contains("aberta") && !lateral.contains(e.target)) lateral.classList.remove("aberta"); });

  /* números do dashboard contando */
  $$("[data-contar]").forEach((el) => {
    const alvo = parseFloat(el.dataset.contar) || 0, moeda = "moeda" in el.dataset, suf = el.dataset.sufixo || "";
    const fmt = (v) => moeda ? brl(v) : Math.round(v).toLocaleString("pt-BR") + suf;
    if (reduzir) { el.textContent = fmt(alvo); return; }
    const t0 = performance.now(), dur = 1100;
    const passo = (t) => { const k = Math.min(1, (t - t0) / dur); el.textContent = fmt(alvo * (1 - Math.pow(1 - k, 4))); if (k < 1) requestAnimationFrame(passo); };
    requestAnimationFrame(passo);
  });

  /* modais */
  let aberto = null, aoConfirmar = null;
  function abrir(nome) {
    const m = $(`[data-modal="${nome}"]`); m.hidden = false; document.body.classList.add("travado");
    requestAnimationFrame(() => m.classList.add("ativo")); aberto = m;
    setTimeout(() => $("[data-confirmar], [data-fechar-modal]", m)?.focus(), 200);
  }
  function fechar() {
    if (!aberto) return; const m = aberto; aberto = null;
    m.classList.remove("ativo"); document.body.classList.remove("travado"); setTimeout(() => { m.hidden = true; }, 250);
  }
  document.addEventListener("click", (e) => { if (e.target.closest("[data-fechar-modal]") || e.target.classList.contains("modal")) fechar(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fechar(); });
  $("[data-confirmar]")?.addEventListener("click", async (e) => { const b = e.currentTarget; b.classList.add("carregando"); try { await aoConfirmar?.(); } finally { b.classList.remove("carregando"); fechar(); } });

  /* lista de produtos: filtrar ao digitar, ativar/desativar, excluir e ver documento */
  const filtro = $("[data-filtrar-tabela]");
  filtro?.addEventListener("input", () => {
    const q = filtro.value.trim().toLowerCase();
    let n = 0;
    $$("[data-linha]").forEach((tr) => { const ok = !q || tr.dataset.busca.includes(q); tr.classList.toggle("oculta", !ok); if (ok) n++; });
    $("[data-contagem]").textContent = n;
    $("[data-sem-resultado]").hidden = n > 0;
  });
  $$("[data-alternar]").forEach((chk) => chk.addEventListener("change", async () => {
    chk.disabled = true;
    try {
      const r = await api(chk.dataset.alternar, { metodo: "POST" });
      chk.checked = r.ativo;
      toast(r.ativo ? "Produto visível na loja." : "Produto escondido da loja.");
    } catch (err) { chk.checked = !chk.checked; toast(err.message, "erro"); }
    chk.disabled = false;
  }));
  $$("[data-excluir]").forEach((b) => b.addEventListener("click", () => {
    const tr = b.closest("tr");
    $("[data-conf-titulo]").textContent = "Excluir produto?";
    $("[data-confirmar]").textContent = "Excluir";
    $("[data-conf-texto]").textContent = `“${tr.dataset.nome}” será apagado do MongoDB (com as fotos enviadas). Essa ação não pode ser desfeita.`;
    aoConfirmar = async () => {
      try {
        await api(b.dataset.excluir, { metodo: "POST" });
        tr.classList.add("saindo");
        setTimeout(() => { tr.remove(); const c = $("[data-contagem]"); if (c) c.textContent = $$("[data-linha]:not(.oculta)").length; }, 350);
        toast("Produto excluído.");
      } catch (err) { toast(err.message, "erro"); }
    };
    abrir("confirmar");
  }));
  const colorir = (json) => esc(json)
    .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="k">$1</span>$2')
    .replace(/(:\s*)(&quot;.*?&quot;)/g, '$1<span class="s">$2</span>')
    .replace(/(:\s*)(-?\d+(\.\d+)?|true|false|null)/g, '$1<span class="n">$2</span>');
  $$("[data-ver-doc]").forEach((b) => b.addEventListener("click", async () => {
    try { const r = await api(b.dataset.verDoc); $("[data-doc-json]").innerHTML = colorir(r.json); abrir("documento"); }
    catch (err) { toast(err.message, "erro"); }
  }));
  $(".linha--nova")?.scrollIntoView({ behavior: "smooth", block: "center" });

  /* pedidos: mudar status */
  $$("[data-status]").forEach((sel) => sel.addEventListener("change", async () => {
    try {
      const r = await api(sel.dataset.status, { metodo: "POST", dados: { status: sel.value } });
      const et = sel.closest(".pedido").querySelector("[data-etiqueta]");
      et.className = `etiqueta etiqueta--${sel.value}`; et.textContent = r.rotulo;
      et.animate?.([{ transform: "scale(1.25)" }, { transform: "none" }], { duration: 350, easing: "cubic-bezier(.34,1.56,.64,1)" });
      toast("Status atualizado no Supabase.");
    } catch (err) { toast(err.message, "erro"); }
  }));

  /* funções usadas pela tela Vitrine (static/js/vitrine.js) */
  window.NomaAdmin = {
    api, toast, brl,
    confirmar(titulo, texto, botao, acao) {
      $("[data-conf-titulo]").textContent = titulo;
      $("[data-conf-texto]").textContent = texto;
      $("[data-confirmar]").textContent = botao;
      aoConfirmar = acao;
      abrir("confirmar");
    },
  };

  /* ------------------------------------------------ formulário de produto */
  const form = $("[data-form-produto]");
  if (!form) return;

  const removerAnimado = (el) => { el.classList.add("saindo-attr"); setTimeout(() => el.remove(), 280); };
  const listaAttr = $("[data-atributos]"), modeloAttr = $("[data-modelo-attr]");
  const novoAttr = (nome = "") => {
    const el = modeloAttr.content.firstElementChild.cloneNode(true);
    listaAttr.append(el);
    const [n, v] = $$("input", el); n.value = nome; (nome ? v : n).focus();
  };
  $("[data-add-attr]").addEventListener("click", () => novoAttr());
  $$("[data-sugestao]").forEach((b) => b.addEventListener("click", () => novoAttr(b.dataset.sugestao)));
  const listaCor = $("[data-cores]"), modeloCor = $("[data-modelo-cor]");
  $("[data-add-cor]").addEventListener("click", () => { const el = modeloCor.content.firstElementChild.cloneNode(true); listaCor.append(el); $("input:not([type=color])", el).focus(); });
  form.addEventListener("click", (e) => {
    const a = e.target.closest("[data-remover-attr], [data-remover-cor]");
    if (a) removerAnimado(a.parentNode);
    const f = e.target.closest("[data-remover-foto]");
    if (f) { const foto = f.closest(".foto"); removerAnimado(foto); setTimeout(atualizarPrevia, 300); if (foto.dataset.arquivo !== undefined) tirarArquivo(+foto.dataset.arquivo); }
  });

  /* contador de caracteres */
  const desc = $("[data-contador-chars]");
  const contar = () => { $("[data-chars]").textContent = desc.value.length; };
  desc.addEventListener("input", contar); contar();

  /* fotos: arrastar para o upload, pré-visualizar e reordenar */
  const fotos = $("[data-fotos]"), arquivos = $("[data-arquivos]"), soltar = $("[data-soltar]");
  let selecionados = new DataTransfer();
  function tirarArquivo(idx) {
    const novo = new DataTransfer();
    [...selecionados.files].forEach((f, i) => { if (i !== idx) novo.items.add(f); });
    selecionados = novo; arquivos.files = selecionados.files;
    $$(".foto--nova", fotos).forEach((el, i) => { el.dataset.arquivo = i; });
  }
  function adicionarArquivos(lista) {
    [...lista].filter((f) => f.type.startsWith("image/")).forEach((f) => {
      if (f.size > 8 * 1024 * 1024) { toast(`${f.name} passa de 8 MB.`, "erro"); return; }
      selecionados.items.add(f);
      const div = document.createElement("div");
      div.className = "foto foto--nova"; div.dataset.arquivo = selecionados.files.length - 1;
      div.innerHTML = `<img src="${URL.createObjectURL(f)}" alt=""><button type="button" class="foto__remover" data-remover-foto aria-label="Remover foto">${icone("fechar")}</button>`;
      fotos.append(div);
    });
    arquivos.files = selecionados.files;
    soltar.classList.remove("erro");
    atualizarPrevia();
  }
  arquivos.addEventListener("change", () => { const novos = [...arquivos.files]; arquivos.files = selecionados.files; adicionarArquivos(novos); });
  ["dragenter", "dragover"].forEach((ev) => soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((ev) => soltar.addEventListener(ev, () => soltar.classList.remove("sobre")));
  soltar.addEventListener("drop", (e) => { e.preventDefault(); adicionarArquivos(e.dataTransfer.files); });
  let arrastada = null;
  fotos.addEventListener("dragstart", (e) => { arrastada = e.target.closest(".foto:not(.foto--nova)"); if (!arrastada) return e.preventDefault(); arrastada.classList.add("arrastando"); });
  fotos.addEventListener("dragend", () => { arrastada?.classList.remove("arrastando"); arrastada = null; atualizarPrevia(); });
  fotos.addEventListener("dragover", (e) => {
    if (!arrastada) return; e.preventDefault();
    const alvo = e.target.closest(".foto"); if (!alvo || alvo === arrastada || alvo.classList.contains("foto--nova")) return;
    const r = alvo.getBoundingClientRect();
    fotos.insertBefore(arrastada, e.clientX > r.left + r.width / 2 ? alvo.nextSibling : alvo);
  });

  /* prévia do card na loja, ao vivo */
  const lerPreco = (t) => { t = (t || "").replace(/[R$\s]/g, ""); if (t.includes(",")) t = t.replace(/\./g, "").replace(",", "."); const n = parseFloat(t); return isNaN(n) ? null : n; };
  function atualizarPrevia() {
    $("[data-previa-nome]").textContent = $('[data-previa="nome"]').value.trim() || "Nome do produto";
    const preco = lerPreco($('[data-previa="preco"]').value), promo = lerPreco($('[data-previa="promo"]').value);
    const temPromo = promo !== null && preco !== null && promo < preco;
    $("[data-previa-de]").textContent = temPromo ? brl(preco) : "";
    $("[data-previa-por]").textContent = brl(temPromo ? promo : preco || 0);
    $("[data-desconto]").textContent = temPromo ? `${Math.round((1 - promo / preco) * 100)}% de desconto` : "";
    const img = $(".foto img", fotos)?.src || $("[data-url-imagem]").value || "/static/img/sem-foto.svg";
    const alvo = $("[data-previa-img]");
    if (alvo.src !== img) { alvo.style.opacity = 0; setTimeout(() => { alvo.src = img; alvo.style.opacity = 1; }, 150); }
  }
  form.addEventListener("input", (e) => { if (e.target.matches("[data-previa], [data-url-imagem]")) atualizarPrevia(); e.target.closest(".campo")?.classList.remove("erro"); });
  atualizarPrevia();

  /* validação antes de enviar */
  form.addEventListener("submit", (e) => {
    const erros = [];
    const nome = $('[name="nome"]'), preco = $('[name="preco"]');
    if (nome.value.trim().length < 2) erros.push(nome);
    if (!(lerPreco(preco.value) > 0)) erros.push(preco);
    const temFoto = $$(".foto", fotos).length || $("[data-url-imagem]").value.trim();
    if (!temFoto) { soltar.classList.add("erro"); erros.push(soltar); }
    if (erros.length) {
      e.preventDefault();
      erros.forEach((el) => { const c = el.closest(".campo") || el; c.classList.add("erro"); c.classList.remove("tremer"); void c.offsetWidth; c.classList.add("tremer"); });
      erros[0].scrollIntoView({ behavior: "smooth", block: "center" });
      toast("Preencha nome, preço e pelo menos uma foto.", "erro");
      return;
    }
    $('button[type="submit"]', form).classList.add("carregando");
  });
})();
