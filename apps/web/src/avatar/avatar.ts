/**
 * 모션 아바타.
 *
 * 세트 네 가지(봇, 얼굴, 정령, 문장)와 보관함의 유명인 전용인 인물 세트가 있고, 세트마다 감정 8가지와 상태 6가지에 맞는 움직임이
 * avatar.css에 프리셋으로 들어 있다. 여기서는 모양만 만들고, 움직임은 data-mood / data-state 값이 정한다.
 * 모양은 원·사각형 같은 기본 도형으로만 조립한다. 아이콘은 Lucide에서 가져온다.
 */
import {
  Anchor, Compass, Crown, Ellipsis, Feather, Flame, Frown, Gavel, Gem, Hand, Landmark, Laugh, Leaf,
  CircleQuestionMark, Moon, Mountain, Scale, Scroll, Search, Shield, Sun, Swords, Telescope, ThumbsUp, Zap,
  type IconNode,
} from 'lucide';
import type { AvatarSet, AvatarSpec, AvatarState, Mood } from '../types';
import { clear, h, icon, safeColor } from '../ui/dom';

export const CREST_ICONS: IconNode[] = [
  Gavel, Flame, Scale, Feather, Shield, Compass, Leaf, Anchor, Gem, Mountain, Sun, Moon, Swords, Crown, Landmark, Telescope, Scroll,
];

export const AVATAR_SETS: { id: AvatarSet; label: string; note: string; first: number; count: number }[] = [
  { id: 'bot', label: '봇', note: '화면 얼굴을 가진 로봇. 눈과 입 막대가 감정을 따라 움직입니다', first: 0, count: 6 },
  { id: 'face', label: '얼굴', note: '도형으로 만든 얼굴. 눈썹과 입 모양이 바뀝니다', first: 0, count: 6 },
  { id: 'orb', label: '정령', note: '고리가 도는 빛의 핵. 회전 속도와 파동으로 감정을 드러냅니다', first: 0, count: 6 },
  { id: 'crest', label: '문장', note: '문양을 담은 금빛 틀. 틀과 문양이 함께 움직입니다', first: 1, count: 16 },
  // 인물은 보관함의 유명인 전용이다. 자동 생성한 참가자에게 무작위로 붙이지 않는다 (pickAvatars, RANDOM_SETS)
  { id: 'figure', label: '인물', note: '보관함의 유명인을 알아볼 수 있게 그린 얼굴. 머리 모양·모자·수염·안경으로 구분하고, 눈썹과 입은 감정대로 움직입니다', first: 0, count: 22 },
];

/** 자동 생성한 참가자에게 무작위로 붙일 수 있는 세트. */
export const RANDOM_SETS = AVATAR_SETS.filter((s) => s.id !== 'figure');

const MOOD_ICON: Partial<Record<Mood, IconNode>> = {
  agree: ThumbsUp, skeptical: Frown, heated: Flame, curious: CircleQuestionMark,
  surprised: Zap, amused: Laugh, thinking: Ellipsis,
};

/* ---------- 봇 ---------- */
const BOT = [
  { rx: 16, ant: 'single', ear: 'rect' }, { rx: 28, ant: 'double', ear: 'dot' },
  { rx: 8, ant: 'bar', ear: 'rect' }, { rx: 22, ant: 'dish', ear: 'none' },
  { rx: 30, ant: 'dots', ear: 'dot' }, { rx: 12, ant: 'side', ear: 'rect' },
];
const BOT_ANT: Record<string, string> = {
  single: '<line class="st" x1="50" y1="12" x2="50" y2="23"/><circle class="fl bot-tip" cx="50" cy="9.5" r="3.6"/>',
  double: '<line class="st" x1="37" y1="13" x2="41" y2="23"/><line class="st" x1="63" y1="13" x2="59" y2="23"/><circle class="fl bot-tip" cx="36" cy="11" r="3"/><circle class="fl bot-tip" cx="64" cy="11" r="3"/>',
  bar: '<rect class="fl" x="36" y="15" width="28" height="6" rx="3"/><circle class="fl bot-tip" cx="50" cy="10" r="2.2"/>',
  dish: '<line class="st" x1="50" y1="15" x2="50" y2="23"/><ellipse class="st" cx="50" cy="13" rx="9" ry="3.4"/><circle class="fl bot-tip" cx="50" cy="8.5" r="2.2"/>',
  dots: '<circle class="fl" cx="40" cy="17" r="2.4"/><circle class="fl bot-tip" cx="50" cy="14" r="2.9"/><circle class="fl" cx="60" cy="17" r="2.4"/>',
  side: '<line class="st" x1="72" y1="11" x2="68" y2="23"/><circle class="fl bot-tip" cx="73" cy="8.5" r="3.2"/>',
};
const BOT_EAR: Record<string, string> = {
  rect: '<rect class="fl" x="9" y="44" width="8" height="18" rx="3"/><rect class="fl" x="83" y="44" width="8" height="18" rx="3"/>',
  dot: '<circle class="fl" cx="13" cy="53" r="4.6"/><circle class="fl" cx="87" cy="53" r="4.6"/>',
  none: '',
};

