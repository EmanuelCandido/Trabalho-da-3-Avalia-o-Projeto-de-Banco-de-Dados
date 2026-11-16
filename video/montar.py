"""Monta o vídeo final a partir da captura (video/capturar.py).

A página video/render/index.html desenha cada quadro em função do tempo; o Chrome (Playwright) tira a
foto de cada quadro e manda direto para o ffmpeg. Vários Chromes renderizam trechos em paralelo e os
trechos são emendados no fim. Depois os efeitos sonoros são sintetizados e mixados (sons.py).

Uso:
    python video/montar.py                          # vídeo completo em video/saida/NOMA-demo.mp4
    python video/montar.py --quadros 3 40.5 120     # só fotos desses instantes, para revisar
    python video/montar.py --de 30 --ate 60         # só um trecho (prévia rápida)
"""
import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import async_playwright

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
import sons  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
TRABALHO = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "noma-video"


def carregar_dados(captura):
    cap = json.loads((captura / "captura.json").read_text(encoding="utf-8"))
    for nome, aba in cap["abas"].items():
        aba["url"] = (captura / nome).as_uri() + "/"
    prod = RAIZ / "static" / "img" / "produtos"
    u = lambda n: (prod / n).as_uri()  # noqa: E731
    fotos = {
        "abertura": [u("polo-1.webp"), u("vestido-midi-linho.webp"), u("camisa-de-linho.webp"), u("bolsa-meia-lua.webp"),
                     u("oculos-solar-duna-2.webp")],
        "fim": [u("trico-de-algodao.webp"), u("blusa-gola-alta-feminina-essencial.webp"),
                (AQUI / "assets" / "sueter-trico-vinho-1.jpg").as_uri(), u("bone-algodao.webp"), u("cinto-de-couro.webp")],
    }
    return {"captura": cap, "fotos": fotos}


async def abrir(pw, dados):
    nav = await pw.chromium.launch(channel="chrome", headless=True,
                                   args=["--force-color-profile=srgb", "--allow-file-access-from-files",
                                         "--disable-gpu-vsync", "--hide-scrollbars"])
    page = await nav.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    await page.goto((AQUI / "render" / "index.html").as_uri(), wait_until="load")
    # carrega todos os pesos das fontes antes (senão o texto fica invisível no 1º quadro em que aparece)
    await page.evaluate("""() => Promise.all([400, 500, 600, 650, 700].flatMap((w) => [
        document.fonts.load(`${w} 40px Inter`, 'AÁÇçãõéêíóú N→·'),
        document.fonts.load(`${w} 20px "JetBrains Mono"`, 'Aa_→')]))""")
    await page.evaluate("document.fonts.ready.then(() => true)")
    info = await page.evaluate("d => iniciar(d)", dados)
    await page.evaluate("Promise.all([...document.images].map((i) => i.decode().catch(() => null)))")
    if erros:
        raise RuntimeError("Erro na página de montagem: " + erros[0])
    cdp = await page.context.new_cdp_session(page)
    return nav, page, cdp, info


async def foto(page, cdp, t, qualidade=94):
    await page.evaluate(f"seek({t:.6f})")
    r = await cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": qualidade})
    return base64.b64decode(r["data"])


async def trecho(pw, dados, i0, i1, fps, arquivo, progresso, n):
    nav, page, cdp, _ = await abrir(pw, dados)
    proc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg",
                             "-i", "-", "-vf", "scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p",
                             "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                             "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                             "-r", str(fps), "-movflags", "+faststart", str(arquivo)], stdin=subprocess.PIPE)
    try:
        for i in range(i0, i1):
            img = await foto(page, cdp, i / fps)
            await asyncio.to_thread(proc.stdin.write, img)
            progresso[n] = i - i0 + 1
    finally:
        proc.stdin.close()
        await asyncio.to_thread(proc.wait)
        await nav.close()


async def mostrar_progresso(progresso, total, inicio):
    while True:
        feito = sum(progresso.values())
        dt = time.time() - inicio
        resta = (total - feito) * dt / feito if feito else 0
        print(f"\r  {feito}/{total} quadros  ({feito / total:5.1%})  faltam ~{resta / 60:4.1f} min", end="", flush=True)
        if feito >= total:
            print()
            return
        await asyncio.sleep(2)


async def principal(a):
    captura = Path(a.captura)
    dados = carregar_dados(captura)
    async with async_playwright() as pw:
        if a.quadros:
            nav, page, cdp, info = await abrir(pw, dados)
            pasta = Path(a.pasta_quadros)
            pasta.mkdir(parents=True, exist_ok=True)
            for t in a.quadros:
                (pasta / f"q_{t:07.2f}.jpg").write_bytes(await foto(page, cdp, t, 90))
            await nav.close()
            print(f"Duração total: {info['duracao']:.1f} s  ·  quadros em {pasta}")
            for nome, ini, fim in info["segmentos"]:
                print(f"  {ini:7.2f} – {fim:7.2f}  {nome}")
            return

        nav, page, cdp, info = await abrir(pw, dados)
        cues = await page.evaluate("sons()")
        await nav.close()
        duracao = info["duracao"]
        print(f"Duração do vídeo: {duracao:.1f} s ({duracao / 60:.2f} min)")
        for nome, ini, fim in info["segmentos"]:
            print(f"  {ini:7.2f} – {fim:7.2f}  {nome}")
        de = a.de or 0.0
        ate = min(a.ate or duracao, duracao)
        n0, n1 = int(round(de * a.fps)), int(round(ate * a.fps))
        tmp = TRABALHO / "render"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        partes = []
        passo = (n1 - n0 + a.trabalhos - 1) // a.trabalhos
        for k in range(a.trabalhos):
            i0, i1 = n0 + k * passo, min(n1, n0 + (k + 1) * passo)
            if i0 < i1:
                partes.append((i0, i1, tmp / f"parte_{k:02d}.mp4"))
        progresso = {k: 0 for k in range(len(partes))}
        inicio = time.time()
        print(f"Renderizando {n1 - n0} quadros a {a.fps} fps com {len(partes)} Chromes…")
        await asyncio.gather(mostrar_progresso(progresso, n1 - n0, inicio),
                             *[trecho(pw, dados, i0, i1, a.fps, arq, progresso, k) for k, (i0, i1, arq) in enumerate(partes)])

    lista = tmp / "partes.txt"
    lista.write_text("".join(f"file '{p.as_posix()}'\n" for _, _, p in partes), encoding="utf-8")
    video = tmp / "video.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(video)],
                   check=True)
    print("Mixando os efeitos sonoros…")
    trilha = [dict(c, t=c["t"] - de) for c in cues if de - 0.2 <= c["t"] <= ate]
    audio = sons.mixar(trilha, ate - de, tmp / "trilha.wav")
    saida = Path(a.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(saida)], check=True)
    print(f"Pronto: {saida}  ({(time.time() - inicio) / 60:.1f} min)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--captura", default=str(TRABALHO / "captura"), help="pasta criada pelo capturar.py")
    ap.add_argument("--saida", default=str(AQUI / "saida" / "NOMA-demo.mp4"))
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--trabalhos", type=int, default=max(2, min(6, (os.cpu_count() or 4) // 3)))
    ap.add_argument("--de", type=float, help="começa neste segundo (prévia)")
    ap.add_argument("--ate", type=float, help="termina neste segundo (prévia)")
    ap.add_argument("--quadros", type=float, nargs="*", help="só salva as fotos destes instantes")
    ap.add_argument("--pasta-quadros", default=str(TRABALHO / "quadros"))
    asyncio.run(principal(ap.parse_args()))
