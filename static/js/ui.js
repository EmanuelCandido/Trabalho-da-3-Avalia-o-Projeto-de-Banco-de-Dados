/* NOMA — componentes de formulário próprios (no lugar dos controles nativos do navegador)
   - <select>               -> lista suspensa estilizada, com teclado (setas, Enter, Esc, letras)
   - input[type=color]      -> amostra + paleta + campo hexadecimal
   - input[data-data-hora]  -> máscara dd/mm/aaaa hh:mm (sem o calendário nativo)
   - input[type=number]     -> botões − e +
   O <select>/<input> original continua no formulário (escondido), então o envio e os eventos "change" não mudam.
   Uso: NomaUI.melhorar(elementoRaiz) depois de inserir HTML novo na página. */
(() => {
  "use strict";
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const seta = '<svg class="i" aria-hidden="true"><use href="#i-baixo"/></svg>';
  let idSeq = 0;
  let aberto = null;

  function fecharAberto() {
    if (!aberto) return;
    aberto.classList.remove("aberto");
    aberto.querySelector("[aria-expanded]")?.setAttribute("aria-expanded", "false");
    aberto = null;
  }
  document.addEventListener("pointerdown", (e) => { if (aberto && !aberto.contains(e.target)) fecharAberto(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && aberto) { const b = aberto.querySelector("button"); fecharAberto(); b?.focus(); } });

  function disparar(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /* ------------------------------------------------ lista suspensa */
  function melhorarSelect(sel) {
    if (sel.dataset.ui || sel.multiple || sel.dataset.nativo !== undefined) return;
    sel.dataset.ui = "1";
    const caixa = document.createElement("div");
    caixa.className = "ui-select" + (sel.className ? " " + sel.className : "");
    const id = "ui-lista-" + (++idSeq);
    caixa.innerHTML = `<button type="button" class="ui-select__botao" aria-haspopup="listbox" aria-expanded="false" aria-controls="${id}"><span class="ui-select__valor"></span>${seta}</button><ul class="ui-select__lista" role="listbox" id="${id}" tabindex="-1"></ul>`;
    sel.parentNode.insertBefore(caixa, sel);
    caixa.append(sel);
    sel.classList.add("ui-nativo");
    sel.tabIndex = -1;
    sel.setAttribute("aria-hidden", "true");
    const botao = caixa.querySelector("button"), lista = caixa.querySelector("ul"), valor = caixa.querySelector(".ui-select__valor");
    const rotulo = sel.getAttribute("aria-label") || sel.closest("label")?.querySelector("span")?.textContent?.trim();
    if (rotulo) botao.setAttribute("aria-label", rotulo);
    let foco = -1;

    const desenhar = () => {
      lista.innerHTML = [...sel.options].map((o, i) =>
        `<li role="option" id="${id}-${i}" data-i="${i}" aria-selected="${o.selected}" class="${o.disabled ? "desab" : ""}">${o.textContent.replace(/[<>&]/g, "")}</li>`).join("");
      valor.textContent = sel.options[sel.selectedIndex]?.textContent || "";
    };
    const marcarFoco = (i) => {
      foco = Math.max(0, Math.min(sel.options.length - 1, i));
      $$("li", lista).forEach((li, j) => li.classList.toggle("foco", j === foco));
      lista.querySelector(`[data-i="${foco}"]`)?.scrollIntoView({ block: "nearest" });
      botao.setAttribute("aria-activedescendant", `${id}-${foco}`);
    };
    const abrir = () => {
      if (sel.disabled) return;
      fecharAberto();
      desenhar();
      caixa.classList.add("aberto");
      botao.setAttribute("aria-expanded", "true");
      aberto = caixa;
      // abre para cima se não couber embaixo
      const r = botao.getBoundingClientRect();
      caixa.classList.toggle("para-cima", innerHeight - r.bottom < Math.min(280, lista.scrollHeight + 16) && r.top > innerHeight - r.bottom);
      marcarFoco(sel.selectedIndex);
    };
    const escolher = (i) => {
      if (sel.options[i]?.disabled) return;
      const mudou = sel.selectedIndex !== i;
      sel.selectedIndex = i;
      desenhar();
      fecharAberto();
      botao.focus();
      if (mudou) { disparar(sel); caixa.classList.remove("mudou"); void caixa.offsetWidth; caixa.classList.add("mudou"); }
    };

    botao.addEventListener("click", () => (caixa.classList.contains("aberto") ? fecharAberto() : abrir()));
    lista.addEventListener("click", (e) => { const li = e.target.closest("li"); if (li) escolher(+li.dataset.i); });
    lista.addEventListener("pointermove", (e) => { const li = e.target.closest("li"); if (li) marcarFoco(+li.dataset.i); });
    let busca = "", buscaTimer;
    botao.addEventListener("keydown", (e) => {
      const estaAberto = caixa.classList.contains("aberto");
      if (["ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault();
        if (!estaAberto) return abrir();
        marcarFoco(foco + (e.key === "ArrowDown" ? 1 : -1));
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        estaAberto ? escolher(foco) : abrir();
      } else if (e.key === "Tab" && estaAberto) {
        fecharAberto();
      } else if (e.key.length === 1) {
        busca += e.key.toLowerCase(); clearTimeout(buscaTimer); buscaTimer = setTimeout(() => { busca = ""; }, 600);
        const i = [...sel.options].findIndex((o) => o.textContent.trim().toLowerCase().startsWith(busca));
        if (i >= 0) estaAberto ? marcarFoco(i) : escolher(i);
      }
    });
    sel.addEventListener("change", desenhar);
    desenhar();
  }

  /* ------------------------------------------------ seletor de cor */
  const PALETA = ["#0b0b0c", "#3a3a40", "#6b6b72", "#a1a1a8", "#e4e4e8", "#ffffff",
    "#1d3a52", "#2463eb", "#5b8def", "#1f9d6b", "#5c6b3a", "#8a7a52",
    "#b07a4f", "#a4622d", "#c2410c", "#d93a3a", "#7a1f2b", "#b8a7a2",
    "#e3d8c8", "#efe9dc", "#cdbb98", "#f2b01e", "#f5d0c5", "#d9fdd3"];
  function melhorarCor(inp) {
    if (inp.dataset.ui) return;
    inp.dataset.ui = "1";
    const inicial = /^#[0-9a-f]{6}$/i.test(inp.value) ? inp.value.toLowerCase() : "#1a1a1a";
    inp.type = "hidden";
    inp.value = inicial;
    const caixa = document.createElement("div");
    caixa.className = "ui-cor";
    caixa.innerHTML = `<button type="button" class="ui-cor__amostra" aria-haspopup="dialog" aria-expanded="false" aria-label="Escolher cor"><i></i></button>
      <div class="ui-cor__painel" role="dialog" aria-label="Escolher cor">
        <div class="ui-cor__grade">${PALETA.map((c) => `<button type="button" style="--c:${c}" data-c="${c}" aria-label="${c}"></button>`).join("")}</div>
        <label class="ui-cor__hex"><span>#</span><input type="text" maxlength="7" spellcheck="false" aria-label="Código da cor"></label>
      </div>`;
    inp.parentNode.insertBefore(caixa, inp);
    caixa.append(inp);
    const amostra = caixa.querySelector(".ui-cor__amostra"), hex = caixa.querySelector(".ui-cor__hex input");
    const aplicar = (c, avisar = true) => {
      c = c.toLowerCase();
      inp.value = c;
      amostra.style.setProperty("--c", c);
      hex.value = c.slice(1);
      $$("[data-c]", caixa).forEach((b) => b.classList.toggle("marcada", b.dataset.c === c));
      if (avisar) disparar(inp);
    };
    amostra.addEventListener("click", () => {
      if (caixa.classList.contains("aberto")) return fecharAberto();
      fecharAberto(); caixa.classList.add("aberto"); amostra.setAttribute("aria-expanded", "true"); aberto = caixa;
    });
    caixa.querySelector(".ui-cor__grade").addEventListener("click", (e) => { const b = e.target.closest("[data-c]"); if (b) { aplicar(b.dataset.c); fecharAberto(); amostra.focus(); } });
    hex.addEventListener("input", () => {
      const v = "#" + hex.value.replace(/[^0-9a-f]/gi, "").slice(0, 6);
      if (v.length === 7) aplicar(v);
    });
    aplicar(inicial, false);
  }

  /* ------------------------------------------------ data e hora com máscara */
  function melhorarDataHora(inp) {
    if (inp.dataset.ui) return;
    inp.dataset.ui = "1";
    inp.setAttribute("inputmode", "numeric");
    inp.setAttribute("placeholder", inp.getAttribute("placeholder") || "dd/mm/aaaa hh:mm");
    inp.setAttribute("maxlength", "16");
    inp.addEventListener("input", () => {
      const d = inp.value.replace(/\D/g, "").slice(0, 12);
      let v = d.slice(0, 2);
      if (d.length > 2) v += "/" + d.slice(2, 4);
      if (d.length > 4) v += "/" + d.slice(4, 8);
      if (d.length > 8) v += " " + d.slice(8, 10);
      if (d.length > 10) v += ":" + d.slice(10, 12);
      inp.value = v;
    });
  }
  // Atalhos de data: <button data-atalho="+6h" data-alvo="#campo">
  const doisDig = (n) => String(n).padStart(2, "0");
  const formatar = (d) => `${doisDig(d.getDate())}/${doisDig(d.getMonth() + 1)}/${d.getFullYear()} ${doisDig(d.getHours())}:${doisDig(d.getMinutes())}`;
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-atalho]");
    if (!b) return;
    const alvo = document.querySelector(b.dataset.alvo);
    if (!alvo) return;
    const a = b.dataset.atalho, d = new Date();
    d.setSeconds(0, 0);
    if (a === "limpar") alvo.value = "";
    else if (a === "hoje") { d.setHours(23, 59); alvo.value = formatar(d); }
    else if (a === "agora") alvo.value = formatar(d);
    else {
      const m = a.match(/^\+(\d+)([hd])$/);
      if (m) { d.setTime(d.getTime() + +m[1] * (m[2] === "h" ? 3600e3 : 86400e3)); alvo.value = formatar(d); }
    }
    disparar(alvo);
    alvo.classList.remove("piscou"); void alvo.offsetWidth; alvo.classList.add("piscou");
  });

  /* ------------------------------------------------ número com − e + */
  function melhorarNumero(inp) {
    if (inp.dataset.ui) return;
    inp.dataset.ui = "1";
    const caixa = document.createElement("div");
    caixa.className = "ui-numero";
    inp.parentNode.insertBefore(caixa, inp);
    caixa.innerHTML = `<button type="button" aria-label="Diminuir" data-passo="-1"><svg class="i" aria-hidden="true"><use href="#i-menos"/></svg></button>`;
    caixa.append(inp);
    caixa.insertAdjacentHTML("beforeend", `<button type="button" aria-label="Aumentar" data-passo="1"><svg class="i" aria-hidden="true"><use href="#i-mais"/></svg></button>`);
    caixa.addEventListener("click", (e) => {
      const b = e.target.closest("[data-passo]");
      if (!b) return;
      const passo = +(inp.step || 1) * +b.dataset.passo;
      let v = (parseFloat(inp.value) || 0) + passo;
      if (inp.min !== "") v = Math.max(+inp.min, v);
      if (inp.max !== "") v = Math.min(+inp.max, v);
      inp.value = v;
      disparar(inp);
    });
  }

  function melhorarFaixa(inp) {
    if (inp.dataset.ui) return;
    inp.dataset.ui = "1";
    const pintar = () => inp.style.setProperty("--pct", ((inp.value - inp.min) / ((inp.max - inp.min) || 1)) * 100 + "%");
    inp.addEventListener("input", pintar);
    pintar();
  }

  function melhorar(raiz = document) {
    $$('input[type="range"]', raiz).forEach(melhorarFaixa);
    $$("select", raiz).forEach(melhorarSelect);
    $$('input[type="color"]', raiz).forEach(melhorarCor);
    $$("input[data-data-hora]", raiz).forEach(melhorarDataHora);
    $$('input[type="number"]', raiz).forEach(melhorarNumero);
  }
  window.NomaUI = { melhorar };
  melhorar();
  // HTML inserido depois (linhas de cor, filtros trocados sem recarregar etc.) também ganha os componentes.
  new MutationObserver((mudancas) => {
    for (const m of mudancas) m.addedNodes.forEach((n) => { if (n.nodeType === 1) melhorar(n.parentNode || n); });
  }).observe(document.body, { childList: true, subtree: true });
})();
