"""Выгрузка политики SB3 + VecNormalize в один ONNX-файл со сверкой.

    python export_onnx.py --ckpt M.zip --vecnorm M.pkl --out p.onnx

Отличие от скрипта главы 09 урока 14 — размерность берётся из самой модели,
а в граф кладутся метаданные (откуда взяты веса, размерности, частота): нода
ROS 2 читает их при загрузке и отказывается работать с чужой политикой.
"""
import argparse
import hashlib
import json
import pickle
import time
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from stable_baselines3 import PPO


class ExportedPolicy(torch.nn.Module):
    """Сырое наблюдение среды -> действие в [-1, 1], ровно как predict()."""

    def __init__(self, policy, mean, var, eps, clip_obs, low, high):
        super().__init__()
        self.policy = policy
        self.register_buffer("mean", torch.as_tensor(mean, dtype=torch.float32))
        self.register_buffer("std", torch.sqrt(torch.as_tensor(var, dtype=torch.float32) + eps))
        self.register_buffer("lo", torch.as_tensor(low, dtype=torch.float32))
        self.register_buffer("hi", torch.as_tensor(high, dtype=torch.float32))
        self.clip_obs = float(clip_obs)

    def forward(self, obs):
        z = torch.clamp((obs - self.mean) / self.std, -self.clip_obs, self.clip_obs)
        return torch.clamp(self.policy(z, deterministic=True)[0], self.lo, self.hi)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--vecnorm", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--robot", required=True, help="метка контракта: tsaplya2, quad, ...")
    ap.add_argument("--control-hz", type=float, required=True)
    args = ap.parse_args()

    model = PPO.load(args.ckpt, device="cpu")
    with open(args.vecnorm, "rb") as fh:
        vn = pickle.load(fh)
    obs_dim = int(model.observation_space.shape[0])
    act_dim = int(model.action_space.shape[0])
    if vn.obs_rms.mean.shape != (obs_dim,):
        raise SystemExit(f"статистика {vn.obs_rms.mean.shape} не от этой модели ({obs_dim},)")

    net = ExportedPolicy(model.policy, vn.obs_rms.mean, vn.obs_rms.var, float(vn.epsilon),
                         float(vn.clip_obs), model.action_space.low,
                         model.action_space.high).eval()
    torch.onnx.export(net, torch.zeros(1, obs_dim), args.out, input_names=["obs"],
                      output_names=["action"], opset_version=17, dynamo=False)

    meta = {"robot": args.robot, "obs_dim": str(obs_dim), "act_dim": str(act_dim),
            "control_hz": str(args.control_hz), "ckpt": Path(args.ckpt).name,
            "ckpt_sha256": sha256(args.ckpt), "vecnorm_sha256": sha256(args.vecnorm)}
    proto = onnx.load(args.out)
    for k, v in meta.items():
        proto.metadata_props.add(key=k, value=v)
    onnx.save(proto, args.out)

    sess = ort.InferenceSession(args.out, providers=["CPUExecutionProvider"])
    mean = np.asarray(vn.obs_rms.mean, dtype=np.float64)
    std = np.sqrt(np.asarray(vn.obs_rms.var, dtype=np.float64) + float(vn.epsilon))
    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(200):
        obs = rng.normal(0.0, 1.0, obs_dim).astype(np.float32)
        z = np.clip((obs - mean) / std, -vn.clip_obs, vn.clip_obs).astype(np.float32)
        ref, _ = model.predict(z, deterministic=True)
        got = sess.run(None, {"obs": obs.reshape(1, -1)})[0][0]
        worst = max(worst, float(np.max(np.abs(ref - got))))
    assert worst < 1e-5, f"ONNX считает НЕ ТО: {worst:.3e}"

    one = rng.normal(0.0, 1.0, (1, obs_dim)).astype(np.float32)
    for _ in range(200):
        sess.run(None, {"obs": one})
    lat = []
    for _ in range(2000):
        t0 = time.perf_counter()
        sess.run(None, {"obs": one})
        lat.append((time.perf_counter() - t0) * 1e6)
    print(json.dumps({**meta, "file": Path(args.out).name, "bytes": Path(args.out).stat().st_size,
                      "max_abs_diff_vs_sb3": float(f"{worst:.3e}"),
                      "latency_us_median": round(float(np.median(lat)), 1),
                      "latency_us_p99": round(float(np.percentile(lat, 99)), 1)},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
