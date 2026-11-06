"""Converte as fotos da loja para WebP em tamanhos responsivos (mais leves em redes lentas).

Uso: python scripts/otimizar_imagens.py   (lê os .jpg/.png de static/img e grava os .webp ao lado)

- produtos/X.webp      até 900 px  (página do produto e telas grandes)
- produtos/X-480.webp  480 px      (cards, carrinho e miniaturas)
- banners/X.webp       1920 px e banners/X-1280.webp  (computador)
- banners/X-m.webp     900 px      (versão vertical do celular)
"""
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent / "static" / "img"


def salvar(im, destino, largura, qualidade):
    copia = im.copy()
    copia.thumbnail((largura, largura * 2), Image.LANCZOS)
    copia.save(destino, "WEBP", quality=qualidade, method=6)
    return destino.stat().st_size


def main():
    antes = depois = 0
    for origem in sorted(RAIZ.rglob("*")):
        if origem.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        im = Image.open(origem).convert("RGB")
        antes += origem.stat().st_size
        base = origem.with_suffix("")
        if origem.parent.name == "produtos":
            depois += salvar(im, base.with_suffix(".webp"), 900, 78)
            depois += salvar(im, Path(f"{base}-480.webp"), 480, 72)
        elif origem.parent.name == "banners" and not base.name.endswith("-m"):
            depois += salvar(im, base.with_suffix(".webp"), 1920, 76)
            depois += salvar(im, Path(f"{base}-1280.webp"), 1280, 74)
        else:
            depois += salvar(im, base.with_suffix(".webp"), 900, 76)
        origem.unlink()
    print(f"Originais: {antes / 1024:.0f} KB -> WebP (todos os tamanhos): {depois / 1024:.0f} KB")


if __name__ == "__main__":
    main()
