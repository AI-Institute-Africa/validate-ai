"""Train the deep detector: a small CNN over the forensic planes, exported to ONNX.

    pip install -e ".[detect-train]"     # torch, torchvision, onnx (not in the default image)
    python -m training.detect.train_cnn --data DIR --kind receipt --out MODEL_DIR
    python -m training.detect.train_cnn --data DIR --kind receipt --out MODEL_DIR --smoke

NOT RUN IN THE BUILD ENVIRONMENT. The environment this was written in has no PyTorch, so the first
run on a machine that has it is this script's first test. Run it with --smoke first (a few steps on
the data you have) before spending hours. No accuracy figure is claimed for it anywhere.

What it does, in order (the reasons are in docs/authenticity-detectors.md):
  1. self-supervised contrastive pretraining (SimCLR style) on the GENUINE training pictures only,
     so the backbone learns what this deployment's documents look like without any fake labels;
  2. supervised fine-tuning on genuine and forged training pictures, including evasion-style copies
     (re-saved, rescaled, noised, re-photographed) so a re-saved genuine picture stays genuine;
  3. calibration, the escalation threshold and the conformal uncertainty band on the held-out
     calibration part, using the same tested code as the classical trainer (fit.operating_point);
  4. export to ONNX with the calibration baked in (the model outputs a probability), a check that
     ONNX Runtime reproduces the PyTorch output, optional int8 quantisation kept only if the
     calibration-set AUC barely moves, and a manifest entry with the file's SHA-256.

The input is exactly what the server builds: `app.detect.onnx_runtime.to_tensor` on the picture with
the manifest's channels (default rgb + noise + fft + ela = 6 planes). Training and serving cannot
drift apart because they call the same function.

Not built yet: the genuine-only autoencoder score, distillation from a larger teacher, and static
int8 quantisation with calibration data. The docs say so.
"""

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from app.detect.manifest import MANIFEST_NAME
from app.detect.onnx_runtime import to_tensor
from training.detect import dataset, fit

CHANNELS = ("rgb", "noise", "fft", "ela")
DEFAULT_LABEL = {"receipt": "forged", "doc": "forged", "face": "synthetic_face"}


def _torch():
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise SystemExit(
            "this needs PyTorch: pip install -e '.[detect-train]' (it is not in the default image)"
        ) from exc
    return torch, nn


def build_model(in_channels: int):
    torch, nn = _torch()

    def block(cin: int, cout: int, stride: int):
        return nn.Sequential(  # depthwise-separable convolution: small and fast on a CPU
            nn.Conv2d(cin, cin, 3, stride, 1, groups=cin, bias=False),
            nn.BatchNorm2d(cin),
            nn.ReLU6(inplace=True),
            nn.Conv2d(cin, cout, 1, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU6(inplace=True),
        )

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv2d(in_channels, 24, 3, 2, 1, bias=False),
                nn.BatchNorm2d(24),
                nn.ReLU6(inplace=True),
                block(24, 48, 2),
                block(48, 64, 2),
                block(64, 96, 2),
                block(96, 128, 2),
                nn.AdaptiveAvgPool2d(1),
                nn.Flatten(),
            )
            self.project = nn.Sequential(nn.Linear(128, 128), nn.ReLU(), nn.Linear(128, 64))
            self.head = nn.Linear(128, 1)

        def forward(self, x):  # the raw logit
            return self.head(self.encoder(x)).squeeze(-1)

        def embed(self, x):  # for the contrastive loss
            z = self.project(self.encoder(x))
            return nn.functional.normalize(z, dim=1)

    return Net()


def nt_xent(z1, z2, temperature: float = 0.2):
    """SimCLR loss: two views of the same picture are positives, everything else is negative."""
    torch, _ = _torch()
    n = z1.shape[0]
    z = torch.cat([z1, z2])
    sim = z @ z.T / temperature
    sim.fill_diagonal_(-1e9)
    target = torch.cat([torch.arange(n, 2 * n), torch.arange(0, n)]).to(z.device)
    return torch.nn.functional.cross_entropy(sim, target)


def augment(img: Image.Image, rnd: random.Random) -> Image.Image:
    """A realistic variation of a genuine picture: crop, re-save, blur, brightness."""
    w, h = img.size
    f = rnd.uniform(0.85, 1.0)
    cw, ch = int(w * f), int(h * f)
    x, y = rnd.randrange(0, w - cw + 1), rnd.randrange(0, h - ch + 1)
    out = img.crop((x, y, x + cw, y + ch)).resize((w, h), Image.Resampling.BILINEAR)
    if rnd.random() < 0.5:
        out = out.filter(ImageFilter.GaussianBlur(rnd.uniform(0.3, 1.0)))
    return dataset.evasion_variants(out, rnd)[0][1] if rnd.random() < 0.5 else out


