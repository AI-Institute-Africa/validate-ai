"""Genuine-looking source pictures for the demo and the self-test (the fictional demo documents).

These are drawn by app/demo/art.py and say SAMPLE on their face. They exist so the whole training
loop can run on a laptop with nothing downloaded. A model trained on them has seen only these.
"""

import io
import random

from PIL import Image

from app.demo import art
from app.devtools import ecocash_fields

BRANDS = ("ecocash", "mpesa", "bank", "innbucks", "omari", "onemoney")


def _open(png: bytes, scale: float) -> Image.Image:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    return img.resize((max(64, int(img.width * scale)), max(64, int(img.height * scale))))


def demo_genuine(
    kind: str, n: int, seed: int = 0, scale: float = 0.5
) -> tuple[list[Image.Image], list[str]]:
    """`n` source pictures and a group label for each (template, persona)."""
    rnd = random.Random(seed)  # noqa: S311 - reproducible test data
    keys = list(art.PERSONAS)
    images: list[Image.Image] = []
    groups: list[str] = []
    for i in range(n):
        if kind == "receipt":
            brand = BRANDS[i % len(BRANDS)]
            fields = ecocash_fields(
                txn=f"PP2610{i % 90:02d}.{1400 + i % 99}.A{rnd.randrange(10000, 99999)}",
                amount=f"{rnd.randrange(5, 400)}.{rnd.randrange(0, 99):02d}",
            )
            images.append(_open(art.receipt_png(fields, brand=brand, salt=i), scale))
            groups.append(brand)
        elif kind == "doc":
            key = keys[i % len(keys)]
            number = f"VD-{1000000 + rnd.randrange(8_000_000)}"
            png = art.id_card_png(art.id_fields(key, number), key, seed=rnd.randrange(1, 10**6))
            images.append(_open(png, scale))
            groups.append(key)
        elif kind == "face":
            key = keys[i % len(keys)]
            images.append(_open(art.selfie_png(key, seed=rnd.randrange(1, 10**6)), scale))
            groups.append(key)
        else:
            raise ValueError(f"unknown kind {kind!r}")
    return images, groups
