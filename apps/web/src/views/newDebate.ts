import {
  ChevronRight, Drama, FileText, Globe, Library, RotateCcw, LoaderCircle, Minus, Play, Plus, RefreshCw, Save, Shuffle, Sparkles, Upload,
} from 'lucide';
import { api } from '../api';
import { AVATAR_SETS, createAvatar, normalizeSpec, pickAvatars, setAvatar } from '../avatar/avatar';
import type { AppContext } from '../main';
import { PALETTE, type AvatarSet, type Mood, type Persona } from '../types';
import { clear, deleteButton, fmtCost, h, icon, put, safeColor, toast } from '../ui/dom';

interface Slot extends Persona { fromLibrary?: boolean }
interface Material { name: string; text: string; chars: number; tokens: number }

const draft = {
  prepCost: 0,   // 이 토론을 준비하며 든 비용(참가자 생성). 시작할 때 서버에 넘겨 총 비용에 더한다
  topic: '',
  concept: '',
  materials: [] as Material[],
  urls: [] as string[],
  count: 4,
  policy: 'auto',
  avatarSet: 'bot' as AvatarSet | 'mix',
  cast: [] as (Slot | null)[],
  moderator: true,
  mode: 'mixed',
  turnsOn: true, maxTurns: 30,
  minutesOn: true, maxMinutes: 10,
  length: 'auto',
  speed: 'normal',
  interjection: true,
  gapScale: 1,
  search: 'auto',
  maxSearches: 2,
  model: '',
  effort: '',
  perSpeaker: false,
  badge: 'on',
  summary: true,
  reactions: 'smart',
  tone: 'default',
  hiddenAgenda: null as boolean | null,
};

/* 진행 설정은 이 브라우저에 기억해 두고 다음에 그대로 쓴다. 주제, 자료, 참가자는 기억하지 않는다. */
const SETTING_KEYS = ['count', 'policy', 'avatarSet', 'moderator', 'mode', 'turnsOn', 'maxTurns', 'minutesOn', 'maxMinutes',
  'length', 'speed', 'interjection', 'gapScale', 'search', 'maxSearches', 'model', 'effort', 'perSpeaker', 'badge', 'summary',
  'reactions', 'tone', 'hiddenAgenda'] as const;
const STORE_KEY = 'aitalk.settings.v1';
const pick = (): Record<string, unknown> => Object.fromEntries(SETTING_KEYS.map((k) => [k, (draft as any)[k]]));
const DEFAULTS = pick();

function persist(): void {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(pick())); } catch { /* 저장이 막혀 있어도 화면은 그대로 쓴다 */ }
}

function restore(): void {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) ?? 'null');
    if (!saved || typeof saved !== 'object') return;
    for (const k of SETTING_KEYS) {
      const value = saved[k];
      const base = DEFAULTS[k];
      if (value === undefined) continue;
      if (base === null ? (value === null || typeof value === 'boolean') : typeof value === typeof base) (draft as any)[k] = value;
    }
    if (!['auto', 'off'].includes(draft.search)) draft.search = 'auto';
    if (!['default', 'humorous', 'serious', 'creative'].includes(draft.tone)) draft.tone = 'default';
    if (!['auto', 'short', 'normal', 'long'].includes(draft.length)) draft.length = 'auto';
    draft.count = Math.max(2, Math.min(10, Math.round(draft.count) || 4));
  } catch { /* 깨진 값은 무시한다 */ }
}
restore();

const EXAMPLES = [
  '주 4일제를 법으로 정해야 하는가',
  'AI가 만든 창작물에 저작권을 인정해야 하는가',
  '제철소의 수소환원제철 전환, 지금 속도가 맞는가',
];
const CONCEPTS = [
  'TV 생방송 토론. 시청자를 의식해 날카롭고 간결하게 말한다',
  '사내 임원 회의. 서로 존중하지만 부서의 이해관계가 걸려 있다',
  '친한 동료들의 편한 점심 수다. 농담을 섞고 격식을 차리지 않는다',
];
const MOOD_CYCLE: Mood[] = ['agree', 'heated', 'curious', 'amused', 'skeptical', 'surprised', 'thinking', 'calm'];

