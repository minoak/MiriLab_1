// 미리마을 좌표 앵커 기본값 — 편집기로 갱신. localStorage 에 저장본이 있으면 그게 우선.
// houses: 캐릭터별 집(시작/귀가). places: 활동 장소 도착점. pos/arrival=[x,y], spread=[가로,세로] 흩어짐 범위.
const ANCHORS_DEFAULT = {
  "schema_version": 1,
  "houses": [
    {
      "id": "h1",
      "residents": [
        "miyoung",
        "jimin"
      ],
      "pos": [
        999,
        934
      ],
      "spread": [
        34,
        26
      ]
    },
    {
      "id": "h2",
      "residents": [
        "sua",
        "junho"
      ],
      "pos": [
        875,
        954
      ],
      "spread": [
        34,
        26
      ]
    },
    {
      "id": "h3",
      "residents": [
        "minsu"
      ],
      "pos": [
        530,
        715
      ],
      "spread": [
        34,
        26
      ]
    },
    {
      "id": "h4",
      "residents": [
        "staff"
      ],
      "pos": [
        703,
        944
      ],
      "spread": [
        34,
        26
      ]
    },
    {
      "id": "h5",
      "residents": [
        "owner"
      ],
      "pos": [
        685,
        730
      ],
      "spread": [
        34,
        26
      ]
    },
    {
      "id": "h6",
      "residents": [
        "grandma"
      ],
      "pos": [
        530,
        929
      ],
      "spread": [
        34,
        26
      ]
    },
    {
      "id": "h7",
      "residents": [
        "oldman"
      ],
      "pos": [
        988,
        739
      ],
      "spread": [
        34,
        26
      ]
    },
    {
      "id": "h8",
      "residents": [
        "daeun"
      ],
      "pos": [
        868,
        727
      ],
      "spread": [
        34,
        26
      ]
    }
  ],
  "places": {
    "policy_center": {
      "label": "정책지원센터",
      "arrival": [
        368,
        203
      ],
      "spread": [
        46,
        30
      ]
    },
    "community_center": {
      "label": "주민센터",
      "arrival": [
        632,
        206
      ],
      "spread": [
        46,
        30
      ]
    },
    "town_hall": {
      "label": "마을회관",
      "arrival": [
        932,
        201
      ],
      "spread": [
        46,
        30
      ]
    },
    "welfare_center": {
      "label": "복지관",
      "arrival": [
        1136,
        174
      ],
      "spread": [
        46,
        30
      ]
    },
    "cafe": {
      "label": "카페",
      "arrival": [
        508,
        470
      ],
      "spread": [
        46,
        30
      ]
    },
    "fountain_plaza": {
      "label": "분수광장",
      "arrival": [
        905,
        478
      ],
      "spread": [
        46,
        30
      ]
    },
    "park_pond": {
      "label": "마을공원",
      "arrival": [
        1364,
        471
      ],
      "spread": [
        46,
        30
      ]
    },
    "garden": {
      "label": "마을텃밭",
      "arrival": [
        196,
        429
      ],
      "spread": [
        46,
        30
      ]
    },
    "bus_stop": {
      "label": "버스정류장",
      "arrival": [
        205,
        602
      ],
      "spread": [
        46,
        30
      ]
    },
    "playground": {
      "label": "어린이놀이터",
      "arrival": [
        1240,
        690
      ],
      "spread": [
        46,
        30
      ]
    },
    "daycare": {
      "label": "마을공동육아",
      "arrival": [
        1262,
        927
      ],
      "spread": [
        46,
        30
      ]
    },
    "school": {
      "label": "학교",
      "arrival": [
        167,
        957
      ],
      "spread": [
        46,
        30
      ]
    }
  }
};
