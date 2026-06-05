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
      "action": "민수는 알람에 맞춰 일어나 커피를 한 잔 내린 후 아침을 간단히 먹는다."
    },
    {
      "start_time": "09:00",
      "end_time": "10:30",
      "location_key": "houses",
      "action": "민수는 구직 사이트를 통해 새로운 일자리를 검색하고 이력서를 업데이트한다."
    },
    {
      "start_time": "10:30",
      "end_time": "11:30",
      "location_key": "cafe",
      "action": "민수는 카페에 가서 박사장에게 인사하며 아르바이트 준비를 시작한다."
    },
    {
      "start_time": "11:30",
      "end_time": "12:30",
      "location_key": "cafe",
      "action": "민수는 카페에서 고객을 응대하며 아르바이트를 한다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:30",
      "location_key": "fountain_plaza",
      "action": "민수는 점심시간에 분수광장으로 나가 미영과 함께 점심을 먹으며 이야기를 나눈다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:30",
      "location_key": "cafe",
      "action": "민수는 카페로 돌아와 오후 아르바이트를 계속한다."
    },
    {
      "start_time": "15:30",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "민수는 아르바이트를 마치고 박사장과 오늘 있었던 일에 대해 이야기하며 잠시 더 머무른다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "민수는 집으로 돌아와 간단히 저녁을 준비한다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "민수는 저녁을 먹으며 수아와 함께 TV 프로그램을 시청한다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:30",
      "location_key": "cafe",
      "action": "민수는 친구들과 카페에서 만나 이야기를 나누며 휴식을 취한다."
    },
    {
      "start_time": "22:30",
      "end_time": "23:30",
      "location_key": "houses",
      "action": "민수는 집으로 돌아와 내일 계획을 세우고 간단히 정리한다."
    },
    {
      "start_time": "23:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "staff": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "community_center",
      "action": "주민센터에 도착한 영희는 같은 팀 동료들과 인사를 나누고 하루 업무를 시작한다."
    },
    {
      "start_time": "08:30",
      "end_time": "10:30",
      "location_key": "community_center",
      "action": "영희는 민원인들의 요청을 꼼꼼히 처리하며 필요한 서류를 정리한다."
    },
    {
      "start_time": "10:30",
      "end_time": "11:00",
      "location_key": "community_center",
      "action": "영희는 복지 지원에 대한 상담을 위해 김할머니와 만나 차 한 잔을 나누며 이야기를 나눈다."
    },
    {
      "start_time": "11:00",
      "end_time": "12:00",
      "location_key": "community_center",
      "action": "영희는 민원 상담을 계속 진행하며 주민들의 목소리를 귀담아 듣는다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "영희는 인근 카페에서 동료들과 함께 점심을 먹으며 일상적인 이야기를 나눈다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:30",
      "location_key": "community_center",
      "action": "영희는 오후 민원 처리를 위해 서류를 정리하고 필요한 자료를 준비한다."
    },
    {
      "start_time": "15:30",
      "end_time": "16:30",
      "location_key": "community_center",
      "action": "영희는 지역 주민들과의 회의에 참석하여 복지 정책에 대해 의견을 나눈다."
    },
    {
      "start_time": "16:30",
      "end_time": "17:30",
      "location_key": "community_center",
      "action": "영희는 현장 조사를 위해 복지관에 방문하여 이용자들과 소통한다."
    },
    {
      "start_time": "17:30",
      "end_time": "18:00",
      "location_key": "community_center",
      "action": "영희는 하루 업무를 정리하고 내일의 계획을 세운다."
    },
    {
      "start_time": "18:00",
      "end_time": "18:30",
      "location_key": "houses",
      "action": "영희는 집으로 돌아가는 길에 김할머니의 집에 들러 안부를 물어본다."
    },
    {
      "start_time": "18:30",
      "end_time": "19:30",
      "location_key": "houses",
      "action": "영희는 집에서 저녁을 준비하며 하루의 피로를 푼다."
    },
    {
      "start_time": "19:30",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "영희는 저녁을 먹고, 가족과 함께 TV를 보며 시간을 보낸다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "영희는 내일 할 업무를 위해 서류를 정리하고 필요한 자료를 준비한다."
    },
    {
      "start_time": "22:00",
      "end_time": "23:30",
      "location_key": "houses",
      "action": "영희는 하루를 마무리하며 독서로 편안한 시간을 가지다가 취침 준비를 한다."
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
      "end_time": "10:00",
      "location_key": "cafe",
      "action": "첫 손님들과 대화를 나누며 커피를 서빙하고, 동네 소식을 듣는다."
    },
    {
      "start_time": "10:00",
      "end_time": "11:00",
      "location_key": "cafe",
      "action": "근처의 고등학생 수아가 카페에 들러 공부하는 모습을 보며 격려해준다."
    },
    {
      "start_time": "11:00",
      "end_time": "12:30",
      "location_key": "community_center",
      "action": "주민센터에서 이웃들과 만나 소소한 이야기를 나누고, 지역 행사에 대한 의견을 나눈다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:30",
      "location_key": "cafe",
      "action": "점심시간에 맞춰 카페로 돌아와 간단한 점심을 먹으며 직원 민수와 담소를 나눈다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:30",
      "location_key": "cafe",
      "action": "오후 손님들을 맞이하며, 커피와 디저트를 서빙하고 이웃들과 소통한다."
    },
    {
      "start_time": "15:30",
      "end_time": "16:00",
      "location_key": "fountain_plaza",
      "action": "분수광장에 나가 잠시 산책하며 동네 사람들과 반갑게 인사를 나눈다."
    },
    {
      "start_time": "16:00",
      "end_time": "18:30",
      "location_key": "cafe",
      "action": "카페로 돌아와 저녁 손님들을 맞이하며 바쁜 오후 시간을 보낸다."
    },
    {
      "start_time": "18:30",
      "end_time": "20:00",
      "location_key": "cafe",
      "action": "저녁 시간이 되어 마감 준비를 하며 직원들과 오늘의 소감을 나눈다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "cafe",
      "action": "카페를 닫고 마지막 손님을 배웅하며 오늘의 매출을 정리한다."
    },
    {
      "start_time": "21:00",
      "end_time": "22:30",
      "location_key": "houses",
      "action": "귀가 후 저녁을 간단히 먹고 하루 동안 있었던 일들을 생각하며 휴식을 취한다."
    },
    {
      "start_time": "22:30",
      "end_time": "23:00",
      "location_key": "houses",
      "action": "하루를 마감하며 잠자리에 들기 전에 책을 읽으며 편안한 시간을 보낸다."
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
      "location_key": "welfare_center",
      "action": "복지관으로 가는 길에 주변 공원을 산책하며 기분 좋게 하루를 시작한다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "welfare_center",
      "action": "복지관에서 친구들과 프로그램에 참여하고 수다를 나눈다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "welfare_center",
      "action": "복지관에서 제공하는 점심을 친구들과 함께 나누어 먹는다."
    },
    {
      "start_time": "13:00",
      "end_time": "14:00",
      "location_key": "welfare_center",
      "action": "점심 후 친구들과 함께 카드 게임을 하며 즐거운 시간을 보낸다."
    },
    {
      "start_time": "14:00",
      "end_time": "15:30",
      "location_key": "park_pond",
      "action": "복지관을 나와 마을 공원에서 자연을 감상하며 한가롭게 산책한다."
    },
    {
      "start_time": "15:30",
      "end_time": "17:00",
      "location_key": "fountain_plaza",
      "action": "분수광장에 앉아 지나가는 사람들을 구경하며 가벼운 담소를 나눈다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "welfare_center",
      "action": "복지관으로 돌아와 친구들과 저녁 모임을 준비한다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "welfare_center",
      "action": "복지관에서 저녁을 먹고, 친구들과 이야기를 나눈다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "welfare_center",
      "action": "저녁 후 복지관에서 진행되는 음악 프로그램에 참석한다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "집으로 돌아와 오늘 하루를 정리하고 간단한 개인 시간을 갖는다."
    },
    {
      "start_time": "21:00",
      "end_time": "21:30",
      "location_key": "houses",
      "action": "잠자기 전 책을 읽고 편안한 마음으로 하루를 마무리한다."
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
      "action": "학교에서 수업을 들으며 시험 준비와 진로에 대한 고민을 했다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "school",
      "action": "점심시간에 친구들과 함께 급식실에서 점심을 먹으며 소소한 이야기를 나눴다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:30",
      "location_key": "school",
      "action": "오후 수업에 참석하며 과목별로 공부 내용을 정리했다."
    },
    {
      "start_time": "15:30",
      "end_time": "16:00",
      "location_key": "bus_stop",
      "action": "학교에서 버스를 타고 카페로 가기 위해 버스정류장에서 기다렸다."
    },
    {
      "start_time": "16:00",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "카페에서 친구 민수와 함께 수다를 떨며 스트레스를 풀었다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "집에 돌아와 간단한 저녁을 먹고 공부할 준비를 했다."
    },
    {
      "start_time": "19:00",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "집에서 진로와 과목 공부를 하며 방과후 시간을 보냈다."
    },
    {
      "start_time": "22:00",
      "end_time": "23:00",
      "location_key": "houses",
      "action": "부모님과 함께 저녁 식사를 하며 일상 이야기를 나누었다."
    },
    {
      "start_time": "23:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 휴식"
    }
  ],
  "junho": [
    {
      "start_time": "08:00",
      "end_time": "12:30",
      "location_key": "school",
      "action": "학교에서 수업을 듣는다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:00",
      "location_key": "school",
      "action": "학교 식당에서 친구들과 점심을 먹는다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:30",
      "location_key": "school",
      "action": "오후 수업을 듣는다."
    },
    {
      "start_time": "15:30",
      "end_time": "16:00",
      "location_key": "playground",
      "action": "학교가 끝나고 놀이터로 가서 친구 수아와 지민을 만난다."
    },
    {
      "start_time": "16:00",
      "end_time": "18:00",
      "location_key": "playground",
      "action": "놀이터에서 친구들과 함께 축구를 하며 놀고 시간을 보낸다."
    },
    {
      "start_time": "18:00",
      "end_time": "18:30",
      "location_key": "houses",
      "action": "집으로 돌아와서 저녁 준비를 돕는다."
    },
    {
      "start_time": "18:30",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "가족과 함께 저녁을 먹는다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "houses",
      "action": "숙제를 하면서 자유로운 시간을 보낸다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "park_pond",
      "action": "저녁 산책 겸 마을 공원으로 나가서 동네 친구들과 또 놀고 이야기를 나눈다."
    },
    {
      "start_time": "21:00",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "집에 돌아와서 샤워하고, 휴대폰으로 게임을 하며 시간을 보낸다."
    },
    {
      "start_time": "22:00",
      "end_time": "22:30",
      "location_key": "houses",
      "action": "잠자기 전 책을 읽고 취침 준비를 한다."
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
      "end_time": "09:00",
      "location_key": "bus_stop",
      "action": "버스를 타고 마을회관으로 이동한다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "town_hall",
      "action": "마을회관에서 자원봉사 활동으로 행사 준비를 돕는다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "근처 카페에서 점심을 먹으며 영희와 대화한다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "garden",
      "action": "마을텃밭에서 채소를 기르며 다은과 소통한다."
    },
    {
      "start_time": "15:00",
      "end_time": "16:00",
      "location_key": "fountain_plaza",
      "action": "분수광장에서 이웃들과 함께 아이를 기다린다."
    },
    {
      "start_time": "16:00",
      "end_time": "17:00",
      "location_key": "daycare",
      "action": "아이를 어린이집에서 데리러 간다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "houses",
      "action": "집에 돌아와 저녁 준비를 시작한다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "가족과 함께 저녁을 먹으며 하루 이야기를 나눈다."
    },
    {
      "start_time": "19:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "아이와 함께 놀아주고 책을 읽어준다."
    },
    {
      "start_time": "21:00",
      "end_time": "22:30",
      "location_key": "houses",
      "action": "아이를 재우고 하루의 일과를 정리하며 쉴 시간을 갖는다."
    },
    {
      "start_time": "22:30",
      "end_time": "23:00",
      "location_key": "houses",
      "action": "잠자리에 들기 전 잠시 책을 읽고 하루를 마무리한다."
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
      "action": "복지관에서 진행하는 커뮤니티 모임에 참석해 이웃들과 담소를 나눈다."
    },
    {
      "start_time": "09:00",
      "end_time": "10:00",
      "location_key": "cafe",
      "action": "마을 카페에서 박사장과 함께 커피를 마시며 지난 주의 이야기를 나눈다."
    },
    {
      "start_time": "10:00",
      "end_time": "12:00",
      "location_key": "park_pond",
      "action": "공원으로 돌아가 장기를 두기 위해 이웃 어르신들을 기다린다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "park_pond",
      "action": "공원에서 장기를 두며 점심시간을 보내고, 이웃들과 간단한 도시락을 나눈다."
    },
    {
      "start_time": "13:00",
      "end_time": "14:00",
      "location_key": "houses",
      "action": "집으로 돌아와 잠시 쉬며 책을 읽고 여유로운 오후를 보낸다."
    },
    {
      "start_time": "14:00",
      "end_time": "16:00",
      "location_key": "park_pond",
      "action": "다시 공원으로 나가 장기를 두고 있는 이웃들과 즐거운 시간을 보낸다."
    },
    {
      "start_time": "16:00",
      "end_time": "17:00",
      "location_key": "community_center",
      "action": "주민센터에서 열리는 취미 클래스에 참여해 새로운 친구들을 사귄다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "houses",
      "action": "집으로 돌아와 저녁 준비를 하며 김할머니와 전화로 이야기를 나눈다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "저녁을 먹고 TV를 보며 하루의 피로를 푼다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "park_pond",
      "action": "저녁 산책을 겸해 공원으로 나가 주변 이웃들과 인사를 나눈다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "집에 돌아와 하루를 정리하며 편안한 마음으로 취침 준비를 한다."
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
      "action": "지민은 어린이집에 가기 위해 버스를 기다리며 놀이터에서 잠깐 놀았다."
    },
    {
      "start_time": "08:30",
      "end_time": "12:00",
      "location_key": "daycare",
      "action": "지민은 어린이집에서 친구들과 함께 다양한 놀이를 하며 즐거운 시간을 보냈다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "daycare",
      "action": "지민은 어린이집에서 점심을 먹고, 친구들과 이야기를 나누었다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "daycare",
      "action": "지민은 어린이집에서 미술 활동을 하며 창의력을 발휘했다."
    },
    {
      "start_time": "15:00",
      "end_time": "15:30",
      "location_key": "bus_stop",
      "action": "어린이집에서 나와 버스를 기다리며 친구인 준호를 만났다."
    },
    {
      "start_time": "15:30",
      "end_time": "17:30",
      "location_key": "playground",
      "action": "지민과 준호는 놀이터에서 함께 그네를 타고 미끄럼틀을 타며 놀았다."
    },
    {
      "start_time": "17:30",
      "end_time": "18:00",
      "location_key": "houses",
      "action": "지민은 집으로 돌아와 엄마와 함께 저녁 준비를 도왔다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "지민은 가족과 함께 저녁을 먹으며 하루의 이야기를 나눴다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "park_pond",
      "action": "저녁 식사 후, 지민은 가족과 함께 마을공원에서 산책을 하며 자연을 관찰했다."
    },
    {
      "start_time": "20:30",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "지민은 집에 돌아와서 목욕을 하고 잠자리에 들 준비를 했다."
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
      "action": "다은은 아침에 일어나 커피를 마시며 하루 일정을 계획했다."
    },
    {
      "start_time": "09:00",
      "end_time": "11:00",
      "location_key": "cafe",
      "action": "다은은 카페에 가서 노트북을 열고 프리랜서 작업을 시작했다."
    },
    {
      "start_time": "11:00",
      "end_time": "12:00",
      "location_key": "garden",
      "action": "다은은 집 근처 텃밭에 가서 식물을 돌보고 잡초를 뽑았다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "다은은 근처 카페로 돌아와 점심을 먹고 잠시 휴식을 취했다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "garden",
      "action": "다은은 점심 후 텃밭에 다시 가서 새로운 씨앗을 심고 물을 주었다."
    },
    {
      "start_time": "15:00",
      "end_time": "17:00",
      "location_key": "cafe",
      "action": "다은은 카페로 돌아와 작업을 계속하며 주위의 분위기를 즐겼다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:00",
      "location_key": "fountain_plaza",
      "action": "다은은 분수광장에서 잠깐 쉬며 이웃들과 담소를 나누었다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "다은은 집으로 돌아와 간단한 저녁을 준비했다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "park_pond",
      "action": "다은은 저녁 식사 후 마을 공원에서 산책하며 하루를 정리했다."
    },
    {
      "start_time": "20:00",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "다은은 집에 돌아와 편안한 옷으로 갈아입고 작업을 계속했다."
    },
    {
      "start_time": "22:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "다은은 작업을 마치고 소설을 읽으며 저녁 시간을 보냈다."
    }
  ]
};
