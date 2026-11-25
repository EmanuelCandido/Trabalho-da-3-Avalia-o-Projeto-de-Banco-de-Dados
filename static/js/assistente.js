/* NOMA — conversa do chat "Pergunte à NOMA" (baixado só no primeiro uso; abrir e fechar o painel fica em noma.js) */
(() => {
  "use strict";
  const { $, $$, api, esc, icone, toast, reduzir } = window.noma;
  const painel = $("[data-chat]");
  const el = (nome) => $(`[data-chat-${nome}]`, painel);
  const corpo = el("corpo"), inicio = el("inicio"), conversa = el("conversa"), form = el("form"), campo = el("campo"),
    enviar = el("enviar"), caixaErro = el("erro"), contador = el("contador"), caixaContexto = el("contexto"), botaoLimpar = el("limpar");

  const MINIMO = 3, MAXIMO = 500, AVISAR_EM = 400;
  const DEMORANDO = 6000, DESISTIR = 45000, DESFAZER = 5000;
  const SUGESTOES = ["Qual peça é mais fresca para o calor?", "Posso trocar depois de 20 dias?",
    "Presente masculino até R$ 200", "Tenho 94 cm de busto, qual tamanho uso?"];
  const SUGESTOES_DA_PECA = ["Como eu cuido desta peça?", "O que dizem as avaliações?"];

  let carregado = null;     // promessa do histórico (uma vez por página)
  let contexto = null;      // {id, nome} da peça de que o cliente está falando
  let ocupado = false;      // pergunta em andamento
  let liberaEm = 0;         // limite de perguntas: instante em que o envio volta
  let relogio = null;
  let limpeza = null;       // conversa apagada na tela, ainda dentro do "Desfazer"

  /* ------------------------------------------------ montagem das mensagens */
  function mensagemDoCliente(texto) {
    const m = document.createElement("p");
    m.className = "msg msg--cliente";
    m.textContent = texto;
    return m;
  }

  // O texto da IA nunca entra como HTML: é escapado antes. Cada [n] vira um botão, numerado na ordem em que aparece.
  function textoDaResposta(texto, fontes) {
    const ordem = [];
    const cita = (n) => {
      if (!fontes.some((f) => f.n === n)) return "";
      if (!ordem.includes(n)) ordem.push(n);
      const k = ordem.indexOf(n) + 1;
      return `<button class="cita" type="button" data-cita="${k}" aria-label="Ver fonte ${k}">${k}</button>`;
    };
    // "oferta [1][3]." -> a pontuação fica junto da palavra e os números vêm depois dela
    const linha = (t) => esc(t.trim()).replace(/((?:\s*\[\d+\])+)([.,;:!?]?)/g, (_, marcas, ponto) =>
      ponto + [...new Set(marcas.match(/\d+/g).map(Number))].map(cita).join(""));
    let html = "", lista = [];
    const fecharLista = () => { if (lista.length) html += `<ul>${lista.map((i) => `<li>${i}</li>`).join("")}</ul>`; lista = []; };
    String(texto || "").split(/\n+/).filter((t) => t.trim()).forEach((t) => {
      if (/^\s*[-•]\s+/.test(t)) lista.push(linha(t.replace(/^\s*[-•]\s+/, "")));
      else { fecharLista(); html += `<p>${linha(t)}</p>`; }
    });
    fecharLista();
    return { html, citadas: ordem.map((n) => fontes.find((f) => f.n === n)) };
  }

  const htmlPeca = (p) => `<a class="sugestao" href="${esc(p.url)}">
      <img src="${esc(p.imagem)}" alt="" loading="lazy" width="48" height="56">
      <span>${esc(p.nome)}${p.esgotado ? "<small>Esgotado</small>" : ""}</span>
      <b>${p.preco_antes ? `<s>${esc(p.preco_antes)}</s>` : ""}${esc(p.preco)}</b></a>`;

  function htmlFontes(citadas) {
    if (!citadas.length) return "";
    return `<details class="fontes"><summary>Fontes (${citadas.length}) ${icone("baixo")}</summary><ol>${citadas.map((f, i) =>
      `<li data-fonte="${i + 1}"><span>${i + 1}</span>${f.url ? `<a href="${esc(f.url)}">${esc(f.titulo)}</a>` : esc(f.titulo)}</li>`).join("")}</ol></details>`;
  }

  function mensagemDaLoja(r) {
    const m = document.createElement("div");
    const fontes = r.fontes || [], produtos = r.produtos || [];
    const { html, citadas } = textoDaResposta(r.resposta || r.aviso, fontes);
    const avaliar = r.id && r.resposta && !r.sem_resposta ? `<div class="notas" data-notas="${+r.id}">
        <span role="status" data-notas-ok></span>
        <button type="button" data-nota="1" aria-pressed="false" aria-label="Resposta útil" title="Resposta útil">${icone("positivo")}</button>
        <button type="button" data-nota="-1" aria-pressed="false" aria-label="Resposta não ajudou" title="Não ajudou">${icone("negativo")}</button>
      </div>` : "";
    m.className = "msg msg--loja";
    m.innerHTML = `<div class="msg__texto">${html}</div>
      ${produtos.length ? `<div class="msg__pecas">${produtos.map(htmlPeca).join("")}</div>` : ""}
      ${r.whatsapp ? `<a class="botao botao--whats botao--mini" href="${esc(r.whatsapp)}" target="_blank" rel="noopener">${icone("whatsapp")}Perguntar no WhatsApp</a>` : ""}
      <div class="msg__pe">${htmlFontes(citadas)}${avaliar}</div>`;
    return m;
  }

  function mensagemDeEspera() {
    const m = document.createElement("div");
    m.className = "msg msg--espera";
    m.setAttribute("role", "status");
    m.innerHTML = `<p>Procurando no catálogo…</p><div aria-hidden="true"><span class="esq esqueleto"></span><span class="esq esqueleto"></span><span class="esq esq--nome2 esqueleto"></span></div>`;
    return m;
  }

  const juntar = (m) => { conversa.append(m); return m; };
  const mostrarNoTopo = (m) => corpo.scrollTo({ top: m.offsetTop - 16, behavior: reduzir ? "auto" : "smooth" });

  /* ------------------------------------------------ tela inicial, contexto e erros */
  function atualizarInicio() {
    const vazia = !conversa.children.length;
    inicio.hidden = !vazia;
    botaoLimpar.hidden = vazia;
    if (!vazia) return;
    const pagina = $("[data-produto]");
    const peca = contexto || (pagina && { id: pagina.dataset.produto, nome: $(".info__nome", pagina).textContent.trim() });
    const daPeca = [pagina && $('[data-grupo="tamanho"]', pagina) ? "Como é o caimento?" : "De que material é feita?", ...SUGESTOES_DA_PECA];
    const linhas = peca ? [...daPeca.map((t) => ({ t, peca })), ...SUGESTOES.slice(0, 2).map((t) => ({ t }))] : SUGESTOES.map((t) => ({ t }));
    // com a peça já escolhida, o nome dela está junto do campo: a abertura não repete
    const abertura = peca ? `Tire dúvidas sobre <b>${esc(peca.nome)}</b> ou sobre a loja.` : "Tire dúvidas de tecido, caimento, tamanho, troca, frete e pagamento.";
    inicio.innerHTML = `${contexto ? "" : `<p>${abertura}</p>`}<ul>${linhas.map((l, i) => `<li><button type="button" data-sugestao="${i}">${esc(l.t)}${icone("direita")}</button></li>`).join("")}</ul>`;
    $$("[data-sugestao]", inicio).forEach((b) => b.addEventListener("click", () => {
      const l = linhas[+b.dataset.sugestao];
      definirContexto(l.peca || null);
      perguntar(l.t);
    }));
  }

  function definirContexto(peca) {
    contexto = peca;
    caixaContexto.hidden = !peca;
    if (peca) el("contexto-nome").textContent = peca.nome;
  }

  function mostrarErro(texto, acao, espera = false) {
    caixaErro.classList.toggle("chat__erro--espera", espera);
    caixaErro.innerHTML = `${icone(espera ? "relogio" : "alerta")}<span>${esc(texto)}</span>${acao ? `<button type="button">${esc(acao.texto)}</button>` : ""}`;
    if (acao) $("button", caixaErro).addEventListener("click", acao.fazer);
    caixaErro.hidden = false;
  }
  const esconderErro = () => { caixaErro.hidden = true; caixaErro.textContent = ""; };

  function ajustarCampo() {
    campo.style.height = "auto";
    campo.style.height = `${Math.min(campo.scrollHeight, 132)}px`;
    const n = campo.value.length;
    contador.hidden = n < AVISAR_EM;
    contador.textContent = `${n}/${MAXIMO}`;
    enviar.disabled = ocupado || Date.now() < liberaEm || campo.value.trim().length < MINIMO;
  }

  // Limite de perguntas: o envio fica travado e o aviso conta o tempo que falta
  function travarPor(segundos) {
    liberaEm = Date.now() + segundos * 1000;
    clearInterval(relogio);
    const contar = () => {
      const falta = Math.ceil((liberaEm - Date.now()) / 1000);
      if (falta <= 0) { clearInterval(relogio); esconderErro(); ajustarCampo(); return; }
      mostrarErro(`Você fez muitas perguntas seguidas. Pergunte de novo em ${falta >= 60 ? `${Math.ceil(falta / 60)} min` : `${falta} s`}.`, null, true);
    };
    contar();
    caixaErro.removeAttribute("role");  // a contagem não é lida a cada segundo pelo leitor de tela
    relogio = setInterval(contar, 1000);
    ajustarCampo();
  }

  /* ------------------------------------------------ perguntar */
  async function perguntar(texto) {
    const pergunta = texto.trim().replace(/\s+/g, " ").slice(0, MAXIMO);
    if (ocupado || pergunta.length < MINIMO || Date.now() < liberaEm) return;
    ocupado = true;
    await concluirLimpeza();
    esconderErro();
    caixaErro.setAttribute("role", "alert");
    campo.value = ""; ajustarCampo();
    const minha = juntar(mensagemDoCliente(pergunta)), espera = juntar(mensagemDeEspera());
    atualizarInicio();
    mostrarNoTopo(minha);
    const demora = setTimeout(() => { $("p", espera).textContent = "Ainda procurando…"; }, DEMORANDO);
    const corte = new AbortController(), desistir = setTimeout(() => corte.abort(), DESISTIR);
    try {
      const r = await api("/api/assistente", { metodo: "POST", dados: { pergunta, produto_id: contexto?.id }, signal: corte.signal });
      espera.replaceWith(mensagemDaLoja(r));
      mostrarNoTopo(minha);
    } catch (e) {
      minha.remove(); espera.remove();
      atualizarInicio();
      if (!campo.value.trim()) campo.value = pergunta;  // a pergunta volta para o campo
      const deNovo = { texto: "Tentar de novo", fazer: () => { if (campo.value.trim() === pergunta) campo.value = ""; perguntar(pergunta); } };
      if (e.status === 429) travarPor(e.dados?.espera || 60);
      else if (e.dados?.sessao) mostrarErro("Sua sessão expirou.", { texto: "Recarregar a página", fazer: () => location.reload() });
      else if (e.status) mostrarErro(e.message, e.dados?.campo ? null : deNovo);
      else if (e.name === "AbortError") mostrarErro("A resposta demorou demais.", deNovo);
      else mostrarErro("Sem conexão com a loja.", deNovo);
    } finally {
      clearTimeout(demora); clearTimeout(desistir);
      ocupado = false; ajustarCampo();
    }
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); perguntar(campo.value); });
  campo.addEventListener("input", ajustarCampo);
  campo.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!enviar.disabled) perguntar(campo.value); }
  });
  el("contexto-tirar").addEventListener("click", () => { definirContexto(null); atualizarInicio(); campo.focus(); });

  /* ------------------------------------------------ fontes e avaliação da resposta */
  conversa.addEventListener("click", async (e) => {
    const cita = e.target.closest("[data-cita]");
    if (cita) {
      const fontes = $(".fontes", cita.closest(".msg"));
      const linha = $(`[data-fonte="${cita.dataset.cita}"]`, fontes);
      fontes.open = true;
      linha.classList.remove("marcada"); void linha.offsetWidth; linha.classList.add("marcada");
      linha.scrollIntoView({ block: "nearest", behavior: reduzir ? "auto" : "smooth" });
      return;
    }
    const botao = e.target.closest("[data-nota]");
    if (!botao || botao.getAttribute("aria-pressed") === "true") return;
    const notas = botao.closest("[data-notas]"), antes = $('[aria-pressed="true"]', notas);
    const marcar = (b) => $$("[data-nota]", notas).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    marcar(botao);
    try {
      await api("/api/assistente/avaliar", { metodo: "POST", dados: { id: +notas.dataset.notas, nota: +botao.dataset.nota } });
      $("[data-notas-ok]", notas).textContent = "Obrigado pela avaliação";
    } catch { marcar(antes); toast("Não foi possível salvar a avaliação.", "erro"); }
  });

  /* ------------------------------------------------ limpar a conversa (com "Desfazer") */
  botaoLimpar.addEventListener("click", () => {
    if (ocupado) return;
    const guardadas = [...conversa.children];
    conversa.replaceChildren();
    esconderErro(); atualizarInicio(); campo.focus();
    limpeza = { timer: setTimeout(concluirLimpeza, DESFAZER) };
    toast("Conversa apagada.", "ok", { texto: "Desfazer", acao: () => {
      if (!limpeza) return;
      clearTimeout(limpeza.timer); limpeza = null;
      conversa.replaceChildren(...guardadas); atualizarInicio();
    } }, DESFAZER);
  });
  // Só aqui a conversa sai do Redis: passou o tempo do "Desfazer", veio outra pergunta ou a página fechou
  async function concluirLimpeza() {
    if (!limpeza) return;
    clearTimeout(limpeza.timer); limpeza = null;
    try { await api("/api/assistente/limpar", { metodo: "POST", keepalive: true }); } catch { /* some sozinha em 2 h */ }
  }
  addEventListener("pagehide", concluirLimpeza);

  /* ------------------------------------------------ abrir */
  async function carregarConversa() {
    try {
      const { mensagens } = await api("/api/assistente/historico");
      mensagens.forEach((m) => juntar(m.papel === "usuario" ? mensagemDoCliente(m.texto)
        : mensagemDaLoja({ ...m, resposta: m.aviso ? null : m.texto, aviso: m.aviso ? m.texto : null })));
    } catch { /* sem o histórico, começa vazia */ }
    conversa.setAttribute("aria-live", "polite");
  }

  async function iniciar({ produto = null, pergunta = "", foco = true } = {}) {
    if (!carregado) { conversa.setAttribute("aria-live", "off"); carregado = carregarConversa(); }
    await carregado;
    form.hidden = false;
    if (produto) definirContexto(produto);
    if (pergunta) campo.value = pergunta.slice(0, MAXIMO);
    atualizarInicio(); ajustarCampo();
    if (conversa.lastElementChild) {
      const ultima = $$(".msg--cliente", conversa).at(-1);
      if (ultima) corpo.scrollTop = ultima.offsetTop - 16;
    }
    if (foco) campo.focus({ preventScroll: true });
  }

  window.nomaChat = { iniciar };
})();
