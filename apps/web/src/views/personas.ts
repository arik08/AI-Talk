import { Copy, Download, LoaderCircle, Pencil, Plus, Sparkles, Upload, X } from 'lucide';
import { api } from '../api';
import { AVATAR_SETS, FIGURES, createAvatar, normalizeSpec, setAvatar } from '../avatar/avatar';
import type { AppContext } from '../main';
import { MOOD_LABEL, PALETTE, type AvatarSet, type Mood, type Persona } from '../types';
import { clear, deleteButton, h, icon, safeColor, toast } from '../ui/dom';

const MOODS = Object.keys(MOOD_LABEL) as Mood[];

function blank(): Persona {
  return {
    name: '', title: '', expertise: '', personality: '', speech: '', viewpoint: '', claims: [], concede: '', hidden: '',
    color: PALETTE[Math.floor(Math.random() * PALETTE.length)], avatar: { set: 'bot', variant: Math.floor(Math.random() * 6) }, tags: [],
  };
}

export function mountPersonas(root: HTMLElement, _ctx: AppContext): () => void {
  let people: Persona[] = [];
  let query = '';
  let tag = '';
  let drawer: HTMLElement | null = null;

  const grid = h('div', { class: 'cast-grid' });
  const tagBar = h('div', { class: 'row' });
  const search = h('input', { class: 'input', type: 'search', placeholder: '이름, 직함, 분야로 찾기', oninput: () => { query = search.value.trim().toLowerCase(); paint(); } });
  const fileInput = h('input', { type: 'file', class: 'hidden', accept: '.json' });
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      const { added } = await api.importPersonas(Array.isArray(data) ? data : [data]);
      toast(`${added}명을 가져왔습니다.`);
      await load();
    } catch (err) {
      toast(`가져오지 못했습니다: ${(err as Error).message}`, 'error');
    }
    fileInput.value = '';
  });

  root.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' },
      h('div', null, h('h1', null, '페르소나 보관함'), h('p', null, '여기 둔 인물은 어느 토론에나 불러 쓸 수 있습니다. 입장은 토론마다 주제에 맞춰 새로 정해집니다. 실존 인물과 역사 속 인물은 널리 알려진 생각과 말투를 본뜬 AI의 재현이며, 실제 그 사람의 발언이 아닙니다.')),
      h('div', { class: 'row' },
        h('button', { type: 'button', class: 'btn', onclick: () => fileInput.click() }, icon(Upload, 18), '가져오기'), fileInput,
        h('button', { type: 'button', class: 'btn', onclick: exportAll }, icon(Download, 18), '내보내기'),
        h('button', { type: 'button', class: 'btn btn--primary', onclick: () => openEditor(blank()) }, icon(Plus, 18), '새로 만들기'))),
    h('div', { class: 'toolbar' }, search, tagBar),
    grid));

  function exportAll(): void {
    const blob = new Blob([JSON.stringify(people, null, 1)], { type: 'application/json' });
    const a = h('a', { href: URL.createObjectURL(blob), download: 'ai-talk-personas.json' });
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function paint(): void {
    const tags = Array.from(new Set(people.flatMap((p) => p.tags ?? []))).sort();
    clear(tagBar);
    tags.forEach((t) => tagBar.append(h('button', { type: 'button', class: `chip${tag === t ? ' is-on' : ''}`, onclick: () => { tag = tag === t ? '' : t; paint(); } }, t)));
    const shown = people.filter((p) => (!tag || (p.tags ?? []).includes(tag))
      && (!query || [p.name, p.title, p.expertise, ...(p.tags ?? [])].join(' ').toLowerCase().includes(query)));
    clear(grid);
    if (!shown.length) {
      grid.append(h('div', { class: 'empty', style: 'grid-column:1/-1' }, h('h3', null, people.length ? '찾는 인물이 없습니다' : '보관함이 비어 있습니다'),
        h('p', null, '"새로 만들기"를 누르고 한 줄 설명만 적으면 AI가 나머지를 채웁니다.')));
      return;
    }
    shown.forEach((p, i) => {
      const color = safeColor(p.color);
      const av = createAvatar(p.avatar, color, 72);
      setAvatar(av, { state: 'listening' });
      let k = 0;
      const card = h('div', { class: 'pcard', style: `--c:${color};animation-delay:${Math.min(i, 12) * 40}ms` },
        h('div', { class: 'pcard-head' },
          h('button', { type: 'button', class: 'avatar-btn', tip: '눌러서 감정 움직임 미리 보기', 'aria-label': '감정 움직임 미리 보기',
            onclick: () => { k += 1; setAvatar(av, { mood: MOODS[k % MOODS.length], state: k % 2 ? 'speaking' : 'listening' }); } }, av),
          h('div', { class: 'grow' }, h('div', { class: 'pcard-name' }, p.name), h('div', { class: 'pcard-title' }, p.title))),
        p.personality ? h('div', { class: 'pcard-view' }, p.personality) : null,
        p.speech ? h('div', { class: 'muted small' }, `말투: ${p.speech}`) : null,
        h('div', { class: 'pcard-meta' }, p.expertise ? h('span', { class: 'chip chip--c' }, p.expertise) : null,
          (p.tags ?? []).map((t) => h('span', { class: 'chip' }, t))),
        h('div', { class: 'pcard-foot' }, h('div', { class: 'grow' }),
          h('button', { type: 'button', class: 'btn btn--icon', tip: '고치기', 'aria-label': '고치기', onclick: () => openEditor({ ...p }) }, icon(Pencil, 18)),
          h('button', { type: 'button', class: 'btn btn--icon', tip: '복제', 'aria-label': '복제', onclick: async () => {
            const { id: _id, ...rest } = p;
            await api.savePersona({ ...rest, name: `${p.name} (사본)` });
            await load();
          } }, icon(Copy, 18)),
          deleteButton(async () => {
            try { await api.deletePersona(p.id!); await load(); } catch (err) { toast((err as Error).message, 'error'); }
          })));
      grid.append(card);
    });
  }

  async function load(): Promise<void> {
    try {
      people = await api.personas();
    } catch (err) {
      toast((err as Error).message, 'error');
    }
    paint();
  }

  /* ---------- 편집 서랍 ---------- */
  function closeEditor(): void { drawer?.remove(); drawer = null; }

  function openEditor(p: Persona): void {
    closeEditor();
    p.avatar = normalizeSpec(p.avatar);
    p.color = safeColor(p.color, PALETTE[0]);
    let mood: Mood = 'calm';
    let talking = false;
    const preview = h('div');
    const pickGrid = h('div', { class: 'av-grid' });
    const setTabs = h('div', { class: 'seg' });
    const setNote = h('div', { class: 'muted small' });
    const moodRow = h('div', { class: 'row' });
    const swatches = h('div', { class: 'swatches' });

    const paintAvatar = () => {
      const av = createAvatar(p.avatar, p.color, 120);
      setAvatar(av, { mood, state: talking ? 'speaking' : 'listening' });
      preview.replaceChildren(av);
      clear(setTabs);
      AVATAR_SETS.forEach((s) => setTabs.append(h('button', { type: 'button', class: p.avatar.set === s.id ? 'is-on' : '',
        onclick: () => { p.avatar = { set: s.id as AvatarSet, variant: s.first }; paintAvatar(); } }, s.label)));
      const set = AVATAR_SETS.find((s) => s.id === p.avatar.set)!;
      setNote.textContent = set.note;
      clear(pickGrid);
      for (let v = set.first; v < set.count; v += 1) {
        const small = createAvatar({ set: set.id, variant: v }, p.color, 44);
        small.classList.add('is-still');
        pickGrid.append(h('button', { type: 'button', class: `av-pick${p.avatar.variant === v ? ' is-on' : ''}`, 'aria-label': set.id === 'figure' ? FIGURES[v].name : `${set.label} ${v + 1}`, tip: set.id === 'figure' ? FIGURES[v].name : null,
          onclick: () => { p.avatar = { set: set.id, variant: v }; paintAvatar(); } }, small));
      }
      clear(moodRow);
      MOODS.forEach((m) => moodRow.append(h('button', { type: 'button', class: `chip${mood === m ? ' is-on' : ''}`, onclick: () => { mood = m; paintAvatar(); } }, MOOD_LABEL[m])));
      moodRow.append(h('button', { type: 'button', class: `chip${talking ? ' is-on' : ''}`, onclick: () => { talking = !talking; paintAvatar(); } }, '말하는 중'));
      clear(swatches);
      PALETTE.forEach((c) => swatches.append(h('button', { type: 'button', class: `swatch${p.color === c ? ' is-on' : ''}`, style: `--c:${c}`, 'aria-label': `색 ${c}`,
        onclick: () => { p.color = c; paintAvatar(); } })));
    };

    const text = (key: keyof Persona, label: string, placeholder = '', rows = 0) => {
      const el = rows
        ? h('textarea', { class: 'textarea', rows, placeholder, oninput: () => { (p as any)[key] = el.value; } })
        : h('input', { class: 'input', placeholder, oninput: () => { (p as any)[key] = el.value; } });
      el.value = String(p[key] ?? '');
      el.dataset.key = String(key);
      return h('div', null, h('div', { class: 'field-label' }, label), el);
    };
    const claims = h('textarea', { class: 'textarea', rows: 3, placeholder: '한 줄에 하나씩', oninput: () => { p.claims = claims.value.split('\n').map((s) => s.trim()).filter(Boolean); } });
    claims.value = (p.claims ?? []).join('\n');
    const tags = h('input', { class: 'input', placeholder: '쉼표로 구분. 예) 제조, 현장', oninput: () => { p.tags = tags.value.split(',').map((s) => s.trim()).filter(Boolean); } });
    tags.value = (p.tags ?? []).join(', ');

    const hint = h('input', { class: 'input', placeholder: '예) 원칙을 중시하는 30년 차 설비 엔지니어' });
    const draftBtn = h('button', { type: 'button', class: 'btn', onclick: async () => {
      if (!hint.value.trim()) { hint.focus(); return; }
      draftBtn.disabled = true;
      draftBtn.replaceChildren(icon(LoaderCircle, 18, 'spin'), '만드는 중');
      try {
        const d = await api.draftPersona(hint.value);
        Object.assign(p, { ...d, color: p.color, avatar: p.avatar, id: p.id, tags: p.tags });
        openEditor(p);
      } catch (err) {
        toast((err as Error).message, 'error');
        draftBtn.disabled = false;
        draftBtn.replaceChildren(icon(Sparkles, 18), '초안 만들기');
      }
    } }, icon(Sparkles, 18), '초안 만들기');

    const save = async () => {
      if (!p.name.trim()) { toast('이름을 적어 주세요.', 'error'); return; }
      try {
        await api.savePersona(p);
        closeEditor();
        await load();
        toast(`${p.name} 님을 저장했습니다.`);
      } catch (err) { toast((err as Error).message, 'error'); }
    };

    drawer = h('div', null,
      h('div', { class: 'drawer-back', onclick: closeEditor }),
      h('div', { class: 'drawer', role: 'dialog', 'aria-label': '페르소나 편집' },
        h('div', { class: 'drawer-head' }, h('h2', null, p.id ? '인물 고치기' : '새 인물'),
          h('button', { type: 'button', class: 'btn btn--icon', 'aria-label': '닫기', tip: '닫기', onclick: closeEditor }, icon(X, 18))),
        h('div', { class: 'drawer-body' },
          h('div', null, h('div', { class: 'field-label' }, '한 줄 설명으로 초안 만들기'), h('div', { class: 'row', style: 'flex-wrap:nowrap' }, hint, draftBtn)),
          h('div', { class: 'av-stage' }, preview, h('div', { class: 'grow', style: 'display:flex;flex-direction:column;gap:.625rem' },
            h('div', { class: 'field-label', style: 'margin:0' }, '감정 움직임 미리 보기'), moodRow, swatches)),
          h('div', null, h('div', { class: 'field-label' }, '아바타'), setTabs, h('div', { style: 'margin:.5rem 0' }, setNote), pickGrid),
          text('name', '이름'), text('title', '한 줄 소개', '직함과 배경'), text('expertise', '전문 분야'),
          text('personality', '성격과 토론 스타일', '공격적인지 신중한지, 논리·사례·감정 중 무엇에 기대는지', 2),
          text('speech', '말투와 말버릇', "예) 짧게 끊어 말함. '솔직히'를 자주 씀", 2),
          text('viewpoint', '평소의 관점', '토론마다 주제에 맞춰 새로 정해집니다', 2),
          h('div', null, h('div', { class: 'field-label' }, '자주 하는 주장'), claims),
          text('concede', '양보할 수 있는 지점'), text('hidden', '숨은 속내', '남에게 드러내지 않는 이해관계'),
          h('div', null, h('div', { class: 'field-label' }, '태그'), tags)),
        h('div', { class: 'drawer-foot' },
          h('button', { type: 'button', class: 'btn', onclick: closeEditor }, '취소'),
          h('button', { type: 'button', class: 'btn btn--primary', onclick: save }, '저장'))));
    document.body.append(drawer);
    paintAvatar();
  }

  const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeEditor(); };
  document.addEventListener('keydown', onKey);
  load();
  return () => { document.removeEventListener('keydown', onKey); closeEditor(); };
}
