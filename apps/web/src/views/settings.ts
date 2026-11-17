import { RefreshCw } from 'lucide';
import { AVATAR_SETS, createAvatar, setAvatar } from '../avatar/avatar';
import type { AppContext } from '../main';
import { MOOD_LABEL, PALETTE, type Mood } from '../types';
import { api } from '../api';
import { clear, fmtCost, h, icon, put, toast } from '../ui/dom';

const PROVIDERS: [string, string, string][] = [
  ['claude', 'Claude', '집에서 개발할 때. ANTHROPIC_API_KEY가 필요합니다'],
  ['pgpt', 'P-GPT', '회사 OA망에서. PGPT_API_KEY와 PGPT_EMPNO가 필요합니다'],
  ['mock', '시험용', 'AI를 부르지 않고 화면만 확인합니다. 요금이 들지 않습니다'],
];
const MOODS = Object.keys(MOOD_LABEL) as Mood[];

export function mountSettings(root: HTMLElement, ctx: AppContext): () => void {
  const body = h('div');
  root.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', null, h('h1', null, '설정'), h('p', null, 'AI 연결 상태와 쓸 수 있는 모델, 아바타 움직임을 확인합니다.')),
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'btn', onclick: async () => { await ctx.refreshStatus(); paint(); } }, icon(RefreshCw, 18), '다시 확인'))),
    body));

  let switching = false;
  async function choose(name: string): Promise<void> {
    switching = true;
    paint();
    try {
      await api.setProvider(name);
      await ctx.refreshStatus();
      toast('쓸 AI를 바꿨습니다.');
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      switching = false;
      paint();
    }
  }

  function paint(): void {
    const s = ctx.status;
    clear(body);
    put(body,
      h('div', { class: 'panel frame card-pad' },
        h('h2', { class: 'block-title', style: 'margin-bottom:.75rem' }, 'AI 연결'),
        !s ? h('div', { class: 'banner' }, '서버에 연결하지 못했습니다.') : h('div', null,
          s.ready ? null : h('div', { class: 'banner' }, s.message),
          h('table', { class: 'table' },
            h('thead', null, h('tr', null, h('th', null, 'AI'), h('th', null, '쓰임'), h('th', null, '상태'), h('th', null, ''))),
            h('tbody', null, PROVIDERS.map(([key, name, note]) => {
              const row = s.providers?.find((r) => r.name === key);
              const active = row ? row.active : s.provider === key;
              const ready = row ? row.ready : active && s.ready;
              return h('tr', null,
                h('td', null, h('b', null, name), ' ', h('span', { class: 'muted small' }, key)),
                h('td', { class: 'muted' }, note),
                h('td', null, ready ? h('span', { class: 'chip chip--c', style: '--c:#2FC23A' }, '준비됨')
                  : h('span', { class: 'chip chip--ember', tip: row?.message || '키가 없습니다' }, '키 없음')),
                h('td', { style: 'text-align:right' }, active
                  ? h('span', { class: 'chip is-on' }, '사용 중')
                  : h('button', { type: 'button', class: 'btn', disabled: !ready || switching, onclick: () => choose(key) }, '이걸로 바꾸기')));
            }))),
          h('p', { class: 'muted small', style: 'margin-top:.875rem' },
            '여기서 고른 AI를 기억해 다음에 켤 때도 그대로 씁니다. 진행 중인 토론은 시작할 때의 AI로 끝까지 갑니다. 키는 프로젝트 폴더의 ',
            h('code', null, '.env'), ' 파일에 두며 화면에 보여 주지 않습니다.'),
          s.ready && s.message ? h('p', { class: 'muted small' }, s.message) : null)),
      s ? h('div', { class: 'panel card-pad', style: 'margin-top:1.5rem' },
        h('h2', { class: 'block-title', style: 'margin-bottom:.75rem' }, '다른 PC에서 접속', h('small', null, '같은 망(회사 내부망 등)에 있는 사람과 함께 봅니다')),
        s.network?.shared
          ? h('div', null,
            h('p', null, '같은 망의 다른 PC에서 아래 주소로 들어올 수 있습니다.'),
            h('div', { class: 'row', style: 'margin:.625rem 0' }, (s.network.addresses.length ? s.network.addresses : ['이 PC의 IP']).map((ip) =>
              h('code', null, `http://${ip}:${s.network!.port}`))),
            s.network.code
              ? h('p', { class: 'muted small' }, '다른 PC에서 들어오면 접속 코드를 묻습니다.')
              : h('div', { class: 'banner', style: 'margin:.75rem 0 0' }, '접속 코드가 없습니다. 같은 망의 누구나 들어와 내 AI 키로 토론을 돌리고 기록을 지울 수 있습니다. .env에 AITALK_ACCESS_CODE를 넣으면 코드를 아는 사람만 들어옵니다.'))
          : h('p', { class: 'muted' }, '지금은 이 PC에서만 접속됩니다 (', h('code', null, '.env'), '에 ', h('code', null, 'AITALK_HOST=127.0.0.1'),
            '이 있습니다). 그 줄을 지우고 ', h('code', null, 'ai-talk.bat'), '으로 다시 켜면 다른 PC에서도 들어올 수 있습니다.')) : null,
      s?.models.length ? h('div', { class: 'panel card-pad', style: 'margin-top:1.5rem' },
        h('h2', { class: 'block-title', style: 'margin-bottom:.75rem' }, '쓸 수 있는 모델', h('small', null, '요금은 100만 토큰당 원화. 공개 요금표에 1달러 1,350원을 곱한 값')),
        h('table', { class: 'table' },
          h('thead', null, h('tr', null, h('th', null, '모델'), h('th', null, '입력'), h('th', null, '캐시 읽기'), h('th', null, '출력'), h('th', null, '추론 노력'), h('th', null, ''))),
          h('tbody', null, s.models.map((m) => h('tr', null,
            h('td', null, m.label, ' ', h('span', { class: 'muted small' }, m.id)),
            h('td', null, m.price ? fmtCost(m.price.in) : '-'), h('td', null, m.price ? fmtCost(m.price.cached) : '-'), h('td', null, m.price ? fmtCost(m.price.out) : '-'),
            h('td', { class: 'muted' }, m.efforts.join(', ')),
            h('td', null, m.id === s.defaults.model ? h('span', { class: 'chip chip--c', style: '--c:#E8C170' }, `기본 · ${s.defaults.effort}`) : (m.note ? h('span', { class: 'muted small' }, m.note) : ''))))))) : null,
      h('div', { class: 'panel card-pad', style: 'margin-top:1.5rem' },
        h('h2', { class: 'block-title', style: 'margin-bottom:.25rem' }, '아바타 움직임', h('small', null, '세트마다 감정 8가지를 자기 방식으로 표현합니다')),
        gallery()));
  }

  function gallery(): HTMLElement {
    let talking = false;
    const wrap = h('div');
    const draw = () => {
      clear(wrap);
      wrap.append(h('div', { class: 'row', style: 'margin:.75rem 0 1rem' },
        h('button', { type: 'button', class: `chip${talking ? ' is-on' : ''}`, onclick: () => { talking = !talking; draw(); } }, talking ? '말하는 중' : '듣는 중'),
        h('span', { class: 'muted small' }, '눌러서 말할 때와 들을 때를 바꿔 봅니다')));
      const table = h('table', { class: 'table' },
        h('thead', null, h('tr', null, h('th', null, '세트'), MOODS.map((m) => h('th', { style: 'text-align:center' }, MOOD_LABEL[m])))),
        h('tbody', null, AVATAR_SETS.map((set, row) => h('tr', null,
          h('td', null, set.label),
          MOODS.map((m, col) => {
            const av = createAvatar({ set: set.id, variant: set.first + ((col + row) % (set.count - set.first)) }, PALETTE[(col + row * 2) % PALETTE.length], 64);
            setAvatar(av, { mood: m, state: talking ? 'speaking' : 'listening' });
            return h('td', { style: 'text-align:center;padding:.875rem .25rem' }, av);
          })))));
      wrap.append(h('div', { style: 'overflow-x:auto' }, table));
    };
    draw();
    return wrap;
  }

  paint();
  if (!ctx.status) ctx.refreshStatus().then(paint);
  return () => undefined;
}
