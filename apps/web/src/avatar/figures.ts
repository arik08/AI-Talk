/**
 * 인물 아바타: 보관함의 유명인을 알아볼 수 있게 그린 색 일러스트.
 *
 * 사진이나 생성 이미지를 쓰지 않고 기본 도형과 곡선으로 그린다. 인물마다 얼굴형, 피부색, 머리 모양과 색,
 * 주름, 수염, 안경, 모자, 복장처럼 널리 알려진 특징을 담는다.
 * 눈썹·눈·입은 avatar.ts가 얼굴 세트와 같은 자리에 그려 넣어 감정에 따라 움직인다:
 * 눈썹 y=40.5, 눈 (39.5, 51)·(60.5, 51), 입 (50, 68). 그림은 이 자리에 맞춰 그린다.
 *
 * 겹치는 순서: clothes → back → 목 → front → 귀 → 얼굴 → marks → hair → beard → (눈썹·눈·입) → over → top
 * top만 둥근 틀 밖으로 나갈 수 있다 (모자의 챙, 투구의 꼭지).
 */

const K = '#2A1C14';            // 윤곽선
const SH = '#8A5A3C';           // 얼굴의 주름과 코에 쓰는 그늘색
const WHITE = '#F4F1EA';
const GOLD = '#D4A63A';

const p = (d: string, fill: string, sw = 1.1): string =>
  `<path d="${d}" fill="${fill}" stroke="${K}" stroke-width="${sw}" stroke-linejoin="round"/>`;
const c = (cx: number, cy: number, r: number, fill: string, sw = 1.1): string =>
  `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" stroke="${K}" stroke-width="${sw}"/>`;
const l = (d: string, color = SH, sw = 1.1, opacity = 1): string =>
  `<path d="${d}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" opacity="${opacity}"/>`;
const soft = (d: string, fill: string, opacity: number): string => `<path d="${d}" fill="${fill}" opacity="${opacity}"/>`;
/** 좌우 대칭인 조각: x를 100에서 뺀 것을 함께 그린다. */
const both = (make: (flip: (x: number) => number) => string): string => make((x) => x) + make((x) => 100 - x);

const FACE: Record<string, string> = {
  oval: 'M26 46 Q26 20 50 20 Q74 20 74 46 Q74 70 62 79 Q50 86 38 79 Q26 70 26 46Z',
  round: 'M24 48 Q24 20 50 20 Q76 20 76 48 Q76 72 62 80 Q50 85 38 80 Q24 72 24 48Z',
  long: 'M28 46 Q28 19 50 19 Q72 19 72 46 Q72 68 61 80 Q50 88 39 80 Q28 68 28 46Z',
  square: 'M26 44 Q26 20 50 20 Q74 20 74 44 L73 66 Q70 80 56 83 L44 83 Q30 80 27 66Z',
  jowly: 'M25 44 Q25 20 50 20 Q75 20 75 44 Q79 70 66 80 Q50 87 34 80 Q21 70 25 44Z',
};

const SHOULDERS = 'M12 102 Q14 86 34 83 L42 81 L58 81 L66 83 Q86 86 88 102Z';
const shoulders = (color: string): string => p(SHOULDERS, color);
const neck = (skin: string): string => p('M42 70 L42 84 Q50 89 58 84 L58 70Z', skin);
const ears = (skin: string, r = 5): string => c(24.5, 53, r, skin) + c(75.5, 53, r, skin);
const shirt = p('M42 81 L50 93 L58 81 L55 78.5 L45 78.5Z', WHITE);
const lapels = l('M42 81 L47.5 98', K, 1.1) + l('M58 81 L52.5 98', K, 1.1);
const tie = (color: string, long = false): string =>
  p(long ? 'M48 85 L52 85 L54.5 100 L50 104 L45.5 100Z' : 'M48 85 L52 85 L54 101 L46 101Z', color, 0.9);
const suit = (color: string, tieColor: string, long = false) => ({ clothes: shoulders(color), front: shirt + tie(tieColor, long) + lapels });

const NOSE = {
  soft: l('M50 54 Q46.5 61 51 62', SH, 1.3),
  big: l('M50 52 Q43.5 62 52.5 63.5', SH, 1.5),
  long: l('M50 50 Q45.5 63 51.5 64', SH, 1.4),
  snub: l('M46.5 59 Q50 64.5 53.5 59', SH, 1.5),
};
const FOREHEAD = l('M38 31 Q50 28 62 31', SH, 0.9, 0.8) + l('M40 35 Q50 32.5 60 35', SH, 0.9, 0.8);
const SMILE_LINES = l('M36.5 60 Q33.5 67 37.5 73', SH, 1, 0.85) + l('M63.5 60 Q66.5 67 62.5 73', SH, 1, 0.85);
const UNDER_EYES = l('M35 57.5 Q39.5 59.5 44 57.5', SH, 0.9, 0.7) + l('M56 57.5 Q60.5 59.5 65 57.5', SH, 0.9, 0.7);

const glassesRound = (color: string, sw = 1.4): string =>
  `<g fill="none" stroke="${color}" stroke-width="${sw}"><circle cx="39.5" cy="51" r="8.4"/><circle cx="60.5" cy="51" r="8.4"/><path d="M47.9 50 Q50 48.5 52.1 50"/><path d="M31.1 50 L25 48.5"/><path d="M68.9 50 L75 48.5"/></g>`;
const glassesSquare = (color: string, sw = 2): string =>
  `<g fill="none" stroke="${color}" stroke-width="${sw}"><rect x="29.5" y="43.5" width="19" height="15" rx="4"/><rect x="51.5" y="43.5" width="19" height="15" rx="4"/><path d="M48.5 49 L51.5 49"/><path d="M29.5 49 L25 47.5"/><path d="M70.5 49 L75 47.5"/></g>`;
const glassesThin = (color: string): string =>
  `<g fill="none" stroke="${color}" stroke-width="1.2"><ellipse cx="39.5" cy="51" rx="9.2" ry="6.2"/><ellipse cx="60.5" cy="51" rx="9.2" ry="6.2"/><path d="M48.7 50 L51.3 50"/><path d="M30.3 50 L25 48.5"/><path d="M69.7 50 L75 48.5"/></g>`;
const mustache = (color: string): string =>
  p('M38 61.5 Q44 57 50 60 Q56 57 62 61.5 Q56 64 50 62.8 Q44 64 38 61.5Z', color, 0.7);

export interface Figure {
  name: string;
  skin: string;
  face: keyof typeof FACE;
  brow: string;          // 눈썹 색
  browH?: number;        // 눈썹 굵기 (기본 3)
  earR?: number;
  clothes: string;
  back?: string;
  front?: string;
  marks?: string;
  hair?: string;
  beard?: string;
  over?: string;
  top?: string;
}

