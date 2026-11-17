import {
  BookOpen, Brain, Coins, Copy, FileText, Flag, Hourglass, Link, ListOrdered, LoaderCircle, Megaphone, Pause, Play, Rewind,
  Search, Send, SkipForward, TriangleAlert, Zap, type IconNode,
} from 'lucide';
import { api } from '../api';
import { createAvatar, setAvatar } from '../avatar/avatar';
import { copyText, recordToMarkdown } from '../export';
import type { AppContext } from '../main';
import { INTENT_LABEL, MOOD_LABEL, TONE_LABEL, type DebateEvent, type DebateRecord, type Mood, type Persona } from '../types';
import { clear, fmtCost, fmtTime, h, icon, put, safeColor, toast, USD_KRW } from '../ui/dom';

interface Seat { persona: Persona; tile: HTMLElement; av: HTMLElement; urge: HTMLElement; status: HTMLElement; badge: HTMLElement }
interface Card { root: HTMLElement; text: HTMLElement; body: HTMLElement; av: HTMLElement; speaker: string; cut: boolean; started: boolean }

const SPEEDS: [string, string][] = [['slow', '느리게'], ['normal', '보통'], ['fast', '빠르게'], ['instant', '즉시']];
const CPS: Record<string, number> = { slow: 8, normal: 14, fast: 26 };   // 서버가 글자를 내보내는 속도와 같다

