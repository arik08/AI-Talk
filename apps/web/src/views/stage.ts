import {
  BookOpen, Brain, Coins, Copy, FileText, Flag, Hourglass, Info, ListOrdered, LoaderCircle, Megaphone, MessagesSquare, Pause,
  PenLine, Play, Rewind, Scale, Search, Send, SkipForward, StepForward, TriangleAlert, Trophy, Zap, type IconNode,
} from 'lucide';
import { api } from '../api';
import { CitationRegistry, collectSources, parseCitations } from '../citations';
import { createAvatar, setAvatar } from '../avatar/avatar';
import { copyText, recordToMarkdown } from '../export';
import type { AppContext } from '../main';
import { INTENT_LABEL, MOOD_LABEL, TONE_LABEL, type DebateEvent, type DebateRecord, type Mood, type Persona } from '../types';
import { richTip, clear, fmtCost, fmtTime, h, icon, put, safeColor, toast, USD_KRW } from '../ui/dom';
import { renderCited, sourceList, sourceToggle } from '../ui/sources';
import { drawSpeech, renderSpeech, speechBlocks, speechLength } from '../ui/speech';

interface Seat { persona: Persona; tile: HTMLElement; av: HTMLElement; urge: HTMLElement; status: HTMLElement; badge: HTMLElement }
interface Card { root: HTMLElement; text: HTMLElement; body: HTMLElement; av: HTMLElement; speaker: string; cut: boolean; started: boolean; raw: string; times: number[] }
const REVEAL_CPS = 90;   // 쓰이는 중인 회의록·판정의 글자가 나타나는 빠르기 (초당 글자 수)

/**
 * 쓰이는 중인 카드(회의록, 판정)의 새 글자를 발언처럼 왼쪽부터 차례로 나타나게 한다.
 * 이 카드들은 조각이 올 때마다 통째로 다시 그려서, 그대로 두면 글이 덩어리째 턱턱 붙는다.
 * 글자마다 나타날 시각을 times에 적어 두고, 다시 그려도 나타나던 글자는 하던 움직임을 이어 간다.
 * 조각이 몰려 와도 앞 글자 뒤에 줄을 세워 한결같은 빠르기로 흘러나온다.
 */
export function reveal(root: HTMLElement, times: number[]): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let total = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    nodes.push(n as Text);
    total += Array.from((n as Text).data).length;
  }
  const now = performance.now();
  if (total < times.length) times.length = total;
  const fresh = total - times.length;
  if (fresh > 0) {
    const step = Math.min(1000 / REVEAL_CPS, 900 / fresh);
    const start = Math.min(Math.max(now, (times[times.length - 1] ?? 0) + step), now + 1200);   // 너무 밀리면 따라잡는다
    for (let k = 0; k < fresh; k += 1) times.push(start + k * step);
  }
  let index = 0;
  for (const node of nodes) {
    const chars = Array.from(node.data);
    const base = index;
    index += chars.length;
    const first = chars.findIndex((_, k) => times[base + k] - now > -CH_IN_MS);
    if (first < 0) continue;   // 이미 다 나타난 글
    const frag = document.createDocumentFragment();
    if (first) frag.append(chars.slice(0, first).join(''));
    for (let k = first; k < chars.length; k += 1) {
      frag.append(h('span', { class: 'ch', style: `animation-delay:${Math.round(times[base + k] - now)}ms` }, chars[k]));
    }
    node.replaceWith(frag);
  }
}

const CH_IN_MS = 550;   // 글자 하나가 나타나는 움직임의 길이 (app.css의 ch-in과 같다)

/** 덧붙이는 설명은 늘 보이게 두지 않고, 정보 아이콘에 마우스를 올렸을 때 보여 준다. */
function infoTip(text: string): HTMLElement {
  return h('span', { class: 'info-tip', role: 'img', 'aria-label': text, tip: text }, icon(Info, 15));
}

const SPEEDS: [string, string][] = [['slow', '느리게'], ['normal', '보통'], ['fast', '빠르게'], ['instant', '즉시']];
const CPS: Record<string, number> = { slow: 8, normal: 14, fast: 26 };   // 서버가 글자를 내보내는 속도와 같다
const SPEECH_CPS = 5.5;   // 토론 시계: 사람이 말하는 속도(초당 글자). 서버의 값과 같다
const QUESTIONS = ['누가 가장 설득력 있었나요?', '가장 크게 갈린 쟁점은 무엇이었나요?', '빠진 관점이 있다면 무엇인가요?'];

/** 타임라인의 한 칸: 발언 하나가 차지하는 구간(진행률 %)과, 그 발언이 시작되는 이벤트의 자리. */
interface Mark { id: number; index: number; from: number; to: number; name: string }

