"""Efeitos sonoros do vídeo (gravações reais de bibliotecas livres) e a mixagem da trilha.

A referência não tem música nem narração: só sons de interface sincronizados com a ação e silêncio
entre eles. Cada evento da montagem (clique, tecla, whoosh, pop, tique, sucesso) vira um som aqui.

De onde vêm os sons (créditos em sons/CREDITOS.md):
- clique, pop e tique: Kenney, pacotes "UI Audio" e "Interface Sounds" (CC0), em sons/kenney/;
- tecla: "Keyboard Soundpack #1", da OpenGameArt, gravado num teclado Cherry KC 1000 (CC0), em sons/teclado/;
- whoosh e sucesso: Mixkit (licença Mixkit, livre para usar em vídeos, mas sem redistribuir os arquivos soltos).
  Por isso eles não ficam no repositório: são baixados na primeira execução para sons/mixkit/.

Cada amostra é recortada no ataque (o whoosh é alinhado pelo pico), tem o volume igualado pelo trecho
mais forte e ganha uma pequena variação de afinação e volume a cada uso, para não soar repetida.
"""
import subprocess
import urllib.request
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

SR = 48000
RNG = np.random.default_rng(7)
PASTA = Path(__file__).resolve().parent / "sons"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

MIXKIT = {  # id → nome no site
    "whoosh": {168: "Fast sweep transition", 2608: "Fast whoosh transition", 1468: "Fast sweeping transition"},
    "sucesso": {2867: "Confirmation tone"},
}
KENNEY = {
    "pop": ["drop_002", "drop_003", "drop_004"],
    "tique": ["tick_002", "tick_001", "select_002"],
}

# volume de cada tipo: RMS dos 50 ms mais fortes, em dBFS (igual ao equilíbrio da trilha anterior)
NIVEIS = {"clique": -27, "tecla": -37, "whoosh": -22, "pop": -21, "tique": -27, "sucesso": -18}
PICO_WHOOSH = 0.27  # o evento marca o início do movimento; o pico do whoosh cai 0,27 s depois


def _ler(caminho):
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(caminho), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).astype(np.float64)


def _mixkit(i):
    destino = PASTA / "mixkit" / f"{i}.mp3"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        pedido = urllib.request.Request(f"https://assets.mixkit.co/active_storage/sfx/{i}/{i}-preview.mp3",
                                        headers={"User-Agent": "Mozilla/5.0"})
        destino.write_bytes(urllib.request.urlopen(pedido, timeout=30).read())
    return destino


def _recortar(x, limiar_db=-45, maximo=None):
    m = np.abs(x).max(1)
    idx = np.where(m > m.max() * 10 ** (limiar_db / 20))[0]
    x = x[idx[0]:idx[-1] + 1]
    if maximo and len(x) > maximo * SR:
        x = x[:int(maximo * SR)]
        x[-int(0.08 * SR):] *= np.linspace(1, 0, int(0.08 * SR))[:, None]
    x[:16] *= np.linspace(0, 1, 16)[:, None]  # sem estalo no corte
    return x


def _nivelar(x, alvo_db):
    w = int(0.05 * SR)
    p = (x ** 2).mean(1)
    e = np.convolve(p, np.ones(w) / w, "valid").max() if len(p) > w else p.mean()
    return x * 10 ** ((alvo_db - 10 * np.log10(e)) / 20)


def _afinar(x, fator):
    """Muda a velocidade (e o tom) em poucos por cento, como pegar outra tecla ou outro mouse."""
    n = int(len(x) / fator)
    pos = np.arange(n) * fator
    return np.stack([np.interp(pos, np.arange(len(x)), x[:, c]) for c in range(2)], 1)


def _banco():
    k = PASTA / "kenney"
    clique, solta = _recortar(_ler(k / "mouseclick1.ogg")), _recortar(_ler(k / "mouserelease1.ogg"))
    banco = {
        "clique": [(clique, solta)],
        "tecla": [_nivelar(_recortar(_ler(p)), NIVEIS["tecla"]) for p in sorted((PASTA / "teclado").glob("keypress-*.wav"))],
        "pop": [_nivelar(_recortar(_ler(k / f"{n}.ogg")), NIVEIS["pop"]) for n in KENNEY["pop"]],
        "tique": [_nivelar(_recortar(_ler(k / f"{n}.ogg")), NIVEIS["tique"]) for n in KENNEY["tique"]],
        "whoosh": [_nivelar(_recortar(_ler(_mixkit(i)), -40, 1.2), NIVEIS["whoosh"]) for i in MIXKIT["whoosh"]],
        "sucesso": [_nivelar(_recortar(_ler(_mixkit(i)), -50, 1.6), NIVEIS["sucesso"]) for i in MIXKIT["sucesso"]],
    }
    return banco


def _clique(par, rng):
    """Apertar e soltar o botão do mouse: dois estalos reais, o de soltar 70–100 ms depois e mais fraco."""
    aperta, solta = par
    k = int(rng.uniform(0.07, 0.10) * SR)
    x = np.zeros((k + len(solta), 2))
    x[:len(aperta)] += aperta
    x[k:] += solta * rng.uniform(0.5, 0.7)
    return _nivelar(x, NIVEIS["clique"])


def mixar(cues, duracao, caminho):
    n = int((duracao + 1) * SR)
    mix = np.zeros((n, 2))
    banco = _banco()
    for i, c in enumerate(cues):
        tipo = c["tipo"]
        variantes = banco.get(tipo)
        if not variantes:
            continue
        if tipo == "clique":
            x = _clique(variantes[0], RNG)
        elif tipo == "tecla":
            x = variantes[RNG.integers(len(variantes))] * RNG.uniform(0.75, 1.05)
        else:
            x = variantes[i % len(variantes)]
        if tipo in ("clique", "tecla", "pop", "tique"):
            x = _afinar(x, RNG.uniform(0.97, 1.03))
        x = x * float(c.get("vol", 1))
        inicio = c["t"]
        if tipo == "whoosh":
            pico = np.argmax(np.convolve(np.abs(x).mean(1), np.ones(480) / 480, "same")) / SR
            inicio += PICO_WHOOSH - pico
        k = int(inicio * SR)
        if k < 0:
            x, k = x[-k:], 0
        if k >= n:
            continue
        m = min(len(x), n - k)
        mix[k:k + m] += x[:m]
    pico = np.max(np.abs(mix)) or 1
    limite = 10 ** (-1.5 / 20)
    if pico > limite:  # limitador simples: nunca passa de -1,5 dBFS
        mix *= limite / pico
    dados = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(dados.tobytes())
    return caminho