function botSvg(variant: number): string {
  const v = BOT[variant % BOT.length];
  const bars = [0, 1, 2, 3, 4]
    .map((i) => `<rect class="bar b${i}" x="${(48.4 + (i - 2) * 5.6).toFixed(1)}" y="71" width="3.2" height="8" rx="1.6"/>`).join('');
  return `<g class="av-body">${BOT_ANT[v.ant]}${BOT_EAR[v.ear]}
    <rect class="shell" x="17" y="23" width="66" height="60" rx="${v.rx}"/>
    <rect class="screen" x="25" y="32" width="50" height="34" rx="${Math.min(v.rx, 10)}"/>
    <rect class="eye eye-l" x="33.5" y="41" width="9" height="15" rx="4.5"/>
    <rect class="eye eye-r" x="57.5" y="41" width="9" height="15" rx="4.5"/>
    <g class="bot-mouth">${bars}</g></g>`;
}

/* ---------- 얼굴 ---------- */
const FACE = [
  { head: 'circle', hair: 'cap', glasses: false }, { head: 'round', hair: 'tuft', glasses: true },
  { head: 'ellipse', hair: 'bun', glasses: false }, { head: 'hex', hair: 'band', glasses: false },
  { head: 'wide', hair: 'buns', glasses: true }, { head: 'square', hair: 'part', glasses: false },
];
const FACE_HEAD: Record<string, string> = {
  circle: '<circle class="head" cx="50" cy="55" r="30"/>',
  round: '<rect class="head" x="21" y="26" width="58" height="60" rx="20"/>',
  ellipse: '<ellipse class="head" cx="50" cy="55" rx="27" ry="32"/>',
  hex: '<polygon class="head" points="50,22 78,37 78,71 50,88 22,71 22,37"/>',
  wide: '<rect class="head" x="18" y="28" width="64" height="56" rx="27"/>',
  square: '<rect class="head" x="22" y="26" width="56" height="60" rx="10"/>',
};
const FACE_HAIR: Record<string, string> = {
  cap: '<rect class="hair" x="24" y="21" width="52" height="13" rx="6.5"/>',
  tuft: '<polygon class="hair" points="50,12 43,28 57,28"/><polygon class="hair" points="61,17 55,28 65,28"/>',
  bun: '<circle class="hair" cx="50" cy="19" r="8.5"/>',
  band: '<rect class="hair" x="24" y="30" width="52" height="5" rx="2.5"/>',
  buns: '<circle class="hair" cx="26" cy="27" r="7.5"/><circle class="hair" cx="74" cy="27" r="7.5"/>',
  part: '<rect class="hair" x="22" y="22" width="36" height="11" rx="5.5" transform="rotate(-6 40 27)"/>',
};

const GLASSES_ROUND = '<circle class="glass" cx="39.5" cy="51" r="8.6"/><circle class="glass" cx="60.5" cy="51" r="8.6"/><line class="glass" x1="48.1" y1="51" x2="51.9" y2="51"/>';
const FACE_EYES = `<rect class="brow brow-l" x="33" y="40.5" width="13" height="3" rx="1.5"/>
    <rect class="brow brow-r" x="54" y="40.5" width="13" height="3" rx="1.5"/>
    <ellipse class="eye eye-l" cx="39.5" cy="51" rx="3.6" ry="4.6"/>
    <ellipse class="eye eye-r" cx="60.5" cy="51" rx="3.6" ry="4.6"/>`;