def tensors(folder: Path, samples: list[dataset.Sample], size: int) -> np.ndarray:
    return np.concatenate(
        [to_tensor(Image.open(folder / s.path).convert("RGB"), size, CHANNELS) for s in samples]
    )


def train(
    folder: Path,
    kind: str,
    out_dir: Path,
    *,
    size: int = 128,
    pretrain_epochs: int = 8,
    epochs: int = 20,
    batch: int = 32,
    lr: float = 1e-3,
    max_false_flag: float = 0.05,
    alpha: float = 0.1,
    seed: int = 0,
    max_minutes: float = 120.0,
    int8: bool = False,
    smoke: bool = False,
) -> dict:
    torch, _ = _torch()
    if smoke:
        pretrain_epochs, epochs, batch = 1, 2, 8
    deadline = time.monotonic() + max_minutes * 60
    rnd = random.Random(seed)  # noqa: S311 - reproducible training, not security
    torch.manual_seed(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = [s for s in dataset.read_index(folder / "index.jsonl") if s.kind == kind]
    parts = dataset.split_by_source(samples, seed)
    tr, ca = parts["train"], parts["calib"]
    if smoke:
        tr = tr[:64]
    genuine = [s for s in tr if s.label == 0]
    if not genuine or all(s.label == 0 for s in tr):
        raise SystemExit("the training part needs both genuine and forged pictures")
    tr_aug = [*tr, *dataset.build_evasion(tr, folder, seed + 1)]

    model = build_model(len(CHANNELS) + 2)  # rgb is 3 planes, each forensic channel 1
    ckpt = out_dir / f"checkpoint-{kind}.pt"
    start_phase, start_epoch = "pretrain", 0
    if ckpt.is_file():  # resume a long run that was stopped
        state = torch.load(ckpt, weights_only=False)
        model.load_state_dict(state["model"])
        start_phase, start_epoch = state["phase"], state["epoch"]
        print(f"resuming at {start_phase} epoch {start_epoch}")

    def save(phase: str, epoch: int) -> None:
        torch.save({"model": model.state_dict(), "phase": phase, "epoch": epoch}, ckpt)

    # 1. contrastive pretraining on genuine pictures only
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    if start_phase == "pretrain":
        for epoch in range(start_epoch, pretrain_epochs):
            model.train()
            order = rnd.sample(range(len(genuine)), len(genuine))
            for i in range(0, len(order) - 1, batch):
                imgs = [
                    Image.open(folder / genuine[j].path).convert("RGB")
                    for j in order[i : i + batch]
                ]
                if len(imgs) < 2:
                    continue
                v1 = torch.from_numpy(
                    np.concatenate([to_tensor(augment(m, rnd), size, CHANNELS) for m in imgs])
                )
                v2 = torch.from_numpy(
                    np.concatenate([to_tensor(augment(m, rnd), size, CHANNELS) for m in imgs])
                )
                loss = nt_xent(model.embed(v1), model.embed(v2))
                opt.zero_grad()
                loss.backward()
                opt.step()
            save("pretrain", epoch + 1)
            print(f"pretrain epoch {epoch + 1}/{pretrain_epochs} loss {float(loss):.4f}")
            if time.monotonic() > deadline:
                print("stopped by --max-minutes during pretraining")
                break
        start_epoch = 0

    # 2. supervised fine-tuning, forged = 1
    x = torch.from_numpy(tensors(folder, tr_aug, size))
    y = torch.tensor([float(s.label) for s in tr_aug])
    pos_weight = torch.tensor(max(1.0, float((y == 0).sum()) / max(1.0, float((y == 1).sum()))))
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.Adam(model.parameters(), lr=lr * 0.5)
    for epoch in range(start_epoch if start_phase == "finetune" else 0, epochs):
        model.train()
        perm = torch.randperm(len(x))
        for i in range(0, len(x), batch):
            idx = perm[i : i + batch]
            if len(idx) < 2:
                continue  # BatchNorm needs more than one example
            loss = lossf(model(x[idx]), y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
        save("finetune", epoch + 1)
        print(f"fine-tune epoch {epoch + 1}/{epochs} loss {float(loss):.4f}")
        if time.monotonic() > deadline:
            print("stopped by --max-minutes during fine-tuning")
            break

    # 3. calibration part: Platt, threshold, conformal band
    model.eval()
    with torch.no_grad():
        raw = (
            model(torch.from_numpy(tensors(folder, ca, size))).numpy()
            if ca
            else np.zeros(0, dtype=np.float32)
        )
    yca = np.array([float(s.label) for s in ca])
    op = fit.operating_point(raw.astype(np.float64), yca, max_false_flag, alpha)
    a, b = op["platt"]

    # 4. export with the calibration inside, check ONNX Runtime agrees, optionally quantise
    class Calibrated(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, t):
            return torch.sigmoid(a * self.m(t) + b).reshape(-1)

    path = out_dir / f"cnn_{kind}.onnx"
    dummy = torch.zeros(1, len(CHANNELS) + 2, size, size)
    torch.onnx.export(
        Calibrated(model).eval(),
        dummy,
        str(path),
        input_names=["x"],
        output_names=["p"],
        dynamic_axes={"x": {0: "batch"}, "p": {0: "batch"}},
        opset_version=17,
    )
    import onnxruntime as ort

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    probe = tensors(folder, (ca or tr)[:4], size)
    with torch.no_grad():
        want = Calibrated(model).eval()(torch.from_numpy(probe)).numpy()
    got = np.array(
        [sess.run(None, {"x": probe[i : i + 1]})[0].reshape(-1)[0] for i in range(len(probe))]
    )
    if not np.allclose(want, got, atol=1e-3):
        raise SystemExit(f"ONNX output differs from PyTorch: {want} vs {got}; not installed")
    quant_note = "not quantised"
    if int8:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        q_path = out_dir / f"cnn_{kind}.int8.onnx"
        quantize_dynamic(str(path), str(q_path), weight_type=QuantType.QInt8)
        qsess = ort.InferenceSession(str(q_path), providers=["CPUExecutionProvider"])
        if ca and len(set(yca.tolist())) == 2:
            full = np.array([sess.run(None, {"x": tensors(folder, [s], size)})[0][0] for s in ca])
            quant = np.array([qsess.run(None, {"x": tensors(folder, [s], size)})[0][0] for s in ca])
            from training.detect.evaluate import auc_np

            drop = auc_np(full[yca == 1], full[yca == 0]) - auc_np(quant[yca == 1], quant[yca == 0])
            if drop <= 0.01:
                path, quant_note = q_path, f"int8 kept (calibration AUC drop {drop:.4f})"
            else:
                quant_note = f"int8 rejected (calibration AUC drop {drop:.4f}); fp32 kept"
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    version = f"cnn-{kind}-{'+'.join(CHANNELS)}-{sha[:8]}"
    entry = {
        "name": f"cnn_{kind}",
        "file": path.name,
        "version": version,
        "sha256": sha,
        "format": "onnx",
        "label": DEFAULT_LABEL[kind],
        "input": {"size": size, "channels": list(CHANNELS)},
        "tta": 1,
        "card": f"model-card-{kind}.md",
    }
    if op["threshold"] is not None:
        entry["threshold"] = op["threshold"]
    if op["band"] is not None:
        entry["uncertain_band"] = list(op["band"])
    manifest_path = out_dir / MANIFEST_NAME
    manifest = (
        json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"detectors": {}}
    )
    manifest["detectors"][kind] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    report = {
        "kind": kind,
        "version": version,
        "sha256": sha,
        "train_pictures": len(tr_aug),
        "threshold": op["threshold"],
        "uncertain_band": op["band"],
        "platt": [a, b],
        "ece": op["ece"],
        "quantisation": quant_note,
        "smoke": smoke,
    }
    (out_dir / f"train-report-{kind}.json").write_text(json.dumps(report, indent=2) + "\n")
    ckpt.unlink(missing_ok=True)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, help="folder made by build_dataset")
    ap.add_argument("--kind", required=True, choices=sorted(DEFAULT_LABEL))
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--pretrain-epochs", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-false-flag", type=float, default=0.05)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-minutes", type=float, default=120.0)
    ap.add_argument("--int8", action="store_true", help="try dynamic int8 quantisation")
    ap.add_argument(
        "--smoke", action="store_true", help="a few steps on tiny data, to check it runs"
    )
    a = ap.parse_args()
    report = train(
        Path(a.data),
        a.kind,
        Path(a.out),
        size=a.size,
        pretrain_epochs=a.pretrain_epochs,
        epochs=a.epochs,
        batch=a.batch,
        max_false_flag=a.max_false_flag,
        alpha=a.alpha,
        seed=a.seed,
        max_minutes=a.max_minutes,
        int8=a.int8,
        smoke=a.smoke,
    )
    json.dump(report, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
