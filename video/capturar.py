"""Grava o sistema NOMA de verdade para o vídeo de demonstração (docs/VIDEO.md).

O Playwright abre o Chrome com dois perfis (admin e cliente), executa o roteiro sozinho e grava as
duas abas com o screencast do Chrome. Cada movimento do mouse, clique, tecla, endereço e área de
elemento usado fica num eventos.json, que o montar.py usa para desenhar o cursor e o zoom.

Uso (com a loja rodando ou não; se não estiver, o script sobe o servidor):
    python video/capturar.py

A senha do admin é lida do .env (ADMIN_EMAIL / ADMIN_SENHA) ou pedida no terminal.
Ela aparece mascarada na gravação e não é gravada em nenhum arquivo.
"""
import argparse
import asyncio
import base64
import getpass
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from playwright.async_api import async_playwright

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = Path(__file__).resolve().parent / "assets"
SAIDA_PADRAO = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "noma-video" / "captura"
VIEW = {"width": 1440, "height": 900}
DPR = 2

PRODUTO = {
    "nome": "Suéter Tricô Vinho",
    "descricao": "Tricô de algodão com ponto inglês, gola careca e punhos canelados. Aquece sem pesar.",
    "preco": "289,90",
    "promo": "239,90",
    "estoque": "24",
    "material": "Algodão",
    "composicao": "100% algodão. Lavar à mão e secar à sombra.",
    "atributos": [("Gola", "Careca", True), ("Ponto", "Inglês", False), ("Caimento", "Regular", True)],
    "cor": ("Vinho", "#7a1f2b"),
    "tamanhos": ["P", "M", "G", "GG"],
    "fotos": ["sueter-trico-vinho-1.jpg", "sueter-trico-vinho-2.jpg"],
}
CLIENTE = {"nome": "Mariana Costa", "obs": "É presente, pode embalar?"}
SENHA_ERRADA = "noma1234"
RITMO = 1.35  # multiplica as pausas: tempo para ler as legendas do vídeo

EVENTOS = []
T0 = time.time()


def log(tipo, **dados):
    EVENTOS.append({"t": round(time.time() - T0, 4), "tipo": tipo, **dados})


def marca(nome):
    log("marca", nome=nome)
    print(f"  [{time.time() - T0:6.1f}s] {nome}")


def suave(u):
    return 4 * u * u * u if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


async def ate(t_abs):
    espera = t_abs - time.time()
    if espera > 0:
        await asyncio.sleep(espera)