const FACE_MOUTH = `<circle class="cheek" cx="31" cy="62" r="4.6"/><circle class="cheek" cx="69" cy="62" r="4.6"/>
    <path class="m m-smile" d="M41 65 Q50 74 59 65"/>
    <path class="m m-frown" d="M42 71 Q50 63 58 71"/>
    <rect class="m m-flat" x="43" y="66.7" width="14" height="2.6" rx="1.3"/>
    <ellipse class="m m-open" cx="50" cy="68" rx="5.6" ry="4.6"/>`;

function faceSvg(variant: number): string {
  const v = FACE[variant % FACE.length];
  return `<g class="av-body">${FACE_HEAD[v.head]}${FACE_HAIR[v.hair]}
    ${FACE_EYES}${v.glasses ? GLASSES_ROUND : ''}
    ${FACE_MOUTH}</g>`;
}

/* ---------- 인물: 보관함의 유명인을 알아볼 수 있게 그린 얼굴 ----------
 * 얼굴 세트의 눈썹·눈·입을 그대로 써서 감정에 따라 똑같이 움직이고, 그 위에 인물마다
 * 머리 모양, 모자, 수염, 안경, 옷깃 같은 널리 알려진 특징을 기본 도형으로 얹는다.
 * back은 머리 뒤, hair와 beard는 얼굴 위(눈·입보다 아래), top은 맨 위에 그린다.
 */
const GLASSES_SQUARE = '<rect class="glass" x="29.5" y="43.5" width="19" height="15" rx="4"/><rect class="glass" x="51.5" y="43.5" width="19" height="15" rx="4"/><line class="glass" x1="48.5" y1="50" x2="51.5" y2="50"/>';
const GLASSES_THIN = '<ellipse class="glass" cx="39.5" cy="51" rx="9.4" ry="6.4"/><ellipse class="glass" cx="60.5" cy="51" rx="9.4" ry="6.4"/><line class="glass" x1="48.9" y1="50" x2="51.1" y2="50"/>';
const SHADES = '<rect class="shade" x="29" y="45" width="19.5" height="12.5" rx="4.5"/><rect class="shade" x="51.5" y="45" width="19.5" height="12.5" rx="4.5"/><rect class="shade" x="47" y="48" width="6" height="2.6"/>';
const COLLAR = '<path class="hair" d="M27 89 L44 85 L50 93 L56 85 L73 89 L77 100 L23 100Z"/>';
const TIE = '<polygon class="tie" points="47.5,90 52.5,90 54.5,100 45.5,100"/>';
const TIE_DARK = '<polygon class="fl" points="47.5,90 52.5,90 54.5,100 45.5,100"/>';
const SHIRT = '<path class="hair-l" d="M38 87 L50 95 L62 87 L64 100 L36 100Z"/>';
const SUIT = COLLAR + SHIRT;
const MUSTACHE = '<path class="hair" d="M39 61 Q50 56.5 61 61 Q50 64 39 61Z"/>';
const GOATEE = '<polygon class="hair" points="44,78 56,78 50,95"/>';
const THIN_TOP = '<path class="hair" d="M23 43 Q22 21 50 21 Q78 21 77 43 Q71 34 62 30 Q50 24 38 30 Q29 34 23 43Z"/>';

interface Figure { name: string; head: string; back?: string; hair?: string; beard?: string; glasses?: string; top?: string }

