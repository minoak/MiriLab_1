// 미리마을 생성 데이터 (gen_schedules.py). generated_with: llm
// index.html 이 data/*.json fetch 실패(file://) 시 이 const 들을 폴백으로 사용한다.
const VILLAGERS = [
  {
    "id": "minsu",
    "name": "민수",
    "age": 27,
    "gender": "남",
    "occupation": "청년 구직자 / 카페 아르바이트",
    "personality": "성실하지만 취업난에 지친 청년. 붙임성이 좋아 단골·이웃과 잘 어울린다.",
    "home": "houses",
    "work": "cafe",
    "daily_rhythm": "오전 구직활동과 서류 준비, 오후 카페 아르바이트, 저녁 친구와 휴식",
    "wake_hint": "08:30",
    "sleep_hint": "00:30",
    "relationships": [
      "owner",
      "sua"
    ]
  },
  {
    "id": "staff",
    "name": "영희",
    "age": 36,
    "gender": "여",
    "occupation": "주민센터 정책 담당 공무원",
    "personality": "주민 민원을 꼼꼼히 챙기는 공무원. 책임감이 강하고 취약계층에게 특히 친절하다.",
    "home": "houses",
    "work": "community_center",
    "daily_rhythm": "이른 출근과 민원 응대, 점심은 인근에서, 오후 현장·서류 업무, 저녁 귀가",
    "wake_hint": "07:00",
    "sleep_hint": "23:30",
    "relationships": [
      "grandma",
      "miyoung"
    ]
  },
  {
    "id": "owner",
    "name": "박사장",
    "age": 48,
    "gender": "남",
    "occupation": "마을 카페 사장",
    "personality": "마을 사랑방 같은 카페를 운영하는 넉살 좋은 사장. 동네 소식에 밝은 소식통이다.",
    "home": "houses",
    "work": "cafe",
    "daily_rhythm": "이른 아침 개점 준비, 종일 카페 운영, 저녁 마감 후 귀가",
    "wake_hint": "06:30",
    "sleep_hint": "23:00",
    "relationships": [
      "minsu",
      "daeun"
    ]
  },
  {
    "id": "grandma",
    "name": "김할머니",
    "age": 75,
    "gender": "여",
    "occupation": "독거 어르신 (복지관 이용자)",
    "personality": "혼자 사는 어르신. 복지관 친구들과의 모임이 큰 낙이고, 디지털 기기는 서툴러 직접 발로 다닌다.",
    "home": "houses",
    "work": "welfare_center",
    "daily_rhythm": "이른 기상과 텃밭 돌보기, 오전 복지관 프로그램, 점심도 복지관, 오후 산책, 저녁 일찍 귀가",
    "wake_hint": "05:30",
    "sleep_hint": "21:30",
    "relationships": [
      "oldman",
      "staff"
    ]
  },
  {
    "id": "sua",
    "name": "수아",
    "age": 17,
    "gender": "여",
    "occupation": "고등학생 (고2)",
    "personality": "성적과 진로 고민이 많은 고2. 친구들과 카페에서 수다 떠는 게 스트레스 해소다.",
    "home": "houses",
    "work": "school",
    "daily_rhythm": "등교 후 종일 수업, 방과후 친구와 카페, 저녁 귀가 후 공부",
    "wake_hint": "07:00",
    "sleep_hint": "00:00",
    "relationships": [
      "junho",
      "minsu"
    ]
  },
  {
    "id": "junho",
    "name": "준호",
    "age": 15,
    "gender": "남",
    "occupation": "중학생",
    "personality": "활동적인 중학생. 방과후 놀이터에서 친구·동생들과 노는 걸 좋아한다.",
    "home": "houses",
    "work": "school",
    "daily_rhythm": "등교 후 수업, 방과후 놀이터, 저녁 귀가",
    "wake_hint": "07:00",
    "sleep_hint": "22:30",
    "relationships": [
      "sua",
      "jimin"
    ]
  },
  {
    "id": "miyoung",
    "name": "미영",
    "age": 34,
    "gender": "여",
    "occupation": "워킹맘 / 마을회관 자원봉사",
    "personality": "아이를 키우며 마을 일에 적극적인 주민. 공동육아와 자원봉사에 열심이다.",
    "home": "houses",
    "work": "town_hall",
    "daily_rhythm": "아침 아이 어린이집 등원, 오전 마을회관 봉사, 오후 장보기와 텃밭, 저녁 아이 하원 후 귀가",
    "wake_hint": "06:30",
    "sleep_hint": "23:00",
    "relationships": [
      "daeun",
      "staff"
    ]
  },
  {
    "id": "oldman",
    "name": "박어르신",
    "age": 72,
    "gender": "남",
    "occupation": "은퇴 어르신",
    "personality": "은퇴 후 공원 산책과 장기를 즐기는 마을 터줏대감. 사람들과 어울리길 좋아한다.",
    "home": "houses",
    "work": "park_pond",
    "daily_rhythm": "이른 기상과 공원 산책, 오전 복지관, 점심 후 공원에서 장기, 저녁 귀가",
    "wake_hint": "05:00",
    "sleep_hint": "21:00",
    "relationships": [
      "grandma"
    ]
  },
  {
    "id": "jimin",
    "name": "지민",
    "age": 6,
    "gender": "남",
    "occupation": "어린이 (어린이집)",
    "personality": "호기심 많은 어린이. 어린이집과 놀이터를 오가며 하루 종일 논다.",
    "home": "houses",
    "work": "daycare",
    "daily_rhythm": "아침 어린이집 등원, 종일 어린이집 생활, 오후 놀이터, 저녁 귀가",
    "wake_hint": "07:30",
    "sleep_hint": "21:00",
    "relationships": [
      "junho",
      "miyoung"
    ]
  },
  {
    "id": "daeun",
    "name": "다은",
    "age": 30,
    "gender": "여",
    "occupation": "재택 프리랜서",
    "personality": "재택으로 일하는 프리랜서. 짬짬이 텃밭을 가꾸고 카페에서 작업하는 걸 즐긴다.",
    "home": "houses",
    "work": "garden",
    "daily_rhythm": "오전 집·카페에서 작업, 점심 후 텃밭 가꾸기, 오후 카페에서 작업, 저녁 산책",
    "wake_hint": "08:00",
    "sleep_hint": "01:00",
    "relationships": [
      "owner",
      "miyoung"
    ]
  }
];
const LOCATIONS = [
  {
    "key": "policy_center",
    "label": "정책지원센터",
    "node": "custom_1",
    "kind": "civic",
    "policy_channel": true,
    "space_key": "online_portal"
  },
  {
    "key": "community_center",
    "label": "주민센터",
    "node": "custom_37",
    "kind": "civic",
    "policy_channel": true,
    "space_key": "community_center"
  },
  {
    "key": "town_hall",
    "label": "마을회관",
    "node": "custom_73",
    "kind": "civic",
    "policy_channel": false,
    "space_key": null
  },
  {
    "key": "welfare_center",
    "label": "복지관",
    "node": "custom_119",
    "kind": "civic",
    "policy_channel": true,
    "space_key": "welfare_center"
  },
  {
    "key": "cafe",
    "label": "카페",
    "node": "custom_25",
    "kind": "commerce",
    "policy_channel": false,
    "space_key": "work_market"
  },
  {
    "key": "fountain_plaza",
    "label": "분수광장",
    "node": "custom_57",
    "kind": "public",
    "policy_channel": false,
    "space_key": null
  },
  {
    "key": "park_pond",
    "label": "마을공원",
    "node": "custom_100",
    "kind": "public",
    "policy_channel": false,
    "space_key": null
  },
  {
    "key": "garden",
    "label": "마을텃밭",
    "node": "custom_597",
    "kind": "public",
    "policy_channel": false,
    "space_key": null
  },
  {
    "key": "bus_stop",
    "label": "버스정류장",
    "node": "custom_566",
    "kind": "transit",
    "policy_channel": false,
    "space_key": null
  },
  {
    "key": "playground",
    "label": "어린이놀이터",
    "node": "custom_187",
    "kind": "public",
    "policy_channel": false,
    "space_key": null
  },
  {
    "key": "daycare",
    "label": "마을공동육아",
    "node": "custom_639",
    "kind": "care",
    "policy_channel": false,
    "space_key": null
  },
  {
    "key": "houses",
    "label": "주택가",
    "node": "custom_315",
    "kind": "home",
    "policy_channel": false,
    "space_key": "home"
  },
  {
    "key": "school",
    "label": "학교",
    "node": "custom_460",
    "kind": "education",
    "policy_channel": false,
    "space_key": null
  }
];
const SCHEDULES = {
  "minsu": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "houses",
      "action": "집에서 휴식"
    },
    {
      "start_time": "08:30",
      "end_time": "09:00",
      "location_key": "houses",
      "action": "민수는 아침 식사를 하고 하루를 시작하기 위해 준비한다."
    },
    {
      "start_time": "09:00",
      "end_time": "11:00",
      "location_key": "community_center",
      "action": "민수는 주민센터에서 구직 관련 세미나에 참석하여 유용한 정보를 얻는다."
    },
    {
      "start_time": "11:00",
      "end_time": "12:00",
      "location_key": "cafe",
      "action": "민수는 카페에 들러 박사장과 간단한 대화를 나누며 아르바이트 준비를 한다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "민수는 점심 시간에 카페에서 간단한 점심을 먹으며 손님들과 이야기를 나눈다."
    },
    {
      "start_time": "13:00",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "민수는 카페에서 아르바이트를 하며 손님들에게 음료를 제공하고 바쁜 오후를 보낸다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "cafe",
      "action": "민수는 아르바이트를 마치고 박사장과 카페 정리를 도와준다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "fountain_plaza",
      "action": "민수는 분수광장에서 수아와 함께 산책하며 하루의 피로를 풀고 이야기를 나눈다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "민수는 집으로 돌아와 간단한 저녁을 만들고 먹는다."
    },
    {
      "start_time": "21:00",
      "end_time": "23:00",
      "location_key": "houses",
      "action": "민수는 집에서 구직활동을 위한 서류를 작성하며 시간을 보낸다."
    },
    {
      "start_time": "23:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "staff": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "community_center",
      "action": "영희는 주민센터에 도착해 사무실 정리를 하고 민원 상담을 위한 자료를 준비한다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "community_center",
      "action": "영희는 주민들의 민원을 접수하고 처리하며, 특히 취약계층의 요청을 꼼꼼히 챙긴다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "영희는 인근 카페에서 동료들과 함께 점심을 먹으며 최근에 처리한 민원에 대해 이야기를 나눈다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "community_center",
      "action": "영희는 오후 민원 업무를 이어가며, 서류 정리와 필요한 조치를 취한다."
    },
    {
      "start_time": "15:00",
      "end_time": "17:00",
      "location_key": "community_center",
      "action": "영희는 현장 방문을 위해 필요한 자료를 준비하고, 주민들을 직접 만나기 위해 외부로 나간다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "community_center",
      "action": "영희는 현장 방문을 마치고 돌아와서 방문 결과를 정리하고 후속 조치를 계획한다."
    },
    {
      "start_time": "18:00",
      "end_time": "18:30",
      "location_key": "cafe",
      "action": "영희는 퇴근하기 전에 카페에 들러 박사장과 담소를 나눈다."
    },
    {
      "start_time": "18:30",
      "end_time": "19:00",
      "location_key": "bus_stop",
      "action": "영희는 버스를 기다리며 오늘의 업무를 되짚어 본다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "houses",
      "action": "영희는 집에 돌아와 저녁을 준비하며, 김할머니에게 안부 전화를 건다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "영희는 저녁을 먹고, 가족과 함께 TV를 보며 휴식을 취한다."
    },
    {
      "start_time": "21:00",
      "end_time": "22:30",
      "location_key": "houses",
      "action": "영희는 다음 날 민원 업무를 준비하며 서류를 정리하고, 필요한 문서를 작성한다."
    },
    {
      "start_time": "22:30",
      "end_time": "23:30",
      "location_key": "houses",
      "action": "영희는 하루를 마무리하며, 독서로 편안한 시간을 보낸 후 취침 준비를 한다."
    },
    {
      "start_time": "23:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "owner": [
    {
      "start_time": "08:00",
      "end_time": "12:00",
      "location_key": "cafe",
      "action": "박사장은 카페를 열고 손님들을 맞이하며 동네 소식을 나누었다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "박사장은 점심 시간에 맞춰 간단한 점심을 먹으며 주방에서 대화하고 있었다."
    },
    {
      "start_time": "13:00",
      "end_time": "17:00",
      "location_key": "cafe",
      "action": "박사장은 오후에도 카페를 운영하며 손님들과 즐거운 대화를 이어갔다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "박사장은 카페의 저녁 메뉴를 준비하며 마무리 작업을 시작했다."
    },
    {
      "start_time": "18:00",
      "end_time": "20:00",
      "location_key": "cafe",
      "action": "박사장은 저녁 손님들을 맞이하며 카페의 분위기를 즐거운 대화로 가득 채웠다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "cafe",
      "action": "박사장은 카페를 정리하며 오늘 하루의 소소한 소식을 정리해 보았다."
    },
    {
      "start_time": "21:00",
      "end_time": "22:00",
      "location_key": "cafe",
      "action": "박사장은 마지막 손님을 보내고 카페 문을 닫기 전 마지막 청소를 했다."
    },
    {
      "start_time": "22:00",
      "end_time": "23:00",
      "location_key": "houses",
      "action": "박사장은 집으로 돌아와 편안한 저녁 시간을 보내며 하루를 마무리했다."
    },
    {
      "start_time": "23:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "grandma": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "bus_stop",
      "action": "김할머니는 버스를 타고 복지관으로 향했다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "welfare_center",
      "action": "복지관에 도착한 김할머니는 친구들과 함께 오전 프로그램에 참여했다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "welfare_center",
      "action": "김할머니는 복지관에서 제공하는 점심을 먹으며 친구들과 이야기를 나눴다."
    },
    {
      "start_time": "13:00",
      "end_time": "14:00",
      "location_key": "welfare_center",
      "action": "점심 후 김할머니는 복지관에서 진행되는 노래 교실에 참여했다."
    },
    {
      "start_time": "14:00",
      "end_time": "15:30",
      "location_key": "park_pond",
      "action": "김할머니는 복지관에서 나와 마을공원으로 산책을 나가며 자연을 만끽했다."
    },
    {
      "start_time": "15:30",
      "end_time": "17:00",
      "location_key": "fountain_plaza",
      "action": "공원에서 산책을 마친 김할머니는 분수광장에서 잠시 쉬며 지나가는 사람들을 구경했다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "houses",
      "action": "집으로 돌아온 김할머니는 저녁 준비를 하며 하루를 정리했다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "김할머니는 간단한 저녁을 차려 혼자서 식사를 했다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "저녁 식사 후 김할머니는 TV를 보며 편안한 시간을 보냈다."
    },
    {
      "start_time": "20:30",
      "end_time": "21:30",
      "location_key": "houses",
      "action": "김할머니는 하루를 마무리하며 샤워 후 잠자리에 들 준비를 했다."
    },
    {
      "start_time": "21:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "sua": [
    {
      "start_time": "08:00",
      "end_time": "12:00",
      "location_key": "school",
      "action": "학교에 도착해 오전 수업을 듣고 친구들과 함께 점심시간을 기다렸다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "school",
      "action": "점심시간에 친구들과 함께 급식소에서 점심을 먹으며 진로에 대한 이야기를 나눴다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "school",
      "action": "오후 수업을 듣고 수업 중에 진로 고민에 대해 생각하며 공부에 집중했다."
    },
    {
      "start_time": "15:00",
      "end_time": "15:30",
      "location_key": "cafe",
      "action": "학교가 끝난 후 친구 민수와 함께 카페에 가서 시원한 음료를 마시며 수다를 떨었다."
    },
    {
      "start_time": "15:30",
      "end_time": "17:00",
      "location_key": "cafe",
      "action": "카페에서 민수와 함께 공부를 하며 서로의 진로 고민을 나누었다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "houses",
      "action": "집으로 돌아가면서 오늘의 수업에서 배운 내용을 복습하며 생각을 정리했다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "저녁을 먹고 가족과 함께 하루에 대해 이야기를 나누었다."
    },
    {
      "start_time": "19:00",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "방으로 가서 학교 숙제를 하며 진로에 대한 고민을 계속 했다."
    },
    {
      "start_time": "22:00",
      "end_time": "23:30",
      "location_key": "houses",
      "action": "자기 전에 유튜브를 보며 스트레스를 해소하고 가벼운 마음으로 하루를 마무리했다."
    },
    {
      "start_time": "23:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "junho": [
    {
      "start_time": "08:00",
      "end_time": "12:00",
      "location_key": "school",
      "action": "준호는 학교에서 수업을 듣고 친구들과 함께 점심시간을 기다리며 이야기를 나눴다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "school",
      "action": "점심시간에 준호는 친구들과 함께 급식실에서 점심을 먹으며 웃고 떠들었다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:30",
      "location_key": "school",
      "action": "준호는 오후 수업을 듣고, 수업이 끝난 후 친구들과 이야기를 나누며 교실을 나왔다."
    },
    {
      "start_time": "15:30",
      "end_time": "18:00",
      "location_key": "playground",
      "action": "학교가 끝난 후 준호는 놀이터에서 친구들과 함께 놀며 신나게 시간을 보냈다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "준호는 집에 돌아와 저녁을 준비하고 가족과 함께 저녁 식사를 했다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "저녁 식사 후 준호는 방과 후 숙제를 하며 시간을 보냈다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:00",
      "location_key": "playground",
      "action": "준호는 다시 놀이터로 나가 친구들과 함께 저녁 시간을 보내며 놀았다."
    },
    {
      "start_time": "22:00",
      "end_time": "22:30",
      "location_key": "houses",
      "action": "준호는 집에 돌아와 하루를 정리한 후 취침 준비를 했다."
    },
    {
      "start_time": "22:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "miyoung": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "bus_stop",
      "action": "미영은 아이를 어린이집에 데려다 주기 위해 버스를 기다렸다."
    },
    {
      "start_time": "08:30",
      "end_time": "09:00",
      "location_key": "daycare",
      "action": "미영은 아이를 어린이집에 안전하게 데려다 주고, 선생님과 간단한 이야기를 나누었다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "town_hall",
      "action": "마을회관에서 자원봉사 활동으로 주민들과 함께 행사 준비를 했다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "봉사활동 후 카페에서 점심을 먹으며 영희와 수다를 떨었다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "garden",
      "action": "마을 텃밭에 가서 채소를 수확하고 잡초를 뽑으며 시간을 보냈다."
    },
    {
      "start_time": "15:00",
      "end_time": "16:00",
      "location_key": "community_center",
      "action": "복지관에서 김할머니와 이야기를 나누며 자원봉사 활동을 이어갔다."
    },
    {
      "start_time": "16:00",
      "end_time": "17:30",
      "location_key": "houses",
      "action": "집으로 돌아와서 간단한 저녁 준비를 하며 하루의 일과를 정리했다."
    },
    {
      "start_time": "17:30",
      "end_time": "18:00",
      "location_key": "daycare",
      "action": "아이를 어린이집에서 데려와 집으로 돌아가는 길에 이야기를 나눴다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "저녁을 차리고 아이와 함께 식사하며 하루의 이야기를 나눴다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "park_pond",
      "action": "저녁 식사 후 아이와 함께 마을 공원에서 산책하며 놀이를 즐겼다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "집에 돌아와 아이와 함께 목욕을 시키고 책을 읽어주며 잠자리에 들 준비를 했다."
    },
    {
      "start_time": "22:00",
      "end_time": "23:00",
      "location_key": "houses",
      "action": "아이를 재우고, 미영은 하루를 정리하며 간단한 독서를 하며 시간을 보냈다."
    },
    {
      "start_time": "23:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "oldman": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "welfare_center",
      "action": "복지관에 가서 친구들과 만나 이야기를 나누며 시간을 보냈다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "welfare_center",
      "action": "복지관에서 진행하는 프로그램에 참여하며 즐겁게 활동했다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "복지관 근처의 카페에서 점심을 먹으며 마을 사람들과 담소를 나눴다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "park_pond",
      "action": "공원에서 장기를 두며 다른 어르신들과 여유로운 오후를 즐겼다."
    },
    {
      "start_time": "15:00",
      "end_time": "17:00",
      "location_key": "park_pond",
      "action": "산책을 하며 공원 주변의 꽃과 나무를 감상하고 산책을 이어갔다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "houses",
      "action": "집에 돌아와 저녁 준비를 하며 하루를 돌아보았다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "아내와 함께 저녁 식사를 하며 지난 하루의 이야기를 나누었다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "park_pond",
      "action": "다시 공원으로 나가 저녁 산책을 하며 친구들과 이야기를 나눴다."
    },
    {
      "start_time": "20:30",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "집으로 돌아와 하루를 마무리하며 편안한 마음으로 취침 준비를 했다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "jimin": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "bus_stop",
      "action": "지민은 어린이집에 가기 위해 버스를 기다렸다."
    },
    {
      "start_time": "08:30",
      "end_time": "12:00",
      "location_key": "daycare",
      "action": "어린이집에서 친구들과 함께 다양한 놀이를 하며 즐거운 시간을 보냈다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "daycare",
      "action": "지민은 어린이집에서 점심을 먹고 친구들과 식사를 나누었다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "daycare",
      "action": "오후에도 어린이집에서 그림 그리기와 블록 쌓기 놀이를 하며 시간을 보냈다."
    },
    {
      "start_time": "15:00",
      "end_time": "15:30",
      "location_key": "bus_stop",
      "action": "어린이집에서 놀다가 집으로 돌아가기 위해 버스를 기다렸다."
    },
    {
      "start_time": "15:30",
      "end_time": "16:00",
      "location_key": "houses",
      "action": "지민은 집에 도착해 엄마에게 오늘 어린이집에서 있었던 이야기를 했다."
    },
    {
      "start_time": "16:00",
      "end_time": "17:00",
      "location_key": "playground",
      "action": "지민은 준호와 함께 놀이터에 가서 미끄럼틀과 그네에서 놀았다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "playground",
      "action": "지민은 놀이터에서 다른 친구들과 공놀이를 하며 즐거운 시간을 보냈다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "저녁 시간이 되어 지민은 집으로 돌아와 가족과 함께 저녁을 먹었다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "지민은 저녁 후에 가족과 함께 TV를 보거나 책을 읽으며 시간을 보냈다."
    },
    {
      "start_time": "20:30",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "지민은 잠자기 전에 엄마와 함께 이야기를 나누며 하루를 마무리했다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "daeun": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "houses",
      "action": "다은은 아침에 일어나서 간단한 아침식사를 준비하고, 오늘 할 일들을 정리했다."
    },
    {
      "start_time": "09:00",
      "end_time": "11:00",
      "location_key": "cafe",
      "action": "카페에 가서 편안한 자리에 앉아 프리랜서 작업을 시작했다."
    },
    {
      "start_time": "11:00",
      "end_time": "12:30",
      "location_key": "garden",
      "action": "자택의 텃밭에 가서 채소를 가꾸고 물을 주며 시간을 보냈다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:30",
      "location_key": "cafe",
      "action": "근처 카페로 돌아와 점심을 먹고 다시 작업을 시작했다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:30",
      "location_key": "cafe",
      "action": "카페에서 프리랜서 작업에 집중하며 필요한 자료를 정리했다."
    },
    {
      "start_time": "15:30",
      "end_time": "17:00",
      "location_key": "garden",
      "action": "텃밭에서 새로운 식물을 심고 주변을 정리했다."
    },
    {
      "start_time": "17:00",
      "end_time": "19:00",
      "location_key": "cafe",
      "action": "카페로 돌아와 저녁을 먹고 작업을 마무리했다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "park_pond",
      "action": "마을 공원으로 산책을 나가서 여유로운 시간을 보냈다."
    },
    {
      "start_time": "20:00",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "집에 돌아와 저녁을 간단히 차려 먹고 휴식을 취했다."
    },
    {
      "start_time": "22:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "자택에서 프리랜서 작업을 이어가며 프로젝트를 마무리 지었다."
    }
  ]
};