export function mountStage(root: HTMLElement, id: string, ctx: AppContext): () => void {
  const seats = new Map<string, Seat>();
  const cards = new Map<number, Card>();
  const sources = new Map<string, string>();
  let record: DebateRecord | null = null;
  let stream: EventSource | null = null;
  let lastIndex = -1;
  let speaking: string | null = null;
  let spotHot = false;
  let lastSpeech: { speaker: string; cut: boolean } | null = null;
  let state = 'running';
  let badgeMode = 'on';
  let speed = 'normal';
  let disposed = false;
  let stick = true;
  let writingMinutes = false;
  let minutesEl: HTMLElement | null = null;
  let costEl: HTMLElement | null = null;
  // 비용: 토론 중에는 사용량 이벤트로, 끝난 뒤에는 저장된 기록과 회의록 응답으로 채운다
  const money = { cost: 0, parts: {} as Record<string, number>, searches: 0, rate: ctx.status?.pricing?.usd_krw ?? USD_KRW, searchUsd: ctx.status?.pricing?.search_usd ?? 0.01 };
  // 다시 보기
  let replaying = false;
  let replayTimer = 0;
  let replayIndex = 0;
  let replayPaused = false;
  let replayRate = 1;

  /* ---------- 뼈대: 왼쪽에 대화, 오른쪽에 참가자 ---------- */
  const phaseChip = h('div', { class: 'phase-chip' }, h('i'), h('span', null, '준비'));
  const topic = h('h1', { class: 'stage-topic' }, '');
  const clockTurn = h('b', null, '0');
  const clockTime = h('b', null, '00:00');
  const clockCost = h('b', null, '0원');
  const sideBtn = h('button', { type: 'button', class: 'btn btn--icon', tip: '자료·출처·사용량 패널', 'aria-label': '옆 패널 열고 닫기' }, icon(BookOpen, 18));
  const cast = h('aside', { class: 'cast', 'aria-label': '참가자' });
  const spotlight = h('div', { class: 'spotlight' });
  const inner = h('div', { class: 'transcript-inner' });
  const transcript = h('div', { class: 'transcript' }, inner);
  const sideBody = h('div', { class: 'side-body' });
  const tabs = h('div', { class: 'side-tabs' });
  const side = h('aside', { class: 'side is-closed' }, tabs, sideBody);
  const fill = h('div', { class: 'track-fill' });
  const head = h('div', { class: 'track-head', style: 'left:0' });
  const track = h('div', { class: 'track' }, fill, head);
  const controls = h('div', { class: 'controls' });
  const embers = h('div', { class: 'embers' }, Array.from({ length: 14 }, () =>
    h('i', { style: `left:${(Math.random() * 100).toFixed(1)}%;--dx:${(Math.random() * 80 - 40).toFixed(0)}px;animation-duration:${(9 + Math.random() * 10).toFixed(1)}s;animation-delay:${(-Math.random() * 16).toFixed(1)}s` })));
  const stage = h('section', { class: 'stage' }, embers,
    h('header', { class: 'stage-head' }, phaseChip, topic,
      h('div', { class: 'clock' },
        h('span', { tip: '진행한 턴' }, icon(ListOrdered, 16), clockTurn),
        h('span', { tip: '토론 시계: 실제로 말했다면 걸렸을 시간' }, icon(Hourglass, 16), clockTime),
        h('span', { tip: '지금까지 든 예상 비용: 토큰 요금 + 웹 검색 요금' }, icon(Coins, 16), clockCost), sideBtn)),
    h('div', { class: 'stage-body' }, transcript, side, cast),
    h('footer', { class: 'dock' }, h('div', { class: 'timeline' }, track), controls));
  root.append(stage);

  transcript.addEventListener('scroll', () => {
    stick = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 120;
  });
  const follow = () => { if (stick) transcript.scrollTop = transcript.scrollHeight; };
  sideBtn.addEventListener('click', () => { side.classList.toggle('is-closed'); if (!side.classList.contains('is-closed')) paintSide(); });

  /* ---------- 옆 패널 ---------- */
  let tab: 'usage' | 'sources' | 'materials' = 'usage';
  let usage: any = null;
  let briefing = '';
  function paintSide(): void {
    clear(tabs);
    ([['usage', '사용량'], ['sources', '출처'], ['materials', '자료']] as const).forEach(([key, label]) =>
      tabs.append(h('button', { type: 'button', class: tab === key ? 'is-on' : '', onclick: () => { tab = key; paintSide(); } }, label)));
    clear(sideBody);
    if (tab === 'usage') {
      if (!usage) { sideBody.append(h('p', { class: 'muted' }, '아직 사용량이 없습니다.')); return; }
      const t = usage.total;
      const rate = Math.round((usage.cache_rate ?? 0) * 100);
      sideBody.append(
        h('h4', null, `캐시 적중률 ${rate}%`), h('div', { class: 'meter' }, h('i', { style: `width:${rate}%` })),
        h('div', { class: 'kv' },
          h('span', null, '새로 읽은 입력'), h('span', null, `${t.input.toLocaleString()} 토큰`),
          h('span', null, '캐시에서 읽은 입력'), h('span', null, `${t.cached.toLocaleString()} 토큰`),
          h('span', null, '캐시에 쓴 입력'), h('span', null, `${t.cache_write.toLocaleString()} 토큰`),
          h('span', null, '출력'), h('span', null, `${t.output.toLocaleString()} 토큰`),
          h('span', null, '웹 검색'), h('span', null, `${Number(t.searches ?? 0).toLocaleString()}건`),
          h('span', null, '예상 비용'), h('span', null, fmtCost(Number(usage.cost ?? 0), money.rate)),
          h('span', null, 'AI 호출'), h('span', null, (() => {
            const calls = usage.calls ?? {};
            const director = calls.director ?? 0;
            const total = Object.values(calls).reduce((a: number, b: any) => a + Number(b), 0);
            return `발언 ${total - director}번 · 연출자 ${director}번`;
          })())),
        h('h4', { style: 'margin-top:1.25rem' }, '화자별 출력'),
        h('div', { class: 'kv' }, Object.entries(usage.by ?? {}).flatMap(([who, u]: [string, any]) => [
          h('span', null, who === 'director' ? '연출자(안 보임)' : seats.get(who)?.persona.name ?? who),
          h('span', null, `${u.output.toLocaleString()} 토큰`)])),
        h('p', { class: 'muted small', style: 'margin-top:1rem' }, `측정된 토큰 수와 검색 건수에 공개 단가를 곱한 값입니다. 웹 검색은 건당 ${fmtCost(money.searchUsd, money.rate)}, 1달러 ${money.rate.toLocaleString()}원으로 계산했습니다.`));
    } else if (tab === 'sources') {
      if (!sources.size) { sideBody.append(h('p', { class: 'muted' }, '웹에서 찾은 출처가 없습니다.')); return; }
      sideBody.append(h('div', { class: 'src-list' }, Array.from(sources, ([url, title]) =>
        h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, title || url))));
    } else {
      const mats = record?.config.materials ?? [];
      const concept = record?.config.concept;
      const tone = record?.config.tone && record.config.tone !== 'default' ? TONE_LABEL[record.config.tone] : '';
      if (!mats.length && !briefing && !concept && !tone) { sideBody.append(h('p', { class: 'muted' }, '붙인 자료가 없습니다.')); return; }
      if (tone) sideBody.append(h('h4', null, '분위기'), h('div', { class: 'brief', style: 'margin-bottom:1rem' }, tone));
      if (concept) sideBody.append(h('h4', null, '설정과 분위기'), h('div', { class: 'brief', style: 'margin-bottom:1rem' }, concept));
      if (mats.length) sideBody.append(h('h4', null, '올린 문서'), h('div', { class: 'kv', style: 'margin-bottom:1rem' },
        mats.flatMap((m: any) => [h('span', null, m.name), h('span', null, `${Number(m.chars).toLocaleString()}자`)])));
      if (briefing) sideBody.append(h('h4', null, '진행자의 사전 조사'), h('div', { class: 'brief' }, briefing));
    }
  }

  /* ---------- 참가자 자리 ---------- */
  function modelLabel(modelId: string, effort: string): string {
    const label = ctx.status?.models.find((m) => m.id === modelId)?.label ?? modelId;
    return `${label.replace(/^Claude /, '')} · ${effort}`;
  }

  function buildCast(config: any, moderator: Persona | null): void {
    clear(cast);
    seats.clear();
    const add = (p: Persona) => {
      const color = safeColor(p.color);
      const av = createAvatar(p.avatar, color, 72);
      setAvatar(av, { state: 'idle', mood: 'calm' });
      const urge = h('i');
      const status = h('div', { class: 'tile-status' });
      const badge = h('div', { class: 'tile-badge' }, p.id === 'moderator' ? '' : modelLabel(p.model || config.model, p.effort || config.effort));
      const tile = h('div', { class: 'tile', style: `--c:${color}` }, av,
        h('div', { class: 'tile-info' },
          h('div', { class: 'tile-name' }, p.name), h('div', { class: 'tile-sub', tip: p.title }, p.title),
          p.id === 'moderator' ? null : h('div', { class: 'urge', tip: '지금 말하고 싶은 정도' }, urge),
          h('div', { class: 'tile-foot' }, status, badge)));
      cast.append(tile);
      seats.set(p.id!, { persona: p, tile, av, urge, status, badge });
    };
    if (moderator) { add(moderator); cast.append(h('div', { class: 'cast-sep' })); }
    (config.participants as Persona[]).forEach(add);
    cast.append(spotlight);
    cast.classList.toggle('is-dense', seats.size > 7);
    paintBadges();
  }

  function paintBadges(): void {
    const show = badgeMode === 'on' || (badgeMode === 'blind' && state === 'ended');
    seats.forEach((s) => { s.badge.style.display = show ? '' : 'none'; });
  }

  function placeSpotlight(who: string | null, hot = spotHot, reveal = false): void {
    spotHot = hot;
    const seat = who ? seats.get(who) : null;
    seats.forEach((s, key) => s.tile.classList.toggle('is-speaking', key === who));
    if (!seat) { spotlight.classList.remove('is-on'); return; }
    const t = seat.tile;
    spotlight.style.width = `${t.offsetWidth}px`;
    spotlight.style.height = `${t.offsetHeight}px`;
    spotlight.style.transform = `translate(${t.offsetLeft}px, ${t.offsetTop}px)`;
    spotlight.classList.add('is-on');
    spotlight.classList.toggle('is-hot', hot);
    if (reveal) t.scrollIntoView({ block: 'nearest' });
  }
  const observer = new ResizeObserver(() => placeSpotlight(speaking));
  observer.observe(cast);

  function setStatus(who: string, node: IconNode | null, text = ''): void {
    const seat = seats.get(who);
    if (!seat) return;
    clear(seat.status);
    if (node) seat.status.append(icon(node, 14), text);
    seat.status.classList.toggle('is-on', !!node);
  }

  /* ---------- 기록에 붙이는 것들 ---------- */
  function addPhase(label: string): void {
    inner.append(h('div', { class: 'phase-rule' }, h('span', null, label)));
    follow();
  }

  function addNotice(kind: string, text: string): void {
    const node = kind === 'question' ? Megaphone : kind === 'warn' || kind === 'error' ? TriangleAlert
      : kind === 'search' ? Search : kind === 'instruct' ? Send : Flag;
    const label = kind === 'question' ? `청중 질문: ${text}` : kind === 'instruct' ? `진행 요청: ${text}` : text;
    const look = kind === 'error' ? 'warn' : kind === 'instruct' ? 'question' : kind;   // 진행 요청도 청중 질문처럼 눈에 띄게
    inner.append(h('div', { class: `notice notice--${look}` }, icon(node, 16), h('span', null, label)));
    follow();
  }

  function startSpeech(ev: DebateEvent): void {
    const seat = seats.get(ev.speaker);
    if (!seat) return;
    const p = seat.persona;
    const color = safeColor(p.color);
    const prev = speaking;
    if (prev && prev !== ev.speaker) setAvatar(seats.get(prev)!.av, { state: lastSpeech?.cut ? 'cut' : 'listening' });
    speaking = ev.speaker;
    setAvatar(seat.av, { state: 'speaking', mood: (ev.mood as Mood) || 'calm', wants: false });
    seat.tile.classList.remove('is-hot');
    setStatus(ev.speaker, null);
    placeSpotlight(ev.speaker, !!ev.interject, true);

    const av = createAvatar(p.avatar, color, 44);   // 대화창의 아바타도 말하는 동안 감정대로 움직인다
    setAvatar(av, { mood: (ev.mood as Mood) || 'calm', state: 'speaking' });
    const target = ev.target ? seats.get(ev.target)?.persona.name : '';
    const intent = INTENT_LABEL[ev.kind === 'free' ? ev.intent : ev.kind] ?? '';
    const text = h('div', { class: 'sp-text' }, h('span', { class: 'sp-wait' }, h('i'), h('i'), h('i')));
    const body = h('div', null,
      h('div', { class: 'sp-head' },
        h('span', { class: 'sp-name' }, p.name),
        ev.interject ? h('span', { class: 'chip chip--ember' }, icon(Zap, 14), '끼어들기') : null,
        intent ? h('span', { class: 'chip' }, target ? `${intent} → ${target}` : intent) : null,
        ev.mood && ev.mood !== 'calm' && p.id !== 'moderator' ? h('span', { class: 'chip chip--c' }, MOOD_LABEL[ev.mood as Mood]) : null,
        h('span', { class: 'sp-no' }, `#${ev.id}`)),
      text);
    const cls = ['sp', 'is-live', ev.interject ? 'sp--interject' : '', p.id === 'moderator' ? 'sp--mod' : ''].filter(Boolean).join(' ');
    const rootEl = h('article', { class: cls, style: `--c:${color}` }, av, body);
    inner.append(rootEl);
    cards.set(ev.id, { root: rootEl, text, body, av, speaker: ev.speaker, cut: false, started: false });
    follow();
  }

  /** 글자가 왼쪽에서 오른쪽으로 흘러나오게 한다: 글자마다 조금씩 늦게 나타난다. */
  function addDelta(ev: DebateEvent, instant: boolean): void {
    const card = cards.get(ev.id);
    if (!card) return;
    if (!card.started) { clear(card.text); card.started = true; }
    const chars = Array.from(String(ev.text));
    if (instant || speed === 'instant' || chars.length > 80) {
      card.text.append(ev.text);
    } else {
      const step = Math.min(1000 / (CPS[speed] ?? 14) / (replaying ? replayRate : 1), 600 / chars.length);
      const frag = document.createDocumentFragment();
      chars.forEach((ch, i) => frag.append(h('span', { class: 'ch', style: `animation-delay:${Math.round(i * step)}ms` }, ch)));
      card.text.append(frag);
    }
    follow();
  }

  function endSpeech(ev: DebateEvent): void {
    const card = cards.get(ev.id);
    if (!card) return;
    if (ev.failed) { card.root.remove(); cards.delete(ev.id); return; }
    card.root.classList.remove('is-live');
    setAvatar(card.av, { state: ev.cut ? 'cut' : 'listening' });   // 말이 끝나면 그 감정으로 듣는 자세가 된다
    card.cut = !!ev.cut;
    lastSpeech = { speaker: card.speaker, cut: !!ev.cut };
    const plain = ev.cut ? String(ev.text).replace(/\s*—$/, '') : String(ev.text);
    const settle = () => {
      if (!card.root.isConnected) return;
      clear(card.text);
      card.text.append(plain);
      if (ev.cut) card.text.append(h('span', { class: 'sp-cut' }, ' —'));
    };
    if (!card.started || ev.cut) settle();
    else window.setTimeout(settle, 1500);   // 흘러나오는 움직임이 끝난 뒤 글자 조각을 한 덩어리로 합친다
    const foot = h('div', { class: 'sp-foot' });
    if (ev.cut) foot.append(h('span', { class: 'chip chip--ember' }, '말이 끊김'));
    for (const s of ev.sources ?? []) {
      sources.set(s.url, s.title);
      foot.append(h('a', { class: 'chip', href: s.url, target: '_blank', rel: 'noopener noreferrer' }, icon(Link, 13),
        String(s.title || s.url).slice(0, 36)));
    }
    if (ev.thinking) {
      const think = h('div', { class: 'sp-think hidden' }, ev.thinking);
      foot.append(h('button', { type: 'button', class: 'chip', onclick: () => think.classList.toggle('hidden') }, icon(Brain, 13), '생각 보기'));
      card.body.append(foot, think);
    } else if (foot.childElementCount) {
      card.body.append(foot);
    }
    if ((ev.sources ?? []).length && tab === 'sources') paintSide();
    const seat = seats.get(card.speaker);
    if (seat && speaking === card.speaker) setAvatar(seat.av, { state: ev.cut ? 'cut' : 'listening' });
    follow();
  }

  function applyDirector(ev: DebateEvent): void {
    for (const row of ev.scores ?? []) {
      const seat = seats.get(row.id);
      if (!seat) continue;
      seat.urge.style.width = `${row.urge * 10}%`;
      seat.tile.classList.toggle('is-hot', row.urge >= 8);
      if (row.id !== speaking || seat.av.dataset.state !== 'speaking') {
        setAvatar(seat.av, { mood: row.mood as Mood, wants: row.urge >= 8, state: seat.av.dataset.state === 'idle' ? 'listening' : undefined });
      }
    }
  }

  const nameColor = (name: string) => {
    for (const s of seats.values()) if (s.persona.name === name) return safeColor(s.persona.color);
    return '#E8C170';
  };

  function addSummary(ev: DebateEvent): void {
    inner.append(h('div', { class: 'panel frame summary' },
      h('h2', null, ev.headline),
      (ev.consensus ?? []).length ? h('div', null, h('h3', null, '대체로 동의한 점'),
        h('ul', null, ev.consensus.map((c: string, i: number) => h('li', { style: `animation-delay:${i * 90}ms` }, c)))) : null,
      h('h3', null, '끝까지 갈린 쟁점'),
      (ev.issues ?? []).map((it: any, i: number) => h('div', { class: 'issue', style: `animation-delay:${200 + i * 140}ms` },
        h('b', null, it.issue),
        h('div', { class: 'issue-pos' }, it.positions.flatMap((pos: any) => [
          h('span', { style: `--c:${nameColor(pos.name)}` }, pos.name), h('span', null, pos.position)])))),
      h('div', { class: 'takeaway' }, ev.takeaway)));
    follow();
  }

  /* ---------- 회의록 ---------- */
  function showMinutes(m: any, scroll = false): void {
    minutesEl?.remove();
    const list = (title: string, items: string[]) => h('div', null, h('h3', null, title),
      items?.length ? h('ul', null, items.map((it) => h('li', null, it))) : h('p', { class: 'muted' }, '없음'));
    minutesEl = h('div', { class: 'panel frame summary minutes' },
      h('div', { class: 'minutes-tag' }, icon(FileText, 16), '회의록'),
      h('h2', null, m.title),
      h('h3', null, '전체 흐름'),
      h('p', { class: 'minutes-over' }, m.overview),
      (m.timeline ?? []).length ? h('div', null, h('h3', null, '시간대별 흐름'),
        h('div', { class: 'tl' }, m.timeline.map((t: any) => h('div', { class: 'tl-item' },
          h('div', { class: 'tl-when' }, h('b', null, t.time), h('span', null, t.turns)),
          h('div', { class: 'tl-what' }, h('b', null, t.phase), h('p', null, t.summary),
            (t.issues ?? []).length ? h('ul', null, t.issues.map((it: string) => h('li', null, it))) : null))))) : null,
      list('안건', m.agenda),
      h('h3', null, '주요 논의'),
      (m.discussions ?? []).map((d: any) => h('div', { class: 'issue' }, h('b', null, d.topic),
        h('div', { class: 'issue-pos' }, (d.points ?? []).flatMap((pt: any) => [
          h('span', { style: `--c:${nameColor(pt.name)}` }, pt.name), h('span', null, pt.point)])))),
      list('합의 사항', m.agreements), list('미결 사항', m.open_issues), list('후속 조치', m.follow_ups),
      h('div', { class: 'takeaway' }, m.conclusion));
    inner.append(minutesEl);
    if (costEl) inner.append(costEl);   // 총 비용은 늘 맨 아래에
    if (scroll) minutesEl.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function paintCost(): void {
    clockCost.textContent = fmtCost(money.cost, money.rate);
  }

  /** 끝난 토론의 맨 아래에 총 비용과 내역을 보여 준다. 회의록을 쓰면 그 비용까지 더해 다시 그린다. */
  function showCost(): void {
    costEl?.remove();
    const p = money.parts;
    const row = (label: string, usd: number, note = '') => h('div', { class: 'cost-row' },
      h('span', null, label, note ? h('small', null, note) : null), h('b', null, fmtCost(usd, money.rate)));
    const t = usage?.total ?? record?.usage;
    costEl = h('div', { class: 'panel frame summary costcard' },
      h('div', { class: 'minutes-tag' }, icon(Coins, 16), '총 비용'),
      h('h2', null, fmtCost(money.cost, money.rate)),
      h('div', { class: 'cost-rows' },
        row('토론 (토큰)', p.tokens ?? money.cost, t ? `입력 ${(t.input + t.cached + t.cache_write).toLocaleString()} · 출력 ${t.output.toLocaleString()} 토큰` : ''),
        row('웹 검색', p.search ?? 0, `${money.searches.toLocaleString()}건 × ${fmtCost(money.searchUsd, money.rate)}`),
        (p.prep ?? 0) > 0 ? row('참가자 생성', p.prep) : null,
        (p.minutes ?? 0) > 0 ? row('회의록', p.minutes) : null),
      h('p', { class: 'muted small' }, `측정된 토큰 수와 검색 건수에 공개 단가를 곱한 값입니다. 1달러 ${money.rate.toLocaleString()}원으로 계산했습니다.`));
    inner.append(costEl);
    follow();
  }

  async function writeMinutes(): Promise<void> {
    if (writingMinutes || !record) return;
    writingMinutes = true;
    paintControls();
    try {
      const res = await api.minutes(id);
      record.minutes = res.minutes;
      record.cost = res.cost;
      record.cost_parts = res.cost_parts;
      money.cost = res.cost;
      money.parts = res.cost_parts;
      paintCost();
      showMinutes(res.minutes, true);
      showCost();
      toast('회의록을 만들었습니다.');
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      writingMinutes = false;
      paintControls();
    }
  }

  async function copyAll(): Promise<void> {
    if (!record) return;
    try {
      if (!record.speeches?.length) record = { ...(await api.debate(id)), minutes: record.minutes ?? undefined } as DebateRecord;
    } catch { /* 가진 것으로 복사한다 */ }
    const text = recordToMarkdown(record);
    const ok = await copyText(text);
    if (!ok) { toast('복사하지 못했습니다. 브라우저가 클립보드 사용을 막았습니다.', 'error'); return; }
    toast(record.minutes
      ? `대화 내용과 회의록을 복사했습니다 (${text.length.toLocaleString()}자).`
      : `회의록이 아직 없어 대화 내용만 복사했습니다 (${text.length.toLocaleString()}자).`);
  }

  /* ---------- 이벤트 처리 ---------- */
  function handle(ev: DebateEvent, instant = false): void {
    switch (ev.type) {
      case 'init':
        if (ev.pricing) money.searchUsd = ev.pricing.search_usd ?? money.searchUsd;   // 환율은 늘 지금의 고정값을 쓴다
        topic.textContent = ev.config.topic;
        badgeMode = ev.config.badge ?? 'on';
        speed = ev.config.speed ?? 'normal';
        buildCast(ev.config, ev.moderator);
        paintControls();
        break;
      case 'phase':
        phaseChip.querySelector('span')!.textContent = ev.label;
        addPhase(ev.label);
        if (ev.phase === 'closing') {   // 마무리 발언에서는 차례가 정해져 있으므로 발언 의지와 감정을 가라앉힌다
          seats.forEach((s) => { setAvatar(s.av, { mood: 'calm', wants: false }); s.urge.style.width = '0%'; s.tile.classList.remove('is-hot'); });
        }
        break;
      case 'research':
        if (ev.status === 'start') { addNotice('search', `진행자가 자료를 조사합니다: ${ev.url}`); setStatus('moderator', Search, '조사 중'); const m = seats.get('moderator'); if (m) setAvatar(m.av, { state: 'searching' }); }
        else if (ev.status === 'search') setStatus('moderator', Search, String(ev.query).slice(0, 14));
        else { setStatus('moderator', null); const m = seats.get('moderator'); if (m) setAvatar(m.av, { state: 'listening' }); for (const s of ev.sources ?? []) sources.set(s.url, s.title); }
        break;
      case 'briefing': briefing = ev.text; if (tab === 'materials') paintSide(); break;
      case 'director': applyDirector(ev); break;
      case 'ready': {
        const seat = seats.get(ev.speaker);
        if (seat && ev.speaker !== speaking) {
          setAvatar(seat.av, { state: 'ready', mood: (ev.mood as Mood) || undefined });
          setStatus(ev.speaker, ev.interject ? Zap : null, ev.interject ? '끼어듭니다' : '');
        }
        break;
      }
      case 'speech_start': startSpeech(ev); break;
      case 'delta': addDelta(ev, instant); break;
      case 'search': {
        setStatus(ev.speaker, Search, String(ev.query).slice(0, 14));
        window.setTimeout(() => setStatus(ev.speaker, null), 4000);
        break;
      }
      case 'speech_end': endSpeech(ev); break;
      case 'clock': {
        clockTurn.textContent = ev.max_turns ? `${ev.turn} / ${ev.max_turns}` : String(ev.turn);
        clockTime.textContent = ev.max_seconds ? `${fmtTime(ev.seconds)} / ${fmtTime(ev.max_seconds)}` : fmtTime(ev.seconds);
        const pct = Math.min(100, (ev.progress ?? 0) * 100);
        fill.style.width = `${pct}%`;
        head.style.left = `${pct}%`;
        if (lastSpeech) {
          const seat = seats.get(lastSpeech.speaker);
          track.append(h('i', { class: `tick${lastSpeech.cut ? ' tick--cut' : ''}`, style: `left:${pct}%;--c:${safeColor(seat?.persona.color)}`,
            tip: `#${ev.turn} ${seat?.persona.name ?? ''}${lastSpeech.cut ? ' (끊김)' : ''}` }));
        }
        break;
      }
      case 'usage':
        usage = ev;
        money.cost = Number(ev.cost ?? 0);
        money.parts = ev.cost_parts ?? { tokens: money.cost };
        money.searches = Number(ev.total?.searches ?? 0);
        paintCost();
        if (tab === 'usage' && !side.classList.contains('is-closed')) paintSide();
        break;
      case 'compaction':
        track.append(h('i', { class: 'tick tick--compact', style: `left:${fill.style.width || '0%'}`, tip: '문맥 압축' }));
        addNotice('info', '대화가 길어져 앞부분을 줄였습니다 (문맥 압축).');
        break;
      case 'notice': if (!instant || !['finish', 'info'].includes(ev.kind)) addNotice(ev.kind, ev.text); break;
      case 'paused': state = 'paused'; paintControls(); break;
      case 'resumed': state = 'running'; paintControls(); break;
      case 'speed': speed = ev.speed; paintControls(); break;
      case 'error':
        addNotice('error', ev.message);
        if (!ev.fatal) { state = 'error'; paintControls(); }
        break;
      case 'summarizing': if (!instant) addNotice('info', '회의록을 쓰는 중입니다.'); break;
      case 'minutes':
        if (record) record.minutes = ev.minutes;
        if (!instant) { showMinutes(ev.minutes); follow(); }
        break;
      case 'summary': addSummary(ev); break;
      case 'end':
        state = 'ended';
        phaseChip.querySelector('span')!.textContent = ev.state === 'aborted' ? '중단됨' : '토론 끝';
        if (speaking) setAvatar(seats.get(speaking)!.av, { state: 'listening' });
        speaking = null;
        placeSpotlight(null);
        seats.forEach((s) => { setAvatar(s.av, { wants: false }); s.tile.classList.remove('is-hot'); });
        paintBadges();
        paintControls();
        if (!instant) showCost();
        break;
      default: break;
    }
    stage.classList.toggle('is-ended', state === 'ended');
    stage.classList.toggle('is-paused', state === 'paused' || state === 'error' || replayPaused);
  }

  /* ---------- 조작 ---------- */
  const send = (action: string, value?: unknown) => api.control(id, action, value).catch((err) => toast((err as Error).message, 'error'));
  let interveneKind: 'instruct' | 'question' = 'instruct';   // 기본은 진행 요청(반드시 따르는 지시)

  function segEl(options: [string, string][], current: string, pick: (v: string) => void): HTMLElement {
    return h('div', { class: 'seg' }, options.map(([v, l]) =>
      h('button', { type: 'button', class: current === v ? 'is-on' : '', onclick: () => pick(v) }, l)));
  }

  function paintControls(): void {
    clear(controls);
    if (replaying) {
      controls.append(
        h('button', { type: 'button', class: 'btn', onclick: () => { replayPaused = !replayPaused; if (!replayPaused) stepReplay(); paintControls(); stage.classList.toggle('is-paused', replayPaused); } },
          icon(replayPaused ? Play : Pause, 18), replayPaused ? '이어 보기' : '멈춤'),
        segEl([['1', '1배'], ['2', '2배'], ['4', '4배']], String(replayRate), (v) => { replayRate = Number(v); paintControls(); }),
        h('button', { type: 'button', class: 'btn', onclick: () => showAll() }, icon(SkipForward, 18), '끝까지 보기'),
        h('span', { class: 'muted small' }, '지난 토론을 같은 박자로 다시 보는 중'));
      return;
    }
    if (state === 'ended' || !record?.live) {
      controls.append(
        h('button', { type: 'button', class: 'btn btn--primary', disabled: writingMinutes, onclick: () => writeMinutes() },
          icon(writingMinutes ? LoaderCircle : FileText, 18, writingMinutes ? 'spin' : ''),
          writingMinutes ? '회의록을 쓰는 중' : record?.minutes ? '회의록 다시 쓰기' : '회의록 쓰기'),
        h('button', { type: 'button', class: 'btn', tip: '다른 프로그램에 붙여 넣을 수 있게 마크다운으로 복사합니다', onclick: () => copyAll() },
          icon(Copy, 18), '대화 + 회의록 복사'),
        h('div', { class: 'sep' }),
        h('button', { type: 'button', class: 'btn', onclick: () => startReplay() }, icon(Rewind, 18), '처음부터 다시 보기'),
        h('button', { type: 'button', class: 'btn', onclick: () => ctx.go('#/') }, icon(Play, 18), '새 토론'));
      return;
    }
    const paused = state === 'paused' || state === 'error';
    const input = h('input', { class: 'input', maxlength: 500, placeholder: interveneKind === 'instruct'
      ? '토론에 지시합니다. 진행자와 참가자 모두 그대로 따릅니다'
      : '청중으로서 질문합니다. 진행자가 받아서 참가자에게 묻습니다' });
    const submit = () => {
      const value = input.value.trim();
      if (!value) return;
      send(interveneKind, value);
      input.value = '';
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) submit(); });
    put(controls,
      h('button', { type: 'button', class: 'btn', onclick: () => send(paused ? 'resume' : 'pause') }, icon(paused ? Play : Pause, 18), paused ? '이어 하기' : '멈춤'),
      state === 'error' ? h('span', { class: 'state-chip' }, icon(TriangleAlert, 16), '오류로 멈췄습니다') : null,
      segEl(SPEEDS, speed, (v) => send('speed', v)),
      h('button', { type: 'button', class: 'btn btn--icon', tip: '이 발언을 끝까지 바로 보기', 'aria-label': '이 발언을 끝까지 바로 보기', onclick: () => send('skip') }, icon(SkipForward, 18)),
      h('button', { type: 'button', class: 'btn', tip: '지금 마무리 발언으로 넘어갑니다', onclick: () => send('finish') }, icon(Flag, 18), '마무리'),
      h('div', { class: 'sep' }),
      h('div', { class: 'intervene' },
        segEl([['instruct', '진행 요청'], ['question', '청중 질문']], interveneKind, (v) => { interveneKind = v as any; paintControls(); }),
        input,
        h('button', { type: 'button', class: 'btn btn--icon', tip: '보내기', 'aria-label': '보내기', onclick: submit }, icon(Send, 18))));
  }

  /* ---------- 다시 보기 ---------- */
  function reset(): void {
    window.clearTimeout(replayTimer);
    clear(inner);
    minutesEl = null;
    costEl = null;
    cards.clear();
    sources.clear();
    track.querySelectorAll('.tick').forEach((t) => t.remove());
    fill.style.width = '0%';
    head.style.left = '0%';
    speaking = null;
    lastSpeech = null;
    usage = null;
    state = 'running';
    clockTurn.textContent = '0';
    clockTime.textContent = '00:00';
  }

  /** 저장된 기록의 비용을 읽는다 (회의록 비용 등 토론이 끝난 뒤에 더해진 것까지). */
  function loadMoney(): void {
    if (!record) return;
    if (record.pricing) money.searchUsd = record.pricing.search_usd ?? money.searchUsd;
    if (record.cost !== undefined) money.cost = Number(record.cost);
    if (record.cost_parts) money.parts = record.cost_parts;
    else if (record.cost !== undefined) money.parts = { tokens: Number(record.cost) };
    if (record.usage?.searches !== undefined) money.searches = Number(record.usage.searches);
    paintCost();
  }

  function showAll(): void {
    if (!record) return;
    replaying = false;
    reset();
    for (const ev of record.events) handle(ev, true);
    state = 'ended';
    loadMoney();
    if (record.minutes) showMinutes(record.minutes);
    showCost();
    paintBadges();
    paintControls();
    paintSide();
    stage.classList.add('is-ended');
    transcript.scrollTop = 0;
  }

  function stepReplay(): void {
    if (!record || disposed || !replaying || replayPaused) return;
    const events = record.events;
    const finish = () => { replaying = false; state = 'ended'; loadMoney(); if (record?.minutes) showMinutes(record.minutes); showCost(); paintControls(); };
    if (replayIndex >= events.length) { finish(); return; }
    const ev = events[replayIndex];
    handle(ev, false);
    replayIndex += 1;
    const next = events[replayIndex];
    if (!next) { finish(); return; }
    const wait = Math.min(Math.max(next.t - ev.t, 0), 6) * 1000 / replayRate;
    replayTimer = window.setTimeout(stepReplay, wait);
  }

  function startReplay(): void {
    if (!record) return;
    reset();
    replaying = true;
    replayPaused = false;
    replayIndex = 0;
    stick = true;
    stage.classList.remove('is-ended');
    paintControls();
    stepReplay();
  }

  /* ---------- 시작 ---------- */
  (async () => {
    try {
      record = await api.debate(id);
    } catch (err) {
      root.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, h('h3', null, '토론을 찾지 못했습니다'), h('p', null, (err as Error).message))));
      return;
    }
    if (disposed) return;
    paintSide();
    if (!record.live) { showAll(); return; }
    paintControls();
    stream = new EventSource(`/api/debates/${id}/events`);
    stream.onmessage = (msg) => {
      const ev = JSON.parse(msg.data) as DebateEvent;
      if (ev.i <= lastIndex) return;   // 다시 연결되면 처음부터 다시 오므로 본 것은 건너뛴다
      lastIndex = ev.i;
      record!.events[ev.i] = ev;
      handle(ev, false);
      if (ev.type === 'end') {
        stream?.close();
        record!.live = false;
        paintControls();
        api.debate(id).then((saved) => { if (!disposed) { record = saved; loadMoney(); showCost(); paintControls(); } }).catch(() => undefined);
      }
    };
  })();

  return () => {
    disposed = true;
    stream?.close();
    observer.disconnect();
    window.clearTimeout(replayTimer);
  };
}