export function mountStage(root: HTMLElement, id: string, ctx: AppContext): () => void {
  const seats = new Map<string, Seat>();
  const cards = new Map<number, Card>();
  const registry = new CitationRegistry();   // 출처 번호표: 이 토론 전체에서 URL마다 번호 하나
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
  let judging = false;
  let asking = false;
  let resuming = false;
  let verdictEl: HTMLElement | null = null;
  let qaEl: HTMLElement | null = null;
  let liveCard: Card | null = null;   // 지금 글자가 나오고 있는 발언
  let marks: Mark[] = [];
  // 토론 시계: 서버는 발언이 끝날 때만 알려 준다. 그 사이에는 화면에 나온 글자 수로 어림해 1초씩 올린다
  const clock = { base: 0, shown: 0, max: null as number | null };
  let minutesEl: HTMLElement | null = null;
  let minutesTimes: number[] = [];   // 쓰이는 중인 회의록·판정의 글자가 나타날 시각 (reveal)
  let verdictTimes: number[] = [];
  let waitEl: HTMLElement | null = null;   // 회의록을 쓰는 동안 그 자리에 놓는 카드
  let waitTimer = 0;
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
  const scrubTip = h('div', { class: 'scrub-tip', 'aria-hidden': 'true' });
  const timeline = h('div', { class: 'timeline', role: 'slider', 'aria-label': '토론 위치', 'aria-valuemin': 0, 'aria-valuemax': 100 }, track, scrubTip);
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
    h('footer', { class: 'dock' }, timeline, controls));
  root.append(stage);

  // 맨 아래를 따라갈 때는 한 번에 뛰지 않고, 용수철에 끌려가듯 속도를 서서히 올리고 서서히 줄인다 (2차 저역 통과 필터).
  // 남은 거리의 일정 비율씩 다가가는 방식(1차)은 줄이 하나 늘 때마다 최고 속도로 출발해 턱턱 끊겨 보였다.
  // 속도가 이어지므로 줄이 잇달아 늘면 움직임이 서로 겹쳐 한결같은 속도로 흘러내린다
  const GLIDE_MS = 320;        // 따라붙는 빠르기. 크면 느긋하고 부드럽고, 작으면 바짝 따라붙는다
  let glide = 0;               // 돌고 있는 requestAnimationFrame
  let glideSpeed = 0;          // 지금 내려가는 속도 (px/ms)
  let glidePos = 0;            // 소수점까지 들고 있는 위치 (scrollTop은 정수로 깎일 수 있다)
  let glideSet = -1;           // 우리가 마지막으로 넣은 scrollTop. 이것과 다르면 사용자가 움직인 것이다
  let glideAt = 0;
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
  transcript.addEventListener('scroll', () => {
    if (glide && Math.abs(transcript.scrollTop - glideSet) < 2) return;   // 우리가 움직인 것
    stick = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 120;
    glidePos = transcript.scrollTop;
    glideSpeed = 0;
  });
  const glideStep = (now: number) => {
    const goal = transcript.scrollHeight - transcript.clientHeight;
    const gap = goal - glidePos;
    if (!stick || (gap < 0.5 && glideSpeed < 0.01)) {
      if (stick) transcript.scrollTop = goal;
      glide = 0;
      glideSpeed = 0;
      return;
    }
    let left = Math.min(now - glideAt, 100);
    glideAt = now;
    const w = 1 / GLIDE_MS;
    while (left > 0) {   // 임계 감쇠 용수철. 프레임이 길어도 흔들리지 않게 잘게 나눠 계산한다
      const dt = Math.min(left, 8);
      left -= dt;
      glideSpeed += (w * w * (goal - glidePos) - 2 * w * glideSpeed) * dt;
      glidePos += glideSpeed * dt;
    }
    if (glidePos >= goal) { glidePos = goal; glideSpeed = 0; }   // 목표를 지나치지 않는다
    transcript.scrollTop = glidePos;
    glideSet = transcript.scrollTop;
    glide = requestAnimationFrame(glideStep);
  };
  const follow = () => {
    if (!stick) return;
    if (calm.matches || document.hidden) { transcript.scrollTop = transcript.scrollHeight; return; }   // 안 보이는 탭은 프레임이 돌지 않는다
    if (glide) return;
    glidePos = transcript.scrollTop;
    glideSet = glidePos;
    glideSpeed = 0;
    glideAt = performance.now();
    glide = requestAnimationFrame(glideStep);
  };
  sideBtn.addEventListener('click', () => { side.classList.toggle('is-closed'); if (!side.classList.contains('is-closed')) paintSide(); });

  /* ---------- 토론 시계 ---------- */
  function paintClock(): void {
    clockTime.textContent = clock.max ? `${fmtTime(clock.shown)} / ${fmtTime(clock.max)}` : fmtTime(clock.shown);
  }
  /** 서버가 알려 준 시각으로 맞춘다. 조금 앞서 있으면 째깍이며 따라가게 두고, 많이 벌어졌으면 바로 맞춘다. */
  function setClock(seconds: number, snap: boolean): void {
    clock.base = seconds;
    if (snap || seconds - clock.shown > 12 || seconds < clock.shown) clock.shown = seconds;
    paintClock();
  }
  const clockTimer = window.setInterval(() => {
    const said = liveCard ? Array.from(liveCard.raw).length / SPEECH_CPS : 0;   // 지금 발언에서 이미 말한 만큼
    if (clock.shown + 1 > clock.base + said) return;
    clock.shown = Math.floor(clock.shown) + 1;
    paintClock();
  }, 200);

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
          h('span', null, '예상 비용', infoTip(`측정된 토큰 수와 검색 건수에 공개 단가를 곱한 값입니다. 웹 검색은 건당 ${fmtCost(money.searchUsd, money.rate)}, 1달러 ${money.rate.toLocaleString()}원으로 계산했습니다.`)),
          h('span', null, fmtCost(Number(usage.cost ?? 0), money.rate)),
          h('span', null, 'AI 호출'), h('span', null, (() => {
            const calls = usage.calls ?? {};
            const director = calls.director ?? 0;
            const total = Object.values(calls).reduce((a: number, b: any) => a + Number(b), 0);
            return `발언 ${total - director}번 · 연출자 ${director}번`;
          })())),
        h('h4', { style: 'margin-top:1.25rem' }, '화자별 출력'),
        h('div', { class: 'kv' }, Object.entries(usage.by ?? {}).flatMap(([who, u]: [string, any]) => [
          h('span', null, who === 'director' ? '연출자(안 보임)' : seats.get(who)?.persona.name ?? who),
          h('span', null, `${u.output.toLocaleString()} 토큰`)])));
    } else if (tab === 'sources') {
      if (!registry.size) { sideBody.append(h('p', { class: 'muted' }, '웹에서 찾은 출처가 없습니다.')); return; }
      const list = sourceList(registry.list(), registry);
      sideBody.append(list.root);
      if (!side.classList.contains('is-closed')) list.refresh();   // 보이는 동안에만 실제 제목을 조회한다
    } else {
      const mats = record?.config.materials ?? [];
      const concept = record?.config.concept;
      const tone = record?.config.tone && record.config.tone !== 'default' ? TONE_LABEL[record.config.tone] : '';
      if (!mats.length && !briefing && !concept && !tone) { sideBody.append(h('p', { class: 'muted' }, '붙인 자료가 없습니다.')); return; }
      if (tone) sideBody.append(h('h4', null, '분위기'), h('div', { class: 'brief', style: 'margin-bottom:1rem' }, tone));
      if (concept) sideBody.append(h('h4', null, '설정과 분위기'), h('div', { class: 'brief', style: 'margin-bottom:1rem' }, concept));
      if (mats.length) sideBody.append(h('h4', null, '올린 문서'), h('div', { class: 'kv', style: 'margin-bottom:1rem' },
        mats.flatMap((m: any) => [h('span', null, m.name), h('span', null, `${Number(m.chars).toLocaleString()}자`)])));
      if (briefing) {
        const brief = h('div', { class: 'brief' });
        renderCited(brief, briefing, registry);
        sideBody.append(h('h4', null, '진행자의 사전 조사'), brief);
      }
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
      // 인물 위에 마우스를 올리면 그 사람이 누구인지 보여 준다. 숨은 의도(hidden)는 넣지 않는다
      const about = [[p.name, p.title].filter(Boolean).join(' · '),
        ...([['분야', p.expertise], ['입장', p.viewpoint], ['성격', p.personality], ['말투', p.speech]] as const)
          .filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`)].join('\n');
      const tile = h('div', { class: 'tile', style: `--c:${color}`, 'data-tip-side': 'left' }, av,
        h('div', { class: 'tile-info' },
          h('div', { class: 'tile-name' }, p.name), h('div', { class: 'tile-sub' }, p.title),
          p.id === 'moderator' ? null : h('div', { class: 'urge', tip: '지금 말하고 싶은 정도' }, urge),
          h('div', { class: 'tile-foot' }, status, badge)));
      richTip(tile, about, () => {
        const face = createAvatar(p.avatar, color, 48);
        face.classList.add('is-still');
        const rows = ([['분야', p.expertise], ['성격', p.personality], ['말투', p.speech]] as const).filter(([, v]) => v);
        return h('div', { class: 'who', style: `--c:${color}` },
          h('div', { class: 'who-head' }, face,
            h('div', null, h('div', { class: 'who-name' }, p.name), p.title ? h('div', { class: 'who-title' }, p.title) : null)),
          p.viewpoint ? h('p', { class: 'who-view' }, p.viewpoint) : null,
          rows.length ? h('dl', { class: 'who-rows' }, rows.flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)])) : null);
      });
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
    liveCard = { root: rootEl, text, body, av, speaker: ev.speaker, cut: false, started: false, raw: '', times: [] };
    cards.set(ev.id, liveCard);
    follow();
  }

  /** 글자가 왼쪽에서 오른쪽으로 흘러나오게 한다: 글자마다 조금씩 늦게 나타난다. */
  function addDelta(ev: DebateEvent, instant: boolean): void {
    const card = cards.get(ev.id);
    if (!card) return;
    if (!card.started) { clear(card.text); card.started = true; }
    // 받은 글 전체를 다시 읽어 링크를 각주로 바꾼다. 아직 닫히지 않은 링크와 내부 표식은 보여 주지 않는다
    card.raw += String(ev.text);
    // 목록, 표, 막대 그림은 글자가 올 때마다 모양이 바뀌므로 통째로 다시 그린다.
    // 글자마다 나타날 시각을 적어 두어, 다시 그려도 나타나던 글자는 하던 움직임을 이어 간다
    const blocks = speechBlocks(parseCitations(card.raw, registry, { streaming: true }), true);
    const total = speechLength(blocks);
    const now = performance.now();
    const count = total - card.times.length;
    if (count < 0) card.times.length = total;   // 표기가 닫히며 글자 수가 줄었다
    const quick = instant || speed === 'instant' || count > 80;
    const step = count > 0 ? Math.min(1000 / (CPS[speed] ?? 14) / (replaying ? replayRate : 1), 600 / count) : 0;
    for (let k = 0; k < count; k += 1) card.times.push(quick ? -Infinity : now + k * step);
    clear(card.text);
    drawSpeech(card.text, blocks, (index) => {
      const wait = card.times[index] - now;
      return wait > -CH_IN_MS ? wait : null;
    });
    follow();
  }

  function endSpeech(ev: DebateEvent): void {
    const card = cards.get(ev.id);
    if (!card) return;
    if (liveCard === card) liveCard = null;
    if (ev.failed) { card.root.remove(); cards.delete(ev.id); return; }
    card.root.classList.remove('is-live');
    setAvatar(card.av, { state: ev.cut ? 'cut' : 'listening' });   // 말이 끝나면 그 감정으로 듣는 자세가 된다
    card.cut = !!ev.cut;
    lastSpeech = { speaker: card.speaker, cut: !!ev.cut };
    const plain = ev.cut ? String(ev.text).replace(/\s*—$/, '') : String(ev.text);
    // 출처는 여기서 바로 번호표에 올린다 (다시 볼 때도 같은 순서로 올라가 번호가 같다)
    const cited = collectSources(plain, ev.sources, registry);
    const toggle = cited.length ? sourceToggle(cited, registry) : null;
    // 생각 보기도 출처처럼 마지막 문장 옆의 아이콘 버튼이다. 누르면 발언 아래에 생각이 펼쳐진다
    const think = ev.thinking ? h('div', { class: 'sp-think hidden' }, ev.thinking) : null;
    const thinkBtn = think ? h('button', { type: 'button', class: 'src-btn', tip: '생각 보기', 'aria-label': '생각 보기', 'aria-expanded': 'false' }, icon(Brain, 15)) : null;
    thinkBtn?.addEventListener('click', () => {
      const open = think!.classList.toggle('hidden') === false;
      const label = open ? '생각 접기' : '생각 보기';
      thinkBtn.dataset.tip = label;
      thinkBtn.setAttribute('aria-label', label);
      thinkBtn.setAttribute('aria-expanded', String(open));
      thinkBtn.classList.toggle('is-on', open);
    });
    const settle = () => {
      if (!card.root.isConnected) return;
      clear(card.text);
      const tail = renderSpeech(card.text, plain, registry);
      if (ev.cut) tail.append(h('span', { class: 'sp-cut' }, ' —'));
      if (toggle) tail.append(toggle.button);   // 마지막 문장 옆. 자리가 없으면 다음 줄로 넘어간다
      if (thinkBtn) tail.append(thinkBtn);
    };
    if (!card.started || ev.cut) settle();
    else window.setTimeout(settle, 1500);   // 흘러나오는 움직임이 끝난 뒤 글자 조각을 한 덩어리로 합친다
    const foot = h('div', { class: 'sp-foot' });
    if (ev.cut) foot.append(h('span', { class: 'chip chip--ember' }, '말이 끊김'));
    if (toggle) card.body.append(toggle.panel);
    if (foot.childElementCount) card.body.append(foot);
    if (think) card.body.append(think);
    if (cited.length && tab === 'sources') paintSide();
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
  /** 회의록을 쓰는 동안 보여 주는 카드. 펜이 움직이고 줄이 차례로 써 내려가며, 지난 시간이 올라간다.
   *  단계별 진행률은 알 수 없으므로 지어내지 않고, 일이 돌아가고 있다는 것과 걸린 시간만 보여 준다. */
  function showMinutesWait(scroll = false): void {
    hideMinutesWait();
    const started = performance.now();
    const elapsed = h('b', null, '00:00');
    waitEl = h('div', { class: 'panel frame summary minutes-wait', role: 'status' },
      h('div', { class: 'mw-head' },
        h('div', { class: 'mw-pen' }, icon(PenLine, 22)),
        h('div', { class: 'mw-title' },
          h('h2', null, '회의록을 쓰는 중입니다'),
          h('p', null, `발언 ${cards.size}개를 다시 읽고 전체 흐름, 시간대별 쟁점, 합의와 결론을 정리합니다.`)),
        h('div', { class: 'mw-clock', tip: '쓰기 시작한 뒤 지난 시간', 'aria-hidden': 'true' }, icon(Hourglass, 14), elapsed)),
      h('div', { class: 'mw-lines', 'aria-hidden': 'true' }, [0, 1, 2, 3].map(() => h('i', null))));
    waitTimer = window.setInterval(() => { elapsed.textContent = fmtTime((performance.now() - started) / 1000); }, 1000);
    const below = [minutesEl, verdictEl, costEl, qaEl].find((el) => el?.isConnected);   // 다시 쓰는 중이면 예전 회의록 바로 위에
    if (below) below.before(waitEl);
    else inner.append(waitEl);
    if (scroll) waitEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
    else follow();
  }

  function hideMinutesWait(): void {
    window.clearInterval(waitTimer);
    waitEl?.remove();
    waitEl = null;
  }

  /** 토론 아래에 붙는 카드의 차례: 회의록, 판정, 총 비용, 묻고 답하기. 새로 만든 카드를 제자리에 넣는다. */
  function placeTail(el: HTMLElement): void {
    const order = [minutesEl, verdictEl, costEl, qaEl];
    const next = order.slice(order.indexOf(el) + 1).find((x) => x?.isConnected);
    if (next) next.before(el);
    else inner.append(el);
  }

  /** 회의록. partial이면 쓰이고 있는 중이라, 지금까지 온 항목만 그린다 (오지 않은 항목을 "없음"이라고 하지 않는다). */
  function showMinutes(m: any, opts: { scroll?: boolean; partial?: boolean } = {}): void {
    hideMinutesWait();
    const partial = !!opts.partial;
    const has = (key: string) => (partial ? m[key] !== undefined && (!Array.isArray(m[key]) || m[key].length > 0) : true);
    const list = (title: string, key: string) => (has(key) ? h('div', null, h('h3', null, title),
      m[key]?.length ? h('ul', null, m[key].map((it: string) => h('li', null, it))) : h('p', { class: 'muted' }, '없음')) : null);
    if (!minutesEl?.isConnected) {
      minutesEl = h('div', { class: 'panel frame summary minutes' });
      placeTail(minutesEl);
    }
    minutesEl.classList.toggle('is-writing', partial);
    clear(minutesEl);
    put(minutesEl,
      h('div', { class: 'minutes-tag' }, icon(partial ? LoaderCircle : FileText, 16, partial ? 'spin' : ''), partial ? '회의록 · 쓰는 중' : '회의록'),
      h('h2', null, m.title ?? ''),
      has('overview') ? h('h3', null, '전체 흐름') : null,
      has('overview') ? h('p', { class: 'minutes-over' }, m.overview) : null,
      (m.timeline ?? []).length ? h('div', null, h('h3', null, '시간대별 흐름'),
        h('div', { class: 'tl' }, m.timeline.map((t: any) => h('div', { class: 'tl-item' },
          h('div', { class: 'tl-when' }, h('b', null, t.time ?? ''), h('span', null, t.turns ?? '')),
          h('div', { class: 'tl-what' }, h('b', null, t.phase ?? ''), h('p', null, t.summary ?? ''),
            (t.issues ?? []).length ? h('ul', null, t.issues.map((it: string) => h('li', null, it))) : null))))) : null,
      list('안건', 'agenda'),
      has('discussions') ? h('h3', null, '주요 논의') : null,
      (m.discussions ?? []).map((d: any) => h('div', { class: 'issue' }, h('b', null, d.topic ?? ''),
        h('div', { class: 'issue-pos' }, (d.points ?? []).flatMap((pt: any) => [
          h('span', { style: `--c:${nameColor(pt.name ?? '')}` }, pt.name ?? ''), h('span', null, pt.point ?? '')])))),
      list('합의 사항', 'agreements'), list('미결 사항', 'open_issues'), list('후속 조치', 'follow_ups'),
      has('conclusion') ? h('div', { class: 'takeaway' }, m.conclusion) : null);
    if (partial || minutesTimes.length) reveal(minutesEl, minutesTimes);   // 다 쓴 순간에도 나오던 글자는 마저 흘러나온다
    if (!partial) minutesTimes = [];
    if (opts.scroll) minutesEl.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  /** 판정: 누가 더 설득력 있었는지. partial이면 쓰이고 있는 중이다. */
  function showVerdict(v: any, opts: { scroll?: boolean; partial?: boolean } = {}): void {
    const partial = !!opts.partial;
    if (!verdictEl?.isConnected) {
      verdictEl = h('div', { class: 'panel frame summary minutes verdict' });
      placeTail(verdictEl);
    }
    verdictEl.classList.toggle('is-writing', partial);
    const decided = !partial || v.reason !== undefined;   // 이름을 쓰는 도중에는 제목에 올리지 않는다
    const moment = v.best_moment ?? {};
    clear(verdictEl);
    put(verdictEl,
      h('div', { class: 'minutes-tag' }, icon(partial ? LoaderCircle : Scale, 16, partial ? 'spin' : ''), partial ? '판정 · 쓰는 중' : '판정'),
      decided ? h('h2', { class: 'verdict-head' }, v.winner ? icon(Trophy, 22) : null,
        v.winner ? h('span', { style: `--c:${nameColor(v.winner)}` }, v.winner) : null,
        v.winner ? '의 설득력이 가장 높았습니다' : '우열을 가리기 어려운 토론이었습니다') : h('h2', null, ''),
      v.reason ? h('p', { class: 'minutes-over' }, v.reason) : null,
      v.summary ? h('h3', null, '총평') : null,
      v.summary ? h('p', { class: 'minutes-over' }, v.summary) : null,
      (v.ranking ?? []).length ? h('h3', null, '참가자별 평가') : null,
      (v.ranking ?? []).map((r: any) => {
        const score = Math.max(0, Math.min(100, Number(r.score) || 0));
        return h('div', { class: 'issue verdict-row', style: `--c:${nameColor(r.name ?? '')}` },
          h('div', { class: 'verdict-who' }, h('b', null, r.name ?? ''),
            h('div', { class: 'verdict-bar', role: 'img', 'aria-label': `설득력 ${score}점` }, h('i', { style: `width:${score}%` })),
            h('span', { class: 'verdict-score' }, r.score === undefined ? '' : `${score}점`)),
          h('div', { class: 'issue-pos' },
            r.strengths ? h('span', null, '잘한 점') : null, r.strengths ? h('span', null, r.strengths) : null,
            r.weaknesses ? h('span', null, '아쉬운 점') : null, r.weaknesses ? h('span', null, r.weaknesses) : null));
      }),
      moment.why ? h('div', { class: 'takeaway' }, h('small', null, `가장 인상적인 장면 · ${moment.turn ?? ''} ${moment.name ?? ''}`), moment.why) : null,
      partial ? null : h('p', { class: 'muted small', style: 'margin-top:1rem' }, '어느 입장이 옳은지가 아니라 누가 토론을 더 잘했는지를 본 AI의 평가입니다.'));
    if (partial || verdictTimes.length) reveal(verdictEl, verdictTimes);
    if (!partial) verdictTimes = [];
    if (opts.scroll) verdictEl.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  /** 묻고 답하기: 끝난 토론을 두고 사용자가 묻고, 함께 지켜본 분석가(참가자가 아님)가 답한다. 회의록 아래로 쌓인다. */
  function showQa(): void {
    if (!record?.speeches?.length && !cards.size) return;
    const draft = (qaEl?.querySelector('.qa-input') as HTMLInputElement | null)?.value ?? '';
    qaEl?.remove();
    const items = h('div', { class: 'qa-list' });
    const item = (q: string, a: string) => {
      const answer = h('div', { class: 'qa-a' }, a);
      items.append(h('div', { class: 'qa-item' }, h('div', { class: 'qa-q' }, q), answer));
      return answer;
    };
    for (const it of record?.qa ?? []) item(it.q, it.a);
    const input = h('input', { class: 'input qa-input', maxlength: 2000, placeholder: '이 토론에 대해 물어보세요. 예) 왜 이 사람이 밀렸나요?', 'aria-label': '토론에 대한 질문' });
    input.value = draft;
    const sendBtn = h('button', { type: 'button', class: 'btn btn--icon', tip: '질문 보내기', 'aria-label': '질문 보내기' }, icon(Send, 18));
    const hints = h('div', { class: 'qa-hints' });
    const paintHints = () => {
      clear(hints);
      if (record?.qa?.length || asking) return;
      QUESTIONS.forEach((q) => hints.append(h('button', { type: 'button', class: 'chip', onclick: () => ask(q) }, q)));
    };
    const ask = async (text: string) => {
      const question = text.trim();
      if (!question || asking || !record) return;
      asking = true;
      input.value = '';
      input.disabled = true;
      sendBtn.disabled = true;
      paintHints();
      const answer = item(question, '');
      const row = answer.parentElement as HTMLElement;
      const wait = h('span', { class: 'sp-wait' }, h('i'), h('i'), h('i'));
      answer.append(wait);
      row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      let text2 = '';
      try {
        const res = await api.ask(id, question, (piece) => {
          text2 += piece;
          answer.textContent = text2;
          follow();
        });
        record.qa = res.qa;
        answer.textContent = res.qa[res.qa.length - 1]?.a ?? text2;
        applyCost(res);
      } catch (err) {
        row.remove();
        input.value = question;   // 다시 보낼 수 있게 돌려놓는다
        toast((err as Error).message, 'error');
      } finally {
        asking = false;
        input.disabled = false;
        sendBtn.disabled = false;
        paintHints();
        if (qaEl?.isConnected) input.focus({ preventScroll: true });
      }
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) ask(input.value); });
    sendBtn.addEventListener('click', () => ask(input.value));
    paintHints();
    qaEl = h('div', { class: 'panel frame summary qa' },
      h('div', { class: 'minutes-tag' }, icon(MessagesSquare, 16), '묻고 답하기'),
      h('p', { class: 'muted qa-note' }, '이 토론에 대해 궁금한 것을 물어보세요. 참가자가 아니라, 함께 지켜본 분석가의 입장에서 답합니다.'),
      items, hints, h('div', { class: 'qa-form' }, input, sendBtn));
    placeTail(qaEl);
  }

  /** 끝난 뒤에 든 비용(회의록, 판정, 답변)을 받아 총 비용을 다시 그린다. */
  function applyCost(res: { cost: number; cost_parts: Record<string, number> }): void {
    if (record) { record.cost = res.cost; record.cost_parts = res.cost_parts; }
    money.cost = res.cost;
    money.parts = res.cost_parts;
    paintCost();
    showCost();
  }

  function paintCost(): void {
    clockCost.textContent = fmtCost(money.cost, money.rate);
  }

  /** 끝난 토론의 맨 아래에 총 비용과 내역을 보여 준다. 회의록을 쓰면 그 비용까지 더해 다시 그린다. */
  function showCost(): void {
    const p = money.parts;
    const row = (label: string, usd: number, note = '') => h('div', { class: 'cost-row' },
      h('span', null, label, note ? h('small', null, note) : null), h('b', null, fmtCost(usd, money.rate)));
    const t = usage?.total ?? record?.usage;
    const old = costEl;
    const fresh = h('div', { class: `panel frame summary costcard${old ? ' is-redraw' : ''}` },
      h('div', { class: 'minutes-tag' }, icon(Coins, 16), '총 비용',
        infoTip(`측정된 토큰 수와 검색 건수에 공개 단가를 곱한 값입니다. 1달러 ${money.rate.toLocaleString()}원으로 계산했습니다.`)),
      h('h2', null, fmtCost(money.cost, money.rate)),
      h('div', { class: 'cost-rows' },
        row('토론 (토큰)', p.tokens ?? money.cost, t ? `입력 ${(t.input + t.cached + t.cache_write).toLocaleString()} · 출력 ${t.output.toLocaleString()} 토큰` : ''),
        row('웹 검색', p.search ?? 0, `${money.searches.toLocaleString()}건 × ${fmtCost(money.searchUsd, money.rate)}`),
        (p.prep ?? 0) > 0 ? row('참가자 생성', p.prep) : null,
        (p.minutes ?? 0) > 0 ? row('회의록', p.minutes) : null,
        (p.extra ?? 0) > 0 ? row('판정과 질문', p.extra, '토론이 끝난 뒤에 든 비용') : null));
    old?.remove();
    costEl = fresh;
    placeTail(fresh);   // 묻고 답하기는 비용 아래에 온다
  }

  async function writeMinutes(): Promise<void> {
    if (writingMinutes || !record) return;
    writingMinutes = true;
    paintControls();
    showMinutesWait(true);
    try {
      const res = await api.minutes(id, (part) => showMinutes(part, { partial: true }));   // 쓰이는 대로 보여 준다
      record.minutes = res.minutes;
      showMinutes(res.minutes);
      applyCost(res);
      toast('회의록을 만들었습니다.');
    } catch (err) {
      if (record.minutes) showMinutes(record.minutes);   // 쓰다 만 것을 치우고 예전 회의록으로 돌려놓는다
      else { minutesEl?.remove(); minutesEl = null; }
      toast((err as Error).message, 'error');
    } finally {
      hideMinutesWait();
      writingMinutes = false;
      paintControls();
    }
  }

  async function judge(): Promise<void> {
    if (judging || !record) return;
    judging = true;
    paintControls();
    showVerdict({}, { partial: true, scroll: true });
    try {
      const res = await api.verdict(id, (part) => showVerdict(part, { partial: true }));
      record.verdict = res.verdict;
      showVerdict(res.verdict);
      applyCost(res);
    } catch (err) {
      if (record.verdict) showVerdict(record.verdict);
      else { verdictEl?.remove(); verdictEl = null; }
      toast((err as Error).message, 'error');
    } finally {
      judging = false;
      paintControls();
    }
  }

  /** 서버가 꺼지거나 중단되어 끊긴 토론을, 마지막으로 끝난 발언 다음부터 이어 간다. */
  async function resumeDebate(): Promise<void> {
    if (resuming) return;
    resuming = true;
    paintControls();
    try {
      await api.resumeDebate(id);
      replaying = false;
      reset();
      stage.classList.remove('is-ended');
      await boot();
    } catch (err) {
      toast((err as Error).message, 'error');
    } finally {
      resuming = false;
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
        clock.max = ev.config.max_minutes ? ev.config.max_minutes * 60 : null;
        paintClock();
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
        else { setStatus('moderator', null); const m = seats.get('moderator'); if (m) setAvatar(m.av, { state: 'listening' }); for (const s of ev.sources ?? []) registry.register(s.url, s.title); if (tab === 'sources') paintSide(); }
        break;
      case 'briefing': briefing = ev.text; parseCitations(briefing, registry); if (tab === 'materials') paintSide(); break;
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
        clock.max = ev.max_seconds ?? null;
        setClock(Number(ev.seconds) || 0, instant || speed === 'instant');
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
      case 'summarizing': if (!instant) showMinutesWait(); break;
      case 'minutes_partial':   // 쓰이고 있는 회의록. 기록에는 남지 않고 지금 보는 화면에만 온다
        showMinutes(ev.minutes, { partial: true });
        follow();
        break;
      case 'minutes':
        if (record) record.minutes = ev.minutes;
        if (!instant) { showMinutes(ev.minutes); follow(); }
        break;
      case 'summary': addSummary(ev); break;
      case 'end':
        hideMinutesWait();   // 회의록을 쓰지 못하고 끝난 경우에도 대기 카드를 남기지 않는다
        if (minutesEl?.classList.contains('is-writing')) { minutesEl.remove(); minutesEl = null; }   // 쓰다가 실패한 회의록
        state = 'ended';
        liveCard = null;
        setClock(clock.base, true);
        phaseChip.querySelector('span')!.textContent = ev.state === 'aborted' ? '중단됨' : '토론 끝';
        if (speaking) setAvatar(seats.get(speaking)!.av, { state: 'listening' });
        speaking = null;
        placeSpotlight(null);
        seats.forEach((s) => { setAvatar(s.av, { wants: false }); s.tile.classList.remove('is-hot'); });
        paintBadges();
        paintControls();
        if (!instant) { showQa(); showCost(); follow(); }
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
    paintSeek();
    clear(controls);
    if (replaying) {
      controls.append(
        h('button', { type: 'button', class: 'btn', onclick: () => { replayPaused = !replayPaused; if (!replayPaused) stepReplay(); paintControls(); stage.classList.toggle('is-paused', replayPaused); } },
          icon(replayPaused ? Play : Pause, 18), replayPaused ? '이어 보기' : '멈춤'),
        segEl([['1', '1배'], ['2', '2배'], ['4', '4배']], String(replayRate), (v) => { replayRate = Number(v); paintControls(); }),
        h('button', { type: 'button', class: 'btn', onclick: () => showAll() }, icon(SkipForward, 18), '끝까지 보기'),
        h('span', { class: 'muted small' }, '지난 토론을 같은 박자로 다시 보는 중. 위의 타임라인을 누르거나 끌어 원하는 발언으로 옮길 수 있습니다'));
      return;
    }
    if (state === 'ended' || !record?.live) {
      const canResume = !!record?.resumable && !record.live;
      put(controls,
        canResume ? h('button', { type: 'button', class: 'btn btn--primary', disabled: resuming, tip: '끊긴 곳 다음 발언부터 토론을 이어 갑니다', onclick: () => resumeDebate() },
          icon(resuming ? LoaderCircle : StepForward, 18, resuming ? 'spin' : ''), resuming ? '이어 가는 중' : '이어 하기') : null,
        h('button', { type: 'button', class: `btn${canResume ? '' : ' btn--primary'}`, disabled: writingMinutes, onclick: () => writeMinutes() },
          icon(writingMinutes ? LoaderCircle : FileText, 18, writingMinutes ? 'spin' : ''),
          writingMinutes ? '회의록을 쓰는 중' : record?.minutes ? '회의록 다시 쓰기' : '회의록 쓰기'),
        h('button', { type: 'button', class: 'btn', disabled: judging, tip: '누가 더 설득력 있게 토론했는지 AI 심사위원의 평가를 받습니다', onclick: () => judge() },
          icon(judging ? LoaderCircle : Scale, 18, judging ? 'spin' : ''), judging ? '판정하는 중' : record?.verdict ? '다시 판정' : '판정'),
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
    hideMinutesWait();
    clear(inner);
    minutesEl = null;
    verdictEl = null;
    qaEl = null;
    costEl = null;
    liveCard = null;
    clock.base = 0;
    clock.shown = 0;
    paintClock();
    cards.clear();
    registry.clear();
    track.querySelectorAll('.tick').forEach((t) => t.remove());
    fill.style.width = '0%';
    head.style.left = '0%';
    speaking = null;
    lastSpeech = null;
    usage = null;
    state = 'running';
    clockTurn.textContent = '0';
  }

  /** 토론 아래에 붙는 것들을 한꺼번에 그린다: 회의록, 판정, 총 비용, 묻고 답하기. */
  function showTail(): void {
    if (record?.minutes) showMinutes(record.minutes);
    if (record?.verdict) showVerdict(record.verdict);
    showQa();
    showCost();
  }

  /* ---------- 타임라인: 눌러서, 끌어서 원하는 발언으로 ---------- */
  function buildMarks(): Mark[] {
    const out: Mark[] = [];
    let from = 0;
    let begin = -1;
    let speaker = '';
    (record?.events ?? []).forEach((ev, i) => {
      if (ev.type === 'ready' && begin < 0) begin = i;
      else if (ev.type === 'speech_start') { if (begin < 0) begin = i; speaker = ev.speaker; }
      else if (ev.type === 'speech_end' && ev.failed) begin = -1;
      else if (ev.type === 'clock' && begin >= 0) {
        const to = Math.min(100, (ev.progress ?? 0) * 100);
        out.push({ id: ev.turn, index: begin, from, to, name: seats.get(speaker)?.persona.name ?? '' });
        from = to;
        begin = -1;
      }
    });
    return out;
  }
  const seekable = () => !!record && !record.live && marks.length > 0 && (replaying || state === 'ended');
  const markAt = (pct: number) => marks.find((m) => pct <= m.to) ?? marks[marks.length - 1];
  const pctOf = (e: PointerEvent) => {
    const box = track.getBoundingClientRect();
    return Math.max(0, Math.min(100, ((e.clientX - box.left) / Math.max(box.width, 1)) * 100));
  };
  let current = -1;   // 타임라인에서 마지막으로 고른 발언 (marks의 자리)
  let dragging = false;

  function previewMark(e: PointerEvent): void {
    const pct = pctOf(e);
    const mark = markAt(pct);
    scrubTip.textContent = `#${mark.id} ${mark.name}`;
    scrubTip.style.left = `${pct}%`;
    scrubTip.classList.add('is-on');
  }

  /** 그 발언으로 간다. 다시 보는 중이면 거기서부터 다시 흐르고, 다 펼쳐 둔 화면이면 그 발언이 보이게 옮긴다. */
  function goToMark(at: number): void {
    const mark = marks[Math.max(0, Math.min(marks.length - 1, at))];
    if (!mark || !record) return;
    current = marks.indexOf(mark);
    timeline.setAttribute('aria-valuenow', String(Math.round(mark.from)));
    timeline.setAttribute('aria-valuetext', `#${mark.id} ${mark.name}`);
    if (!replaying) {
      const card = cards.get(mark.id)?.root;
      if (!card) return;
      card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      card.classList.remove('is-flash');
      void card.offsetWidth;
      card.classList.add('is-flash');
      return;
    }
    window.clearTimeout(replayTimer);
    reset();
    for (let k = 0; k < mark.index; k += 1) handle(record.events[k], true);   // 그 앞까지는 한 번에 펼친다
    replayIndex = mark.index;
    stage.classList.remove('is-ended');
    stage.classList.toggle('is-paused', replayPaused);
    stick = true;
    transcript.scrollTop = transcript.scrollHeight;
    paintControls();
    stepReplay();
  }

  timeline.addEventListener('pointerdown', (e) => {
    if (!seekable() || e.button !== 0) return;
    dragging = true;
    timeline.setPointerCapture(e.pointerId);
    previewMark(e);
  });
  timeline.addEventListener('pointermove', (e) => { if (seekable()) previewMark(e); });
  timeline.addEventListener('pointerup', (e) => {
    if (!dragging) return;
    dragging = false;
    if (seekable()) goToMark(marks.indexOf(markAt(pctOf(e))));
  });
  timeline.addEventListener('pointercancel', () => { dragging = false; scrubTip.classList.remove('is-on'); });
  timeline.addEventListener('pointerleave', () => { if (!dragging) scrubTip.classList.remove('is-on'); });
  timeline.addEventListener('keydown', (e) => {
    if (!seekable() || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
    e.preventDefault();
    let at = current;
    if (replaying) at = marks.reduce((found, m, i) => (m.index <= replayIndex ? i : found), 0);
    goToMark(at + (e.key === 'ArrowRight' ? 1 : -1));
  });
  function paintSeek(): void {
    const on = seekable();
    timeline.classList.toggle('is-seekable', on);
    if (on) timeline.setAttribute('tabindex', '0');
    else timeline.removeAttribute('tabindex');
    timeline.dataset.tip = on ? (replaying ? '누르거나 끌어서 원하는 발언부터 다시 봅니다' : '눌러서 그 발언으로 갑니다') : '';
    if (!on) scrubTip.classList.remove('is-on');
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
    liveCard = null;
    if (record.resumable) {   // 끝까지 가지 못한 토론
      phaseChip.querySelector('span')!.textContent = '끊김';
      addNotice('warn', `토론이 #${record.speeches?.length ?? 0} 발언 뒤에 끊겼습니다. 아래의 '이어 하기'를 누르면 다음 발언부터 이어 갑니다.`);
    }
    loadMoney();
    showTail();
    marks = buildMarks();
    paintBadges();
    paintControls();
    paintSide();
    stage.classList.add('is-ended');
    transcript.scrollTop = 0;
  }

  function stepReplay(): void {
    if (!record || disposed || !replaying || replayPaused) return;
    const events = record.events;
    const finish = () => { replaying = false; state = 'ended'; liveCard = null; loadMoney(); showTail(); paintControls(); stage.classList.add('is-ended'); };
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
    marks = buildMarks();
    replaying = true;
    replayPaused = false;
    replayIndex = 0;
    stick = true;
    stage.classList.remove('is-ended');
    paintControls();
    stepReplay();
  }

  /* ---------- 시작 ---------- */
  async function boot(): Promise<void> {
    try {
      record = await api.debate(id);
    } catch (err) {
      root.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, h('h3', null, '토론을 찾지 못했습니다'), h('p', null, (err as Error).message))));
      return;
    }
    if (disposed) return;
    paintSide();
    if (!record.live) { showAll(); return; }
    // 진행 중인 토론: 지금까지의 것은 한 번에 펼치고, 그 뒤부터 이어서 받는다 (새로고침이나 이어 하기 뒤에도 같다)
    for (const ev of record.events) handle(ev, true);
    lastIndex = record.events.length - 1;
    transcript.scrollTop = transcript.scrollHeight;
    paintControls();
    stream?.close();
    stream = new EventSource(`/api/debates/${id}/events?since=${lastIndex + 1}`);
    stream.onmessage = (msg) => {
      const ev = JSON.parse(msg.data) as DebateEvent;
      if (ev.i >= 0) {   // i가 -1인 것은 기록에 남지 않는 임시 이벤트(쓰이고 있는 회의록)
        if (ev.i <= lastIndex) return;   // 다시 연결되면 앞의 것부터 다시 오므로 본 것은 건너뛴다
        lastIndex = ev.i;
        record!.events[ev.i] = ev;
      }
      handle(ev, false);
      if (ev.type === 'end') {
        stream?.close();
        record!.live = false;
        paintControls();
        api.debate(id).then((saved) => {
          if (disposed) return;
          record = saved;
          marks = buildMarks();
          loadMoney();
          showCost();
          paintControls();
        }).catch(() => undefined);
      }
    };
  }
  void boot();

  return () => {
    disposed = true;
    stream?.close();
    observer.disconnect();
    cancelAnimationFrame(glide);
    window.clearTimeout(replayTimer);
    window.clearInterval(waitTimer);
    window.clearInterval(clockTimer);
  };
}
