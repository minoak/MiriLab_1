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
      "end_time": "09:00",
      "location_key": "houses",
      "action": "잠에서 깨어나 간단한 아침 식사를 준비하며 하루를 시작한다."
    },
    {
      "start_time": "09:00",
      "end_time": "11:30",
      "location_key": "houses",
      "action": "노트북을 켜고 최신 채용 공고를 확인하며 자기소개서를 정성껏 수정한다."
    },
    {
      "start_time": "11:30",
      "end_time": "13:00",
      "location_key": "park_pond",
      "action": "마을공원 산책로를 걸으며 머리를 식히고 벤치에 앉아 이웃들과 가벼운 인사를 나눈다."
    },
    {
      "start_time": "13:00",
      "end_time": "14:00",
      "location_key": "policy_center",
      "action": "청년 구직 활동 지원 프로그램에 대한 상담을 받기 위해 센터를 방문하여 서류를 확인한다."
    },
    {
      "start_time": "14:00",
      "end_time": "19:00",
      "location_key": "cafe",
      "action": "박사장님을 도와 카페 카운터 업무를 보고 단골 손님인 수아와 반갑게 인사를 나눈다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "fountain_plaza",
      "action": "아르바이트를 마친 후 분수대 근처에서 이웃들과 담소를 나누며 저녁 바람을 쐰다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:30",
      "location_key": "town_hall",
      "action": "마을회관 휴게실에서 동네 친구들을 만나 소소한 고민을 나누며 시간을 보낸다."
    },
    {
      "start_time": "22:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집으로 돌아와 오늘 하루를 정리하고 내일의 구직 계획을 세운 뒤 잠자리에 든다."
    }
  ],
  "staff": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "houses",
      "action": "집에서 출근 준비를 마치고 마을의 아침 상태를 살피며 주민센터로 걸어간다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "community_center",
      "action": "오전 민원 서류를 검토하고 방문하는 주민들의 복지 관련 상담을 꼼꼼하게 진행한다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "박사장의 카페에서 점심 식사 대용 샌드위치를 먹으며 이웃들과 짧은 대화를 나눈다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "welfare_center",
      "action": "복지관을 방문하여 김할머니의 건강 상태를 확인하고 시설 이용에 불편함이 없는지 살핀다."
    },
    {
      "start_time": "15:00",
      "end_time": "17:00",
      "location_key": "town_hall",
      "action": "마을회관에서 자원봉사자 미영과 함께 지역 사회 봉사 프로그램 일정에 대해 논의한다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:30",
      "location_key": "community_center",
      "action": "사무실로 복귀하여 오늘 현장에서 파악한 민원 사항을 시스템에 기록하고 서류를 정리한다."
    },
    {
      "start_time": "18:30",
      "end_time": "19:30",
      "location_key": "fountain_plaza",
      "action": "퇴근 후 분수광장을 한 바퀴 돌며 산책하는 주민들과 가벼운 인사를 나누고 휴식을 취한다."
    },
    {
      "start_time": "19:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집으로 돌아와 저녁 식사를 하고 조용히 독서를 하며 하루를 마무리한 뒤 잠자리에 든다."
    }
  ],
  "owner": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "houses",
      "action": "아침 식사를 간단히 마치고 오늘 카페에서 사용할 원두와 비품 목록을 점검한다."
    },
    {
      "start_time": "08:30",
      "end_time": "12:00",
      "location_key": "cafe",
      "action": "카페 문을 열고 단골 손님인 다은과 인사를 나누며 신선한 커피를 내린다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "fountain_plaza",
      "action": "점심 식사 후 분수광장을 산책하며 이웃 주민들과 만나 마을의 새로운 소식을 공유한다."
    },
    {
      "start_time": "13:00",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "아르바이트생 민수와 함께 몰려드는 오후 손님들을 응대하며 바쁘게 카페를 운영한다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "town_hall",
      "action": "마을회관에 들러 어르신들께 인사를 드리고 마을 잔치 일정에 대해 의논한다."
    },
    {
      "start_time": "19:00",
      "end_time": "21:30",
      "location_key": "cafe",
      "action": "조용한 저녁 분위기에 맞춰 음악을 바꾸고 카페 내부를 정돈하며 마감 준비를 한다."
    },
    {
      "start_time": "21:30",
      "end_time": "22:30",
      "location_key": "cafe",
      "action": "민수와 함께 주방 집기를 청소하고 오늘 하루의 매출을 정산하며 마감 작업을 마무리한다."
    },
    {
      "start_time": "22:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집으로 귀가하여 따뜻한 물로 샤워를 하고 내일 영업을 위해 일찍 잠자리에 든다."
    }
  ],
  "grandma": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "garden",
      "action": "마을텃밭에서 상추와 고추가 잘 자랐는지 살피며 잡초를 정성껏 뽑는다."
    },
    {
      "start_time": "09:00",
      "end_time": "10:00",
      "location_key": "bus_stop",
      "action": "복지관 셔틀버스를 기다리며 정류장에 모인 이웃 주민들과 반갑게 인사를 나눈다."
    },
    {
      "start_time": "10:00",
      "end_time": "12:00",
      "location_key": "welfare_center",
      "action": "복지관 노래 교실 수업에 참여하여 친구들과 함께 즐겁게 노래를 따라 부른다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:30",
      "location_key": "welfare_center",
      "action": "복지관 식당에서 친한 할머니들과 모여 앉아 수다를 떨며 점심 식사를 한다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:00",
      "location_key": "fountain_plaza",
      "action": "분수광장 벤치에 앉아 아이들이 노는 모습을 구경하며 시원한 바람을 쐰다."
    },
    {
      "start_time": "15:00",
      "end_time": "16:30",
      "location_key": "community_center",
      "action": "주민센터에 직접 방문하여 담당 공무원 영희에게 궁금한 행정 절차를 물어본다."
    },
    {
      "start_time": "16:30",
      "end_time": "18:00",
      "location_key": "park_pond",
      "action": "마을공원 연못가를 천천히 산책하던 중 박어르신을 만나 건강에 대한 이야기를 나눈다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:30",
      "location_key": "houses",
      "action": "집으로 돌아와 텃밭에서 따온 채소들로 간단하게 저녁 식사를 챙겨 먹는다."
    },
    {
      "start_time": "19:30",
      "end_time": "21:30",
      "location_key": "houses",
      "action": "거실에서 연속극을 시청하며 하루를 마무리하고 잠자리에 들 준비를 한다."
    },
    {
      "start_time": "21:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "내일 아침 일찍 일어날 수 있도록 일찍 불을 끄고 깊은 잠에 든다."
    }
  ],
  "sua": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "bus_stop",
      "action": "버스정류장에서 등교 버스를 기다리며 우연히 마주친 준호와 짧게 인사를 나눈다."
    },
    {
      "start_time": "08:30",
      "end_time": "16:30",
      "location_key": "school",
      "action": "학교에서 정규 수업을 듣고 쉬는 시간마다 친구들과 진로에 대한 고민을 나눈다."
    },
    {
      "start_time": "16:30",
      "end_time": "18:30",
      "location_key": "cafe",
      "action": "단골 카페에서 아르바이트 중인 민수 오빠에게 주문을 하고 친구들과 수다를 떨며 스트레스를 푼다."
    },
    {
      "start_time": "18:30",
      "end_time": "19:30",
      "location_key": "fountain_plaza",
      "action": "집으로 돌아가는 길에 분수광장에 잠시 앉아 시원한 물소리를 들으며 복잡한 머릿속을 정리한다."
    },
    {
      "start_time": "19:30",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "집에 도착해 가족들과 함께 저녁 식사를 하며 학교에서 있었던 일들을 이야기한다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "자신의 방 책상에 앉아 부족한 과목 인터넷 강의를 듣고 자정 무렵 취침을 준비한다."
    }
  ],
  "junho": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "houses",
      "action": "아침 식사를 마친 뒤 교복을 입고 가방을 챙기며 등교 준비를 한다."
    },
    {
      "start_time": "08:30",
      "end_time": "09:00",
      "location_key": "bus_stop",
      "action": "학교로 가는 버스를 기다리며 스마트폰으로 친구들과 오늘 계획을 이야기한다."
    },
    {
      "start_time": "09:00",
      "end_time": "16:00",
      "location_key": "school",
      "action": "학교에서 정규 수업을 듣고 쉬는 시간과 점심 시간에 친구들과 어울린다."
    },
    {
      "start_time": "16:00",
      "end_time": "17:30",
      "location_key": "playground",
      "action": "어린이놀이터에서 지민이와 술래잡기를 하며 동생들과 활동적으로 뛰어논다."
    },
    {
      "start_time": "17:30",
      "end_time": "18:30",
      "location_key": "fountain_plaza",
      "action": "분수광장 벤치에서 수아 누나를 만나 학교 생활에 대한 고민을 나누며 간식을 먹는다."
    },
    {
      "start_time": "18:30",
      "end_time": "19:30",
      "location_key": "houses",
      "action": "집으로 돌아와 가족들과 함께 저녁 식사를 하며 하루 일과를 공유한다."
    },
    {
      "start_time": "19:30",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "방에서 오늘 배운 내용을 복습하고 학교 숙제를 차근차근 마무리한다."
    },
    {
      "start_time": "21:00",
      "end_time": "22:30",
      "location_key": "houses",
      "action": "세면을 마친 뒤 좋아하는 음악을 들으며 내일 등교를 위해 가방을 정리한다."
    },
    {
      "start_time": "22:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "침대에 누워 다음 날을 위해 일찍 잠을 청한다."
    }
  ],
  "miyoung": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "houses",
      "action": "아이의 아침 식사를 챙겨주고 옷을 입히며 등원 준비를 한다."
    },
    {
      "start_time": "09:00",
      "end_time": "09:30",
      "location_key": "daycare",
      "action": "아이를 마을공동육아 시설에 맡기며 다른 학부모들과 짧게 인사를 나눈다."
    },
    {
      "start_time": "09:30",
      "end_time": "12:30",
      "location_key": "town_hall",
      "action": "마을회관에서 어르신들을 위한 다과를 준비하고 시설 내부를 정리하는 자원봉사를 한다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:30",
      "location_key": "cafe",
      "action": "카페에서 다은을 만나 시원한 음료를 마시며 육아와 마을 일에 대해 수다를 떤다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:00",
      "location_key": "community_center",
      "action": "주민센터에 들러 담당 공무원 영희와 다음 달 마을 봉사 일정에 대해 논의한다."
    },
    {
      "start_time": "15:00",
      "end_time": "16:30",
      "location_key": "garden",
      "action": "마을텃밭에서 저녁 식재료로 쓸 상추와 고추를 수확하고 흙을 고른다."
    },
    {
      "start_time": "16:30",
      "end_time": "17:30",
      "location_key": "daycare",
      "action": "어린이집에서 아이를 하원시키며 선생님으로부터 아이의 하루 일과를 듣는다."
    },
    {
      "start_time": "17:30",
      "end_time": "18:30",
      "location_key": "playground",
      "action": "아이가 친구들과 놀이터에서 노는 동안 다른 주민들과 마을 소식을 공유한다."
    },
    {
      "start_time": "18:30",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "텃밭에서 가져온 채소로 저녁 식사를 준비하여 가족과 함께 먹는다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "아이를 씻기고 동화책을 읽어주며 잠자리에 들 준비를 돕는다."
    },
    {
      "start_time": "22:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "밀린 집안일을 마무리하고 조용히 차를 마시며 하루를 정리한 뒤 취침한다."
    }
  ],
  "oldman": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "houses",
      "action": "집에서 아침 식사를 하고 가벼운 스트레칭을 하며 하루를 시작한다."
    },
    {
      "start_time": "09:00",
      "end_time": "11:00",
      "location_key": "park_pond",
      "action": "마을 공원 연못가를 천천히 산책하며 지나가는 이웃들과 반갑게 인사를 나눈다."
    },
    {
      "start_time": "11:00",
      "end_time": "12:30",
      "location_key": "welfare_center",
      "action": "복지관에서 운영하는 서예 프로그램에 참여하여 붓글씨 쓰기에 집중한다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:30",
      "location_key": "welfare_center",
      "action": "복지관 식당에서 김할머니를 만나 함께 점심 식사를 하며 안부를 묻는다."
    },
    {
      "start_time": "13:30",
      "end_time": "16:30",
      "location_key": "park_pond",
      "action": "공원 정자에 앉아 이웃 어르신들과 장기를 두며 즐거운 시간을 보낸다."
    },
    {
      "start_time": "16:30",
      "end_time": "17:30",
      "location_key": "cafe",
      "action": "박사장의 카페에 들러 따뜻한 차 한 잔을 마시며 잠시 휴식을 취한다."
    },
    {
      "start_time": "17:30",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "집으로 돌아와 직접 간단한 저녁 식사를 차려 먹는다."
    },
    {
      "start_time": "19:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "거실에서 텔레비전 뉴스를 시청하며 편안하게 휴식한다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "내일의 일과를 위해 일찍 잠자리에 들어 깊은 잠을 청한다."
    }
  ],
  "jimin": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "houses",
      "action": "엄마 미영과 함께 아침밥을 먹고 어린이집에 갈 준비를 하며 가방을 챙긴다."
    },
    {
      "start_time": "09:00",
      "end_time": "13:00",
      "location_key": "daycare",
      "action": "어린이집에서 친구들과 함께 장난감을 가지고 놀며 신나는 오전 활동에 참여한다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "daycare",
      "action": "점심 식사를 마친 후 선생님이 읽어주시는 동화책 소리를 들으며 낮잠을 잔다."
    },
    {
      "start_time": "15:00",
      "end_time": "16:30",
      "location_key": "daycare",
      "action": "낮잠에서 깨어나 맛있는 오후 간식을 먹고 친구들과 블록 쌓기 놀이를 한다."
    },
    {
      "start_time": "16:30",
      "end_time": "18:00",
      "location_key": "playground",
      "action": "놀이터에서 형 준호를 만나 함께 미끄럼틀을 타고 모래놀이를 하며 즐겁게 뛰어논다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "fountain_plaza",
      "action": "분수광장에서 물줄기를 구경하며 산책 나온 마을 이웃들에게 반갑게 인사한다."
    },
    {
      "start_time": "19:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "집으로 돌아와 가족들과 저녁을 먹고 자기 전까지 좋아하는 만화 영화를 본다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "오늘 하루의 즐거웠던 기억을 뒤로하고 침대에 누워 깊은 잠에 든다."
    }
  ],
  "daeun": [
    {
      "start_time": "08:00",
      "end_time": "09:30",
      "location_key": "houses",
      "action": "집에서 간단히 아침을 먹고 이메일을 확인하며 프리랜서 업무를 시작한다."
    },
    {
      "start_time": "09:30",
      "end_time": "12:30",
      "location_key": "cafe",
      "action": "카페의 창가 자리에 앉아 박사장과 인사를 나누고 집중해서 프로젝트 작업을 진행한다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:30",
      "location_key": "houses",
      "action": "집으로 돌아와 직접 차린 간단한 점심 식사를 하며 휴식을 취한다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:30",
      "location_key": "garden",
      "action": "마을 텃밭에서 키우는 채소들에 물을 주고 잡초를 뽑으며 이웃들과 가벼운 대화를 나눈다."
    },
    {
      "start_time": "15:30",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "다시 카페로 이동해 오후 마감 업무를 처리하며 박사장이 추천해준 신메뉴 음료를 마신다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:30",
      "location_key": "houses",
      "action": "집에서 저녁 식사를 준비해 먹고 편안한 옷으로 갈아입는다."
    },
    {
      "start_time": "19:30",
      "end_time": "21:00",
      "location_key": "fountain_plaza",
      "action": "분수광장을 산책하며 미영을 만나 마을 소식과 육아 고민에 대해 다정하게 이야기를 나눈다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 오늘 작업한 결과물을 최종 검토한 뒤 독서를 하며 차분하게 하루를 마무리한다."
    }
  ]
};