export const FIGURES: Figure[] = [
  { name: '일론 머스크', head: 'round', back: COLLAR,
    hair: '<path class="hair" d="M21 41 Q19 17 50 17 Q81 17 79 41 Q72 27 52 29 Q34 30 21 41Z"/>' },
  { name: '스티브 잡스', head: 'ellipse', back: '<rect class="hair" x="35" y="83" width="30" height="17" rx="6"/>',
    hair: '<path class="hair" d="M23 47 Q22 32 31 26 L32 40Z"/><path class="hair" d="M77 47 Q78 32 69 26 L68 40Z"/>',
    beard: '<path class="st stub" d="M28 64 Q31 85 50 88 Q69 85 72 64"/>', glasses: GLASSES_ROUND },
  { name: '워런 버핏', head: 'wide', back: SUIT + TIE,
    hair: '<path class="hair-l" d="M19 43 Q17 22 50 21 Q83 22 81 43 Q70 29 46 31 Q30 33 19 43Z"/>', glasses: GLASSES_SQUARE },
  { name: '샘 올트먼', head: 'ellipse', back: '<path class="hair" d="M31 88 Q50 97 69 88 L73 100 L27 100Z"/>',
    hair: '<polygon class="hair" points="23,41 25,24 33,29 38,17 46,26 53,15 60,26 68,18 73,28 77,41 66,31 50,29 34,31"/>' },
  { name: '도널드 트럼프', head: 'wide', back: `${SUIT}<polygon class="tie" points="47,89 53,89 56,102 50,106 44,102"/>`,
    hair: '<path class="hair-l" d="M15 43 Q11 14 52 12 Q89 12 85 41 Q80 26 58 27 Q36 26 24 34 Q18 38 15 43Z"/><path class="st thin" d="M25 31 Q50 18 79 28"/>' },
  { name: '박태준', head: 'square', back: SUIT + TIE_DARK,
    top: '<path class="hair" d="M21 35 Q21 10 50 10 Q79 10 79 35Z"/><rect class="hair" x="15" y="33" width="70" height="5.5" rx="2.75"/><rect class="helm" x="47" y="12.5" width="6" height="19" rx="2.5"/>' },
  { name: '박정희', head: 'ellipse', back: SUIT + TIE_DARK,
    hair: '<path class="hair" d="M24 41 Q24 20 50 20 Q76 20 76 41 Q66 30 50 30 Q34 30 24 41Z"/>', glasses: SHADES },
  { name: '이순신', head: 'round',
    back: '<rect class="hair" x="11" y="36" width="13" height="36" rx="4"/><rect class="hair" x="76" y="36" width="13" height="36" rx="4"/><path class="hair" d="M27 89 L50 96 L73 89 L77 100 L23 100Z"/>',
    beard: MUSTACHE + GOATEE,
    top: '<path class="hair" d="M22 36 Q22 14 50 14 Q78 14 78 36Z"/><rect class="hair" x="18" y="34" width="64" height="5.5" rx="2.5"/><line class="st" x1="50" y1="14" x2="50" y2="5"/><polygon class="fl" points="50,0 45.5,7 54.5,7"/><circle class="helm" cx="50" cy="26" r="4"/>' },
  { name: '세종대왕', head: 'round',
    back: '<rect class="hair" x="31" y="7" width="38" height="20" rx="9"/><path class="tie" d="M26 89 L50 97 L74 89 L78 100 L22 100Z"/>',
    beard: MUSTACHE + GOATEE,
    top: '<rect class="hair" x="22" y="18" width="56" height="19" rx="8.5"/><rect class="helm" x="30" y="30" width="40" height="2.4" rx="1.2"/>' },
  { name: '소크라테스', head: 'circle',
    back: '<circle class="hair-l" cx="21" cy="47" r="6.5"/><circle class="hair-l" cx="79" cy="47" r="6.5"/><path class="hair-l" d="M26 90 Q50 82 74 90 L78 100 L22 100Z"/>',
    beard: [[26, 65], [30, 75], [38, 83], [50, 86], [62, 83], [70, 75], [74, 65]]
      .map(([x, y]) => `<circle class="hair-l" cx="${x}" cy="${y}" r="7.4"/>`).join('') },
  { name: '니콜로 마키아벨리', head: 'hex', back: '<path class="hair" d="M30 88 L50 82 L70 88 L74 100 L26 100Z"/>',
    hair: '<path class="hair" d="M21 38 L50 19 L79 38 L79 62 L73 62 L73 41 L50 30 L27 41 L27 62 L21 62Z"/>' },
  { name: '장 자크 루소', head: 'ellipse',
    back: '<circle class="hair-l" cx="20" cy="50" r="6"/><circle class="hair-l" cx="19" cy="62" r="6"/><circle class="hair-l" cx="80" cy="50" r="6"/><circle class="hair-l" cx="81" cy="62" r="6"/><path class="hair" d="M27 89 L50 95 L73 89 L77 100 L23 100Z"/><path class="hair-l" d="M43 88 L57 88 L54 99 L46 99Z"/>',
    top: '<path class="hair" d="M19 37 Q19 9 50 9 Q81 9 81 37 Q65 30 50 30 Q35 30 19 37Z"/><path class="st fur" d="M27 23 Q50 12 73 23"/>' },
  { name: '마하트마 간디', head: 'ellipse',
    back: '<circle class="head" cx="22" cy="54" r="7.5"/><circle class="head" cx="78" cy="54" r="7.5"/><path class="hair-l" d="M23 91 Q50 80 77 91 L81 100 L19 100Z"/>',
    beard: '<path class="hair-l" d="M40 61 Q50 57.5 60 61 Q50 64.5 40 61Z"/>', glasses: GLASSES_ROUND },
  { name: '정주영', head: 'round', back: SUIT + TIE_DARK, hair: THIN_TOP, glasses: GLASSES_SQUARE },
  { name: '이건희', head: 'ellipse', back: SUIT + TIE_DARK,
    hair: '<path class="hair" d="M23 41 Q23 19 50 19 Q77 19 77 41 Q72 29 58 28 L40 31 Q30 33 23 41Z"/>', glasses: GLASSES_THIN },
  { name: '블라디미르 푸틴', head: 'ellipse', back: SUIT + TIE_DARK,
    hair: '<path class="hair-l" d="M24 41 Q24 22 50 22 Q76 22 76 41 Q68 33 50 32 Q32 33 24 41Z"/>' },
  { name: '시진핑', head: 'wide', back: SUIT + TIE,
    hair: '<path class="hair" d="M18 43 Q16 18 50 18 Q84 18 82 43 Q74 30 50 31 Q26 30 18 43Z"/>' },
  { name: '나폴레옹', head: 'round',
    back: `${COLLAR}<rect class="fl" x="12" y="90" width="17" height="6" rx="3"/><rect class="fl" x="71" y="90" width="17" height="6" rx="3"/>`,
    hair: '<path class="hair" d="M38 27 Q47 40 60 30Z"/>',
    top: '<path class="hair" d="M5 33 Q27 5 50 5 Q73 5 95 33 Q73 25 50 25 Q27 25 5 33Z"/><circle class="tie" cx="50" cy="15" r="4.2"/>' },
  { name: '프리드리히 니체', head: 'square', back: COLLAR,
    hair: '<path class="hair" d="M21 41 Q17 13 52 15 Q83 17 79 41 Q70 26 50 28 Q32 28 21 41Z"/>',
    beard: '<path class="hair" d="M26 63 Q38 53 50 60 Q62 53 74 63 Q71 78 50 68 Q29 78 26 63Z"/>' },
  { name: '이마누엘 칸트', head: 'ellipse',
    back: `<circle class="hair-l" cx="21" cy="48" r="6"/><circle class="hair-l" cx="79" cy="48" r="6"/>${COLLAR}<circle class="hair-l" cx="50" cy="92" r="5.5"/>`,
    hair: '<path class="hair-l" d="M24 39 Q24 17 50 17 Q76 17 76 39 Q66 27 50 27 Q34 27 24 39Z"/>' },
  { name: '노자', head: 'circle',
    back: '<circle class="hair-l" cx="50" cy="16" r="8.5"/><rect class="hair" x="45" y="22" width="10" height="4" rx="2"/><path class="hair-l" d="M24 90 Q50 82 76 90 L80 100 L20 100Z"/>',
    beard: '<path class="hair-l" d="M38 76 Q50 82 62 76 L54.5 102 Q50 106 45.5 102Z"/><path class="st" d="M44 62 Q38 66 36 77"/><path class="st" d="M56 62 Q62 66 64 77"/>',
    top: '<path class="st thin" d="M33 41 Q25 45 22 58"/><path class="st thin" d="M67 41 Q75 45 78 58"/>' },
  { name: '아이작 뉴턴', head: 'ellipse',
    back: '<path class="hair-l" d="M50 13 Q19 11 15 44 Q11 70 19 98 L35 98 Q27 70 28 44 Q32 27 50 27 Q68 27 72 44 Q73 70 65 98 L81 98 Q89 70 85 44 Q81 11 50 13Z"/><path class="st thin" d="M19 54 q4 4 0 8 q-4 4 0 8 q4 4 0 8 M81 54 q-4 4 0 8 q4 4 0 8 q-4 4 0 8"/><path class="hair-l" d="M43 88 L57 88 L54 99 L46 99Z"/>' },
];

