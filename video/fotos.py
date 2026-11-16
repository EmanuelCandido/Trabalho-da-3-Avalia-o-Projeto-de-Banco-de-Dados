"""Gera as fotos do produto que é cadastrado ao vivo no vídeo (Suéter Tricô Vinho).

Parte das fotos do Tricô de Algodão (verde) da própria loja e troca só a cor da peça:
pixels verdes e saturados viram vinho; o fundo bege e a pele quase não mudam.
Rodar: python video/fotos.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "static" / "img" / "produtos"
DESTINO = Path(__file__).resolve().parent / "assets"


def recolorir(caminho, saida, matiz=0.965, sat_extra=0.10, luz=0.82):
    img = Image.open(caminho).convert("RGB")
    orig = np.asarray(img).astype(np.float32)
    hsv = np.asarray(img.convert("HSV")).astype(np.float32) / 255.0
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # máscara suave da peça: matiz oliva, saturação mínima e tom escuro
    # (a peça: matiz ~0,15, saturada e escura; fundo e calça: matiz ~0,08, pouco saturados e claros)
    dist = np.abs(h - 0.15)
    m_h = np.clip(1 - (dist - 0.04) / 0.03, 0, 1)
    m_s = np.clip((s - 0.22) / 0.12, 0, 1)
    m_v = np.clip((0.58 - v) / 0.15, 0, 1)
    m = (m_h * m_s * m_v)[..., None]
    # cor nova calculada em HSV e misturada em RGB (misturar matiz atravessaria o azul)
    nova = np.stack([np.full_like(h, matiz), np.clip(s * 1.05 + sat_extra, 0, 1), np.clip(v * luz, 0, 1)], -1)
    nova_rgb = np.asarray(Image.fromarray((nova * 255).round().astype(np.uint8), "HSV").convert("RGB")).astype(np.float32)
    out = orig * (1 - m) + nova_rgb * m
    Image.fromarray(out.round().clip(0, 255).astype(np.uint8)).save(saida, quality=92)
    return saida


if __name__ == "__main__":
    DESTINO.mkdir(exist_ok=True)
    for nome, alvo in [("trico-de-algodao-2.webp", "sueter-trico-vinho-1.jpg"),
                       ("trico-de-algodao.webp", "sueter-trico-vinho-2.jpg")]:
        print(recolorir(ORIGEM / nome, DESTINO / alvo))
