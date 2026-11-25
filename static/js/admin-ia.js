/* NOMA — painel > Assistente IA: reindexar, laboratório de RAG e documentos da base (só carregado nessas telas) */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const { toast, esc, icone, abrir, fechar, confirmar } = window.NomaAdmin;
  const CSRF = $('meta[name="csrf-token"]')?.content || "";
  const BASE = "/admin/assistente";
  const num = (v, casas = 2) => Number(v).toFixed(casas).replace(".", ",");
  const segundos = (ms) => `${num((ms || 0) / 1000, 1)} s`;
  const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

  // Erro com o status e o JSON da resposta (o api() do admin.js só devolve a mensagem)
  async function pedir(url, { dados, form } = {}) {
    const r = await fetch(url, { method: dados || form ? "POST" : "GET", credentials: "same-origin",
      headers: { "X-CSRF-Token": CSRF, "X-Requested-With": "fetch", ...(form ? {} : { "Content-Type": "application/json" }) },
      body: form || (dados ? JSON.stringify(dados) : undefined) });
    let json = {};
    try { json = await r.json(); } catch { /* sem corpo */ }
    if (r.status === 401) { location.href = "/admin/login"; }
    if (!r.ok) throw Object.assign(new Error(json.erro || "Algo deu errado. Tente de novo."), { status: r.status, dados: json });
    return json;
  }

  // Troca um pedaço da página pela versão nova vinda do servidor (sem recarregar tudo)
  async function recarregar(seletor) {
    const html = await (await fetch(location.href, { headers: { "X-Requested-With": "fetch" } })).text();
    const novo = new DOMParser().parseFromString(html, "text/html").querySelector(seletor);
    if (novo) $(seletor).replaceWith(novo);
    return $(seletor);
  }

  const resumoIndexacao = (r) => (r.novos || r.removidos)
    ? `${plural(r.novos, "trecho novo ou alterado", "trechos novos ou alterados")}, ${plural(r.iguais, "igual", "iguais")} e ${plural(r.removidos, "removido", "removidos")} em ${segundos(r.ms)}.`
    : `Nada mudou: ${plural(r.iguais, "trecho igual", "trechos iguais")}, conferidos em ${segundos(r.ms)}.`;

  /* ================================================ visão geral: reindexar */
  document.addEventListener("click", async (e) => {
    const botao = e.target.closest("[data-reindexar]");
    if (!botao || botao.classList.contains("carregando")) return;
    const estado = $("[data-indice-estado]");
    botao.classList.add("carregando");
    estado.classList.remove("indice-estado--erro");
    estado.textContent = "Indexando…";
    const demora = setTimeout(() => { estado.textContent = "Ainda indexando: o Gemini está gerando os vetores."; }, 5000);
    try {
      const r = await pedir(`${BASE}/reindexar`, { dados: {} });
      await recarregar("[data-visao]");
      const novo = $("[data-indice-estado]");
      novo.textContent = resumoIndexacao(r);
      novo.classList.remove("indice-estado--pendente");
      toast("Índice atualizado.");
    } catch (err) {
      estado.textContent = err.message;
      estado.classList.add("indice-estado--erro");
      botao.classList.remove("carregando");
    } finally { clearTimeout(demora); }
  });

  /* ================================================ laboratório */
  const lab = $("[data-lab-form]");
  if (lab) {
    const campo = $("[data-lab-campo]", lab), enviar = $("[data-lab-enviar]", lab), erro = $("[data-lab-erro]", lab);
    const etapas = $("[data-etapas]"), mais = $("[data-lab-mais]");
    const LIMIAR = +lab.dataset.limiar;
    const etapa = (nome) => $(`[data-etapa="${nome}"]`, etapas);
    const corpo = (nome) => $("[data-corpo]", etapa(nome));
    const tempo = (nome, texto) => { $("[data-tempo]", etapa(nome)) && ($("[data-tempo]", etapa(nome)).textContent = texto || ""); };
    let ultima = null;     // resultado mostrado (os botões de baixo usam a mesma pergunta)

    const ajustarCampo = () => { campo.style.height = "auto"; campo.style.height = `${Math.min(campo.scrollHeight, 160)}px`; };
    campo.addEventListener("input", ajustarCampo);
    campo.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); lab.requestSubmit(); } });
    $$("[data-exemplo]", lab).forEach((b) => b.addEventListener("click", () => { campo.value = b.textContent.trim(); ajustarCampo(); lab.requestSubmit(); }));

    const esqueleto = (n = 3) => `<div class="lab-esqueleto" aria-hidden="true">${Array.from({ length: n }, (_, i) => `<span class="esq esqueleto" style="width:${[92, 76, 58, 84][i % 4]}%"></span>`).join("")}</div>`;
    const pctSim = (s) => Math.max(0, Math.min(100, (s - 0.4) / 0.5 * 100));  // barra de 0,40 a 0,90
    const barraSim = (s) => `<span class="sim"><span class="sim__barra"><i style="--pct:${pctSim(s)}%"></i><b style="--pct:${pctSim(LIMIAR)}%"></b></span><span class="sim__valor">${num(s, 3)}</span></span>`;
    const FONTES = { produto: "produto", avaliacao: "avaliações", documento: "documento" };

    function grafico(vetor) {
      const maior = Math.max(...vetor.map(Math.abs)) || 1, meio = 32;
      const d = vetor.map((v, i) => `M${i + 0.5} ${meio}V${(meio - (v / maior) * 30).toFixed(1)}`).join("");
      return `<svg class="vetor-grafico" viewBox="0 0 ${vetor.length} 64" preserveAspectRatio="none" role="img" aria-label="Os ${vetor.length} números do vetor"><path class="vetor-grafico__zero" d="M0 ${meio}H${vetor.length}"/><path d="${d}"/></svg>`;
    }

    function textoComCitacoes(texto, fontes) {
      return esc(texto).replace(/\[(\d+)\]/g, (m, n) => {
        const f = fontes.find((x) => x.n === +n);
        return f ? `<span class="cita" title="${esc(f.titulo)}">${n}</span>` : "";
      }).split(/\n+/).map((l) => `<p>${l}</p>`).join("");
    }

    function filtrosDaPergunta(f) {
      const itens = [];
      if (f.preco_max) itens.push(`preço até R$ ${num(f.preco_max, 0)}`);
      if (f.preco_min) itens.push(`preço a partir de R$ ${num(f.preco_min, 0)}`);
      if (f.genero) itens.push(`${f.genero.toLowerCase()} ou unissex`);
      return itens.length ? `<p class="lab-filtros">Filtros tirados da pergunta: ${itens.map((i) => `<span class="etiqueta">${esc(i)}</span>`).join(" ")}</p>` : "";
    }

    function mostrar(r) {
      // 1. pergunta
      corpo("pergunta").innerHTML = `<p class="lab-pergunta">${esc(r.pergunta)}</p>
        ${r.consulta && r.consulta !== r.pergunta ? `<p class="suave">Texto buscado: ${esc(r.consulta)}</p>` : ""}${filtrosDaPergunta(r.filtros || {})}`;
      // 2. embedding
      tempo("embedding", r.tempos.embedding_do_cache ? `do cache do Redis · ${r.tempos.embedding} ms` : `${r.tempos.embedding} ms`);
      corpo("embedding").innerHTML = `<p><b>${r.dimensoes} números</b> · ${esc(r.modelo_embedding)}</p>
        <code class="vetor">[${r.vetor.slice(0, 10).map((v) => v.toFixed(4)).join(", ")}, … mais ${r.dimensoes - 10}]</code>${grafico(r.vetor)}`;
      // 3. busca
      tempo("busca", `${r.tempos.busca} ms`);
      let n = 0;
      const linhas = r.candidatos.map((c) => {
        const usado = !c.descartado && ++n;
        return `<tr class="${usado ? "" : "descartado"}"><td class="direita">${usado ? `[${usado}]` : ""}</td>
          <td><span class="celula-corte" title="${esc(c.titulo)}">${esc(c.titulo)}</span><small class="bloco">${FONTES[c.fonte]}${c.preco ? ` · ${esc(c.preco)}` : ""}</small></td>
          <td>${barraSim(c.similaridade)}</td><td class="direita">${num(c.distancia, 4)}</td>
          <td>${usado ? `<span class="etiqueta etiqueta--ok">vai para o prompt</span>` : esc(c.descartado.replace(/(\d)\.(\d)/g, "$1,$2"))}</td></tr>`;
      }).join("");
      corpo("busca").innerHTML = `<pre class="codigo codigo--sql">${esc(r.sql).replace(/&lt;=&gt;/g, "<mark>&lt;=&gt;</mark>")}</pre>
        <div class="tabela-rolagem"><table class="tabela tabela--mini tabela--candidatos">
          <thead><tr><th class="direita">Nº</th><th>Trecho</th><th>Similaridade <small>· linha = mínimo ${num(r.limiar)}</small></th><th class="direita">Distância</th><th>Resultado</th></tr></thead>
          <tbody>${linhas}</tbody></table></div>`;
      // 4. prompt
      if (r.prompt) {
        const ultimaMsg = r.prompt.mensagens.at(-1).texto;
        tempo("prompt", r.tokens.entrada ? `${r.tokens.entrada.toLocaleString("pt-BR")} tokens de entrada` : "");
        corpo("prompt").innerHTML = `<details class="lab-sanfona"><summary>Instrução de sistema ${icone("baixo")}</summary><pre class="prompt">${esc(r.prompt.sistema)}</pre></details>
          <pre class="prompt prompt--contexto">${esc(ultimaMsg).replace(/^(CONTEXTO:|PERGUNTA DO CLIENTE:)$/gm, '<span class="prompt__rotulo">$1</span>').replace(/^(\[\d+\] .*)$/gm, "<b>$1</b>")}</pre>`;
      } else {
        tempo("prompt", "");
        corpo("prompt").innerHTML = `<p class="lab-nada">Nenhum trecho passou da similaridade mínima (${num(r.limiar)}): o prompt não foi montado.</p>`;
      }
      // 5. resposta
      const t = r.tempos, partes = [["Reescrita", t.reescrita], ["Embedding", t.embedding], ["Busca", t.busca], ["Geração", t.geracao]].filter(([, ms]) => ms);
      const soma = partes.reduce((a, [, ms]) => a + ms, 0) || 1;
      tempo("resposta", t.geracao ? `${segundos(t.geracao)} · ${esc(r.modelo)}` : "o modelo não foi chamado");
      corpo("resposta").innerHTML = `<div class="lab-resposta">${r.resposta ? textoComCitacoes(r.resposta, r.fontes) : `<p>${esc(r.aviso || "")}</p>`}</div>
        ${r.aviso ? `<p class="aviso aviso--erro">${icone("alerta")} O Gemini não escreveu a resposta: a loja mostra os produtos encontrados.</p>` : ""}
        <div class="tempos" role="img" aria-label="Tempo total ${segundos(t.total)}">
          <div class="tempos__barra">${partes.map(([nome, ms]) => `<i class="tempos__${nome.toLowerCase().normalize("NFD").replace(/[^a-z]/g, "")}" style="flex:${ms / soma}" title="${nome}: ${ms} ms"></i>`).join("")}</div>
          <ul class="tempos__legenda">${partes.map(([nome, ms]) => `<li><span class="tempos__${nome.toLowerCase().normalize("NFD").replace(/[^a-z]/g, "")}"></span>${nome} ${ms >= 1000 ? segundos(ms) : `${ms} ms`}</li>`).join("")}<li class="tempos__total">Total ${segundos(t.total)}${r.tokens.saida ? ` · ${r.tokens.saida} tokens de saída` : ""}</li></ul>
        </div>`;
    }

    async function perguntar() {
      const pergunta = campo.value.trim().replace(/\s+/g, " ");
      erro.hidden = true;
      if (pergunta.length < 3) { erro.textContent = "Escreva uma pergunta."; erro.hidden = false; campo.focus(); return; }
      enviar.classList.add("carregando"); campo.readOnly = true;
      etapas.hidden = false; etapas.setAttribute("aria-busy", "true"); mais.hidden = true;
      $$("[data-painel]").forEach((p) => { p.hidden = true; });
      $$("[data-corpo]", etapas).forEach((c, i) => { c.innerHTML = esqueleto(i === 2 ? 4 : 2); });
      corpo("pergunta").innerHTML = `<p class="lab-pergunta">${esc(pergunta)}</p>`;
      $$("[data-tempo]", etapas).forEach((t) => { t.textContent = ""; });
      tempo("resposta", "gerando…");
      history.replaceState(null, "", `?q=${encodeURIComponent(pergunta)}`);
      try {
        ultima = await pedir(`${BASE}/laboratorio/perguntar`, { dados: { pergunta } });
        mostrar(ultima);
        mais.hidden = false;
      } catch (err) {
        etapas.hidden = true; ultima = null;
        erro.innerHTML = `${esc(err.message)}${err.status === 503 ? ' <button class="link" type="button" data-lab-tentar>Tentar de novo</button>' : ""}`;
        erro.hidden = false;
        $("[data-lab-tentar]", erro)?.addEventListener("click", perguntar);
      } finally {
        enviar.classList.remove("carregando"); campo.readOnly = false; etapas.setAttribute("aria-busy", "false");
      }
    }
    lab.addEventListener("submit", (e) => { e.preventDefault(); perguntar(); });

    /* botões de baixo: sem RAG, busca por texto e plano do Postgres */
    const itemProduto = (p) => `<li><img src="${esc(p.imagem)}" alt="" loading="lazy"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.nome)}</a>
      ${p.similaridade != null ? `<span class="sim__valor">${num(p.similaridade, 3)}</span>` : `<span class="suave">${esc(p.preco)}</span>`}</li>`;
    const marcarPlano = (linhas) => linhas.map((l) => /Seq Scan|Index Scan|Execution Time/.test(l) ? `<b>${esc(l)}</b>` : esc(l)).join("\n");
    const EXTRAS = {
      "sem-rag": { carregando: "Perguntando ao Gemini sem nenhum contexto da loja…",
        mostrar: (r) => `<div class="lado-a-lado">
          <div><h3>Com RAG <small>${plural(ultima.candidatos.filter((c) => !c.descartado).length, "trecho", "trechos")} do pgvector</small></h3><div class="lab-resposta">${ultima.resposta ? textoComCitacoes(ultima.resposta, ultima.fontes) : esc(ultima.aviso || "")}</div></div>
          <div><h3>Sem RAG <small>só o modelo · ${segundos(r.ms)}</small></h3><div class="lab-resposta">${esc(r.resposta).split(/\n+/).map((l) => `<p>${l}</p>`).join("")}</div></div></div>` },
      comparar: { carregando: "Buscando nos dois jeitos…",
        mostrar: (r) => `<div class="lado-a-lado">
          <div><h3>Busca por texto <small>MongoDB · a frase inteira no nome, cor ou material</small></h3>${r.texto.length ? `<ul class="lista-produtos">${r.texto.map(itemProduto).join("")}</ul>` : `<p class="lab-nada">Nenhum produto tem essa frase escrita.</p>`}</div>
          <div><h3>Busca vetorial <small>pgvector · pelo significado</small></h3>${r.vetorial.length ? `<ul class="lista-produtos">${r.vetorial.map(itemProduto).join("")}</ul>` : `<p class="lab-nada">Nenhum produto parecido o bastante.</p>`}</div></div>` },
      plano: { carregando: "Pedindo o plano ao Postgres…",
        mostrar: (r) => `<div class="lado-a-lado">
          <div><h3>O que o Postgres escolhe <small>com poucas linhas, ler a tabela toda é mais rápido</small></h3><pre class="codigo codigo--plano">${marcarPlano(r.normal)}</pre></div>
          <div><h3>Forçando o índice HNSW <small>SET LOCAL enable_seqscan = off</small></h3><pre class="codigo codigo--plano">${marcarPlano(r.indice)}</pre></div></div>` },
    };
    $$("[data-extra]").forEach((b) => b.addEventListener("click", async () => {
      if (!ultima || b.classList.contains("carregando")) return;
      const nome = b.dataset.extra, painel = $(`[data-painel="${nome}"]`), extra = EXTRAS[nome];
      b.classList.add("carregando");
      painel.hidden = false;
      painel.innerHTML = `<p class="suave">${extra.carregando}</p>${esqueleto(3)}`;
      painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      try { painel.innerHTML = extra.mostrar(await pedir(`${BASE}/laboratorio/${nome}`, { dados: { pergunta: ultima.pergunta } })); }
      catch (err) { painel.innerHTML = `<p class="campo__erro">${icone("alerta")} ${esc(err.message)}</p>`; }
      finally { b.classList.remove("carregando"); }
    }));

    ajustarCampo();
    if (campo.value.trim() && !campo.disabled) perguntar();  // veio de "Testar no laboratório"
  }

  /* ================================================ documentos da base */
  const listaDocs = $("[data-lista-docs]");
  if (listaDocs) {
    const MAXIMO = +(document.currentScript?.dataset.maximo || $("script[data-maximo]")?.dataset.maximo || 60000);
    const soltar = $("[data-soltar-doc]"), arquivo = $("[data-arquivo-doc]"), erroEnvio = $("[data-envio-erro]");
    const form = $("[data-form-doc]"), conflito = $("[data-doc-conflito]");
    let editando = null;

    async function atualizarLista(destacar) {
      await recarregar("[data-lista-docs]");
      if (destacar) {
        const tr = $(`[data-doc="${destacar}"]`);
        tr?.classList.add("linha--nova");
        tr?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
    const avisoDoResultado = (r, acao) => {
      if (r.aviso) return toast(r.aviso, "erro");
      const d = r.documento;
      toast(`“${d.titulo}” ${acao}: ${plural(d.trechos, "trecho", "trechos")} no índice.`);
    };

    /* enviar arquivo */
    const titulo = $("[data-soltar-titulo]"), dica = $("[data-soltar-dica]");
    const textoOriginal = [titulo.textContent, dica.textContent];
    async function enviar(f) {
      erroEnvio.hidden = true;
      if (!f) return;
      if (!/\.(md|txt|pdf)$/i.test(f.name)) { erroEnvio.textContent = "Envie um arquivo .md, .txt ou .pdf."; erroEnvio.hidden = false; return; }
      if (f.size > 2 * 1024 * 1024) { erroEnvio.textContent = "O arquivo pode ter até 2 MB."; erroEnvio.hidden = false; return; }
      soltar.classList.add("enviando"); soltar.setAttribute("aria-busy", "true");
      titulo.textContent = `Enviando ${f.name}…`; dica.textContent = "Dividindo em trechos e gerando os vetores";
      const dados = new FormData(); dados.append("arquivo", f);
      try {
        const r = await pedir(`${BASE}/documentos`, { form: dados });
        await atualizarLista(r.documento.id);
        avisoDoResultado(r, r.substituiu ? "substituído" : "adicionado");
      } catch (err) { erroEnvio.textContent = err.message; erroEnvio.hidden = false; }
      finally {
        soltar.classList.remove("enviando", "sobre"); soltar.removeAttribute("aria-busy");
        [titulo.textContent, dica.textContent] = textoOriginal; arquivo.value = "";
      }
    }
    arquivo.addEventListener("change", () => enviar(arquivo.files[0]));
    ["dragenter", "dragover"].forEach((ev) => soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.add("sobre"); }));
    ["dragleave", "drop"].forEach((ev) => soltar.addEventListener(ev, () => soltar.classList.remove("sobre")));
    soltar.addEventListener("drop", (e) => { e.preventDefault(); if (!soltar.classList.contains("enviando")) enviar(e.dataTransfer.files[0]); });

    /* escrever e editar */
    const campoTitulo = $("[data-doc-titulo]", form), campoTexto = $("[data-doc-texto]", form), contador = $("[data-contador-doc]", form);
    const contar = () => { contador.textContent = `${campoTexto.value.length.toLocaleString("pt-BR")} / ${MAXIMO.toLocaleString("pt-BR")}`; };
    campoTexto.addEventListener("input", contar);
    form.addEventListener("input", (e) => { e.target.closest(".campo")?.classList.remove("erro"); });
    function limparErros() {
      $$(".campo__erro", form).forEach((x) => { x.hidden = true; });
      $$(".campo", form).forEach((c) => c.classList.remove("erro"));
      conflito.hidden = true;
    }
    function abrirEditor(doc = null, texto = "") {
      editando = doc;
      limparErros();
      $("[data-editar-titulo]").textContent = doc ? "Editar documento" : "Escrever texto";
      campoTitulo.value = doc?.titulo || ""; campoTexto.value = texto; contar();
      abrir("editar-doc");
      setTimeout(() => (doc ? campoTexto : campoTitulo).focus(), 250);
    }
    $("[data-escrever-doc]").addEventListener("click", () => abrirEditor());
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      limparErros();
      const botao = $("[data-salvar-doc]", form);
      botao.classList.add("carregando");
      try {
        const dados = { titulo: campoTitulo.value, texto: campoTexto.value, ...(editando ? { visto_em: editando.visto } : {}) };
        const r = await pedir(editando ? `${BASE}/documentos/${editando.id}` : `${BASE}/documentos`, { dados });
        fechar();
        await atualizarLista(r.documento.id);
        avisoDoResultado(r, editando ? "salvo" : (r.substituiu ? "substituído" : "adicionado"));
      } catch (err) {
        if (err.dados?.conflito) {
          conflito.innerHTML = `${icone("alerta")} ${esc(err.message)} <button class="link" type="button" data-recarregar>Recarregar</button>`;
          conflito.hidden = false;
          $("[data-recarregar]", conflito).addEventListener("click", () => location.reload());
        } else if (err.dados?.campos) {
          Object.entries(err.dados.campos).forEach(([c, msg]) => {
            const el = $(`[data-erro="${c}"]`, form);
            if (el) { el.textContent = msg; el.hidden = false; el.closest(".campo").classList.add("erro"); }
          });
        } else toast(err.message, "erro");
      } finally { botao.classList.remove("carregando"); }
    });

    /* ações de cada linha */
    document.addEventListener("click", async (e) => {
      const tr = e.target.closest("[data-doc]");
      if (!tr) return;
      const id = tr.dataset.doc, nome = tr.dataset.titulo;
      if (e.target.closest("[data-doc-trechos]")) {
        try {
          const r = await pedir(`${BASE}/documentos/${id}`);
          $("[data-trechos-titulo]").textContent = r.documento.titulo;
          const repetem = r.trechos.some((t) => t.repetido);
          $("[data-trechos-resumo]").textContent = `${plural(r.trechos.length, "trecho", "trechos")}${repetem ? " · em destaque, o fim do trecho anterior repetido" : ""}`;
          $("[data-trechos-lista]").innerHTML = r.trechos.map((t, i) => `<li><header><b>Trecho ${i + 1}</b>${t.secao ? ` · ${esc(t.secao)}` : ""}<small>${t.caracteres} caracteres</small></header>
            <p>${t.repetido ? `<mark>${esc(t.repetido)}</mark>\n\n` : ""}${esc(t.texto)}</p></li>`).join("");
          abrir("trechos");
        } catch (err) { toast(err.message, "erro"); }
      } else if (e.target.closest("[data-doc-editar]")) {
        try {
          const r = await pedir(`${BASE}/documentos/${id}`);
          abrirEditor({ id, titulo: r.documento.titulo, visto: r.documento.atualizado_em }, r.texto);
        } catch (err) { toast(err.message, "erro"); }
      } else if (e.target.closest("[data-doc-excluir]")) {
        const n = +tr.dataset.trechos;
        confirmar("Excluir documento?", `“${nome}” sai da base${n ? ` e ${plural(n, "vetor sai", "vetores saem")} do índice` : ""}. Não dá para desfazer.`, "Excluir", async () => {
          try {
            await pedir(`${BASE}/documentos/${id}/excluir`, { dados: {} });
            tr.classList.add("saindo");
            setTimeout(() => atualizarLista(), 350);
            toast("Documento excluído.");
          } catch (err) { toast(err.message, "erro"); }
        });
      } else if (e.target.closest("[data-doc-indexar]")) {
        const b = e.target.closest("[data-doc-indexar]");
        b.textContent = "Indexando…"; b.disabled = true;
        try { const r = await pedir(`${BASE}/documentos/${id}/indexar`, { dados: {} }); await atualizarLista(id); avisoDoResultado(r, "indexado"); }
        catch (err) { toast(err.message, "erro"); b.textContent = "Indexar agora"; b.disabled = false; }
      }
    });
    document.addEventListener("change", async (e) => {
      const chave = e.target.closest("[data-doc-ativo]");
      if (!chave) return;
      const tr = chave.closest("[data-doc]");
      chave.disabled = true;
      try {
        const r = await pedir(`${BASE}/documentos/${tr.dataset.doc}/ativo`, { dados: {} });
        await atualizarLista();
        if (r.aviso) toast(r.aviso, "erro");
        else toast(r.documento.ativo ? `De volta ao índice: ${plural(r.documento.trechos, "trecho", "trechos")}.` : "Fora do índice: os vetores dele saíram do pgvector.");
      } catch (err) { chave.checked = !chave.checked; chave.disabled = false; toast(err.message, "erro"); }
    });
  }
})();
