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
      "action": "부족한 잠을 보충하며 침대에서 휴식을 취한다."
    },
    {
      "start_time": "08:30",
      "end_time": "10:00",
      "location_key": "houses",
      "action": "기상하여 간단히 아침을 먹고 오늘 지원할 채용 공고 리스트를 정리한다."
    },
    {
      "start_time": "10:00",
      "end_time": "12:30",
      "location_key": "houses",
      "action": "집중해서 자기소개서를 작성하고 포트폴리오 자료를 최신화한다."
    },
    {
      "start_time": "12:30",
      "end_time": "13:30",
      "location_key": "fountain_plaza",
      "action": "점심 식사 후 분수광장에서 산책을 하며 이웃들과 가볍게 안부를 나눈다."
    },
    {
      "start_time": "13:30",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "박사장님을 도와 카페에서 아르바이트를 하며 주문을 받고 음료를 제조한다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:30",
      "location_key": "cafe",
      "action": "근무를 마무리하고 박사장님이 챙겨준 샌드위치로 간단히 저녁 식사를 한다."
    },
    {
      "start_time": "19:30",
      "end_time": "21:30",
      "location_key": "park_pond",
      "action": "마을공원 연못 주변을 산책하며 취업 스트레스를 해소하고 운동 나온 주민들과 대화한다."
    },
    {
      "start_time": "21:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집으로 돌아와 오늘 하루를 기록하고 내일의 구직 계획을 세운 뒤 잠자리에 든다."
    }
  ],
  "staff": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "houses",
      "action": "출근 준비를 마치고 집을 나서며 현관 앞을 정리한다."
    },
    {
      "start_time": "08:30",
      "end_time": "09:00",
      "location_key": "fountain_plaza",
      "action": "주민센터로 걸어가며 분수광장의 시설 상태와 청결도를 꼼꼼히 살핀다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "community_center",
      "action": "주민센터에서 오전 민원을 응대하고 접수된 정책 관련 서류들을 검토한다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "cafe",
      "action": "카페에서 박사장과 가벼운 인사를 나누며 샌드위치로 점심 식사를 한다."
    },
    {
      "start_time": "13:00",
      "end_time": "15:00",
      "location_key": "welfare_center",
      "action": "복지관을 방문하여 김할머니의 안부를 묻고 어르신들의 생활 불편사항을 경청한다."
    },
    {
      "start_time": "15:00",
      "end_time": "18:30",
      "location_key": "community_center",
      "action": "현장에서 파악한 민원 내용을 정리하고 보고서를 작성하며 오후 업무를 마무리한다."
    },
    {
      "start_time": "18:30",
      "end_time": "19:30",
      "location_key": "town_hall",
      "action": "퇴근길에 마을회관에 들러 자원봉사 중인 미영과 주민들의 근황에 대해 이야기를 나눈다."
    },
    {
      "start_time": "19:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에 도착해 저녁 식사를 하고 독서를 하며 조용한 휴식 시간을 보낸다."
    }
  ],
  "owner": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "cafe",
      "action": "카페 문을 열고 신선한 원두를 볶으며 손님 맞이 준비를 시작한다."
    },
    {
      "start_time": "09:00",
      "end_time": "11:30",
      "location_key": "cafe",
      "action": "출근하는 주민들에게 커피를 내어주며 가벼운 아침 인사를 건네고 마을 소식을 듣는다."
    },
    {
      "start_time": "11:30",
      "end_time": "12:30",
      "location_key": "garden",
      "action": "마을 텃밭에 들러 직접 기르는 허브 상태를 확인하고 이웃 주민들과 작물에 대해 대화한다."
    },
    {
      "start_time": "12:30",
      "end_time": "15:00",
      "location_key": "cafe",
      "action": "점심 식사 후 카페를 찾은 손님들을 민수와 함께 바쁘게 응대하며 음료를 제조한다."
    },
    {
      "start_time": "15:00",
      "end_time": "16:30",
      "location_key": "fountain_plaza",
      "action": "잠시 카페를 민수에게 맡기고 분수광장 벤치에 앉아 휴식을 취하며 산책 중인 주민들과 담소를 나눈다."
    },
    {
      "start_time": "16:30",
      "end_time": "19:00",
      "location_key": "cafe",
      "action": "오후 단골손님인 다은에게 신메뉴 시음을 부탁하며 마을의 이런저런 이야기를 공유한다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "town_hall",
      "action": "마을회관에 들러 저녁 모임 중인 어르신들께 인사를 드리고 마을 행사에 대해 논의한다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:00",
      "location_key": "cafe",
      "action": "카페로 돌아와 마감 청소를 하고 비품 재고를 확인하며 하루 영업을 정리한다."
    },
    {
      "start_time": "22:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집으로 귀가하여 따뜻한 물로 샤워를 한 뒤 소파에서 휴식을 취하다 잠자리에 든다."
    }
  ],
  "grandma": [
    {
      "start_time": "08:00",
      "end_time": "09:30",
      "location_key": "garden",
      "action": "아침 일찍 텃밭에 나가 자라난 상추와 고추를 살피며 물을 준다."
    },
    {
      "start_time": "09:30",
      "end_time": "10:30",
      "location_key": "houses",
      "action": "집으로 돌아와 외출 준비를 하고 복지관에 갈 채비를 마친다."
    },
    {
      "start_time": "10:30",
      "end_time": "12:00",
      "location_key": "welfare_center",
      "action": "복지관에서 운영하는 노래 교실 프로그램에 참여해 이웃들과 노래를 부른다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:30",
      "location_key": "welfare_center",
      "action": "복지관 식당에서 친구들과 함께 점심 식사를 하며 담소를 나눈다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:00",
      "location_key": "town_hall",
      "action": "마을회관 따뜻한 방바닥에 앉아 박어르신과 장기 두는 것을 구경하며 쉰다."
    },
    {
      "start_time": "15:00",
      "end_time": "16:30",
      "location_key": "park_pond",
      "action": "소화도 시킬 겸 공원 연못가를 천천히 한 바퀴 돌며 산책한다."
    },
    {
      "start_time": "16:30",
      "end_time": "17:30",
      "location_key": "community_center",
      "action": "주민센터에 들러 영희에게 다음 달 복지 프로그램 일정을 직접 물어본다."
    },
    {
      "start_time": "17:30",
      "end_time": "19:00",
      "location_key": "houses",
      "action": "집으로 돌아와 간단하게 저녁을 차려 먹고 주방을 정리한다."
    },
    {
      "start_time": "19:00",
      "end_time": "21:30",
      "location_key": "houses",
      "action": "거실에서 텔레비전 뉴스를 시청하며 하루 일과를 마무리한다."
    },
    {
      "start_time": "21:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "내일의 이른 기상을 위해 일찍 잠자리에 든다."
    }
  ],
  "sua": [
    {
      "start_time": "08:00",
      "end_time": "08:30",
      "location_key": "houses",
      "action": "교복을 챙겨 입고 가방에 교과서를 넣으며 등교 준비를 마무리한다."
    },
    {
      "start_time": "08:30",
      "end_time": "09:00",
      "location_key": "bus_stop",
      "action": "학교 가는 버스를 기다리는 동안 단어장을 보며 영어 단어를 외운다."
    },
    {
      "start_time": "09:00",
      "end_time": "16:30",
      "location_key": "school",
      "action": "정규 수업과 보충 수업에 집중하며 대입 진로에 대해 고민한다."
    },
    {
      "start_time": "16:30",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "아르바이트 중인 민수에게 인사를 건네고 친구들과 음료를 마시며 수다를 떤다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "fountain_plaza",
      "action": "집으로 돌아가는 길에 분수대 근처 벤치에 앉아 친구와 남은 이야기를 나눈다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:00",
      "location_key": "houses",
      "action": "가족들과 함께 저녁 식사를 하며 학교에서 있었던 일들을 공유한다."
    },
    {
      "start_time": "20:00",
      "end_time": "22:30",
      "location_key": "houses",
      "action": "책상에 앉아 오늘 배운 내용을 복습하고 다음 시험 범위 문제집을 푼다."
    },
    {
      "start_time": "22:30",
      "end_time": "23:30",
      "location_key": "park_pond",
      "action": "공부하다 머리를 식히러 나와 산책 중인 준호를 만나 가볍게 안부를 묻는다."
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
      "end_time": "08:30",
      "location_key": "houses",
      "action": "아침 식사를 마치고 교복을 챙겨 입으며 등교 준비를 한다."
    },
    {
      "start_time": "08:30",
      "end_time": "09:00",
      "location_key": "bus_stop",
      "action": "버스정류장에서 학교로 가는 버스를 기다리며 친구와 인사를 나눈다."
    },
    {
      "start_time": "09:00",
      "end_time": "15:30",
      "location_key": "school",
      "action": "교실에서 정규 수업을 듣고 점심시간에는 친구들과 운동장에서 뛰어논다."
    },
    {
      "start_time": "15:30",
      "end_time": "16:30",
      "location_key": "school",
      "action": "방과 후 교실에 남아 숙제를 미리 하거나 친구들과 가벼운 운동을 한다."
    },
    {
      "start_time": "16:30",
      "end_time": "18:00",
      "location_key": "playground",
      "action": "어린이놀이터에서 지민이와 놀아주거나 동네 친구들과 술래잡기를 하며 시간을 보낸다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:00",
      "location_key": "fountain_plaza",
      "action": "분수광장 근처 벤치에 앉아 땀을 식히며 지나가는 이웃들에게 인사한다."
    },
    {
      "start_time": "19:00",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "집으로 돌아와 가족들과 함께 저녁 식사를 하며 학교에서 있었던 일을 이야기한다."
    },
    {
      "start_time": "20:30",
      "end_time": "22:00",
      "location_key": "houses",
      "action": "자기 전 방에서 좋아하는 음악을 듣거나 내일 학교 수업을 위한 가방을 챙긴다."
    },
    {
      "start_time": "22:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "내일의 활기찬 하루를 위해 일찍 불을 끄고 잠자리에 든다."
    }
  ],
  "miyoung": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "daycare",
      "action": "딸 지민이를 어린이집에 등원시키고 담당 선생님과 아이의 건강 상태에 대해 짧게 대화합니다."
    },
    {
      "start_time": "09:00",
      "end_time": "12:00",
      "location_key": "town_hall",
      "action": "마을회관에서 어르신들의 점심 식사 준비를 돕고 시설 내부를 정돈하며 봉사 활동에 전념합니다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:30",
      "location_key": "cafe",
      "action": "다은과 만나 가벼운 점심 식사를 하며 마을 공동체 프로그램에 대한 아이디어를 공유합니다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:30",
      "location_key": "garden",
      "action": "마을 텃밭에서 공동으로 재배하는 채소에 물을 주고 잡초를 뽑으며 주변 환경을 정리합니다."
    },
    {
      "start_time": "15:30",
      "end_time": "17:00",
      "location_key": "community_center",
      "action": "주민센터에서 영희를 만나 다음 달 마을회관 봉사 일정과 필요한 지원 물품에 대해 논의합니다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:30",
      "location_key": "playground",
      "action": "지민이를 어린이집에서 데려온 후 놀이터에서 아이가 친구들과 충분히 뛰어놀 수 있도록 지켜봅니다."
    },
    {
      "start_time": "18:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집으로 돌아와 가족과 저녁 식사를 하고 지민이를 재운 뒤 집안일을 마무리하며 휴식을 취합니다."
    }
  ],
  "oldman": [
    {
      "start_time": "08:00",
      "end_time": "09:30",
      "location_key": "park_pond",
      "action": "공원 연못가를 천천히 산책하며 아침 공기를 마시고 가벼운 체조를 한다."
    },
    {
      "start_time": "09:30",
      "end_time": "12:00",
      "location_key": "welfare_center",
      "action": "복지관에서 진행하는 서예 프로그램에 참여하여 붓글씨를 연습한다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:00",
      "location_key": "welfare_center",
      "action": "복지관 식당에서 김할머니와 나란히 앉아 점심 식사를 하며 안부를 묻는다."
    },
    {
      "start_time": "13:00",
      "end_time": "17:00",
      "location_key": "park_pond",
      "action": "공원 정자에서 동네 친구들과 바둑과 장기를 두며 즐거운 오후 시간을 보낸다."
    },
    {
      "start_time": "17:00",
      "end_time": "18:30",
      "location_key": "town_hall",
      "action": "마을회관에 들러 마을 돌아가는 소식을 듣고 이웃 주민들과 짧게 담소를 나눈다."
    },
    {
      "start_time": "18:30",
      "end_time": "20:30",
      "location_key": "houses",
      "action": "집으로 귀가하여 간단하게 저녁을 챙겨 먹고 텔레비전을 시청한다."
    },
    {
      "start_time": "20:30",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "내일 일과를 위해 일찍 잠자리에 들어 깊은 잠을 청한다."
    }
  ],
  "jimin": [
    {
      "start_time": "08:00",
      "end_time": "09:00",
      "location_key": "houses",
      "action": "엄마 미영이 준비해준 아침밥을 먹고 어린이집에 갈 준비를 하며 가방을 챙긴다."
    },
    {
      "start_time": "09:00",
      "end_time": "10:00",
      "location_key": "bus_stop",
      "action": "엄마 손을 잡고 버스정류장에서 친구들을 기다리며 노란색 어린이집 버스에 올라탄다."
    },
    {
      "start_time": "10:00",
      "end_time": "15:30",
      "location_key": "daycare",
      "action": "어린이집에서 친구들과 함께 수업을 듣고 맛있는 점심과 간식을 먹으며 즐거운 시간을 보낸다."
    },
    {
      "start_time": "15:30",
      "end_time": "17:30",
      "location_key": "playground",
      "action": "하원 후 놀이터에서 미끄럼틀을 타고 모래놀이를 하며 동네 친구들과 신나게 뛰어논다."
    },
    {
      "start_time": "17:30",
      "end_time": "18:30",
      "location_key": "fountain_plaza",
      "action": "분수광장에서 솟아오르는 물줄기를 구경하고 지나가는 이웃들에게 반갑게 인사하며 산책한다."
    },
    {
      "start_time": "18:30",
      "end_time": "20:00",
      "location_key": "houses",
      "action": "집에 돌아와 깨끗이 씻고 가족들과 둘러앉아 도란도란 이야기를 나누며 저녁 식사를 한다."
    },
    {
      "start_time": "20:00",
      "end_time": "21:00",
      "location_key": "houses",
      "action": "잠들기 전 거실에서 가장 좋아하는 동화책을 읽으며 꿈나라로 갈 준비를 한다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "방에 불을 끄고 포근한 이불 속에서 내일의 놀이를 기대하며 깊은 잠에 든다."
    }
  ],
  "daeun": [
    {
      "start_time": "08:00",
      "end_time": "09:30",
      "location_key": "houses",
      "action": "기상 후 간단한 아침 식사를 하고 노트북을 켜서 업무 메일을 확인합니다."
    },
    {
      "start_time": "09:30",
      "end_time": "12:00",
      "location_key": "cafe",
      "action": "노트북을 챙겨 카페로 이동해 박사장님과 인사하고 집중해서 프로젝트 작업을 진행합니다."
    },
    {
      "start_time": "12:00",
      "end_time": "13:30",
      "location_key": "houses",
      "action": "집으로 돌아와 간단하게 점심을 챙겨 먹으며 휴식 시간을 가집니다."
    },
    {
      "start_time": "13:30",
      "end_time": "15:30",
      "location_key": "garden",
      "action": "마을 텃밭으로 나가 키우고 있는 채소들에 물을 주고 잡초를 뽑으며 시간을 보냅니다."
    },
    {
      "start_time": "15:30",
      "end_time": "18:00",
      "location_key": "cafe",
      "action": "다시 카페에 들러 시원한 음료를 마시며 남은 업무 분량을 마무리합니다."
    },
    {
      "start_time": "18:00",
      "end_time": "19:30",
      "location_key": "houses",
      "action": "집에서 직접 만든 저녁 식사를 하며 하루 일과를 정리합니다."
    },
    {
      "start_time": "19:30",
      "end_time": "21:00",
      "location_key": "park_pond",
      "action": "소화를 시킬 겸 마을 공원 연못가를 천천히 산책하며 밤바람을 즐깁니다."
    },
    {
      "start_time": "21:00",
      "end_time": "24:00",
      "location_key": "houses",
      "action": "집에서 독서를 하거나 조용히 음악을 들으며 취침 전 개인 정비 시간을 가집니다."
    }
  ]
};