class Aba:
    """Uma aba gravada: screencast + mouse/teclado com registro de eventos."""

    def __init__(self, nome, page, pasta):
        self.nome, self.page, self.pasta = nome, page, pasta
        self.quadros = []
        self.mouse = (VIEW["width"] * 0.62, VIEW["height"] * 0.72)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._tarefas = set()
        page.on("framenavigated", lambda f: f == page.main_frame and log("url", aba=nome, url=f.url))

    async def gravar(self):
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._quadro)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": VIEW["width"] * DPR,
                                                    "maxHeight": VIEW["height"] * DPR, "everyNthFrame": 1})

    def _quadro(self, ev):
        agora = time.time()
        ts = ev.get("metadata", {}).get("timestamp") or agora
        if abs(ts - agora) > 2:  # relógio do Chrome diferente: usa a hora de chegada
            ts = agora
        nome = f"{len(self.quadros):06d}.jpg"
        self.quadros.append([round(ts - T0, 4), nome])
        t = asyncio.ensure_future(self._salvar(nome, ev["data"], ev["sessionId"]))
        self._tarefas.add(t)
        t.add_done_callback(self._tarefas.discard)

    async def _salvar(self, nome, dados, sessao):
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": sessao})
        except Exception:
            pass
        await asyncio.to_thread((self.pasta / nome).write_bytes, base64.b64decode(dados))

    async def parar(self):
        try:
            await self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        if self._tarefas:
            await asyncio.gather(*self._tarefas, return_exceptions=True)

    # ------------------------------------------------------------ ações
    async def ir(self, url):
        await self.page.goto(url, wait_until="load")
        await self.page.wait_for_timeout(400)

    async def caixa(self, alvo):
        loc = self.page.locator(alvo) if isinstance(alvo, str) else alvo
        await loc.first.wait_for(state="visible", timeout=20000)
        return await loc.first.bounding_box()

    async def foco(self, alvo=None, nome=None, folga=40, zoom_max=2.0, altura_max=None):
        """Registra a área que a câmera deve enquadrar (None = página inteira)."""
        await self.forma()  # a página pode ter mudado embaixo do mouse
        if alvo is None:
            log("foco", aba=self.nome, nome=nome, caixa=None)
            return
        b = await self.caixa(alvo)
        altura = min(b["height"], altura_max) if altura_max else b["height"]
        log("foco", aba=self.nome, nome=nome, caixa=[b["x"] - folga, b["y"] - folga, b["width"] + 2 * folga,
                                                    altura + 2 * folga], zoom_max=zoom_max)

    async def area(self, nome, alvo, folga=0):
        b = await self.caixa(alvo)
        log("area", aba=self.nome, nome=nome, caixa=[b["x"] - folga, b["y"] - folga, b["width"] + 2 * folga,
                                                    b["height"] + 2 * folga])

    async def forma(self):
        x, y = self.mouse
        f = await self.page.evaluate("""([x, y]) => {
            const el = document.elementFromPoint(x, y);
            if (!el) return 'seta';
            const c = getComputedStyle(el).cursor;
            if (el.closest('input:not([type=checkbox]):not([type=radio]):not([type=file]),textarea')) return 'texto';
            if (c === 'pointer' || el.closest('a,button,summary,label,[role=button],[role=option],select')) return 'mao';
            if (c === 'text') return 'texto';
            return 'seta';
        }""", [x, y])
        log("cursor", aba=self.nome, forma=f)

    async def mover(self, x, y, dur=None):
        x0, y0 = self.mouse
        dist = math.hypot(x - x0, y - y0)
        if dist < 1:
            return
        dur = dur or min(1.05, 0.32 + dist / 1700)
        # arco leve: ponto de controle deslocado para o lado
        nx, ny = -(y - y0) / dist, (x - x0) / dist
        curva = random.uniform(-0.12, 0.12) * dist
        cx, cy = (x0 + x) / 2 + nx * curva, (y0 + y) / 2 + ny * curva
        log("cursor", aba=self.nome, forma="seta")
        n = max(4, int(dur * 60))
        inicio = time.time()
        for i in range(1, n + 1):
            u = suave(i / n)
            px = (1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x
            py = (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y
            await self.page.mouse.move(px, py)
            log("mouse", aba=self.nome, x=round(px, 1), y=round(py, 1))
            await ate(inicio + dur * i / n)
        self.mouse = (x, y)
        await self.forma()

    async def apontar(self, alvo, dx=0.5, dy=0.5):
        b = await self.caixa(alvo)
        jx = random.uniform(-0.08, 0.08) * min(b["width"], 60)
        jy = random.uniform(-0.08, 0.08) * min(b["height"], 30)
        await self.mover(b["x"] + b["width"] * dx + jx, b["y"] + b["height"] * dy + jy)

    async def clicar(self, alvo, espera=0.35, dx=0.5, dy=0.5):
        await self.apontar(alvo, dx, dy)
        await asyncio.sleep(0.14)
        log("clique", aba=self.nome, x=self.mouse[0], y=self.mouse[1])
        await self.page.mouse.down()
        await asyncio.sleep(0.08)
        await self.page.mouse.up()
        await asyncio.sleep(espera)

    async def digitar(self, texto, rapido=False):
        base = (0.028, 0.06) if rapido else (0.05, 0.11)
        for ch in texto:
            await self.page.keyboard.type(ch)
            log("tecla", aba=self.nome)
            pausa = random.uniform(*base)
            if ch in " ,." and random.random() < 0.35:
                pausa += random.uniform(0.05, 0.16)
            await asyncio.sleep(pausa)
        await asyncio.sleep(0.25)

    async def tecla(self, nome):
        await self.page.keyboard.press(nome)
        log("tecla", aba=self.nome)

    async def rolar(self, alvo=None, y=None, dur=0.9, bloco="center", margem=0):
        """Rolagem suave da página até um elemento (ou posição) com curva ease-in-out."""
        if alvo is not None:
            loc = self.page.locator(alvo).first if isinstance(alvo, str) else alvo.first
            await loc.wait_for(state="attached", timeout=20000)
            y = await loc.evaluate("""(el, [bloco, margem]) => {
                const r = el.getBoundingClientRect();
                const alvo = bloco === 'start' ? r.top - margem : r.top + r.height / 2 - innerHeight / 2;
                return Math.max(0, Math.min(scrollY + alvo, document.documentElement.scrollHeight - innerHeight));
            }""", [bloco, margem])
        log("rolar", aba=self.nome, dur=dur)
        await self.page.evaluate("""([y, d]) => new Promise((ok) => {
            const y0 = scrollY, t0 = performance.now();
            const passo = (agora) => {
                let u = Math.min(1, (agora - t0) / d);
                u = u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
                window.scrollTo({ top: y0 + (y - y0) * u, behavior: 'instant' });
                u < 1 ? requestAnimationFrame(passo) : ok();
            };
            requestAnimationFrame(passo);
        })""", [y, dur * 1000])
        await asyncio.sleep(0.15)

    async def pausa(self, s):
        await asyncio.sleep(s * RITMO)


# ------------------------------------------------------------------ roteiro

async def roteiro(admin, loja, base, cred, teste):
    p = PRODUTO
    # Preparação (fora do vídeo): loja do cliente aberta em Novidades, ainda sem o produto novo
    await loja.ir(base + "/novidades")
    await loja.page.mouse.move(*loja.mouse)
    await admin.page.mouse.move(*admin.mouse)
    await admin.ir(base + "/admin/login")
    await asyncio.sleep(1.0)

    # ---------------------------------------------------------- 1. login
    marca("login_inicio")
    await admin.area("form_login", ".login__form", folga=28)
    await admin.foco(".login__form", "form_login", folga=60)
    await admin.pausa(0.8)
    if not teste:
        await admin.clicar('input[name="email"]')
        await admin.digitar(cred["email"])
        marca("login_senha_errada")
        await admin.clicar('input[name="senha"]')
        await admin.digitar(SENHA_ERRADA)
        marca("login_entrar_errado")
        await admin.clicar('.login__form button[type="submit"]', espera=0.1)
        await admin.page.wait_for_load_state("load")
        await admin.page.locator(".aviso--erro").wait_for(timeout=20000)
        marca("login_erro")
        await admin.area("form_login", ".login__form", folga=28)
        await admin.foco(".login__form", "form_login_erro", folga=60)
        await admin.pausa(3.2)
        marca("login_expandir")
        await admin.foco(None, "login_pagina")
        await admin.pausa(1.6)
        marca("login_senha_certa")
        await admin.clicar('input[name="senha"]')
        await admin.digitar(cred["senha"])
        marca("login_entrar_certo")
        await admin.clicar('.login__form button[type="submit"]', espera=0.1)
        try:
            await admin.page.wait_for_url("**/admin/", timeout=30000)
        except Exception:
            raise SystemExit("O login não entrou no painel. Confira ADMIN_EMAIL e ADMIN_SENHA no .env "
                             "(ou se o acesso foi bloqueado por tentativas: espere 15 min) e rode de novo.")
    else:  # ensaio: digita sem enviar e entra pela sessão de teste do servidor de ensaio
        await admin.clicar('input[name="email"]')
        await admin.digitar("admin@exemplo.com")
        marca("login_senha_errada")
        await admin.clicar('input[name="senha"]')
        await admin.digitar(SENHA_ERRADA)
        marca("login_entrar_errado")
        await admin.pausa(1.0)
        marca("login_erro")
        await admin.pausa(1.5)
        marca("login_expandir")
        await admin.foco(None, "login_pagina")
        await admin.pausa(1.6)
        marca("login_senha_certa")
        await admin.pausa(1.2)
        marca("login_entrar_certo")
        await admin.ir(base + "/__sessao_teste")
    await admin.page.wait_for_load_state("load")
    marca("dashboard")
    await admin.foco(None, "dashboard")
    await admin.pausa(1.6)
    await admin.foco(".bancos", "bancos", folga=24)
    await admin.pausa(3.0)
    await admin.foco(".numeros-adm", "kpis", folga=24)
    await admin.pausa(2.6)
    acessos = admin.page.locator("section.cartao", has_text="Acessos ao painel")
    await admin.rolar(acessos, dur=1.0)
    await admin.foco(acessos, "acessos", folga=20)
    await admin.pausa(3.6)
    marca("dashboard_fim")

    # ---------------------------------------------------------- 2. cadastro
    await admin.foco(None, "lateral")
    await admin.clicar('.lateral a:has-text("Produtos")', espera=0.1)
    await admin.page.wait_for_url("**/admin/produtos", timeout=20000)
    marca("produtos_lista")
    await admin.pausa(1.6)
    await admin.foco(".topo-lista, .contagem", "lista_topo", folga=30)
    await admin.clicar('main a.botao:has-text("Novo produto")', espera=0.1)
    await admin.page.wait_for_url("**/admin/produtos/novo", timeout=20000)
    await admin.page.wait_for_load_state("load")
    marca("form_inicio")
    await admin.foco(None, "form")
    await admin.pausa(1.2)

    info = admin.page.locator("section.cartao", has_text="Informações")
    await admin.foco(info, "form_info", folga=24)
    await admin.clicar('input[name="nome"]')
    await admin.digitar(p["nome"])
    await admin.clicar('textarea[name="descricao"]')
    await admin.digitar(p["descricao"], rapido=True)
    await admin.pausa(0.4)

    preco = admin.page.locator("section.cartao", has_text="Preço e estoque")
    await admin.rolar(preco, dur=0.7)
    await admin.foco(preco, "form_preco", folga=24)
    await admin.clicar('input[name="preco"]')
    await admin.digitar(p["preco"])
    await admin.clicar('input[name="preco_promocional"]')
    await admin.digitar(p["promo"])
    await admin.pausa(0.6)
    await admin.clicar('input[name="estoque"]')
    await admin.tecla("Control+a")
    await admin.digitar(p["estoque"])
    await admin.clicar('input[name="material"]')
    await admin.digitar(p["material"])
    await admin.tecla("Escape")
    await admin.clicar('input[name="composicao"]')
    await admin.digitar(p["composicao"], rapido=True)
    await admin.pausa(0.4)

    attrs = admin.page.locator("section.cartao", has_text="Atributos extras")
    await admin.rolar(attrs, dur=0.8)
    await admin.foco(attrs, "form_atributos", folga=24)
    await admin.pausa(0.6)
    for nome, valor, sugestao in p["atributos"]:
        if sugestao:
            await admin.clicar(f'[data-sugestao="{nome}"]', espera=0.3)
        else:
            await admin.clicar("[data-add-attr]", espera=0.3)
            await admin.digitar(nome)
            await admin.tecla("Tab")
        await admin.digitar(valor)
    await admin.foco(attrs, "form_atributos_cheio", folga=24)
    await admin.pausa(1.2)

    fotos = admin.page.locator("section.cartao", has_text="Fotos")
    await admin.rolar(fotos, dur=0.9)
    await admin.foco(fotos, "form_fotos", folga=24)
    await admin.pausa(0.5)
    async with admin.page.expect_file_chooser() as escolha:
        await admin.clicar("[data-soltar]", espera=0.1)
    await asyncio.sleep(0.5)
    await (await escolha.value).set_files([str(ASSETS / f) for f in p["fotos"]])
    log("upload", aba="admin")
    await admin.pausa(1.0)
    await admin.foco(fotos, "form_fotos_cheio", folga=24)
    await admin.pausa(1.4)

    cores = admin.page.locator("section.cartao", has_text="Cores")
    await admin.rolar(cores, dur=0.8)
    await admin.foco(cores, "form_cores", folga=24)
    await admin.clicar("[data-add-cor]", espera=0.3)
    await admin.digitar(p["cor"][0])
    await admin.clicar("[data-cores] .cor-linha:last-child .ui-cor__amostra", espera=0.35)
    await admin.clicar(f'[data-cores] .cor-linha:last-child [data-c="{p["cor"][1]}"]', espera=0.4)
    for t in p["tamanhos"]:
        await admin.clicar(f'.tamanhos-adm label:has(input[value="{t}"])', espera=0.18)
    await admin.pausa(0.6)

    vitrine = admin.page.locator("section.cartao", has_text="Vitrine")
    await admin.rolar(vitrine, dur=0.8)
    await admin.foco(vitrine, "form_vitrine", folga=24)
    await admin.clicar('.chave-linha:has-text("Novidades") .chave', espera=0.5)
    await admin.pausa(0.5)
    previa = admin.page.locator("section.previa-card")
    await admin.rolar(previa, dur=0.8)
    await admin.foco(previa, "form_previa", folga=40)
    await admin.pausa(2.4)
    await admin.foco(".salvar", "form_salvar", folga=60)
    await admin.pausa(0.5)
    marca("salvar")
    await admin.clicar('.salvar button[type="submit"]', espera=0.1)
    await admin.page.wait_for_url("**/admin/produtos?novo=*", timeout=40000)
    await admin.page.wait_for_load_state("load")
    marca("produto_salvo")
    await admin.foco(None, "lista_salvo")
    await admin.pausa(1.6)
    nova = admin.page.locator("tr.linha--nova")
    await nova.wait_for(timeout=10000)
    await admin.pausa(0.8)
    await admin.foco(nova, "linha_nova", folga=30, zoom_max=1.6)
    await admin.pausa(2.0)
    await admin.clicar("tr.linha--nova [data-ver-doc]", espera=0.2)
    await admin.page.locator("[data-doc-json]").wait_for(state="visible", timeout=10000)
    await admin.pausa(0.6)
    marca("documento")
    await admin.foco('[data-modal="documento"] [data-doc-json]', "documento", folga=30)
    await admin.pausa(2.0)
    # rola o JSON até os atributos
    await admin.page.evaluate("""() => new Promise((ok) => {
        const pre = document.querySelector('[data-doc-json]');
        const linhas = pre.textContent.split('\\n');
        const i = linhas.findIndex((l) => l.includes('"atributos"'));
        const alvo = Math.max(0, (i / linhas.length) * pre.scrollHeight - 40);
        const y0 = pre.scrollTop, t0 = performance.now(), d = 1400;
        const passo = (agora) => { let u = Math.min(1, (agora - t0) / d); u = u < .5 ? 4*u*u*u : 1 - Math.pow(-2*u+2, 3)/2;
            pre.scrollTop = y0 + (alvo - y0) * u; u < 1 ? requestAnimationFrame(passo) : ok(); };
        requestAnimationFrame(passo);
    })""")
    log("rolar", aba="admin", dur=1.4)
    await admin.pausa(3.2)
    await admin.foco(None, "documento_fim")
    await admin.clicar('[data-modal="documento"] [data-fechar-modal]', espera=0.6)
    marca("cadastro_fim")

    # ---------------------------------------------------------- 3. loja atualizada
    await admin.pausa(0.5)
    marca("loja_antes")
    await loja.apontar('header a:has-text("Novidades")')
    await loja.pausa(2.2)
    marca("loja_recarregar")
    await loja.clicar('header a:has-text("Novidades")', espera=0.1)
    await loja.page.wait_for_load_state("load")
    await loja.pausa(1.2)
    card = loja.page.locator(f'a:has-text("{p["nome"]}")').first
    await card.wait_for(timeout=20000)
    marca("loja_produto_visivel")
    await loja.pausa(2.2)
    await loja.apontar(card.locator("img").first)
    await loja.pausa(1.6)
    marca("busca")
    await loja.clicar("header [data-abrir-busca]", espera=0.5)
    await loja.digitar("tricô vinho")
    await loja.page.locator("[data-busca-resultados] a.sugestao").first.wait_for(timeout=15000)
    await loja.pausa(0.5)
    await loja.foco("[data-busca-resultados]", "busca_resultados", folga=30, zoom_max=1.7)
    await loja.pausa(2.4)
    await loja.clicar("[data-busca-resultados] a.sugestao", espera=0.1)
    await loja.page.wait_for_url("**/produto/**", timeout=20000)
    await loja.page.wait_for_load_state("load")
    marca("pagina_produto")
    await loja.foco(None, "pagina_produto")
    await loja.pausa(2.4)
    await loja.foco(".info__fixo", "info_produto", folga=20, zoom_max=1.5, altura_max=560)
    await loja.pausa(2.6)
    carac = loja.page.locator("details.sanfona", has_text="Características")
    await loja.rolar(carac, dur=0.9)
    await loja.clicar(carac.locator("summary"), espera=0.6)
    await loja.foco(carac, "caracteristicas", folga=30, zoom_max=1.8)
    await loja.pausa(3.0)
    marca("loja_fim")

    # ---------------------------------------------------------- 4. compra
    marca("compra_inicio")
    await loja.foco(None, "produto_compra")
    await loja.rolar(".info__fixo", dur=0.9, bloco="start", margem=90)
    await loja.foco(".compra", "compra", folga=30, zoom_max=1.6)
    await loja.clicar('label.tam:has(input[value="M"])', espera=0.5)
    await loja.clicar("[data-qtd] [data-mais]", espera=0.5)
    await loja.clicar("[data-adicionar]", espera=0.1)
    marca("adicionou_1")
    await loja.page.locator("[data-gaveta].aberta, [data-gaveta][aria-hidden='false']").first.wait_for(timeout=10000)
    await loja.pausa(0.8)
    await loja.foco("[data-gaveta]", "gaveta", folga=10, zoom_max=1.4)
    await loja.pausa(2.8)
    await loja.foco(None, "gaveta_fecha")
    fechar = loja.page.locator('[data-gaveta] [data-fechar-gaveta], [data-gaveta] button[aria-label*="Fechar"]').first
    await loja.clicar(fechar, espera=0.6)
    marca("acessorios")
    await loja.clicar('header a:has-text("Acessórios")', espera=0.1)
    await loja.page.wait_for_url("**/acessorios", timeout=20000)
    await loja.page.wait_for_load_state("load")
    await loja.pausa(1.4)
    cinto = loja.page.locator('a:has-text("Cinto de couro")').first
    await loja.rolar(cinto, dur=0.9)
    await loja.clicar(cinto, espera=0.1)
    await loja.page.wait_for_url("**/produto/**", timeout=20000)
    await loja.page.wait_for_load_state("load")
    await loja.pausa(1.2)
    marca("vistos")
    vistos = loja.page.locator("[data-vistos]")
    await loja.rolar(vistos, dur=1.4)
    await loja.pausa(0.6)
    await loja.foco(vistos, "vistos", folga=20, zoom_max=1.5)
    await loja.pausa(3.2)
    await loja.foco(None, "vistos_fim")
    await loja.rolar(".info__fixo", dur=1.2, bloco="start", margem=90)
    await loja.pausa(0.3)
    await loja.foco(".compra", "compra_cinto", folga=30, zoom_max=1.5)
    tam = loja.page.locator('label.tam:has(input[value="Único"])')
    if await tam.count():
        await loja.clicar(tam, espera=0.4)
    await loja.clicar("[data-adicionar]", espera=0.1)
    marca("adicionou_2")
    await loja.pausa(1.2)
    await loja.foco("[data-gaveta]", "gaveta_2", folga=10, zoom_max=1.4)
    await loja.pausa(1.4)
    marca("carrinho_qtd")
    item = loja.page.locator('[data-gaveta] article.item', has_text="Cinto").first
    await loja.clicar(item.locator("[data-item-mais]"), espera=1.0)
    await loja.clicar(item.locator("[data-item-menos]"), espera=1.2)
    await loja.pausa(0.6)
    await loja.area("botao_finalizar", "[data-finalizar]", folga=8)
    await loja.foco("[data-finalizar]", "finalizar", folga=120, zoom_max=2.0)
    await loja.pausa(1.0)
    marca("finalizar_clique")
    await loja.clicar("[data-finalizar]", espera=0.2)
    await loja.page.locator("[data-fin-nome]").wait_for(state="visible", timeout=10000)
    await loja.pausa(0.8)
    marca("finalizar_modal")
    fin = loja.page.locator("[data-fin]")
    await loja.foco(fin, "modal_fin", folga=24)
    await loja.clicar("[data-fin-nome]")
    await loja.digitar(CLIENTE["nome"])
    await loja.clicar("[data-fin-obs]")
    await loja.digitar(CLIENTE["obs"])
    await loja.pausa(1.0)
    await loja.foco("[data-fin-previa]", "previa_msg", folga=40, zoom_max=1.9)
    await loja.pausa(3.4)
    await loja.foco(fin, "modal_fin_2", folga=24)
    marca("enviar_pedido")
    await loja.clicar("[data-enviar-pedido]", espera=0.1)
    await loja.page.locator("[data-sucesso]").wait_for(state="visible", timeout=30000)
    marca("pedido_ok")
    await loja.foco("[data-sucesso]", "sucesso", folga=40, zoom_max=1.8)
    await loja.page.wait_for_url("**whatsapp.com/**", timeout=30000, wait_until="commit")
    try:
        await loja.page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    try:
        await loja.page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    marca("whatsapp")
    url = loja.page.url
    texto = parse_qs(urlparse(url).query).get("text", [""])[0]
    log("whatsapp", aba="loja", url=url, texto=texto, numero=parse_qs(urlparse(url).query).get("phone", [""])[0])
    await loja.foco(None, "whats_pagina")
    await loja.pausa(1.8)
    caixa_msg = loja.page.get_by_text(texto.split("\n")[0][:40], exact=False).first
    try:
        await loja.foco(caixa_msg, "whats_msg", folga=50, zoom_max=1.9)
    except Exception:
        pass
    await loja.pausa(4.2)
    marca("compra_fim")

    # ---------------------------------------------------------- 5. pedido no Supabase
    marca("pedidos_inicio")
    await admin.foco(None, "admin_volta")
    await admin.clicar('.lateral a:has-text("Pedidos")', espera=0.1)
    await admin.page.wait_for_url("**/admin/pedidos", timeout=20000)
    await admin.page.wait_for_load_state("load")
    await admin.pausa(1.4)
    primeiro = admin.page.locator("details.pedido").first
    await admin.foco(primeiro, "pedido", folga=20, zoom_max=1.5)
    await admin.clicar(primeiro.locator("summary"), espera=0.8)
    await admin.foco(primeiro, "pedido_aberto", folga=20, zoom_max=1.5)
    await admin.pausa(4.0)
    marca("dashboard_final")
    await admin.foco(None, "dashboard_volta")
    await admin.clicar('.lateral a:has-text("Dashboard")', espera=0.1)
    await admin.page.wait_for_url("**/admin/", timeout=20000)
    await admin.page.wait_for_load_state("load")
    await admin.pausa(1.8)
    await admin.foco(".numeros-adm", "kpis_final", folga=24)
    await admin.pausa(2.6)
    ultimos = admin.page.locator("section.cartao", has_text="Últimos pedidos")
    await admin.foco(ultimos, "ultimos_pedidos", folga=20, zoom_max=1.7)
    await admin.pausa(3.2)
    marca("redis_final")
    vistos_r = admin.page.locator("section.cartao", has_text="Mais vistos")
    await admin.foco(vistos_r, "mais_vistos", folga=20, zoom_max=1.7)
    await admin.pausa(3.0)
    comandos = admin.page.locator("section.cartao", has_text="Comandos recentes no Redis")
    await admin.rolar(comandos, dur=1.1)
    await admin.foco(comandos, "comandos_redis", folga=20, zoom_max=1.7)
    await admin.pausa(3.4)
    marca("fim")
    await admin.pausa(0.8)


# ------------------------------------------------------------------ infraestrutura

def ler_env():
    env = {}
    arq = RAIZ / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


LIMPAR = r"""
import sys
sys.path.insert(0, ".")
from config import Config
from bancos import mongo, redis_store
mongo.init(Config.MONGO_URI, Config.MONGO_DB)
redis_store.init(Config.REDIS_URL, Config.CACHE_TTL)
ids = [str(d["_id"]) for d in mongo.produtos().find({"nome": sys.argv[1]}, {"_id": 1})]
for i in ids:
    mongo.excluir(i)
if ids:
    redis_store.invalidar_cache()
print(len(ids))
"""


def limpar_produto_demo():
    """Apaga o produto de demonstração de uma gravação anterior (o vídeo precisa mostrá-lo sendo criado)."""
    py = RAIZ / ".venv" / "Scripts" / "python.exe"
    r = subprocess.run([str(py if py.exists() else sys.executable), "-c", LIMPAR, PRODUTO["nome"]], cwd=RAIZ,
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print("Aviso: não consegui conferir produtos de gravações anteriores:", r.stderr.strip()[-300:])
    elif r.stdout.strip() not in ("", "0"):
        print(f"Removido o produto de demonstração de uma gravação anterior ({r.stdout.strip()}).")


def no_ar(base):
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


async def simular_pedido(route, base):
    """Modo de teste: não grava pedido no Supabase, só monta a mesma resposta."""
    req = route.request
    corpo = json.loads(req.post_data or "{}")
    resp = await route.fetch(url=base + "/api/mensagem", method="POST", headers=req.headers, post_data=req.post_data)
    texto = (await resp.json())["mensagem"].split("\n\n")[0]
    texto += "\n\nPedido: NOMA-TESTE" + (f"\nNome: {corpo.get('nome')}" if corpo.get("nome") else "")
    texto += f"\nObservação: {corpo['observacao']}" if corpo.get("observacao") else ""
    numero = ler_env().get("WHATSAPP_NUMERO", "5500000000000")
    await route.fulfill(json={"codigo": "NOMA-TESTE", "total": "", "mensagem": texto,
                              "url": f"https://wa.me/{numero}?text={quote(texto)}"})


async def principal(args):
    saida = Path(args.saida)
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    base = args.base.rstrip("/")

    servidor = None
    if not no_ar(base):
        py = RAIZ / ".venv" / "Scripts" / "python.exe"
        print("Subindo a loja em", base)
        servidor = subprocess.Popen([str(py if py.exists() else sys.executable), "app.py"], cwd=RAIZ,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if no_ar(base):
                break
            time.sleep(1)

    limpar_produto_demo()
    cred = {}
    if not args.teste:
        env = ler_env()
        cred["email"] = env.get("ADMIN_EMAIL") or input("E-mail do admin: ").strip()
        cred["senha"] = env.get("ADMIN_SENHA") or getpass.getpass("Senha do admin (não aparece): ")

    async with async_playwright() as pw:
        nav = await pw.chromium.launch(channel="chrome", headless=not args.ver,
                                       args=["--hide-scrollbars", "--force-color-profile=srgb", "--lang=pt-BR"])
        opcoes = dict(viewport=VIEW, device_scale_factor=DPR, locale="pt-BR", timezone_id="America/Fortaleza",
                      reduced_motion="no-preference", color_scheme="light")
        ctx_admin = await nav.new_context(**opcoes)
        ctx_loja = await nav.new_context(**opcoes)
        if args.teste:
            await ctx_loja.route("**/api/pedido", lambda r: simular_pedido(r, base))
        admin = Aba("admin", await ctx_admin.new_page(), saida / "admin")
        loja = Aba("loja", await ctx_loja.new_page(), saida / "loja")
        await admin.gravar()
        await loja.gravar()
        global T0
        print("Gravando…")
        try:
            await roteiro(admin, loja, base, cred, args.teste)
        finally:
            await asyncio.sleep(0.5)
            await admin.parar()
            await loja.parar()
            dados = {"view": VIEW, "dpr": DPR, "base": base, "teste": args.teste,
                     "abas": {a.nome: {"quadros": a.quadros} for a in (admin, loja)}, "eventos": EVENTOS}
            (saida / "captura.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
            await nav.close()
            if servidor:
                servidor.terminate()
    print(f"Pronto: {saida}  ({len(admin.quadros)} quadros do admin, {len(loja.quadros)} da loja)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:5000", help="endereço da loja")
    ap.add_argument("--saida", default=str(SAIDA_PADRAO), help="pasta da captura (fora do OneDrive)")
    ap.add_argument("--ver", action="store_true", help="mostra a janela do Chrome durante a gravação")
    ap.add_argument("--teste", action="store_true",
                    help="ensaio sem login e com pedido simulado (precisa de um servidor de ensaio com /__sessao_teste)")
    asyncio.run(principal(ap.parse_args()))
