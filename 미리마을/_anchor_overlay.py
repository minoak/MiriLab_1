# -*- coding: utf-8 -*-
"""_anchor_overlay.py — 현재 anchors(집·장소)를 map.png 에 겹쳐 그려 어긋난 좌표를 눈으로 찾는다.

라벨은 영문 key/id 로(matplotlib 한글 폰트 회피). 장소=파랑(arrival), 집=빨강(pos),
참고로 각 장소의 도로 노드(path_data)도 작은 초록 점으로 표시해 'anchor vs 도로' 거리를 본다.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


anchors = _load("anchors.json")
locations = _load(os.path.join("data", "locations.json"))["locations"]
img = mpimg.imread(os.path.join(HERE, "assets", "map.png"))
H, W = img.shape[0], img.shape[1]

# 도로 노드 좌표(path_data.json): {nodes:{custom_N:[x,y]}} 형태 추정 — 유연 처리
nodes = {}
try:
    pd = _load("path_data.json")
    raw = pd.get("nodes", pd) if isinstance(pd, dict) else {}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            nodes[k] = (v[0], v[1])
        elif isinstance(v, dict) and "x" in v:
            nodes[k] = (v["x"], v["y"])
except Exception as e:
    print("path_data 로드 실패(노드 생략):", e)

loc_node = {l["key"]: l.get("node") for l in locations}

fig, ax = plt.subplots(figsize=(20, 15))
ax.imshow(img)

# 장소 도로 노드(초록)
for key, nkey in loc_node.items():
    if nkey in nodes:
        nx, ny = nodes[nkey]
        ax.scatter([nx], [ny], c="lime", s=40, edgecolors="black", zorder=4)

# 장소 arrival(파랑)
for key, p in anchors.get("places", {}).items():
    if not p.get("arrival"):
        continue
    x, y = p["arrival"]
    ax.scatter([x], [y], c="dodgerblue", s=180, edgecolors="white", zorder=6, marker="o")
    ax.annotate(key, (x, y), color="white", fontsize=12, weight="bold", zorder=7,
                xytext=(6, 6), textcoords="offset points",
                bbox=dict(boxstyle="round", fc="dodgerblue", ec="white", alpha=0.85))

# 집 pos(빨강) + 거주자
for h in anchors.get("houses", []):
    if not h.get("pos"):
        continue
    x, y = h["pos"]
    res = ",".join(h.get("residents", []))
    ax.scatter([x], [y], c="red", s=160, edgecolors="white", zorder=6, marker="s")
    ax.annotate(f"{h.get('id')}:{res}", (x, y), color="white", fontsize=10, weight="bold", zorder=7,
                xytext=(6, -12), textcoords="offset points",
                bbox=dict(boxstyle="round", fc="red", ec="white", alpha=0.85))

ax.set_xlim(0, W)
ax.set_ylim(H, 0)
ax.axis("off")
ax.set_title(f"anchors overlay (map {W}x{H}) - blue=place arrival, green=road node, red=house",
             fontsize=14)
plt.tight_layout()
out = os.path.join(HERE, "_anchor_overlay.png")
plt.savefig(out, dpi=70, bbox_inches="tight")
print("saved", out, "| map", W, "x", H, "| places",
      len(anchors.get("places", {})), "| houses", len(anchors.get("houses", [])),
      "| nodes", len(nodes))