export const FIGURES: Figure[] = [
  { name: '일론 머스크', skin: '#F0CBA8', face: 'square', brow: '#3A2A20',
    clothes: shoulders('#1F1F24'), front: p('M40 82 Q50 91 60 82 L58 79 L42 79Z', '#3A3A42'),
    marks: NOSE.soft + l('M56 71 Q60 70 62 67', SH, 1, 0.8),
    hair: p('M25 44 Q21 15 50 15 Q79 15 75 44 Q73 31 61 27 Q45 23 34 29 Q28 33 25 44Z', '#3A2A20') },

  { name: '스티브 잡스', skin: '#EFC9A9', face: 'long', brow: '#6E6E6E',
    clothes: shoulders('#161618'), front: p('M40 74 Q50 79 60 74 L61.5 86 Q50 91 38.5 86Z', '#232327'),
    marks: NOSE.long + FOREHEAD,
    hair: soft('M30 31 Q50 13 70 31 Q50 23 30 31Z', '#8E8E8E', 0.5)
      + both((f) => p(`M${f(28)} 47 Q${f(25)} 31 ${f(33)} 24 L${f(34)} 39Z`, '#8E8E8E')),
    beard: soft('M29 58 Q30 79 50 86 Q70 79 71 58 Q66 74 50 76 Q34 74 29 58Z', '#7A7A7A', 0.55),
    over: glassesRound('#2B2B2B', 1.2) },

  { name: '워런 버핏', skin: '#F2CDB5', face: 'jowly', brow: '#D8D8D8', ...suit('#27344D', '#B8322C'),
    marks: NOSE.big + FOREHEAD + SMILE_LINES,
    hair: p('M24 44 Q20 18 50 17 Q80 18 76 44 Q73 30 56 28 Q38 27 30 33 Q26 37 24 44Z', '#EFEFEF'),
    over: glassesSquare('#4B3A2C', 2.2) },

  { name: '샘 올트먼', skin: '#F1CCAB', face: 'long', brow: '#5B4131',
    clothes: shoulders('#5F6B7A'), front: p('M41 81 Q50 89 59 81 L57 78.5 L43 78.5Z', '#4F5A68'),
    marks: NOSE.soft,
    hair: p('M27 44 Q24 22 31 25 Q32 15 40 21 Q44 11 51 20 Q57 11 62 21 Q69 15 70 25 Q76 22 73 44 Q70 31 60 29 Q46 26 36 30 Q30 34 27 44Z', '#5B4131') },

  { name: '도널드 트럼프', skin: '#EFA76B', face: 'jowly', brow: '#D9AE45', browH: 3.4, ...suit('#1F2A44', '#C8242B', true),
    marks: `<ellipse cx="39.5" cy="50.5" rx="8.4" ry="6.6" fill="#F9DAB6" opacity=".85"/><ellipse cx="60.5" cy="50.5" rx="8.4" ry="6.6" fill="#F9DAB6" opacity=".85"/>${NOSE.big}${SMILE_LINES}`,
    hair: p('M20 46 Q11 11 54 10 Q93 9 81 44 Q78 26 58 27 Q40 26 30 32 Q22 37 20 46Z', '#F3CB52')
      + l('M26 31 Q50 16 79 27', '#C99A2E', 1.1) + l('M30 27 Q52 15 74 22', '#C99A2E', 0.9) },

  { name: '박태준', skin: '#E9BE98', face: 'square', brow: '#2A2A2A',
    clothes: shoulders('#3F5F86'), front: p('M42 81 L50 90 L58 81 L63 84.5 L54 96 L50 91.5 L46 96 L37 84.5Z', '#35527A'),
    marks: NOSE.soft + SMILE_LINES,
    hair: both((f) => p(`M${f(26)} 48 Q${f(25)} 38 ${f(27.5)} 36 L${f(30.5)} 38 L${f(29.5)} 48Z`, '#2A2A2A', 0.8)),
    over: glassesThin('#3A3A3A')
      + p('M22 36 Q22 9 50 9 Q78 9 78 36Z', '#F5F4EE') + p('M46.5 9.6 L53.5 9.6 L53.5 34 L46.5 34Z', '#2F6DB5', 0.8)
      + p('M14 34 L86 34 Q88.5 39.5 84 39.5 L16 39.5 Q11.5 39.5 14 34Z', '#E4E2D8') },

  { name: '박정희', skin: '#D8A67C', face: 'long', brow: '#17171A', ...suit('#2A2A30', '#17171A'),
    marks: NOSE.long + l('M38 62 Q35.5 68 38.5 73', SH, 1, 0.85) + l('M62 62 Q64.5 68 61.5 73', SH, 1, 0.85),
    hair: p('M28 43 Q26 18 50 18 Q74 18 72 43 Q68 28 50 27 Q32 28 28 43Z', '#17171A'),
    over: `<g fill="#101012" stroke="${K}" stroke-width=".8"><rect x="29.5" y="45" width="19" height="12.5" rx="4.5"/><rect x="51.5" y="45" width="19" height="12.5" rx="4.5"/></g>${l('M48.5 48.5 L51.5 48.5', '#101012', 2)}${l('M29.5 49 L25 47.5', '#101012', 1.4)}${l('M70.5 49 L75 47.5', '#101012', 1.4)}` },

  { name: '이순신', skin: '#E2B38A', face: 'round', brow: '#1A1A1A', browH: 3.6,
    clothes: shoulders('#7C1E1E') + l('M16 92 Q34 86 42 84', GOLD, 1.4) + l('M84 92 Q66 86 58 84', GOLD, 1.4),
    back: both((f) => p(`M${f(13)} 41 L${f(26)} 36 L${f(27)} 75 L${f(15)} 80Z`, '#7C1E1E')
      + [46, 56, 66].map((y) => c(f(19.5), y, 1.5, GOLD, 0.5)).join('')),
    front: p('M42 81 L50 90 L58 81 L55 78.5 L45 78.5Z', GOLD),
    marks: NOSE.soft,
    beard: both((f) => p(`M${f(27)} 58 Q${f(30)} 78 ${f(44)} 83 L${f(44)} 77 Q${f(34)} 72 ${f(31.5)} 58Z`, '#1A1A1A', 0.8))
      + mustache('#1A1A1A') + p('M44 77 Q50 80 56 77 L52.5 95 Q50 98 47.5 95Z', '#1A1A1A', 0.8),
    over: p('M23 37 Q23 11 50 11 Q77 11 77 37Z', '#3C3C44') + p('M45.5 12 L54.5 12 L55.5 34 L44.5 34Z', GOLD, 0.8)
      + p('M19 34 L81 34 L83.5 40.5 L16.5 40.5Z', GOLD),
    top: l('M50 11 L50 4', K, 2.2) + c(50, 2.5, 3.4, '#C0392B') },

  { name: '세종대왕', skin: '#EEC8A0', face: 'round', brow: '#1A1A1A',
    clothes: shoulders('#B5232A') + c(50, 98, 6.5, '#E2B43C', 0.9),
    front: p('M42 81 L50 91 L58 81 L56 78 L50 86 L44 78Z', WHITE),
    marks: NOSE.soft + SMILE_LINES,
    beard: mustache('#1A1A1A') + p('M46 78 Q50 80 54 78 L51.6 91 Q50 93 48.4 91Z', '#1A1A1A', 0.8),
    over: both((f) => p(`M${f(35)} 10 Q${f(32)} 1.5 ${f(38)} 1 Q${f(43)} 2.5 ${f(42)} 10Z`, '#1B1B20'))
      + p('M31 25 Q31 6 50 6 Q69 6 69 25Z', '#1B1B20')
      + p('M23 39 Q22 17 50 17 Q78 17 77 39 Q64 33.5 50 33.5 Q36 33.5 23 39Z', '#25252C')
      + l('M30 27 Q50 21 70 27', '#4A4A55', 1) },

  { name: '소크라테스', skin: '#E1B48C', face: 'round', brow: '#DADADA', browH: 3.6,
    clothes: shoulders('#E9E3D2') + l('M22 98 Q40 88 56 84', '#B9B09A', 1.2) + l('M34 100 Q50 92 64 86', '#B9B09A', 1.2),
    back: both((f) => c(f(23.5), 45, 6, '#ECECEC') + c(f(22.5), 55, 5.5, '#ECECEC')),
    marks: NOSE.snub + FOREHEAD + l('M36 27 Q50 24 64 27', SH, 0.9, 0.7),
    beard: [[27, 64], [31, 74], [39, 81], [50, 84.5], [61, 81], [69, 74], [73, 64]].map(([x, y]) => c(x, y, 7.2, '#ECECEC')).join('')
      + soft('M30 62 Q50 78 70 62 Q66 84 50 86 Q34 84 30 62Z', '#ECECEC', 1)
      + p('M37 62 Q44 56.5 50 60 Q56 56.5 63 62 Q56 66 50 64 Q44 66 37 62Z', '#F6F6F6', 0.8) },

  { name: '니콜로 마키아벨리', skin: '#E9C2A0', face: 'long', brow: '#2B2220',
    clothes: shoulders('#8C1C1C'), front: p('M40 80 L50 86 L60 80 L62.5 86.5 L50 94 L37.5 86.5Z', '#1A1A1A'),
    marks: NOSE.long + l('M35 60 Q36 68 40 73', SH, 1, 0.8) + l('M65 60 Q64 68 60 73', SH, 1, 0.8),
    hair: p('M28 45 Q25 20 50 19 Q75 20 72 45 Q70 31 62 27 Q50 21.5 38 27 Q30 31 28 45Z', '#2B2220') },

  { name: '장 자크 루소', skin: '#F0CDB2', face: 'oval', brow: '#8A7A6A',
    clothes: shoulders('#5C4033'), front: p('M43 79 L57 79 L55.5 93 L50 96.5 L44.5 93Z', WHITE) + l('M47 84 L53 84', '#C9C4B8', 0.9) + l('M47.5 88 L52.5 88', '#C9C4B8', 0.9),
    back: both((f) => c(f(23.5), 49, 5.8, '#D8D8D8') + c(f(22.5), 59, 5.4, '#D8D8D8')),
    marks: NOSE.soft,
    over: p('M20 39 Q15 8 50 8 Q85 8 80 39 Q66 31.5 50 31.5 Q34 31.5 20 39Z', '#6B4A2E')
      + l('M25 26 Q50 12 75 26', '#9A744C', 1.6, 0.9).replace('stroke-linecap', 'stroke-dasharray="2.2 3.6" stroke-linecap')
      + l('M23 33 Q50 22 77 33', '#9A744C', 1.6, 0.9).replace('stroke-linecap', 'stroke-dasharray="2.2 3.6" stroke-linecap') },

  { name: '마하트마 간디', skin: '#B57A50', face: 'long', brow: '#8A8A8A', earR: 6.6,
    clothes: p('M12 102 Q16 84 38 80 Q50 89 62 80 Q84 84 88 102Z', '#F1EDE2') + l('M24 96 Q38 88 46 86', '#C9C3B2', 1.1) + l('M76 96 Q62 88 54 86', '#C9C3B2', 1.1),
    marks: NOSE.big + FOREHEAD + SMILE_LINES,
    beard: p('M40 61.5 Q45 58 50 60.3 Q55 58 60 61.5 Q55 64 50 63 Q45 64 40 61.5Z', '#EDEDED', 0.7),
    over: glassesRound('#3F3526', 1.3) },

  { name: '정주영', skin: '#E5B68D', face: 'round', brow: '#3F3F42', ...suit('#4B5563', '#1F3A6B'),
    marks: NOSE.big + FOREHEAD + SMILE_LINES,
    hair: p('M24 45 Q21 19 50 19 Q79 19 76 45 Q72 33 64 29 Q50 21 36 29 Q28 33 24 45Z', '#3F3F42'),
    over: glassesSquare('#2E2E30', 2) },

  { name: '이건희', skin: '#EEC6A2', face: 'oval', brow: '#8F8F8F', ...suit('#23242B', '#2F5D9B'),
    marks: NOSE.soft + UNDER_EYES + SMILE_LINES,
    hair: p('M26 45 Q23 18 50 18 Q77 18 74 45 Q72 30 60 27 L42 30 Q31 33 26 45Z', '#BDBDBD'),
    over: glassesThin('#4A4A4A') },

  { name: '블라디미르 푸틴', skin: '#F0CDB0', face: 'oval', brow: '#B9A88A', ...suit('#1E2638', '#6E1F2B'),
    marks: NOSE.soft + UNDER_EYES + FOREHEAD + l('M37 62 Q35 68 38 73', SH, 1, 0.8) + l('M63 62 Q65 68 62 73', SH, 1, 0.8),
    hair: p('M29 39 Q28 21 50 21 Q72 21 71 39 Q65 29.5 50 29 Q35 29.5 29 39Z', '#CDBDA0') },

  { name: '시진핑', skin: '#EBC39B', face: 'jowly', brow: '#141416', ...suit('#20222A', '#C4262E'),
    marks: NOSE.soft + SMILE_LINES,
    hair: p('M22 47 Q17 16 50 16 Q83 16 78 47 Q76 31 62 29 Q46 27 34 31 Q25 35 22 47Z', '#141416') },

  { name: '나폴레옹', skin: '#F0D0B4', face: 'round', brow: '#3A2A20',
    clothes: shoulders('#1F2F5C') + both((f) => p(`M${f(11)} 89 L${f(30)} 85 L${f(31)} 91.5 L${f(12)} 96Z`, GOLD)),
    front: p('M42 81 L50 93 L58 81 L55 78.5 L45 78.5Z', WHITE) + p('M40 78 L50 84 L60 78 L62.5 85 L57 88 L50 84.5 L43 88 L37.5 85Z', '#B5302A'),
    marks: NOSE.long,
    hair: p('M37 22 Q46 39 61 27 Q50 24 37 22Z', '#3A2A20') + both((f) => p(`M${f(25)} 47 Q${f(24)} 36 ${f(28)} 32 L${f(30)} 46Z`, '#3A2A20', 0.8)),
    top: p('M3 35 Q25 3 50 3 Q75 3 97 35 Q74 25.5 50 25.5 Q26 25.5 3 35Z', '#1B1B20') + l('M9 31 Q28 8 50 8 Q72 8 91 31', GOLD, 1.3)
      + c(50, 15.5, 4.8, '#B5302A', 0.7) + c(50, 15.5, 2.9, WHITE, 0) + c(50, 15.5, 1.4, '#1F3F8F', 0) },

  { name: '프리드리히 니체', skin: '#EFCDB2', face: 'square', brow: '#3B2A1E', browH: 4.6,
    clothes: shoulders('#2B2B30'), front: shirt + p('M47 84 L53 84 L54 90 L50 92 L46 90Z', '#17171A', 0.9) + lapels,
    marks: NOSE.long + FOREHEAD,
    hair: p('M24 45 Q17 12 52 13 Q85 14 76 45 Q72 28 54 26 Q36 25 24 45Z', '#3B2A1E'),
    over: p('M26 62 Q38 52.5 50 59 Q62 52.5 74 62 Q73 77 50 68.5 Q27 77 26 62Z', '#3B2A1E') },

  { name: '이마누엘 칸트', skin: '#F2D6BE', face: 'long', brow: '#B5B5B5',
    clothes: shoulders('#6A4B35'), front: p('M44 79 L56 79 L57.5 88 L50 96 L42.5 88Z', WHITE) + l('M46 84 Q50 86 54 84', '#C9C4B8', 0.9) + l('M46.5 89 Q50 91 53.5 89', '#C9C4B8', 0.9),
    back: both((f) => c(f(24), 47, 5.8, '#DCDCDC') + c(f(23.5), 57, 5.2, '#DCDCDC')) + p('M46 86 L54 86 L54 91 L46 91Z', '#17171A', 0.8),
    marks: NOSE.long + FOREHEAD,
    hair: p('M27 42 Q25 15 50 15 Q75 15 73 42 Q66 27 50 26 Q34 27 27 42Z', '#DCDCDC') + l('M34 24 Q50 17 66 24', '#B8B8B8', 0.9) },

  { name: '노자', skin: '#E8C29A', face: 'round', brow: '#D5D5D5',
    clothes: shoulders('#6E7F5A'), front: p('M42 81 L50 91 L58 81 L56 78 L50 86 L44 78Z', '#EFE7CF'),
    back: c(50, 13, 8.2, '#F0F0F0') + p('M44.5 19.5 L55.5 19.5 L55.5 23.5 L44.5 23.5Z', '#6E7F5A', 0.8),
    marks: NOSE.soft + FOREHEAD + SMILE_LINES,
    hair: both((f) => p(`M${f(25)} 47 Q${f(22.5)} 31 ${f(31)} 24 L${f(32)} 40Z`, '#F0F0F0')),
    beard: p('M36 72 Q50 80 64 72 L56 100 Q50 106 44 100Z', '#F0F0F0'),
    over: p('M40 62 Q46 58.5 50 60.5 Q54 58.5 60 62 L64.5 77 L60.5 77 L56 64.5 Q50 66 44 64.5 L39.5 77 L35.5 77Z', '#F6F6F6', 0.8)
      + l('M33 41 Q25 45 22.5 58', '#F0F0F0', 2.4) + l('M67 41 Q75 45 77.5 58', '#F0F0F0', 2.4) },

  { name: '아이작 뉴턴', skin: '#F3D8C2', face: 'long', brow: '#8C7B66',
    clothes: shoulders('#3B2F2F'),
    back: p('M50 12 Q18 9 14 44 Q10 72 18 102 L38 102 Q28 72 29 46 Q32 26 50 26 Q68 26 71 46 Q72 72 62 102 L82 102 Q90 72 86 44 Q82 9 50 12Z', '#B9A58B')
      + l('M19 52 q5 4 0 8 q-5 4 0 8 q5 4 0 8 q-5 4 0 8', '#8C7B66', 1.1) + l('M81 52 q-5 4 0 8 q5 4 0 8 q-5 4 0 8 q5 4 0 8', '#8C7B66', 1.1),
    front: p('M43 79 L57 79 L55.5 93 L50 96.5 L44.5 93Z', WHITE),
    marks: NOSE.long,
    hair: p('M28 43 Q28 17 50 16 Q72 17 72 43 Q64 29.5 50 28.5 Q36 29.5 28 43Z', '#B9A58B') + l('M50 16 L50 28', '#8C7B66', 1) },

  // 짧게 깎은 희끗한 머리, 가는 사각 안경, 갸름한 얼굴, 짙은 재킷과 어두운 니트
  { name: '데미스 하사비스', skin: '#E6BC96', face: 'long', brow: '#3A3230',
    clothes: shoulders('#23283A'), front: p('M41 81 Q50 90 59 81 L57 78.5 L43 78.5Z', '#3B4256') + lapels,
    marks: NOSE.long + FOREHEAD + l('M38 62 Q36 68 39 73', SH, 1, 0.8) + l('M62 62 Q64 68 61 73', SH, 1, 0.8),
    hair: p('M28 43 Q26 18 50 18 Q74 18 72 43 Q69 29 60 26.5 Q50 23.5 40 26.5 Q31 29 28 43Z', '#4A4442')
      + both((f) => soft(`M${f(28.5)} 44 Q${f(27.5)} 34 ${f(31)} 29 L${f(32.5)} 40Z`, '#A9A6A2', 0.9)),
    over: `<g fill="none" stroke="#2E2E33" stroke-width="1.5"><rect x="30" y="45" width="18" height="12" rx="3"/><rect x="52" y="45" width="18" height="12" rx="3"/><path d="M48 49.5 L52 49.5"/><path d="M30 49.5 L25 48"/><path d="M70 49.5 L75 48"/></g>` },

  // 풍성한 갈색 곱슬머리, 둥근 뿔테 안경, 짧은 수염 자국, 재킷과 깃 없는 셔츠
  { name: '다리오 아모데이', skin: '#EDC5A2', face: 'oval', brow: '#4A3324',
    clothes: shoulders('#3A4252'), front: p('M41 81 Q50 90 59 81 L57 78.5 L43 78.5Z', '#D9DDE4') + lapels,
    marks: NOSE.soft + SMILE_LINES,
    hair: [[27, 38], [29, 28], [36, 21], [45, 17], [55, 17], [64, 21], [71, 28], [73, 38], [40, 26], [50, 23], [60, 26], [33, 33], [67, 33]]
      .map(([x, y]) => c(x, y, 6.6, '#4A3324', 0.9)).join('')
      + soft('M30 38 Q32 24 50 23 Q68 24 70 38 Q60 31 50 31 Q40 31 30 38Z', '#4A3324', 1),
    beard: soft('M29 58 Q30 78 50 85.5 Q70 78 71 58 Q66 73 50 75 Q34 73 29 58Z', '#4A3324', 0.28),
    over: glassesRound('#2B211B', 1.7) },

  // 민머리, 짙은 눈썹, 각진 턱, 짙은 재킷에 단추를 푼 셔츠
  { name: '제프 베이조스', skin: '#EFC6A4', face: 'square', brow: '#3A2C24', browH: 3.6,
    clothes: shoulders('#1E2230'), front: p('M42 81 L47 92 L50 88 L53 92 L58 81 L55 78.5 L45 78.5Z', '#DCE6F2') + lapels,
    marks: NOSE.big + SMILE_LINES + soft('M36 24 Q44 20 52 22 Q44 23.5 36 27Z', '#FFFFFF', 0.35)
      + l('M38 32 Q50 29.5 62 32', SH, 0.9, 0.7) },

  // 짧고 촘촘한 곱슬머리, 흰 피부, 넓은 이마, 헐렁한 회색 티셔츠와 가는 목걸이
  { name: '마크 저커버그', skin: '#F4D3B8', face: 'oval', brow: '#7A5A3C',
    clothes: shoulders('#6B7280'), front: p('M40 82 Q50 91 60 82 L58 79 L42 79Z', '#7C8491') + l('M44 83 Q50 89 56 83', '#E3C55A', 1),
    marks: NOSE.soft,
    hair: [[28, 34], [31, 26], [37, 21], [44, 18.5], [50, 18], [56, 18.5], [63, 21], [69, 26], [72, 34]]
      .map(([x, y]) => c(x, y, 5.2, '#8A6644', 0.9)).join('')
      + soft('M29 37 Q31 23 50 22 Q69 23 71 37 Q62 29.5 50 29.5 Q38 29.5 29 37Z', '#8A6644', 1) },

  // 넘긴 은발, 가는 금속테 안경, 검은 가죽 재킷
  { name: '젠슨 황', skin: '#E8BD96', face: 'oval', brow: '#6E6E6E',
    clothes: shoulders('#121214') + l('M20 97 Q30 89 40 85', '#3A3A40', 1.2) + l('M80 97 Q70 89 60 85', '#3A3A40', 1.2),
    front: p('M41 81 Q50 89 59 81 L57 78.5 L43 78.5Z', '#1D1D21')
      + p('M42 81 L36 86 L45 99 L49 90Z', '#1A1A1D') + p('M58 81 L64 86 L55 99 L51 90Z', '#1A1A1D'),
    marks: NOSE.soft + SMILE_LINES + UNDER_EYES,
    hair: p('M25 45 Q20 15 52 15 Q82 16 75 45 Q73 30 60 27 Q44 24 33 30 Q27 34 25 45Z', '#C9C9CC')
      + l('M30 29 Q50 18 72 27', '#9A9AA0', 1) + l('M34 25 Q52 16 68 22', '#9A9AA0', 0.9),
    over: glassesThin('#5A5A60') },

  // 숱이 적은 흰 머리, 크고 두꺼운 검은 뿔테 안경, 깊은 주름, 짙은 회색 정장
  { name: '찰리 멍거', skin: '#F0CDB8', face: 'long', brow: '#CFCFCF', ...suit('#2E3138', '#3D4F7A'),
    marks: NOSE.big + FOREHEAD + SMILE_LINES + UNDER_EYES,
    hair: soft('M31 30 Q50 15 69 30 Q50 23.5 31 30Z', '#EDEDED', 0.75)
      + both((f) => p(`M${f(28)} 47 Q${f(25.5)} 32 ${f(33)} 25 L${f(33.5)} 39Z`, '#EDEDED', 0.9)),
    over: glassesSquare('#1E1E20', 2.6) },

  // 물결치는 흰 머리, 눈 밑의 처진 살, 둥근 얼굴, 가는 테 안경, 남색 정장
  { name: '조지 소로스', skin: '#EDC4A6', face: 'jowly', brow: '#BEBEC2', ...suit('#232B3F', '#7A2E3A'),
    marks: NOSE.big + FOREHEAD + SMILE_LINES + UNDER_EYES + l('M34 59.5 Q39.5 62.5 45 59.5', SH, 0.9, 0.6) + l('M55 59.5 Q60.5 62.5 66 59.5', SH, 0.9, 0.6),
    hair: p('M23 46 Q19 26 28 24 Q30 15 41 19 Q47 12 56 18 Q66 13 71 23 Q81 25 77 46 Q74 33 63 30 Q50 26 37 30 Q27 34 23 46Z', '#E4E4E8')
      + l('M32 26 Q40 21 47 24', '#B4B4BA', 0.9) + l('M53 23 Q61 20 68 26', '#B4B4BA', 0.9),
    over: glassesThin('#6A6A70') },

  // 옆으로 넘긴 회색 머리, 갸름한 얼굴, 넥타이 없이 푸른 셔츠와 짙은 재킷
  { name: '레이 달리오', skin: '#EBC3A2', face: 'long', brow: '#7C7C80',
    clothes: shoulders('#262B36'), front: p('M42 81 L47 92 L50 88 L53 92 L58 81 L55 78.5 L45 78.5Z', '#A9C4E4') + lapels,
    marks: NOSE.long + FOREHEAD + SMILE_LINES,
    hair: p('M27 45 Q23 17 50 16.5 Q77 17 73 45 Q71 31 62 27 Q48 22 36 29 Q29 34 27 45Z', '#A6A6AA')
      + l('M36 28 Q50 19 68 27', '#7C7C80', 1) + l('M34 32 Q39 26 46 24', '#7C7C80', 0.9) },

  // 어깨까지 오는 금발, 짙은 뿔테 안경, 짙은 재킷에 가는 십자가 목걸이
  { name: '캐시 우드', skin: '#F3D2BA', face: 'oval', brow: '#A8854F', browH: 2.4,
    clothes: shoulders('#2B2540'), back: p('M21 46 Q17 72 25 90 L75 90 Q83 72 79 46Z', '#D9B45E'),
    front: p('M41 81 Q50 91 59 81 L57 78.5 L43 78.5Z', '#F1E9DC') + lapels
      + l('M44.5 81.5 Q50 88 55.5 81.5', GOLD, 0.8) + l('M50 87 L50 91.5', GOLD, 1) + l('M48.4 88.6 L51.6 88.6', GOLD, 1),
    marks: NOSE.soft + SMILE_LINES,
    hair: p('M22 60 Q17 17 50 16 Q83 17 78 60 Q75 38 66 29 Q52 22 38 28 Q26 36 22 60Z', '#E3C06A')
      + l('M40 27 Q50 20 63 27', '#B8923F', 1) + l('M27 40 Q31 31 38 28', '#B8923F', 0.9),
    over: glassesSquare('#3A2A22', 1.8) },

  // 짧게 깎은 갈색 머리, 수염 자국, 각진 턱, 정장 없이 짙은 티셔츠
  { name: '마이클 버리', skin: '#EEC6A6', face: 'square', brow: '#5A4030',
    clothes: shoulders('#2F3B36'), front: p('M40 82 Q50 91 60 82 L58 79 L42 79Z', '#3B4A44'),
    marks: NOSE.soft + UNDER_EYES + l('M38 33 Q50 30.5 62 33', SH, 0.9, 0.7),
    hair: p('M27 43 Q25 18 50 17.5 Q75 18 73 43 Q70 30 60 27.5 Q50 25 40 27.5 Q30 30 27 43Z', '#5A4030'),
    beard: soft('M28 58 Q29 78 50 84.5 Q71 78 72 58 Q67 73 50 75 Q33 73 28 58Z', '#5A4030', 0.22) },

  // 옆으로 세 겹 말린 흰 가발, 큰 코, 짙은 녹색 코트와 흰 목수건
  { name: '애덤 스미스', skin: '#F1D2B8', face: 'oval', brow: '#9A8F84',
    clothes: shoulders('#3F4A3A'), front: p('M43 79 L57 79 L55.5 93 L50 96.5 L44.5 93Z', WHITE) + l('M47 84 L53 84', '#C9C4B8', 0.9) + l('M47.5 88 L52.5 88', '#C9C4B8', 0.9),
    back: both((f) => c(f(23.5), 45, 6, '#E6E2DA') + c(f(22.5), 55, 5.8, '#E6E2DA') + c(f(23.5), 65, 5.4, '#E6E2DA')),
    marks: NOSE.big + FOREHEAD,
    hair: p('M27 42 Q25 15 50 15 Q75 15 73 42 Q66 27 50 26 Q34 27 27 42Z', '#E6E2DA') + l('M33 25 Q50 17 67 25', '#BDB8AE', 0.9) },

  // 벗겨진 이마, 짙은 옆머리, 풍성한 콧수염, 정장과 넥타이
  { name: '존 메이너드 케인스', skin: '#EFCBAE', face: 'long', brow: '#4A3A30', ...suit('#2C2F3A', '#5A2D3A'),
    marks: NOSE.long + FOREHEAD + UNDER_EYES,
    hair: p('M34 24 Q50 15.5 66 24 Q50 20.5 34 24Z', '#4A3A30', 0.8)
      + both((f) => p(`M${f(28)} 47 Q${f(25.5)} 30 ${f(35)} 23 L${f(34)} 39Z`, '#4A3A30', 0.9)),
    over: p('M36 62.5 Q44 56 50 59.5 Q56 56 64 62.5 Q56 66.5 50 64.5 Q44 66.5 36 62.5Z', '#4A3A30', 0.8) },

  // 사자 갈기 같은 회백색 머리와 덥수룩한 수염, 짙은 콧수염, 검은 외투
  { name: '카를 마르크스', skin: '#E9C3A2', face: 'round', brow: '#4A4A4A', browH: 4,
    clothes: shoulders('#26262B'),
    back: both((f) => c(f(21), 46, 7, '#CFCFCF') + c(f(20.5), 58, 7, '#CFCFCF')),
    marks: NOSE.big + FOREHEAD,
    hair: p('M20 50 Q11 10 50 11 Q89 10 80 50 Q77 30 62 27 Q50 24 38 27 Q23 30 20 50Z', '#CFCFCF')
      + l('M27 30 Q38 18 50 20', '#A4A4A4', 1) + l('M73 30 Q62 18 50 20', '#A4A4A4', 1),
    beard: [[26, 64], [29, 75], [37, 83], [50, 87.5], [63, 83], [71, 75], [74, 64]].map(([x, y]) => c(x, y, 8, '#D6D6D6')).join('')
      + soft('M29 61 Q50 79 71 61 Q68 87 50 90 Q32 87 29 61Z', '#D6D6D6', 1)
      + p('M35 62.5 Q44 56 50 60 Q56 56 65 62.5 Q56 67 50 64.5 Q44 67 35 62.5Z', '#5A5A5A', 0.8) },

  // 젊은 얼굴, 짧고 검은 머리, 푸른 회색 작업복
  { name: '전태일', skin: '#E6B78F', face: 'oval', brow: '#17171A',
    clothes: shoulders('#5E6E7E'), front: p('M42 81 L50 90 L58 81 L63 84.5 L54 96 L50 91.5 L46 96 L37 84.5Z', '#52616F'),
    marks: NOSE.soft,
    hair: p('M26 45 Q22 16 50 16 Q78 16 74 45 Q72 31 62 28 Q46 24 34 31 Q28 35 26 45Z', '#17171A') },

  // 귀를 덮는 짧은 갈색 웨이브 머리, 녹색 재킷과 흰 블라우스
  { name: '레이첼 카슨', skin: '#F2D3BC', face: 'oval', brow: '#6B4A34', browH: 2.4,
    clothes: shoulders('#4F6B5A'), back: p('M21 46 Q17 62 26 71 L74 71 Q83 62 79 46Z', '#5A4030'),
    front: p('M41 81 Q50 91 59 81 L57 78.5 L43 78.5Z', '#F1E9DC') + lapels,
    marks: NOSE.soft,
    hair: p('M22 54 Q16 17 50 16 Q84 17 78 54 Q76 37 66 29 Q52 23 38 28 Q25 36 22 54Z', '#5A4030')
      + l('M27 42 Q30 32 38 28', '#3E2B1E', 0.9) + l('M40 26 Q52 20 64 27', '#3E2B1E', 0.9) + l('M73 42 Q71 33 65 29', '#3E2B1E', 0.9) },

  // 옆가르마를 탄 짙은 머리, 갸름한 젊은 얼굴, 트위드 재킷과 넥타이
  { name: '앨런 튜링', skin: '#F1CFB4', face: 'long', brow: '#2E221C', ...suit('#6B5B45', '#3B4A6B'),
    marks: NOSE.long,
    hair: p('M27 45 Q23 16 50 16 Q77 16 73 45 Q72 32 64 28 Q50 27 36 23 Q29 32 27 45Z', '#2E221C')
      + l('M36 23 Q50 19 68 26', '#54423A', 0.9) },

  // 위로 틀어 올린 잿빛 곱슬머리, 목까지 올라오는 검은 옷
  { name: '마리 퀴리', skin: '#F3D6C2', face: 'oval', brow: '#7A6650', browH: 2.4,
    clothes: shoulders('#1E1E22'), back: c(50, 13, 9.5, '#8A7358') + l('M44 10 Q50 6 56 10', '#6B573F', 0.9),
    front: p('M42 75 Q50 79 58 75 L58.5 83 Q50 87 41.5 83Z', '#1E1E22'),
    marks: NOSE.soft + UNDER_EYES,
    hair: p('M25 46 Q20 17 50 17 Q80 17 75 46 Q72 31 62 27 Q50 22 38 27 Q28 31 25 46Z', '#8A7358')
      + l('M30 30 Q38 22 48 22', '#6B573F', 0.9) + l('M70 30 Q62 22 52 22', '#6B573F', 0.9) },

  // 검은 갓과 갓끈, 흰 도포, 가는 수염
  { name: '정약용', skin: '#EBC49E', face: 'oval', brow: '#1A1A1A',
    clothes: shoulders('#F1EDE2'), front: p('M42 81 L50 91 L58 81 L56 78 L50 86 L44 78Z', '#D5CDB8'),
    marks: NOSE.soft + SMILE_LINES,
    beard: mustache('#1A1A1A') + p('M46 78 Q50 80 54 78 L51.6 92 Q50 94 48.4 92Z', '#1A1A1A', 0.8),
    over: l('M27 36 Q25 62 45 85', '#1B1B20', 0.9) + l('M73 36 Q75 62 55 85', '#1B1B20', 0.9),
    top: p('M3 31 Q50 21 97 31 Q50 40 3 31Z', '#1B1B20') + p('M35 30 L37 7 Q50 4 63 7 L65 30 Q50 33 35 30Z', '#25252C')
      + l('M36 26 Q50 29 64 26', '#4A4A55', 1) },

  // 뒤로 넘긴 흰 머리, 흰 콧수염, 둥근 안경, 회색 정장
  { name: '프리드리히 하이에크', skin: '#F0D0B8', face: 'long', brow: '#C4C4C4', ...suit('#3A3F4A', '#6B2D2D'),
    marks: NOSE.long + FOREHEAD + SMILE_LINES,
    hair: p('M28 42 Q26 17 50 17 Q74 17 72 42 Q68 27 50 25 Q32 27 28 42Z', '#E4E4E4') + l('M35 24 Q50 18 65 24', '#B8B8B8', 0.9),
    beard: mustache('#E0E0E0'),
    over: glassesRound('#3A3A3A', 1.3) },

  // 사방으로 뻗친 흰 머리, 큰 흰 콧수염, 편한 스웨터
  { name: '알베르트 아인슈타인', skin: '#EDC8A8', face: 'round', brow: '#BEBEBE', browH: 3.6,
    clothes: shoulders('#6B6257'), front: p('M41 81 Q50 91 59 81 L57 78.5 L43 78.5Z', '#D8D2C4'),
    back: both((f) => c(f(20), 40, 7.5, '#EDEDED') + c(f(19), 52, 7, '#EDEDED') + c(f(22), 62, 5.5, '#EDEDED')),
    marks: NOSE.big + FOREHEAD + UNDER_EYES,
    hair: [[24, 32], [29, 22], [38, 15], [50, 12.5], [62, 15], [71, 22], [76, 32]].map(([x, y]) => c(x, y, 8, '#EDEDED', 0.9)).join('')
      + soft('M27 38 Q29 20 50 19 Q71 20 73 38 Q62 29 50 29 Q38 29 27 38Z', '#EDEDED', 1),
    over: p('M34 62.5 Q43 55.5 50 59.5 Q57 55.5 66 62.5 Q57 67.5 50 65 Q43 67.5 34 62.5Z', '#E6E6E6', 0.8) },

  // 챙이 넓고 윗면이 납작한 모자, 마른 긴 얼굴, 짙은 정장
  { name: '로버트 오펜하이머', skin: '#EFCDB0', face: 'long', brow: '#3A322C', ...suit('#3B3B42', '#2A3550'),
    marks: NOSE.long + l('M35 60 Q36 68 40 73', SH, 1, 0.8) + l('M65 60 Q64 68 60 73', SH, 1, 0.8),
    hair: both((f) => p(`M${f(26.5)} 48 Q${f(25.5)} 38 ${f(28)} 35 L${f(30.5)} 37 L${f(29.5)} 48Z`, '#3A322C', 0.8)),
    over: p('M27 33 L28 13 Q50 10 72 13 L73 33Z', '#6A5F52') + p('M27.3 27 L72.7 27 L73 33 L27 33Z', '#3A322B', 0.8),
    top: p('M7 33 Q50 26 93 33 Q50 41 7 33Z', '#6A5F52') },

  // 상투와 비녀, 짙은 눈썹, 길게 늘어뜨린 수염, 갈색 옷
  { name: '공자', skin: '#E6BE96', face: 'round', brow: '#2A2422', browH: 3.8,
    clothes: shoulders('#7A4B2E'), front: p('M42 81 L50 91 L58 81 L56 78 L50 86 L44 78Z', '#E8DCC0'),
    back: c(50, 12.5, 7.8, '#2A2422') + l('M37 12.5 L63 12.5', '#8A6A3A', 1.8),
    marks: NOSE.big + FOREHEAD + SMILE_LINES,
    hair: p('M27 43 Q26 19 50 19 Q74 19 73 43 Q66 28 50 27 Q34 28 27 43Z', '#2A2422'),
    beard: p('M36 72 Q50 80 64 72 L57 99 Q50 105 43 99Z', '#3A3432'),
    over: p('M40 62 Q46 58.5 50 60.5 Q54 58.5 60 62 L64.5 77 L60.5 77 L56 64.5 Q50 66 44 64.5 L39.5 77 L35.5 77Z', '#3A3432', 0.8) },

  // 높은 검은 모자, 콧수염 없는 턱수염, 마른 긴 얼굴, 검은 정장과 나비넥타이
  { name: '에이브러햄 링컨', skin: '#E3BC9A', face: 'long', brow: '#2A2220', browH: 3.6,
    clothes: shoulders('#1A1A1E'), front: shirt + p('M44 84 L50 87 L56 84 L56 90 L50 87 L44 90Z', '#1A1A1E', 0.9) + lapels,
    marks: NOSE.long + l('M35 59 Q35.5 67 39.5 72', SH, 1, 0.85) + l('M65 59 Q64.5 67 60.5 72', SH, 1, 0.85),
    hair: both((f) => p(`M${f(26.5)} 50 Q${f(25)} 38 ${f(28)} 35 L${f(31)} 37 L${f(30)} 50Z`, '#2A2220', 0.8)),
    beard: p('M27.5 56 Q28 80 50 88.5 Q72 80 72.5 56 Q69 73.5 50 76.5 Q31 73.5 27.5 56Z', '#2A2220'),
    top: p('M31 31 L32 2 L68 2 L69 31Z', '#1A1A1E') + l('M32 25.5 L68 25.5', '#3A3A42', 2.4)
      + p('M16 30 L84 30 Q86.5 35.5 82 35.5 L18 35.5 Q13.5 35.5 16 30Z', '#1A1A1E') },

  // 둥글고 살진 얼굴, 숱 없는 머리, 물방울무늬 나비넥타이, 입에 문 시가
  { name: '윈스턴 처칠', skin: '#F3CFB8', face: 'jowly', brow: '#C9C2B8', clothes: shoulders('#22242C'),
    front: shirt + p('M43 83.5 L50 87 L57 83.5 L57 91 L50 87.5 L43 91Z', '#1F2F5C', 0.9)
      + [[45.5, 86], [45.5, 89], [54.5, 86], [54.5, 89]].map(([x, y]) => c(x, y, 0.7, WHITE, 0)).join('') + lapels,
    marks: NOSE.big + FOREHEAD + SMILE_LINES + UNDER_EYES,
    hair: soft('M33 28 Q50 17 67 28 Q50 23 33 28Z', '#E8E4DC', 0.6)
      + both((f) => p(`M${f(26.5)} 48 Q${f(24.5)} 35 ${f(31)} 28 L${f(32)} 40Z`, '#E8E4DC', 0.9)),
    over: p('M56 69.5 L73 74 L72.2 77.4 L55.2 72.9Z', '#7A4A2A', 0.8) + c(73.2, 75.8, 1.9, '#E0764A', 0.6) },

  // 햇볕에 그을린 둥근 민머리, 옆에 남은 흰 머리, 파란 줄무늬 셔츠
  { name: '파블로 피카소', skin: '#D9A57A', face: 'round', brow: '#3A3230', browH: 3.8,
    clothes: shoulders(WHITE) + l('M22 90 Q50 84.5 78 90', '#1F3A6B', 2) + l('M17 95 Q50 89.5 83 95', '#1F3A6B', 2) + l('M15 100 Q50 94.5 85 100', '#1F3A6B', 2),
    marks: NOSE.big + FOREHEAD + SMILE_LINES + soft('M36 24 Q44 20 52 22 Q44 23.5 36 27Z', '#FFFFFF', 0.3),
    hair: both((f) => p(`M${f(26.5)} 50 Q${f(23.5)} 36 ${f(30)} 30 L${f(31.5)} 42Z`, '#E6E6E6', 0.9)) },

  // 옆으로 빗어 넘긴 회색 머리, 마른 얼굴, 높은 흰 깃과 짙은 넥타이
  { name: '헨리 포드', skin: '#EFCDB4', face: 'long', brow: '#8E8E92', ...suit('#4A4E57', '#2B2B30'),
    marks: NOSE.long + FOREHEAD + SMILE_LINES + UNDER_EYES,
    hair: p('M28 44 Q25 17 50 17 Q75 17 72 44 Q70 30 60 26 Q44 23 34 29 Q29 34 28 44Z', '#B8B8BC')
      + l('M35 28 Q48 20 66 25', '#8E8E92', 0.9),
    over: p('M42 76 L47.5 80.5 L46 84 L41.5 81Z', WHITE, 0.8) + p('M58 76 L52.5 80.5 L54 84 L58.5 81Z', WHITE, 0.8) },

  // 위로 부풀린 검은 곱슬머리, 색이 들어간 큰 안경, 지퍼를 올린 카키색 점퍼
  { name: '김정일', skin: '#E9C09A', face: 'round', brow: '#1A1A1C',
    clothes: shoulders('#8A8466'),
    front: p('M42 81 L50 90 L58 81 L63 84.5 L54 96 L50 91.5 L46 96 L37 84.5Z', '#7A7558') + l('M50 91.5 L50 102', '#55513B', 1.3),
    marks: NOSE.soft + SMILE_LINES,
    hair: p('M22 46 Q14 7 50 7 Q86 7 78 46 Q75 30 61 27 Q46 25 36 29 Q26 33 22 46Z', '#1A1A1C')
      + l('M29 24 Q40 12 54 13', '#3C3C40', 1) + l('M46 12 Q60 10 71 22', '#3C3C40', 1),
    over: `<g fill="#6B5A3A" fill-opacity=".32" stroke="#33312E" stroke-width="1.6"><rect x="28.5" y="43" width="20" height="16" rx="5"/><rect x="51.5" y="43" width="20" height="16" rx="5"/></g>`
      + l('M48.5 48.5 L51.5 48.5', '#33312E', 1.6) + l('M28.5 49 L25 47.5', '#33312E', 1.4) + l('M71.5 49 L75 47.5', '#33312E', 1.4) },

  // 앞머리를 내린 짧은 검은 머리, 갸름한 얼굴, 넥타이 없는 정장, 옷깃 아래 흑백 바둑돌
  { name: '이세돌', skin: '#EBC39E', face: 'long', brow: '#17171A',
    clothes: shoulders('#262A36'), front: p('M42 81 L47 92 L50 88 L53 92 L58 81 L55 78.5 L45 78.5Z', WHITE) + lapels
      + c(33, 94, 3.2, '#111114', 0.8) + c(67, 94, 3.2, WHITE, 0.8),
    marks: NOSE.soft,
    hair: p('M27 46 Q22 16 50 16 Q78 16 73 46 Q72 34 66 31 Q58 34 50 31 Q42 35 34 31 Q29 35 27 46Z', '#17171A') },

  // 둥글고 넉넉한 얼굴, 짧은 검은 머리, 웃음 주름, 단추가 두 줄인 흰 조리복
  { name: '백종원', skin: '#E8BD96', face: 'round', brow: '#1E1E20',
    clothes: shoulders(WHITE) + l('M50 88 L50 102', '#C9C4B8', 1)
      + [[45, 92], [45, 98], [55, 92], [55, 98]].map(([x, y]) => c(x, y, 1.3, '#3A3A40', 0)).join(''),
    front: p('M41 81 Q50 86 59 81 L60 85 Q50 90 40 85Z', WHITE),
    marks: NOSE.big + SMILE_LINES,
    hair: p('M24 45 Q21 18 50 18 Q79 18 76 45 Q73 32 64 28 Q50 24 36 28 Q27 32 24 45Z', '#1E1E20') },

  // 크게 부풀린 갈색 웨이브 머리, 붉은 재킷과 흰 블라우스
  { name: '오은영', skin: '#F3D3BC', face: 'oval', brow: '#6B4530', browH: 2.4,
    clothes: shoulders('#B5304A'),
    back: p('M14 50 Q6 14 50 9 Q94 14 86 50 Q90 72 80 86 L20 86 Q10 72 14 50Z', '#7A4A30')
      + l('M17 58 q5 5 0 10 q-5 5 0 10', '#5A3420', 1.1) + l('M83 58 q-5 5 0 10 q5 5 0 10', '#5A3420', 1.1),
    front: p('M41 81 Q50 91 59 81 L57 78.5 L43 78.5Z', '#F6EFE6') + lapels,
    marks: NOSE.soft,
    hair: p('M21 56 Q12 12 50 11 Q88 12 79 56 Q77 38 68 30 Q56 22 44 26 Q28 32 21 56Z', '#7A4A30')
      + l('M30 34 Q40 21 56 22', '#5A3420', 1) + l('M60 23 Q70 27 74 38', '#5A3420', 1) },

  // 짧게 깎은 머리, 짧은 콧수염과 턱수염, 둥근 얼굴, 야외용 녹색 점퍼
  { name: '강형욱', skin: '#E6BA94', face: 'round', brow: '#1E1C1A',
    clothes: shoulders('#3F5A46'),
    front: p('M42 81 L50 90 L58 81 L63 84.5 L54 96 L50 91.5 L46 96 L37 84.5Z', '#35503D') + l('M50 91.5 L50 102', '#22382A', 1.3),
    marks: NOSE.soft + SMILE_LINES,
    hair: p('M26 43 Q24 19 50 18.5 Q76 19 74 43 Q71 31 61 28 Q50 25.5 39 28 Q29 31 26 43Z', '#1E1C1A'),
    beard: soft('M29 60 Q30 79 50 85 Q70 79 71 60 Q66 73 50 75.5 Q34 73 29 60Z', '#1E1C1A', 0.5)
      + mustache('#1E1C1A') },

  // 옆으로 넘긴 회색 머리, 가는 테 안경, 셔츠 깃이 보이는 푸른 스웨터
  { name: '빌 게이츠', skin: '#F2D0B8', face: 'oval', brow: '#9A948C',
    clothes: shoulders('#3B5A7A'),
    front: p('M41 81 Q50 91 59 81 L57 78.5 L43 78.5Z', '#3B5A7A')
      + p('M42 80 L49 86 L45.5 90 L40 83Z', WHITE, 0.8) + p('M58 80 L51 86 L54.5 90 L60 83Z', WHITE, 0.8),
    marks: NOSE.soft + FOREHEAD + SMILE_LINES,
    hair: p('M26 45 Q22 17 50 17 Q78 17 74 45 Q72 32 64 28 Q48 23 35 30 Q28 35 26 45Z', '#B4AEA6')
      + l('M35 29 Q49 20 67 26', '#8C867E', 0.9),
    over: glassesThin('#4A4A4E') },

  // 삭발한 머리, 갸름한 얼굴, 가는 금속테 안경, 짙은 재킷과 깃 없는 셔츠
  { name: '유발 하라리', skin: '#EBC4A2', face: 'long', brow: '#3A322C',
    clothes: shoulders('#22252E'), front: p('M41 81 Q50 89 59 81 L57 78.5 L43 78.5Z', '#4A5568') + lapels,
    marks: NOSE.long + l('M38 62 Q36 68 39 73', SH, 1, 0.8) + l('M62 62 Q64 68 61 73', SH, 1, 0.8)
      + soft('M36 24 Q44 20 52 22 Q44 23.5 36 27Z', '#FFFFFF', 0.35)
      + soft('M29 40 Q28 21 50 20 Q72 21 71 40 Q64 26.5 50 26 Q36 26.5 29 40Z', '#3A322C', 0.22),
    over: glassesThin('#6A6A70') },

  // 부스스한 흰 머리, 마른 긴 얼굴과 큰 코, 셔츠 위에 입은 회색 스웨터
  { name: '제프리 힌턴', skin: '#F1D2BC', face: 'long', brow: '#D0D0D0',
    clothes: shoulders('#5A606B'),
    front: p('M41 81 Q50 91 59 81 L57 78.5 L43 78.5Z', '#5A606B')
      + p('M42 80 L49 86 L45.5 90 L40 83Z', '#C9D6EA', 0.8) + p('M58 80 L51 86 L54.5 90 L60 83Z', '#C9D6EA', 0.8),
    marks: NOSE.big + FOREHEAD + SMILE_LINES + UNDER_EYES,
    hair: p('M26 46 Q20 20 30 22 Q33 13 44 18 Q52 12 60 18 Q70 14 71 24 Q80 22 74 46 Q72 33 62 29 Q50 25 38 29 Q28 33 26 46Z', '#EEEEEE')
      + l('M33 26 Q41 20 48 23', '#C2C2C2', 0.9) + l('M54 22 Q62 20 67 26', '#C2C2C2', 0.9) },

  // 양쪽으로 길게 땋아 내린 머리, 앳된 둥근 얼굴, 노란 비옷
  { name: '그레타 툰베리', skin: '#F4D6C0', face: 'round', brow: '#8A6A48', browH: 2.4,
    clothes: shoulders('#E8C22E') + l('M50 88 L50 102', '#B8961E', 1.2),
    back: both((f) => [60, 68, 76, 84, 92].map((y, k) => c(f(k % 2 ? 20.5 : 22), y, 4.6, '#A9825A', 0.9)).join('')),
    front: p('M41 81 Q50 87 59 81 L61 85.5 Q50 92 39 85.5Z', '#D9B325'),
    marks: NOSE.snub,
    hair: p('M23 54 Q19 18 50 18 Q81 18 77 54 Q75 36 62 29 L50 24 L38 29 Q25 36 23 54Z', '#A9825A')
      + l('M50 18 L50 24', '#7E5E3E', 1) },

  // 숱이 줄어든 회색 머리, 가는 테 안경, 셔츠 위의 알록달록한 멜빵
  { name: '레이 커즈와일', skin: '#EFCDB6', face: 'oval', brow: '#8A8A8E',
    clothes: shoulders('#DCE6F2')
      + both((f) => p(`M${f(36)} 83.5 L${f(41)} 82.5 L${f(38)} 102 L${f(32)} 102Z`, '#C0392B', 0.8)
        + c(f(37.2), 89, 1.2, '#F2C94C', 0) + c(f(36), 95, 1.2, '#2F80ED', 0)),
    front: p('M42 81 L47 92 L50 88 L53 92 L58 81 L55 78.5 L45 78.5Z', WHITE),
    marks: NOSE.soft + FOREHEAD + SMILE_LINES + UNDER_EYES,
    hair: p('M29 41 Q28 20 50 20 Q72 20 71 41 Q66 28.5 50 28 Q34 28.5 29 41Z', '#A8A8AC')
      + both((f) => p(`M${f(27)} 49 Q${f(25.5)} 38 ${f(29)} 34 L${f(31)} 46Z`, '#A8A8AC', 0.8)),
    over: glassesThin('#3E3E44') },

  // 숱 적은 흰 머리, 주름 깊은 갸름한 얼굴, 흰 두루마기
  { name: '이승만', skin: '#EBC9A8', face: 'long', brow: '#D6D6D6',
    clothes: shoulders('#F1EDE2'), front: p('M42 81 L50 91 L58 81 L56 78 L50 86 L44 78Z', WHITE) + l('M50 91 L47 102', '#C9C3B2', 1.1),
    marks: NOSE.long + FOREHEAD + SMILE_LINES + UNDER_EYES + l('M36 27 Q50 24 64 27', SH, 0.9, 0.7),
    hair: p('M29 40 Q28 19 50 19 Q72 19 71 40 Q65 27 50 26 Q35 27 29 40Z', '#EDEDED')
      + both((f) => p(`M${f(27)} 49 Q${f(25.5)} 38 ${f(29)} 34 L${f(31)} 46Z`, '#EDEDED', 0.8)) },

  // 벗겨진 머리, 굵은 눈썹, 각진 얼굴, 깃에 별을 단 군복
  { name: '전두환', skin: '#E3B68E', face: 'square', brow: '#1A1A1C', browH: 4.2,
    clothes: shoulders('#5B6240') + both((f) => p(`M${f(13)} 90 L${f(30)} 85.5 L${f(31)} 90.5 L${f(14)} 95.5Z`, '#4A5034', 0.8)),
    front: p('M42 81 L50 90 L58 81 L63 84.5 L54 96 L50 91.5 L46 96 L37 84.5Z', '#4E5537')
      + both((f) => c(f(42.5), 88.5, 1.5, GOLD, 0.4)),
    marks: NOSE.big + SMILE_LINES + soft('M36 24 Q44 20 52 22 Q44 23.5 36 27Z', '#FFFFFF', 0.35)
      + l('M38 32 Q50 29.5 62 32', SH, 0.9, 0.7),
    hair: both((f) => p(`M${f(26)} 50 Q${f(23.5)} 36 ${f(30)} 30 L${f(31.5)} 43Z`, '#1A1A1C', 0.9)) },

  // 가르마를 탄 검은 머리, 큰 귀, 웃는 인상, 정장과 푸른 넥타이
  { name: '노태우', skin: '#E8BE98', face: 'oval', brow: '#222224', earR: 6.6, ...suit('#2A2E3A', '#2F5D9B'),
    marks: NOSE.big + SMILE_LINES + UNDER_EYES,
    hair: p('M26 45 Q22 17 50 17 Q78 17 74 45 Q72 31 62 28 Q46 24 35 30 Q28 35 26 45Z', '#222224')
      + l('M36 29 Q50 21 66 27', '#48484C', 0.9) },

  // 풍성하게 넘긴 은발, 갸름한 얼굴, 정장과 붉은 넥타이
  { name: '김영삼', skin: '#EDC6A4', face: 'long', brow: '#B8B8BC', ...suit('#232733', '#B8322C'),
    marks: NOSE.long + FOREHEAD + SMILE_LINES,
    hair: p('M25 46 Q19 14 52 14 Q83 15 75 46 Q73 30 60 27 Q44 24 33 30 Q27 34 25 46Z', '#E2E2E6')
      + l('M30 29 Q50 17 72 27', '#AEAEB4', 1) + l('M34 25 Q52 15 68 22', '#AEAEB4', 0.9) },

  // 뒤로 빗어 넘긴 검은 머리, 살진 얼굴과 처진 눈 밑, 정장과 짙은 녹색 넥타이
  { name: '김대중', skin: '#E6BC98', face: 'jowly', brow: '#2A2A2C', ...suit('#23262E', '#2F6B4F'),
    marks: NOSE.big + FOREHEAD + SMILE_LINES + UNDER_EYES + l('M34 59.5 Q39.5 62.5 45 59.5', SH, 0.9, 0.6) + l('M55 59.5 Q60.5 62.5 66 59.5', SH, 0.9, 0.6),
    hair: p('M26 43 Q24 17 50 17 Q76 17 74 43 Q68 27 50 26 Q32 27 26 43Z', '#1E1E20')
      + l('M34 24 Q50 18 66 24', '#44444A', 0.9) + l('M42 21 L42 26', '#44444A', 0.8) + l('M58 21 L58 26', '#44444A', 0.8) },

  // 이마를 가로지르는 깊은 주름 한 줄, 검은 머리, 정장과 노란 넥타이
  { name: '노무현', skin: '#E7BB94', face: 'oval', brow: '#1E1E20', ...suit('#262A34', '#E8C22E'),
    marks: NOSE.big + l('M34 33.5 Q50 30.5 66 33.5', SH, 1.7, 0.95) + SMILE_LINES,
    hair: p('M26 44 Q23 17 50 17 Q77 17 74 44 Q72 30 62 27 Q48 23 36 29 Q29 33 26 44Z', '#1E1E20') },

  // 숱이 줄어든 짙은 머리, 갸름한 얼굴, 가는 테 안경, 정장과 푸른 넥타이
  { name: '이명박', skin: '#E9C09C', face: 'long', brow: '#3A3A3E', ...suit('#20242E', '#2F6DB5'),
    marks: NOSE.long + FOREHEAD + SMILE_LINES,
    hair: p('M29 41 Q28 19 50 19 Q72 19 71 41 Q66 28 54 26 Q40 25 33 31 Q30 35 29 41Z', '#3A3A3E')
      + both((f) => p(`M${f(27)} 49 Q${f(25.5)} 38 ${f(29)} 34 L${f(31)} 46Z`, '#3A3A3E', 0.8)),
    over: glassesThin('#3A3A3E') },

  // 뒤로 부풀려 올린 머리, 깃을 세운 푸른 재킷과 브로치
  { name: '박근혜', skin: '#F2D2BA', face: 'oval', brow: '#3A2C26', browH: 2.4,
    clothes: shoulders('#2F5D9B') + c(34, 92, 2.4, GOLD, 0.6),
    back: p('M19 48 Q10 8 50 6 Q90 8 81 48 Q84 60 77 66 L23 66 Q16 60 19 48Z', '#2A2220'),
    front: p('M41.5 76 Q50 80 58.5 76 L60 84 Q50 88.5 40 84Z', '#2F5D9B') + l('M50 80 L50 88', '#234A7E', 1),
    marks: NOSE.soft + SMILE_LINES,
    hair: p('M22 52 Q14 12 50 11 Q86 12 78 52 Q76 36 67 30 Q56 23 44 26 Q28 31 22 52Z', '#2A2220')
      + l('M30 32 Q42 19 58 21', '#4A3E3A', 1) + l('M62 22 Q71 27 74 37', '#4A3E3A', 1) },

  // 옆으로 넘긴 은회색 머리, 가는 테 안경, 온화한 얼굴, 남색 정장과 푸른 넥타이
  { name: '문재인', skin: '#EBC4A0', face: 'oval', brow: '#8E8E92', ...suit('#1F2A44', '#3B6FB5'),
    marks: NOSE.soft + FOREHEAD + SMILE_LINES,
    hair: p('M26 45 Q22 17 50 17 Q78 17 74 45 Q72 32 64 28 Q48 23 35 30 Q28 35 26 45Z', '#C4C4C8')
      + l('M35 29 Q49 20 67 26', '#96969C', 0.9),
    over: glassesThin('#4A4A50') },

  // 이마로 비스듬히 내려온 앞머리, 코 밑의 짧고 네모난 콧수염, 갈색 제복과 검은 넥타이
  { name: '아돌프 히틀러', skin: '#EFCDB4', face: 'oval', brow: '#2A211C', browH: 3.4,
    clothes: shoulders('#7A5F3C'), front: shirt + tie('#17171A') + lapels,
    marks: NOSE.long + UNDER_EYES + l('M38 62 Q36 68 39 73', SH, 1, 0.8) + l('M62 62 Q64 68 61 73', SH, 1, 0.8),
    hair: p('M26 45 Q23 17 50 17 Q77 17 74 45 Q72 31 64 27 L60 26 Q50 34 34 40 Q28 40 26 45Z', '#2A211C')
      + l('M60 26 Q48 22 36 26', '#4A3C34', 0.9),
    over: p('M45.5 59 L54.5 59 L55 64.5 L45 64.5Z', '#2A211C', 0.7) },

  // 벗어진 넓은 이마, 적갈색 콧수염과 뾰족한 턱수염, 조끼를 받쳐 입은 짙은 정장
  { name: '블라디미르 레닌', skin: '#EDC7A6', face: 'oval', brow: '#7A4A2E', browH: 3.2,
    clothes: shoulders('#2A2C33'), front: shirt + p('M43 84 L50 92 L57 84 L57 100 L43 100Z', '#3A3D46', 0.9) + tie('#7A1F1F') + lapels,
    marks: NOSE.soft + SMILE_LINES + soft('M36 24 Q44 20 52 22 Q44 23.5 36 27Z', '#FFFFFF', 0.35)
      + l('M38 32 Q50 29.5 62 32', SH, 0.9, 0.7),
    hair: both((f) => p(`M${f(26.5)} 50 Q${f(23.5)} 37 ${f(30)} 31 L${f(31.5)} 43Z`, '#7A4A2E', 0.9)),
    beard: p('M41 73 Q50 77 59 73 L54 88 Q50 92 46 88Z', '#7A4A2E', 0.8) + mustache('#7A4A2E') },

  // 다리 없는 둥근 코안경, 위로 치켜 문 긴 담배 물부리, 넘긴 회색 머리, 짙은 정장
  { name: '프랭클린 루스벨트', skin: '#F0CDB4', face: 'jowly', brow: '#8E8E92', ...suit('#23283A', '#3D4F7A'),
    marks: NOSE.big + FOREHEAD + SMILE_LINES,
    hair: p('M26 45 Q22 17 50 17 Q78 17 74 45 Q72 31 62 27 Q48 23 35 29 Q28 34 26 45Z', '#B4B4B8')
      + l('M35 29 Q49 20 67 26', '#8E8E92', 0.9),
    over: `<g fill="none" stroke="#3A3A3E" stroke-width="1.2"><circle cx="39.5" cy="51" r="7.4"/><circle cx="60.5" cy="51" r="7.4"/><path d="M46.9 50 Q50 47.5 53.1 50"/></g>`
      + p('M56 69.5 L78 60.5 L78.8 62.6 L56.8 71.6Z', '#1E1E22', 0.6) + p('M77 59.6 L84 56.8 L85 59.4 L78 62.2Z', WHITE, 0.6)
      + c(85.2, 57.6, 1.3, '#E0764A', 0.4) },
];

/** 둥근 틀 안에 들어가는 그림(눈썹·눈·입 아래). */
export function figureBase(v: Figure): string {
  return `${v.clothes}${v.back ?? ''}${neck(v.skin)}${v.front ?? ''}${ears(v.skin, v.earR)}${p(FACE[v.face], v.skin, 1.2)}${v.marks ?? ''}${v.hair ?? ''}${v.beard ?? ''}`;
}
