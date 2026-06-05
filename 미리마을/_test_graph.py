# -*- coding: utf-8 -*-
"""_test_graph.py — index.html 의 경로 그래프 로직(28px 병합 + BFS)을 Python 으로 미러 검증.

목적: 캐릭터가 실제로 어느 장소든 길을 찾아갈 수 있는지(=그래프가 충분히 연결됐는지) 확인.
실행: python 미리마을/_test_graph.py
"""
import json
import math
import os
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
THR = 28  # index.html MERGE_THR 과 동일해야 함

with open(os.path.join(HERE, "path_data.json"), encoding="utf-8") as f:
    PATH = json.load(f)
with open(os.path.join(HERE, "data", "locations.json"), encoding="utf-8") as f:
    LOCS = json.load(f)["locations"]

nodes = PATH["nodes"]
polylines = PATH["polylines"]
keys = list(nodes.keys())
idx = {k: i for i, k in enumerate(keys)}

# --- union-find: 28px 이내 노드 병합 ---
parent = list(range(len(keys)))


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb


for i in range(len(keys)):
    x1, y1 = nodes[keys[i]]
    for j in range(i + 1, len(keys)):
        x2, y2 = nodes[keys[j]]
        if math.hypot(x1 - x2, y1 - y2) < THR:
            union(i, j)

# --- 인접리스트: polyline 연속 노드를 대표끼리 ---
adj = {}


def edge(a, b):
    if a == b:
        return
    adj.setdefault(a, set()).add(b)
    adj.setdefault(b, set()).add(a)


for line in polylines:
    for i in range(1, len(line)):
        edge(find(idx[line[i - 1]]), find(idx[line[i]]))

comps = {find(i) for i in range(len(keys))}
print(f"[1] 노드 {len(keys)}개 -> 28px 병합 교차점 {len(comps)}개 (index.html buildGraph 로그와 동일)")

fails = 0
loc_node = {}
for L in LOCS:
    n = L["node"]
    loc_node[L["key"]] = n
    if n not in idx:
        print(f"    [FAIL] location '{L['key']}' 의 node {n} 가 PATH_DATA 에 없음")
        fails += 1


# --- 진짜 연결성: 인접 그래프(adj)에서 BFS 로 도달 가능한가 ---
def bfs(fk, tk):
    s, g = find(idx[fk]), find(idx[tk])
    if s == g:
        return [s]
    prev = {s: None}
    q = deque([s])
    while q:
        c = q.popleft()
        if c == g:
            break
        for nb in adj.get(c, ()):
            if nb not in prev:
                prev[nb] = c
                q.append(nb)
    if g not in prev:
        return None
    p, c = [], g
    while c is not None:
        p.append(c)
        c = prev[c]
    return p[::-1]


# [2] 모든 location 쌍이 그래프(adj-BFS)로 상호 도달 가능한가
loc_keys = [k for k in loc_node if loc_node[k] in idx]
unreachable = 0
for ai, a in enumerate(loc_keys):
    for b in loc_keys[ai + 1:]:
        if bfs(loc_node[a], loc_node[b]) is None:
            print(f"    [FAIL] {a} -> {b} 도달 불가")
            unreachable += 1
n_pairs = len(loc_keys) * (len(loc_keys) - 1) // 2
print(f"[2] location {len(loc_keys)}곳, 전체 {n_pairs}쌍 BFS -> 도달불가 {unreachable}쌍 (0이면 전부 길찾기 가능)")
if unreachable:
    fails += 1

print("[3] 샘플 경로(집/건물 간 도달성):")
samples = [
    ("houses", "school"), ("cafe", "welfare_center"),
    ("houses", "park_pond"), ("community_center", "daycare"),
    ("houses", "policy_center"), ("garden", "town_hall"),
]
for a, b in samples:
    p = bfs(loc_node[a], loc_node[b])
    if p:
        print(f"    OK  {a:16s} -> {b:16s} : {len(p)}홉")
    else:
        print(f"    FAIL {a} -> {b} : 경로 없음")
        fails += 1

print()
print("=== 결과:", "PASS (모든 장소 상호 도달 가능)" if fails == 0 else f"FAIL ({fails}건)", "===")