function figureSvg(variant: number): string {
  const v = FIGURES[variant % FIGURES.length];
  return `<g class="av-body">${v.back ?? ''}${FACE_HEAD[v.head]}${v.hair ?? ''}${v.beard ?? ''}
    ${FACE_EYES}${v.glasses ?? ''}
    ${FACE_MOUTH}${v.top ?? ''}</g>`;
}

/* ---------- 정령 ---------- */
const ORB = [
  { core: 'circle', dash: '', sats: 1 }, { core: 'diamond', dash: '2 7', sats: 2 },
  { core: 'hex', dash: '16 8', sats: 1 }, { core: 'tri', dash: '1 9', sats: 3 },
  { core: 'ring', dash: '30 6', sats: 2 }, { core: 'square', dash: '6 4', sats: 1 },
];
const ORB_CORE: Record<string, string> = {
  circle: '<circle class="core" cx="50" cy="50" r="15"/>',
  diamond: '<rect class="core" x="37" y="37" width="26" height="26" rx="3" transform="rotate(45 50 50)"/>',
  hex: '<polygon class="core" points="50,33 64.7,41.5 64.7,58.5 50,67 35.3,58.5 35.3,41.5"/>',
  tri: '<polygon class="core" points="50,32 67,61 33,61"/>',
  ring: '<circle class="core-st" cx="50" cy="50" r="13"/><circle class="core" cx="50" cy="50" r="5"/>',
  square: '<rect class="core" x="37" y="37" width="26" height="26" rx="7"/>',
};