function seg<T extends string>(options: [T, string][], get: () => T, set: (v: T) => void): HTMLElement {
  const el = h('div', { class: 'seg', role: 'group' });
  const paint = () => {
    clear(el);
    for (const [value, label] of options) {
      el.append(h('button', { type: 'button', class: get() === value ? 'is-on' : '', onclick: () => { set(value); persist(); paint(); } }, label));
    }
  };
  paint();
  return el;
}

function toggle(label: string, get: () => boolean, set: (v: boolean) => void): HTMLElement {
  const input = h('input', { type: 'checkbox', checked: get(), onchange: () => { set(input.checked); persist(); } });
  return h('label', { class: 'switch' }, input, h('i'), h('span', null, label));
}

function field(label: string, control: HTMLElement, note = ''): HTMLElement {
  return h('div', null, h('div', { class: 'field-label' }, label), control, note ? h('div', { class: 'muted small', style: 'margin-top:.375rem' }, note) : null);
}

export function mountNewDebate(root: HTMLElement, ctx: AppContext): () => void {
  const status = ctx.status;
  if (status && !status.models.some((m) => m.id === draft.model)) {   // 기억해 둔 모델이 지금 AI에 없으면 기본값으로
    draft.model = status.defaults.model;
    draft.effort = status.defaults.effort;
  }
  let library: Persona[] = [];
  let busy = false;
  let menu: HTMLElement | null = null;
  const loading = new Set<number>();

  const page = h('div', { class: 'page' });
  root.append(page);

  /* ---- 주제 ---- */
  const topic = h('textarea', {
    class: 'topic-input', placeholder: '토론할 주제를 적어 주세요. 한 줄도 좋고, 배경을 몇 문단 적어도 좋습니다.', rows: 3,
    oninput: () => { draft.topic = topic.value; paintStart(); },
  });
  topic.value = draft.topic;
  const concept = h('textarea', {
    class: 'concept-input', rows: 2, placeholder: '예) 심야 라디오 토론. 진행자는 느긋하고, 참가자들은 서로를 잘 아는 오랜 논객들이다.',
    oninput: () => { draft.concept = concept.value; },
  });
  concept.value = draft.concept;
  put(page,
    h('div', { class: 'hero' }, h('h1', null, '무엇을 두고 토론할까요?'),
      h('p', null, '주제를 던지면 AI 참가자들이 실제 토론처럼 말을 주고받습니다.')),
    status && !status.ready ? h('div', { class: 'banner' }, status.message || 'AI에 연결되지 않았습니다.') : null,
    !status ? h('div', { class: 'banner' }, '서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인하세요.') : null,
    h('div', { class: 'panel frame topic-box' }, topic,
      h('div', { class: 'topic-foot' }, h('span', { class: 'muted small' }, '예시'),
        EXAMPLES.map((text) => h('button', { type: 'button', class: 'chip', onclick: () => { topic.value = text; draft.topic = text; paintStart(); topic.focus(); } }, text)))),
    h('div', { class: 'panel concept-box' },
      h('div', { class: 'concept-label' }, icon(Drama, 18), '컨셉과 분위기', h('small', null, '선택. 어떤 자리인지, 어떤 분위기인지. 참가자 모두에게 똑같이 적용됩니다')),
      concept,
      h('div', { class: 'topic-foot' }, h('span', { class: 'muted small' }, '예시'),
        CONCEPTS.map((text) => h('button', { type: 'button', class: 'chip', onclick: () => { concept.value = text; draft.concept = text; concept.focus(); } }, text)))),
  );

  /* ---- 자료 ---- */
  const matList = h('div', { class: 'mat-list' });
  const fileInput = h('input', { type: 'file', class: 'hidden', accept: '.pdf,.docx,.txt,.md,.markdown', multiple: true });
  const urlInput = h('input', { class: 'input', type: 'url', placeholder: 'https:// 로 시작하는 웹 주소', style: 'max-width:28rem' });
  const addUrl = () => {
    const value = urlInput.value.trim();
    if (!/^https?:\/\/\S+$/.test(value)) { toast('http:// 또는 https:// 로 시작하는 주소를 적어 주세요.', 'error'); return; }
    if (!draft.urls.includes(value)) draft.urls.push(value);
    urlInput.value = '';
    paintMaterials();
  };
  urlInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); addUrl(); } });
  fileInput.addEventListener('change', async () => {
    for (const file of Array.from(fileInput.files ?? [])) {
      try {
        draft.materials.push(await api.uploadMaterial(file));
      } catch (err) {
        toast(`${file.name}: ${(err as Error).message}`, 'error');
      }
      paintMaterials();
    }
    fileInput.value = '';
  });
  function paintMaterials(): void {
    clear(matList);
    draft.materials.forEach((m, i) => matList.append(h('div', { class: 'mat-item' }, icon(FileText, 18),
      h('span', { class: 'name' }, m.name),
      h('span', { class: 'muted small' }, `약 ${m.tokens.toLocaleString()}토큰`),
      m.tokens > 60000 ? h('span', { class: 'chip chip--ember', tip: '호출마다 이만큼의 입력이 들어갑니다. 캐시가 맞으면 대부분 할인됩니다' }, '긴 문서') : null,
      deleteButton(() => { draft.materials.splice(i, 1); paintMaterials(); }))));
    draft.urls.forEach((u, i) => matList.append(h('div', { class: 'mat-item' }, icon(Globe, 18),
      h('span', { class: 'name' }, u), h('span', { class: 'muted small' }, '시작할 때 진행자가 조사합니다'),
      deleteButton(() => { draft.urls.splice(i, 1); paintMaterials(); }))));
  }
  page.append(h('section', { class: 'block' },
    h('h2', { class: 'block-title' }, '자료', h('small', null, '선택. 문서를 올리거나 웹 주소를 붙이면 그것을 놓고 토론합니다')),
    h('div', { class: 'mat-row' },
      h('button', { type: 'button', class: 'btn', onclick: () => fileInput.click() }, icon(Upload, 18), '문서 올리기'), fileInput,
      urlInput, h('button', { type: 'button', class: 'btn', onclick: addUrl }, icon(Plus, 18), '주소 추가')),
    matList));
  paintMaterials();

  /* ---- 참가자 ---- */
  const countLabel = h('b', null, '');
  const minus = h('button', { type: 'button', 'aria-label': '한 명 줄이기', onclick: () => setCount(draft.count - 1) }, icon(Minus, 16));
  const plus = h('button', { type: 'button', 'aria-label': '한 명 늘리기', onclick: () => setCount(draft.count + 1) }, icon(Plus, 16));
  const policy = h('select', { class: 'select', style: 'width:auto', onchange: () => { draft.policy = policy.value; persist(); } },
    ([['auto', '알아서 구성'], ['balanced', '찬반 균형'], ['stakeholders', '여러 이해관계자'], ['experts', '전문가 패널']] as const)
      .map(([v, l]) => h('option', { value: v, selected: draft.policy === v }, l)));
  const genBtn = h('button', { type: 'button', class: 'btn', onclick: () => generateAll() }, icon(Sparkles, 18), '자동 생성');
  const castGrid = h('div', { class: 'cast-grid' });
  const countNote = h('span', { class: 'muted small' });
  page.append(h('section', { class: 'block' },
    h('h2', { class: 'block-title' }, '참가자', h('small', null, '주제에 맞춰 AI가 만들거나, 보관함에서 고릅니다')),
    h('div', { class: 'cast-bar' },
      h('div', { class: 'stepper' }, minus, countLabel, plus), policy,
      seg<AvatarSet | 'mix'>([...AVATAR_SETS.map((s) => [s.id, s.label] as [AvatarSet, string]), ['mix', '섞어서']],
        () => draft.avatarSet, (v) => { draft.avatarSet = v; reassignAvatars(); }),
      genBtn, toggle('진행자', () => draft.moderator, (v) => { draft.moderator = v; }), countNote),
    castGrid));

  function setCount(n: number): void {
    draft.count = Math.max(2, Math.min(10, n));
    while (draft.cast.length < draft.count) draft.cast.push(null);
    draft.cast.length = draft.count;
    paintCast();
  }

  function dress(p: Partial<Persona>, index: number, avatar = pickAvatars(1, draft.avatarSet)[0]): Slot {
    return {
      name: p.name ?? '', title: p.title ?? '', expertise: p.expertise ?? '', personality: p.personality ?? '',
      speech: p.speech ?? '', viewpoint: p.viewpoint ?? '', claims: p.claims ?? [], concede: p.concede ?? '',
      hidden: p.hidden ?? '', tags: p.tags ?? [], id: p.id,
      color: safeColor(p.color, PALETTE[index % PALETTE.length]),
      avatar: p.avatar && (p.avatar as any).set ? normalizeSpec(p.avatar) : avatar,
    };
  }

  function reassignAvatars(): void {
    const picks = pickAvatars(draft.count, draft.avatarSet);
    draft.cast.forEach((p, i) => { if (p && !p.fromLibrary) p.avatar = picks[i]; });
    paintCast();
  }

  async function generateAll(): Promise<boolean> {
    if (!draft.topic.trim()) { toast('주제를 먼저 적어 주세요.', 'error'); topic.focus(); return false; }
    if (busy) return false;
    busy = true;
    const kept = draft.cast.filter((p): p is Slot => !!p && !!p.fromLibrary);
    draft.cast.forEach((_, i) => loading.add(i));
    paintCast();
    try {
      const { personas, cost } = await api.cast({
        topic: draft.topic, concept: draft.concept, tone: draft.tone, count: draft.count, policy: draft.policy, fixed: kept,
        materials: draft.materials.map((m) => m.text).join('\n\n').slice(0, 6000),
        model: draft.model || undefined, effort: draft.effort || undefined,
      });
      draft.prepCost += cost ?? 0;
      const picks = pickAvatars(draft.count, draft.avatarSet);
      draft.cast = Array.from({ length: draft.count }, (_, i) => {
        const p = personas[i];
        if (!p) return null;
        const slot = dress(p, i, picks[i]);
        if (i < kept.length) { slot.fromLibrary = true; slot.color = kept[i].color; slot.avatar = kept[i].avatar; }
        return slot;
      });
      return true;
    } catch (err) {
      toast((err as Error).message, 'error');
      return false;
    } finally {
      busy = false;
      loading.clear();
      paintCast();
    }
  }

  async function regenerate(index: number): Promise<void> {
    if (!draft.topic.trim()) { toast('주제를 먼저 적어 주세요.', 'error'); return; }
    const others = draft.cast.filter((p, i): p is Slot => !!p && i !== index);
    loading.add(index);
    paintCast();
    try {   // 다른 참가자를 알려 주어 겹치지 않는 인물을 받는다
      const { personas, cost } = await api.cast({
        topic: draft.topic, concept: draft.concept, tone: draft.tone, count: others.length + 1, policy: draft.policy, fixed: others, materials: '',
        model: draft.model || undefined, effort: draft.effort || undefined,
      });
      draft.prepCost += cost ?? 0;
      const fresh = personas[others.length];
      if (fresh) {
        const old = draft.cast[index];
        draft.cast[index] = dress({ ...fresh, color: old?.color ?? PALETTE[index % PALETTE.length] }, index, old?.avatar);
      }
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      loading.delete(index);
      paintCast();
    }
  }

  function closeMenu(): void { menu?.remove(); menu = null; }
  function openLibrary(index: number, anchor: HTMLElement): void {
    closeMenu();
    const used = new Set(draft.cast.filter(Boolean).map((p) => p!.id).filter(Boolean));
    menu = h('div', { class: 'menu' });
    const items = library.filter((p) => !used.has(p.id));
    if (!items.length) menu.append(h('div', { class: 'muted small', style: 'padding:.5rem .625rem' }, '고를 인물이 없습니다. 페르소나 메뉴에서 만들 수 있습니다.'));
    for (const p of items) {
      const av = createAvatar(p.avatar, p.color, 32);
      av.classList.add('is-still');
      menu.append(h('button', { type: 'button', onclick: () => {
        draft.cast[index] = { ...dress(p, index), fromLibrary: true };
        closeMenu();
        paintCast();
      } }, av, h('span', null, h('div', null, p.name), h('div', { class: 'muted' }, p.title))));
    }
    const card = anchor.closest('.pcard') as HTMLElement;
    card.append(menu);
    menu.style.left = '1rem';
    menu.style.bottom = '3.25rem';
  }
  const onDocClick = (e: MouseEvent) => { if (menu && !(e.target as HTMLElement).closest('.menu, .lib-btn')) closeMenu(); };
  document.addEventListener('click', onDocClick);

  function modelSelects(p: Slot): HTMLElement {
    const models = status?.models ?? [];
    const model = h('select', { class: 'select', onchange: () => { p.model = model.value || undefined; p.effort = undefined; paintCast(); } },
      h('option', { value: '' }, '기본 모델'), models.map((m) => h('option', { value: m.id, selected: p.model === m.id }, m.label)));
    const efforts = (models.find((m) => m.id === (p.model || draft.model)) ?? models[0])?.efforts ?? [];
    const effort = h('select', { class: 'select', onchange: () => { p.effort = effort.value || undefined; } },
      h('option', { value: '' }, '기본 노력'), efforts.map((e) => h('option', { value: e, selected: p.effort === e }, e)));
    return h('div', { class: 'row', style: 'flex-wrap:nowrap' }, model, effort);
  }

  function paintCast(): void {
    countLabel.textContent = `${draft.count}명`;
    minus.disabled = draft.count <= 2;
    plus.disabled = draft.count >= 10;
    countNote.textContent = draft.count > 5 ? '5명이 넘으면 한 사람의 발언 기회가 줄어듭니다' : '';
    genBtn.disabled = busy;
    clear(genBtn);
    genBtn.append(icon(busy ? LoaderCircle : Sparkles, 18, busy ? 'spin' : ''), busy ? '만드는 중' : draft.cast.some(Boolean) ? '다시 자동 생성' : '자동 생성');
    clear(castGrid);
    while (draft.cast.length < draft.count) draft.cast.push(null);
    draft.cast.forEach((p, i) => {
      const libBtn = h('button', { type: 'button', class: 'btn btn--icon lib-btn', tip: '보관함에서 고르기', 'aria-label': '보관함에서 고르기',
        onclick: (e: MouseEvent) => openLibrary(i, e.currentTarget as HTMLElement) }, icon(Library, 18));
      if (!p) {
        castGrid.append(h('div', { class: `pcard pcard--empty${loading.has(i) ? ' is-loading' : ''}`, style: `animation-delay:${i * 50}ms` },
          h('div', null, loading.has(i) ? '인물을 만드는 중' : `참가자 ${i + 1}`),
          loading.has(i) ? null : h('div', { class: 'row' },
            h('button', { type: 'button', class: 'btn', onclick: () => regenerate(i) }, icon(Sparkles, 18), '만들기'), libBtn)));
        return;
      }
      const av = createAvatar(p.avatar, p.color, 72);
      setAvatar(av, { state: 'listening' });
      let moodIndex = 0;
      const avBtn = h('button', { type: 'button', class: 'avatar-btn', tip: '눌러서 감정 움직임 미리 보기', 'aria-label': '감정 움직임 미리 보기',
        onclick: () => { setAvatar(av, { mood: MOOD_CYCLE[moodIndex % MOOD_CYCLE.length], state: moodIndex % 2 ? 'speaking' : 'listening' }); moodIndex += 1; } }, av);
      castGrid.append(h('div', { class: `pcard${loading.has(i) ? ' is-loading' : ''}`, style: `--c:${p.color};animation-delay:${i * 60}ms` },
        h('div', { class: 'pcard-head' }, avBtn,
          h('div', { class: 'grow' }, h('div', { class: 'pcard-name' }, p.name), h('div', { class: 'pcard-title' }, p.title))),
        p.viewpoint ? h('div', { class: 'pcard-view' }, p.viewpoint) : null,
        p.claims.length ? h('ul', { class: 'pcard-claims' }, p.claims.slice(0, 3).map((c) => h('li', null, c))) : null,
        h('div', { class: 'pcard-meta' },
          p.personality ? h('span', { class: 'chip', tip: '성격과 토론 스타일' }, p.personality.length > 22 ? `${p.personality.slice(0, 22)}…` : p.personality) : null,
          p.fromLibrary ? h('span', { class: 'chip chip--c', tip: '자동 생성을 눌러도 인물은 그대로 두고 입장만 주제에 맞춥니다' }, '보관함 인물') : null),
        draft.perSpeaker ? modelSelects(p) : null,
        h('div', { class: 'pcard-foot' },
          h('div', { class: 'grow' }),
          h('button', { type: 'button', class: 'btn btn--icon', tip: '아바타 바꾸기', 'aria-label': '아바타 바꾸기', onclick: () => {
            const set = AVATAR_SETS.find((s) => s.id === p.avatar.set)!;
            const next = p.avatar.variant + 1;
            p.avatar = { set: p.avatar.set, variant: next >= set.count ? set.first : next };
            paintCast();
          } }, icon(Shuffle, 18)),
          h('button', { type: 'button', class: 'btn btn--icon', tip: '이 사람만 다시 만들기', 'aria-label': '이 사람만 다시 만들기', onclick: () => regenerate(i) }, icon(RefreshCw, 18)),
          libBtn,
          h('button', { type: 'button', class: 'btn btn--icon', tip: '보관함에 저장', 'aria-label': '보관함에 저장', onclick: async () => {
            try {
              const { fromLibrary: _f, model: _m, effort: _e, ...rest } = p;
              const saved = await api.savePersona(rest as Persona);
              p.id = saved.id;
              library = await api.personas();
              toast(`${p.name} 님을 보관함에 저장했습니다.`);
            } catch (err) { toast((err as Error).message, 'error'); }
          } }, icon(Save, 18)),
          deleteButton(() => { draft.cast[i] = null; paintCast(); }))));
    });
    paintStart();
  }

  /* ---- 진행 설정 ---- */
  const models = status?.models ?? [];
  /** 슬라이더와 숫자 칸이 같은 값을 가리킨다. 슬라이더로 대강 잡고 숫자로 정확히 적는다. */
  function limitRow(opts: { min: number; max: number; sliderMax: number; unit: string; get: () => number; set: (v: number) => void;
    on: () => boolean; setOn: (v: boolean) => void }): HTMLElement {
    const clamp = (v: number) => Math.max(opts.min, Math.min(opts.max, Math.round(v) || opts.min));
    const range = h('input', { class: 'range', type: 'range', min: opts.min, max: opts.sliderMax, step: 1, 'aria-label': `${opts.unit} 슬라이더` });
    const num = h('input', { class: 'input', type: 'number', min: opts.min, max: opts.max, 'aria-label': `${opts.unit} 입력` });
    const row = h('div', { class: 'slider-row' });
    const sync = () => {
      const v = opts.get();
      range.value = String(Math.min(v, opts.sliderMax));
      num.value = String(v);
      range.style.setProperty('--p', `${((Math.min(v, opts.sliderMax) - opts.min) / (opts.sliderMax - opts.min)) * 100}%`);
      row.classList.toggle('is-off', !opts.on());
      paintStart();
    };
    range.addEventListener('input', () => { opts.set(clamp(Number(range.value))); sync(); });
    num.addEventListener('change', () => { opts.set(clamp(Number(num.value))); sync(); });
    row.append(toggle('', opts.on, (v) => { opts.setOn(v); sync(); }), range, num, h('span', { class: 'muted' }, opts.unit));
    queueMicrotask(sync);
    return row;
  }
  const turnsRow = limitRow({ min: 6, max: 200, sliderMax: 100, unit: '턴', get: () => draft.maxTurns, set: (v) => { draft.maxTurns = v; },
    on: () => draft.turnsOn, setOn: (v) => { draft.turnsOn = v; } });
  const minutesRow = limitRow({ min: 2, max: 120, sliderMax: 60, unit: '분', get: () => draft.maxMinutes, set: (v) => { draft.maxMinutes = v; },
    on: () => draft.minutesOn, setOn: (v) => { draft.minutesOn = v; } });
  const effortSel = h('select', { class: 'select', onchange: () => { draft.effort = effortSel.value; paintStart(); } });
  const paintEfforts = () => {
    const m = models.find((x) => x.id === draft.model) ?? models[0];
    if (m && !m.efforts.includes(draft.effort)) draft.effort = m.default_effort;
    clear(effortSel);
    (m?.efforts ?? []).forEach((e) => effortSel.append(h('option', { value: e, selected: draft.effort === e }, e)));
  };
  const modelSel = h('select', { class: 'select', onchange: () => { draft.model = modelSel.value; paintEfforts(); paintStart(); } },
    models.map((m) => h('option', { value: m.id, selected: draft.model === m.id }, m.price ? `${m.label} · 입력 ${fmtCost(m.price.in)} / 출력 ${fmtCost(m.price.out)}` : m.label)));
  paintEfforts();
  const searches = h('input', { class: 'input', type: 'number', min: 1, max: 5, value: draft.maxSearches, onchange: () => { draft.maxSearches = Math.max(1, Math.min(5, Number(searches.value) || 2)); persist(); } });
  const gap = h('input', { type: 'range', min: 0, max: 2, step: 0.25, value: draft.gapScale, class: 'range', oninput: () => { draft.gapScale = Number(gap.value); gap.style.setProperty('--p', `${draft.gapScale * 50}%`); gapNote.textContent = draft.gapScale === 0 ? '뜸 없음' : `${draft.gapScale}배`; persist(); } });
  gap.style.setProperty('--p', `${draft.gapScale * 50}%`);
  const gapNote = h('span', { class: 'muted small', style: 'display:block;margin-top:.5rem' }, draft.gapScale === 0 ? '뜸 없음' : `${draft.gapScale}배`);
  const hidden = draft.hiddenAgenda ?? status?.defaults.hidden_agenda ?? true;

  page.append(h('section', { class: 'block' },
    h('h2', { class: 'block-title' }, '진행 설정', h('small', null, '마지막에 쓴 설정을 기억합니다'),
      h('button', { type: 'button', class: 'btn', style: 'order:1;font-family:var(--font-body)', tip: '모든 설정을 처음 값으로 되돌립니다', onclick: () => {
        Object.assign(draft, structuredClone(DEFAULTS));
        try { localStorage.removeItem(STORE_KEY); } catch { /* 무시 */ }
        toast('설정을 처음 상태로 되돌렸습니다.');
        ctx.reload();
      } }, icon(RotateCcw, 16), '초기 설정으로')),
    h('div', { class: 'settings-grid' },
      field('진행 방식', seg([['mixed', '혼합'], ['free', '자유'], ['sequential', '순차']], () => draft.mode, (v) => { draft.mode = v; }),
        '혼합: 모두발언은 차례대로, 그 뒤는 말하고 싶은 사람이'),
      field('턴 수 제한', turnsRow, '슬라이더는 100턴까지, 숫자로는 200턴까지 적을 수 있습니다'),
      field('시간 제한', minutesRow, '실제로 말했다면 걸렸을 시간으로 잽니다. 둘 중 먼저 닿는 쪽에서 마무리합니다'),
      field('분위기', seg([['default', '기본'], ['humorous', '유머러스'], ['serious', '진지함'], ['creative', '창의적']], () => draft.tone, (v) => { draft.tone = v; }),
        '기본: 분위기에 대한 지시 없이 그대로 진행합니다'),
      field('발언 길이', seg([['auto', '자동'], ['short', '짧게'], ['normal', '보통'], ['long', '길게']], () => draft.length, (v) => { draft.length = v; }),
        '자동: 상황에 따라 짧게 받아치기도 하고 길게 풀어 말하기도 합니다'),
      field('출력 속도', seg([['slow', '느리게'], ['normal', '보통'], ['fast', '빠르게'], ['instant', '즉시']], () => draft.speed, (v) => { draft.speed = v; })),
      field('웹 검색', seg([['auto', '자동'], ['off', '끔']], () => draft.search, (v) => { draft.search = v; }),
        '자동: 참가자가 필요하다고 판단할 때만 스스로 검색합니다. 검색한 만큼 요금이 따로 듭니다')),
    h('details', { class: 'adv' },
      h('summary', null, icon(ChevronRight, 16), '고급 설정'),
      h('div', { class: 'settings-grid' },
        field('모델', modelSel, '참가자, 진행자, 연출자가 모두 이 모델을 씁니다. 요금은 100만 토큰당 원화입니다'),
        field('추론 노력', effortSel),
        field('화자별 모델', toggle('참가자마다 모델과 추론 노력을 따로 정하기', () => draft.perSpeaker, (v) => { draft.perSpeaker = v; paintCast(); }),
          '성능이 다른 AI를 비교할 때 씁니다. 캐시 할인이 줄어듭니다'),
        field('끼어들기', toggle('말을 끊고 끼어들 수 있음', () => draft.interjection, (v) => { draft.interjection = v; })),
        field('발언 사이 뜸', h('div', null, gap, gapNote)),
        field('발언당 검색 횟수', h('div', { class: 'inline-num' }, searches, h('span', { class: 'muted' }, '회'))),
        field('모델 배지', seg([['on', '보이기'], ['off', '숨기기'], ['blind', '블라인드']], () => draft.badge, (v) => { draft.badge = v; }),
          '블라인드: 토론이 끝난 뒤에 모델을 공개합니다'),
        field('끝난 뒤', toggle('요약 카드 만들기', () => draft.summary, (v) => { draft.summary = v; })),
        field('아바타 반응', toggle('모든 발언에 반응하기', () => draft.reactions === 'all', (v) => { draft.reactions = v ? 'all' : 'smart'; }),
          '끄면 개회와 마무리 발언에서는 반응을 따로 계산하지 않아 AI 호출이 줄어듭니다'),
        field('숨은 속내', toggle('참가자의 드러내지 않는 속내 쓰기', () => hidden, (v) => { draft.hiddenAgenda = v; }),
          status?.provider === 'pgpt' ? 'P-GPT에서는 다른 참가자가 알아챌 수 있습니다' : ''))),
    status?.provider === 'pgpt' ? h('div', { class: 'banner banner--info', style: 'margin-top:1.5rem' },
      'P-GPT는 대화 문맥을 서버에 보관합니다. 올린 문서와 토론 내용이 P-GPT 서버에 저장됩니다.') : null));

  /* ---- 시작 ---- */
  const startNote = h('span', { class: 'muted' });
  const startBtn = h('button', { type: 'button', class: 'btn btn--primary btn--lg', onclick: () => start() }, icon(Play, 20), '토론 시작');
  page.append(h('div', { class: 'start-bar' }, startNote, startBtn));

  function paintStart(): void {
    persist();
    const limits = [draft.turnsOn ? `${draft.maxTurns}턴` : '', draft.minutesOn ? `${draft.maxMinutes}분` : ''].filter(Boolean).join(' 또는 ');
    const model = models.find((m) => m.id === draft.model)?.label ?? '';
    startNote.textContent = [`참가자 ${draft.count}명${draft.moderator ? ' + 진행자' : ''}`, limits || '제한 없음', model ? `${model} · ${draft.effort}` : '']
      .filter(Boolean).join('  ·  ');
    startBtn.disabled = busy || !status?.ready;
  }

  async function start(): Promise<void> {
    if (!draft.topic.trim()) { toast('주제를 적어 주세요.', 'error'); topic.focus(); return; }
    if (!draft.turnsOn && !draft.minutesOn) { toast('턴 수와 시간 제한 가운데 하나는 켜야 합니다.', 'error'); return; }
    if (draft.cast.some((p) => !p) || draft.cast.length !== draft.count) {
      if (draft.cast.every((p) => !p)) {
        if (!(await generateAll())) return;
      } else {
        for (let i = 0; i < draft.count; i += 1) if (!draft.cast[i]) await regenerate(i);
        if (draft.cast.some((p) => !p)) return;
      }
    }
    startBtn.disabled = true;
    clear(startBtn);
    startBtn.append(icon(LoaderCircle, 20, 'spin'), '무대를 준비하는 중');
    try {
      const { id } = await api.startDebate({
        topic: draft.topic, concept: draft.concept, tone: draft.tone, materials: draft.materials.map((m) => ({ name: m.name, text: m.text })), urls: draft.urls,
        participants: draft.cast.map((p, i) => {
          const { fromLibrary: _f, ...rest } = p!;
          return { ...rest, id: `s${i + 1}`, model: draft.perSpeaker ? rest.model : undefined, effort: draft.perSpeaker ? rest.effort : undefined };
        }),
        moderator: draft.moderator, mode: draft.mode,
        max_turns: draft.turnsOn ? draft.maxTurns : null, max_minutes: draft.minutesOn ? draft.maxMinutes : null,
        length: draft.length, interjection: draft.interjection, speed: draft.speed, gap_scale: draft.gapScale,
        search: draft.search, max_searches: draft.maxSearches, model: draft.model || null, effort: draft.effort || null,
        badge: draft.badge, summary: draft.summary, reactions: draft.reactions, hidden_agenda: draft.hiddenAgenda,
        prep_cost: draft.prepCost,
      });
      draft.prepCost = 0;
      ctx.go(`#/stage/${id}`);
    } catch (err) {
      toast((err as Error).message, 'error');
      clear(startBtn);
      startBtn.append(icon(Play, 20), '토론 시작');
      paintStart();
    }
  }

  setCount(draft.count);
  api.personas().then((list) => { library = list; }).catch(() => undefined);
  return () => { document.removeEventListener('click', onDocClick); closeMenu(); };
}
