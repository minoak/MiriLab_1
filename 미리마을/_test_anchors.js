// 좌표 앵커 로직 단위 검증 (headless). index.html 의 함수들을 동일 재현해 데이터로 확인.
const fs=require('fs');
const villagers=JSON.parse(fs.readFileSync(__dirname+'/data/villagers.json','utf8')).villagers;
const locations=JSON.parse(fs.readFileSync(__dirname+'/data/locations.json','utf8')).locations;
const nodes=JSON.parse(fs.readFileSync(__dirname+'/path_data.json','utf8')).nodes;
// anchors.js 는 순수 객체 리터럴이라 eval 없이 JSON 본문만 떼어내 안전하게 파싱
const anchorsSrc=fs.readFileSync(__dirname+'/data/anchors.js','utf8');
const ANCHORS_DEFAULT=JSON.parse(anchorsSrc.match(/const ANCHORS_DEFAULT\s*=\s*([\s\S]*);\s*$/)[1]);
const ANCHORS=JSON.parse(JSON.stringify(ANCHORS_DEFAULT));
const VILLAGERS=villagers, LOCATIONS=locations;
const HOME_KEY='houses';
const LOC_BY_KEY={}; LOCATIONS.forEach(l=>LOC_BY_KEY[l.key]=l);
const SLOT_N=VILLAGERS.length;
const SLOT_NORM=Array.from({length:SLOT_N},(_,i)=>{const GA=2.399963,ang=i*GA,r=Math.sqrt((i+0.5)/SLOT_N)*0.5;return [Math.cos(ang)*r,Math.sin(ang)*r];});
function slotOffset(i,spread){const s=SLOT_NORM[i]||[0,0];const w=(spread&&spread[0]!=null)?spread[0]:34,h=(spread&&spread[1]!=null)?spread[1]:26;return {x:s[0]*w,y:s[1]*h};}
const HOUSE_BY_AGENT={}; (ANCHORS.houses||[]).forEach(h=>(h.residents||[]).forEach(r=>HOUSE_BY_AGENT[r]=h));
function homePosFor(id,i){const h=HOUSE_BY_AGENT[id];if(h&&h.pos){const o=slotOffset(i,h.spread);return {x:h.pos[0]+o.x,y:h.pos[1]+o.y};}const loc=LOC_BY_KEY[HOME_KEY];const n=(loc&&nodes[loc.node])?nodes[loc.node]:[700,500];const o=slotOffset(i,[34,26]);return {x:n[0]+o.x,y:n[1]+o.y};}
function arrivalPosFor(key,id,i){if(key===HOME_KEY)return homePosFor(id,i);const p=ANCHORS.places&&ANCHORS.places[key];if(p&&p.arrival){const o=slotOffset(i,p.spread);return {x:p.arrival[0]+o.x,y:p.arrival[1]+o.y};}const loc=LOC_BY_KEY[key];const n=(loc&&nodes[loc.node])?nodes[loc.node]:null;if(n){const o=slotOffset(i,[46,30]);return {x:n[0]+o.x,y:n[1]+o.y};}return null;}

let fail=0; const bad=m=>{console.log('  FAIL '+m);fail++;};
// 1) 시작 위치가 한 점이 아니라 8채에 분산
const starts=VILLAGERS.map((v,i)=>homePosFor(v.id,i));
const uniqHouses=new Set(VILLAGERS.map(v=>HOUSE_BY_AGENT[v.id]&&HOUSE_BY_AGENT[v.id].id));
console.log('[1] 배정된 집 수:',uniqHouses.size,'(기대 8)');
if(uniqHouses.size!==8) bad('집 8채가 아님');
// 2) 각 캐릭터가 자기 집 박스 안
VILLAGERS.forEach((v,i)=>{const h=HOUSE_BY_AGENT[v.id];const p=homePosFor(v.id,i);const d=Math.hypot(p.x-h.pos[0],p.y-h.pos[1]);const maxd=Math.hypot((h.spread[0]||34)/2,(h.spread[1]||26)/2);if(d>maxd+0.01)bad('슬롯 박스 초과 '+v.id+' d='+d.toFixed(1)+' max='+maxd.toFixed(1));});
console.log('[2] 모든 캐릭터 집 박스 내 배치 확인');
// 3) slotOffset 이 spread 박스 절반 안
for(let i=0;i<SLOT_N;i++){const o=slotOffset(i,[46,30]);if(Math.abs(o.x)>23.01||Math.abs(o.y)>15.01)bad('slot 범위 초과 '+i+' '+JSON.stringify(o));}
console.log('[3] slotOffset 박스 범위 확인');
// 4) 모든 활동 장소 arrival 좌표 존재
Object.keys(ANCHORS.places).forEach(key=>{const p=arrivalPosFor(key,'minsu',0);if(!p)bad('arrival null '+key);});
console.log('[4] 활동 장소 12곳 arrival 확인');
// 5) houses 키 도착 = 집 좌표
const ah=arrivalPosFor('houses','miyoung',6), hh=homePosFor('miyoung',6);
if(Math.abs(ah.x-hh.x)>0.01||Math.abs(ah.y-hh.y)>0.01)bad('houses 도착 != 집');
console.log('[5] houses 도착=집 확인');
// 6) 모든 캐릭터가 집에 배정됨
VILLAGERS.forEach(v=>{if(!HOUSE_BY_AGENT[v.id])bad('미배정 '+v.id);});
console.log('[6] 캐릭터 10명 전원 집 배정 확인');
// 7) 시작점 평균 분산(한 점 뭉침이 아님): 좌우 폭이 충분
const xs=starts.map(p=>p.x); const span=Math.max(...xs)-Math.min(...xs);
console.log('[7] 시작 x 분포 폭:',span.toFixed(0),'px (기대 >400, 기존 단일노드는 ~60)');
if(span<300)bad('시작 분산 부족 span='+span.toFixed(0));
console.log(fail===0?'\nALL PASS':('\nFAILS='+fail));
process.exit(fail?1:0);