function orbSvg(variant: number): string {
  const v = ORB[variant % ORB.length];
  const spikes = Array.from({ length: 8 }, (_, i) =>
    `<rect x="48.6" y="4" width="2.8" height="9" rx="1.4" transform="rotate(${i * 45} 50 50)"/>`).join('');
  const sats = Array.from({ length: v.sats }, (_, i) =>
    `<circle cx="50" cy="13" r="3.2" transform="rotate(${(360 / v.sats) * i} 50 50)"/>`).join('');
  return `<g class="av-body">
    <circle class="orb-ripple rp1" cx="50" cy="50" r="18"/><circle class="orb-ripple rp2" cx="50" cy="50" r="18"/><circle class="orb-ripple rp3" cx="50" cy="50" r="18"/>
    <g class="orb-r1"><circle class="st" cx="50" cy="50" r="37" ${v.dash ? `stroke-dasharray="${v.dash}"` : ''}/></g>
    <g class="orb-r2"><circle class="st thin" cx="50" cy="50" r="29" stroke-dasharray="3 5"/></g>
    <g class="orb-spikes">${spikes}</g><g class="orb-sats">${sats}</g>
    <g class="orb-core">${ORB_CORE[v.core]}<circle class="hl" cx="45" cy="45" r="3.6"/></g></g>`;
}

/* ---------- 문장 ---------- */
function crestSvg(): string {
  const ticks = [0, 90, 180, 270]
    .map((a) => `<rect x="48" y="4" width="4" height="7" rx="1.5" transform="rotate(${a} 50 50)"/>`).join('');
  return `<g class="av-body">
    <g class="cr-f3"><rect class="st thin" x="14" y="14" width="72" height="72" rx="3" stroke-dasharray="5 9"/></g>
    <g class="cr-f1"><rect class="shell" x="24" y="24" width="52" height="52" rx="3" transform="rotate(45 50 50)"/></g>
    <g class="cr-f2"><rect class="st thin" x="31" y="31" width="38" height="38" rx="2" transform="rotate(45 50 50)"/></g>
    <g class="cr-ticks">${ticks}</g></g>`;
}

/* ---------- 만들기와 바꾸기 ---------- */
export function normalizeSpec(spec: Partial<AvatarSpec> | undefined | null): AvatarSpec {
  const set = AVATAR_SETS.find((s) => s.id === spec?.set) ?? AVATAR_SETS[0];
  const variant = Number.isFinite(spec?.variant) ? Math.abs(Math.trunc(spec!.variant!)) % set.count : set.first;
  return { set: set.id, variant };
}

