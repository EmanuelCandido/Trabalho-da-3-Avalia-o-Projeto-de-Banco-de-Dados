/* NOMA — painel > Vitrine: banners do carrossel e faixa promocional do topo */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const { api, toast, confirmar } = window.NomaAdmin;

  /* contadores de caracteres: <em data-contador-de="nome-do-campo"> */
  $$("[data-contador-de]").forEach((em) => {
    const campo = $(`[name="${em.dataset.contadorDe}"]`);
    if (!campo) return;
    const atualizar = () => { em.textContent = `${campo.value.length}/${campo.maxLength}`; em.classList.toggle("perto", campo.value.length > campo.maxLength * 0.85); };
    campo.addEventListener("input", atualizar); atualizar();
  });
  /* botões que preenchem um campo: <button data-preencher="#id" data-valor="..."> */
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-preencher]");
    if (!b) return;
    const alvo = $(b.dataset.preencher);
    alvo.value = b.dataset.valor;
    alvo.dispatchEvent(new Event("input", { bubbles: true }));
    alvo.classList.remove("piscou"); void alvo.offsetWidth; alvo.classList.add("piscou");
  });

  /* ================================================ lista de banners */
  const lista = $("[data-banners]");
  if (lista) {
    // arrastar pela alça para reordenar (mouse e toque, com Pointer Events)
    let arrastando = null, salvarTimer;
    const numerar = () => $$("[data-pos]", lista).forEach((el, i) => { el.textContent = i + 1; });
    const salvarOrdem = () => {
      clearTimeout(salvarTimer);
      salvarTimer = setTimeout(async () => {
        try {
          await api(lista.dataset.ordemUrl, { metodo: "POST", dados: { ids: $$(".banner-linha", lista).map((li) => li.dataset.id) } });
          toast("Ordem dos banners salva.");
        } catch (err) { toast(err.message, "erro"); }
      }, 350);
    };
    lista.addEventListener("pointerdown", (e) => {
      const alca = e.target.closest("[data-alca]");
      if (!alca) return;
      e.preventDefault();
      arrastando = alca.closest(".banner-linha");
      arrastando.classList.add("arrastando");
      alca.setPointerCapture(e.pointerId);
    });
    lista.addEventListener("pointermove", (e) => {
      if (!arrastando) return;
      const outro = document.elementsFromPoint(e.clientX, e.clientY).map((el) => el.closest?.(".banner-linha")).find((el) => el && el !== arrastando);
      if (!outro) return;
      const r = outro.getBoundingClientRect();
      const antes = e.clientY < r.top + r.height / 2;
      // animação FLIP: as linhas deslizam para o novo lugar
      const posicoes = new Map($$(".banner-linha", lista).map((li) => [li, li.getBoundingClientRect().top]));
      lista.insertBefore(arrastando, antes ? outro : outro.nextSibling);
      $$(".banner-linha", lista).forEach((li) => {
        const dy = posicoes.get(li) - li.getBoundingClientRect().top;
        if (dy && li !== arrastando) li.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 220, easing: "cubic-bezier(.22,1,.36,1)" });
      });
      numerar();
    });
    const soltar = () => {
      if (!arrastando) return;
      arrastando.classList.remove("arrastando");
      arrastando = null;
      salvarOrdem();
    };
    lista.addEventListener("pointerup", soltar);
    lista.addEventListener("pointercancel", soltar);
    // teclado: alça + setas para cima/baixo
    lista.addEventListener("keydown", (e) => {
      const alca = e.target.closest("[data-alca]");
      if (!alca || !["ArrowUp", "ArrowDown"].includes(e.key)) return;
      e.preventDefault();
      const li = alca.closest(".banner-linha");
      const vizinho = e.key === "ArrowUp" ? li.previousElementSibling : li.nextElementSibling;
      if (!vizinho) return;
      lista.insertBefore(li, e.key === "ArrowUp" ? vizinho : vizinho.nextSibling);
      alca.focus(); numerar(); salvarOrdem();
    });

    // ligar / desligar
    $$("[data-alternar-banner]", lista).forEach((chk) => chk.addEventListener("change", async () => {
      chk.disabled = true;
      try {
        const r = await api(chk.dataset.alternarBanner, { metodo: "POST" });
        chk.checked = r.ativo;
        const et = $("[data-status]", chk.closest(".banner-linha"));
        et.className = `etiqueta etiqueta--${r.ativo ? "no_ar" : "desligado"}`;
        et.textContent = r.ativo ? "No ar" : "Desligado";
        toast(r.ativo ? "Banner ligado na loja." : "Banner desligado.");
      } catch (err) { chk.checked = !chk.checked; toast(err.message, "erro"); }
      chk.disabled = false;
    }));

    // excluir
    $$("[data-excluir-banner]", lista).forEach((b) => b.addEventListener("click", () => {
      const li = b.closest(".banner-linha");
      confirmar("Excluir banner?", `“${li.dataset.nome}” sai do carrossel e as imagens enviadas são apagadas do GridFS.`, "Excluir", async () => {
        try {
          await api(b.dataset.excluirBanner, { metodo: "POST" });
          li.classList.add("saindo");
          setTimeout(() => { li.remove(); numerar(); }, 350);
          toast("Banner excluído.");
        } catch (err) { toast(err.message, "erro"); }
      });
    }));
  }

  /* ================================================ prévia da faixa */
  const formFaixa = $("[data-form-faixa]");
  if (formFaixa) {
    const barra = $("[data-previa-faixa]"), texto = $("[data-previa-texto]"), tempo = $("[data-previa-tempo]");
    const campoFim = $("[data-faixa-fim]");
    const lerFim = () => {
      const m = campoFim.value.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/);
      if (m) return new Date(+m[3], m[2] - 1, +m[1], +m[4], +m[5]).getTime();
      const d = new Date(); d.setHours(23, 59, 59, 0); return d.getTime();
    };
    const pad = (n) => String(n).padStart(2, "0");
    const relogio = () => {
      const r = Math.max(0, Math.floor((lerFim() - Date.now()) / 1000));
      const dias = Math.floor(r / 86400);
      tempo.textContent = `${dias ? dias + "d " : ""}${pad(Math.floor((r % 86400) / 3600))}:${pad(Math.floor((r % 3600) / 60))}:${pad(r % 60)}`;
    };
    const atualizar = () => {
      texto.textContent = $("[data-faixa-texto]").value || "Texto da faixa";
      barra.style.setProperty("--faixa-fundo", $("[data-faixa-fundo]").value);
      barra.style.setProperty("--faixa-texto", $("[data-faixa-cor]").value);
      tempo.hidden = !$("[data-faixa-contagem]").checked;
      barra.classList.toggle("desligada", !$("[data-faixa-ativa]").checked);
      relogio();
    };
    formFaixa.addEventListener("input", atualizar);
    formFaixa.addEventListener("change", atualizar);
    atualizar(); setInterval(relogio, 1000);
  }

  /* tempo do carrossel */
  const faixaTempo = $("[data-tempo]");
  if (faixaTempo) {
    const barra = $("[data-previa-barra]");
    faixaTempo.addEventListener("input", () => {
      $("[data-tempo-valor]").textContent = `${faixaTempo.value} s`;
      barra.style.setProperty("--duracao", `${faixaTempo.value}s`);
      barra.style.animation = "none"; void barra.offsetWidth; barra.style.animation = "";
    });
  }

  /* ================================================ formulário do banner */
  const formBanner = $("[data-form-banner]");
  if (formBanner) {
    const previa = $("[data-previa-banner]");
    const fotos = { imagem: $('[data-foto="imagem"] [data-foto-previa]').getAttribute("src") || "",
                    imagem_celular: $('[data-foto="imagem_celular"] [data-foto-previa]').getAttribute("src") || "" };
    const valor = (nome) => formBanner.querySelector(`[name="${nome}"]:checked`)?.value || formBanner.querySelector(`[name="${nome}"]`)?.value || "";
    const desenhar = () => {
      const tela = valor("_tela");
      previa.dataset.telaAtual = tela;
      previa.style.setProperty("--fundo", valor("cor_fundo"));
      previa.classList.toggle("escuro", valor("tema") === "escuro");
      previa.classList.toggle("centro", valor("alinhamento") === "centro");
      const img = $("[data-pb-img]", previa);
      const src = tela === "cel" ? (fotos.imagem_celular || fotos.imagem) : fotos.imagem;
      if (img.getAttribute("src") !== src) { if (src) img.src = src; else img.removeAttribute("src"); }
      img.hidden = !src;
      $("[data-pb-chapeu]", previa).textContent = valor("chapeu");
      $("[data-pb-titulo]", previa).textContent = valor("titulo") || "Título do banner";
      $("[data-pb-subtitulo]", previa).textContent = valor("subtitulo");
      const botao = $("[data-pb-botao]", previa);
      botao.textContent = valor("botao_texto") ? `${valor("botao_texto")} →` : "";
      botao.hidden = !valor("botao_texto");
    };
    formBanner.addEventListener("input", desenhar);
    formBanner.addEventListener("change", desenhar);

    // destino do botão: lista pronta ou endereço livre
    const destino = $("[data-destino]"), destinoTexto = $("[data-destino-texto]");
    destino.addEventListener("change", () => {
      const outro = destino.value === "outro";
      destinoTexto.hidden = !outro;
      if (!outro) destinoTexto.value = destino.value; else { destinoTexto.value = ""; destinoTexto.focus(); }
    });

    // imagens: arrastar, escolher, pré-visualizar e remover
    $$("[data-foto]").forEach((zona) => {
      const campo = zona.dataset.foto, entrada = $('input[type="file"]', zona), img = $("[data-foto-previa]", zona);
      const remover = $(`[data-remover-foto-banner="${campo}"]`), flag = $(`[data-remover-campo="${campo}"]`);
      const mostrar = (arquivo) => {
        if (!arquivo || !arquivo.type.startsWith("image/")) return toast("Escolha um arquivo de imagem.", "erro");
        if (arquivo.size > 8 * 1024 * 1024) return toast("A imagem passa de 8 MB.", "erro");
        const url = URL.createObjectURL(arquivo);
        img.src = url; img.hidden = false; zona.classList.add("tem-foto"); remover.hidden = false; flag.value = "0";
        fotos[campo] = url; zona.closest(".campo").classList.remove("erro");
        desenhar();
      };
      entrada.addEventListener("change", () => mostrar(entrada.files[0]));
      ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("sobre"); }));
      ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, () => zona.classList.remove("sobre")));
      zona.addEventListener("drop", (e) => {
        e.preventDefault();
        const arquivo = e.dataTransfer.files[0];
        if (!arquivo) return;
        const dt = new DataTransfer(); dt.items.add(arquivo); entrada.files = dt.files;
        mostrar(arquivo);
      });
      remover.addEventListener("click", () => {
        entrada.value = ""; img.hidden = true; img.removeAttribute("src"); zona.classList.remove("tem-foto");
        remover.hidden = true; flag.value = "1"; fotos[campo] = ""; desenhar();
      });
    });

    formBanner.addEventListener("submit", (e) => {
      const titulo = $('[name="titulo"]', formBanner);
      const semFoto = !fotos.imagem;
      if (titulo.value.trim().length < 2 || semFoto) {
        e.preventDefault();
        [titulo.value.trim().length < 2 && titulo.closest(".campo"), semFoto && $('[data-foto="imagem"]').closest(".campo")]
          .filter(Boolean).forEach((c) => { c.classList.add("erro"); c.classList.remove("tremer"); void c.offsetWidth; c.classList.add("tremer"); });
        toast("Preencha o título e envie a imagem para computador.", "erro");
        return;
      }
      $('button[type="submit"]', formBanner).classList.add("carregando");
    });
    desenhar();
  }
})();
