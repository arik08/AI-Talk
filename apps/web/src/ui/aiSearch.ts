import { Sparkles } from 'lucide';
import { api } from '../api';
import type { Persona } from '../types';
import { clear, h, icon, toast } from './dom';

/** AI가 추천한 인물 한 명: 보관함의 id와 추천하는 까닭 한 줄. */
export interface Pick { id: string; why: string }

const TEXT_HINT = '이름, 직함, 분야로 찾기';
const AI_HINT = '찾는 사람을 말로 적고 Enter. 예) 원전에 찬성할 과학자';

/**
 * 인물 검색창. 안쪽 왼편의 반짝이 버튼을 켜면 AI 추천으로 바뀐다.
 * - 꺼져 있을 때: 글자를 칠 때마다 onText로 찾는 말을 넘긴다 (이름·직함·분야에서 찾기).
 * - 켜져 있을 때: 찾는 사람을 말로 적고 Enter를 누르면 AI에게 묻고, 추천을 잘 맞는 순서대로 onPicks로 넘긴다.
 *   글자를 칠 때마다 묻지 않는다: 물을 때마다 요금이 든다. 칸을 비우거나 버튼을 끄면 onPicks(null)로 추천을 걷는다.
 */
export function aiSearch(opts: {
  onText: (query: string) => void;
  onPicks: (picks: Pick[] | null) => void;
  onCost?: (cost: number) => void;
}): { root: HTMLElement; input: HTMLInputElement } {
  let on = false;
  let busy = false;
  let asked = 0;   // 늦게 돌아온 예전 답을 버리려고 센다
  const input = h('input', { class: 'input', type: 'search', placeholder: TEXT_HINT, 'aria-label': '인물 찾기' });
  const btn = h('button', { type: 'button', class: 'ai-toggle' });
  const root = h('div', { class: 'ai-search' }, btn, input);

  const paint = () => {
    const label = busy ? 'AI가 고르는 중' : on ? 'AI 추천 끄기' : 'AI 추천: 찾는 사람을 말로 적으면 AI가 골라 줍니다';
    clear(btn);
    btn.append(busy ? h('span', { class: 'ai-spin', 'aria-hidden': 'true' }) : icon(Sparkles, 16));
    btn.classList.toggle('is-on', on);
    btn.dataset.tip = label;
    btn.setAttribute('aria-label', label);
    btn.setAttribute('aria-pressed', String(on));
    input.placeholder = on ? AI_HINT : TEXT_HINT;
    root.classList.toggle('is-ai', on);
  };

  const ask = async () => {
    const query = input.value.trim();
    if (!query || busy) return;
    const mine = (asked += 1);
    busy = true;
    paint();
    try {
      const res = await api.suggestPersonas(query);
      if (mine !== asked || !on) return;   // 그사이에 껐거나 칸을 비웠다
      opts.onCost?.(res.cost ?? 0);
      opts.onPicks(res.picks);
      if (!res.picks.length) toast('어울리는 인물을 찾지 못했습니다. 다르게 적어 보세요.');
    } catch (err) {
      if (mine === asked) toast((err as Error).message, 'error');
    } finally {
      if (mine === asked) { busy = false; paint(); }
    }
  };

  input.addEventListener('input', () => {
    if (!on) { opts.onText(input.value); return; }
    if (!input.value.trim()) { asked += 1; busy = false; paint(); opts.onPicks(null); }   // 칸을 비우면 추천을 걷는다
  });
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.isComposing || !on) return;
    e.preventDefault();
    void ask();
  });
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    on = !on;
    asked += 1;
    busy = false;
    if (on) {
      opts.onText('');   // 글자로 찾던 것은 풀고, 적어 둔 말이 있으면 바로 묻는다
      if (input.value.trim()) void ask();
    } else {
      opts.onPicks(null);
      opts.onText(input.value);
    }
    paint();
    input.focus();
  });
  paint();
  return { root, input };
}

/** 찾는 말이 이 인물의 이름·직함·분야·태그에 들어 있는지. */
export function matchesText(p: Persona, query: string): boolean {
  const q = query.trim().toLowerCase();
  return !q || [p.name, p.title, p.expertise, ...(p.tags ?? [])].join(' ').toLowerCase().includes(q);
}

/**
 * 목록의 줄(rows[i]는 people[i]의 줄)을 찾는 말이나 AI 추천에 맞춰 보이고 숨긴다. 보이는 줄의 수를 돌려준다.
 * 추천이 있으면 추천한 순서대로 앞에 놓고, 줄의 둘째 줄(.muted)에 직함 대신 추천하는 까닭을 적는다.
 * end: 줄들이 그 앞에 놓여야 하는 요소. 줄이 부모의 마지막 자식들이면 null.
 */
export function arrangeRows(people: Persona[], rows: HTMLElement[], parent: HTMLElement, end: Node | null, query: string, picks: Pick[] | null): number {
  const rank = new Map((picks ?? []).map((p, i) => [p.id, i]));
  let shown = 0;
  people.forEach((p, i) => {
    const hit = picks ? rank.has(p.id!) : matchesText(p, query);
    rows[i].hidden = !hit;
    if (hit) shown += 1;
    const sub = rows[i].querySelector('.muted');
    if (sub) sub.textContent = (picks && hit && picks[rank.get(p.id!)!].why) || p.title;
    rows[i].classList.toggle('is-pick', !!picks && hit);
  });
  const order = people.map((_, i) => i);
  if (picks) order.sort((a, b) => (rank.get(people[a].id!) ?? 1e6) - (rank.get(people[b].id!) ?? 1e6) || a - b);
  for (const i of order) parent.insertBefore(rows[i], end);
  return shown;
}