export function createAvatar(spec: Partial<AvatarSpec> | undefined | null, color: string | undefined, size = 96): HTMLElement {
  const s = normalizeSpec(spec);
  const el = h('div', {
    class: s.set === 'figure' ? 'av av--face av--figure' : `av av--${s.set}`, 'data-state': 'idle', 'data-mood': 'calm', role: 'img',
    style: `--c:${safeColor(color)};--av-size:${size}px;--d:${(-Math.random() * 4).toFixed(2)}s`,
  });
  const inner = s.set === 'bot' ? botSvg(s.variant) : s.set === 'face' ? faceSvg(s.variant)
    : s.set === 'orb' ? orbSvg(s.variant) : s.set === 'figure' ? figureSvg(s.variant) : crestSvg();
  if (s.set === 'figure') el.setAttribute('aria-label', FIGURES[s.variant % FIGURES.length].name);
  el.innerHTML = `<span class="av-aura"></span><svg class="av-svg" viewBox="0 0 100 100" aria-hidden="true">${inner}</svg>`;
  if (s.set === 'crest') {
    el.append(h('span', { class: 'crest-icon' }, icon(CREST_ICONS[s.variant % CREST_ICONS.length], 40)));
  }
  el.append(h('span', { class: 'av-badge' }));
  return el;
}

const cutTimers = new WeakMap<HTMLElement, number>();

/** 아바타의 감정과 상태를 바꾼다. 움직임은 CSS 프리셋이 맡는다. */
export function setAvatar(el: HTMLElement, patch: { state?: AvatarState; mood?: Mood; wants?: boolean }): void {
  if (patch.mood) el.dataset.mood = patch.mood;
  if (patch.state) {
    window.clearTimeout(cutTimers.get(el));
    el.dataset.state = patch.state;
    if (patch.state === 'cut') {
      cutTimers.set(el, window.setTimeout(() => { if (el.dataset.state === 'cut') setAvatar(el, { state: 'listening' }); }, 700));
    }
  }
  if (patch.wants !== undefined) el.dataset.wants = patch.wants ? '1' : '';
  const badge = el.querySelector('.av-badge') as HTMLElement | null;
  if (!badge) return;
  const state = el.dataset.state;
  const node = state === 'searching' ? Search
    : (state !== 'speaking' && el.dataset.wants === '1') ? Hand
    : MOOD_ICON[el.dataset.mood as Mood];
  const key = node ? String(iconKey(node)) : '';
  if (badge.dataset.key === key) return;
  badge.dataset.key = key;
  clear(badge);
  if (node) badge.append(icon(node, 16));
  badge.classList.toggle('is-on', !!node);
}

/* 같은 아이콘을 다시 그리지 않으려고 아이콘마다 번호를 매겨 둔다 */
const iconKeys = new Map<IconNode, number>();
function iconKey(node: IconNode): number {
  if (!iconKeys.has(node)) iconKeys.set(node, iconKeys.size + 1);
  return iconKeys.get(node)!;
}

/** 참가자 수만큼 서로 다른 아바타를 고른다. */
export function pickAvatars(count: number, set: AvatarSet | 'mix'): AvatarSpec[] {
  const pool: AvatarSpec[] = [];
  for (const s of RANDOM_SETS) {
    if (set !== 'mix' && s.id !== set) continue;
    for (let v = s.first; v < s.count; v += 1) pool.push({ set: s.id, variant: v });
  }
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  if (set === 'mix') {   // 섞을 때는 세트가 고르게 나오게 한다
    const order: AvatarSet[] = ['bot', 'face', 'orb', 'crest'];
    const bySet = order.map((id) => pool.filter((p) => p.set === id));
    const out: AvatarSpec[] = [];
    for (let i = 0; out.length < count; i += 1) {
      const bucket = bySet[i % bySet.length];
      const next = bucket[Math.floor(i / bySet.length) % bucket.length];
      out.push(next);
    }
    return out;
  }
  return Array.from({ length: count }, (_, i) => pool[i % pool.length]);
}
