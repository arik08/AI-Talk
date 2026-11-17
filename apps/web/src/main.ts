import '@fontsource/noto-sans-kr/400.css';
import '@fontsource/noto-sans-kr/500.css';
import '@fontsource/noto-sans-kr/600.css';
import '@fontsource/noto-serif-kr/500.css';
import '@fontsource/noto-serif-kr/600.css';
import '@fontsource/noto-serif-kr/700.css';
import '@fontsource/cinzel/700.css';
import './styles/app.css';
import './styles/avatar.css';

import { History, KeyRound, MessagesSquare, Settings, Users } from 'lucide';
import { api } from './api';
import type { Status } from './types';
import { clear, h, icon, installTooltips } from './ui/dom';
import { mountHistory } from './views/history';
import { mountNewDebate } from './views/newDebate';
import { mountPersonas } from './views/personas';
import { mountSettings } from './views/settings';
import { mountStage } from './views/stage';

export interface AppContext {
  status: Status | null;
  refreshStatus: () => Promise<Status | null>;
  go: (hash: string) => void;
  reload: () => void;
}

const NAV = [
  { hash: '#/', label: '새 토론', icon: MessagesSquare },
  { hash: '#/personas', label: '페르소나', icon: Users },
  { hash: '#/history', label: '지난 토론', icon: History },
  { hash: '#/settings', label: '설정', icon: Settings },
];
const PROVIDER_LABEL: Record<string, string> = { claude: 'Claude', pgpt: 'P-GPT', mock: '시험용(mock)' };

const app = document.getElementById('app')!;
const prov = h('div', { class: 'prov', tip: '지금 쓰는 AI. .env의 AITALK_PROVIDER로 바꿉니다' }, h('i'), h('span', null, '연결 확인 중'));
const nav = h('nav', { class: 'nav' }, NAV.map((n) => h('a', { class: 'nav-link', href: n.hash }, icon(n.icon, 18), n.label)));
const view = h('main', { id: 'view' });
app.append(
  h('header', { class: 'topbar' },
    h('a', { class: 'logo', href: '#/', html: 'AI<span>·</span>TALK' }), nav,
    h('div', { class: 'topbar-right' }, prov)),
  view,
);
installTooltips();

const ctx: AppContext = {
  status: null,
  async refreshStatus() {
    try {
      ctx.status = await api.status();
      needCode = false;
    } catch (err) {
      ctx.status = null;
      needCode = (err as any).status === 401;
    }
    const s = ctx.status;
    prov.classList.toggle('is-off', !s?.ready);
    prov.querySelector('span')!.textContent = s
      ? `${PROVIDER_LABEL[s.provider] ?? s.provider}${s.ready ? '' : ' · 준비 안 됨'}`
      : '서버 연결 안 됨';
    return s;
  },
  go(hash) { window.location.hash = hash; },
  reload() { route(); },
};

let cleanup: (() => void) | void;
let needCode = false;

/** 다른 PC에서 들어왔고 접속 코드가 걸려 있을 때 보이는 화면. */
function mountEnter(root: HTMLElement): void {
  const input = h('input', { class: 'input', type: 'password', placeholder: '접속 코드', autocomplete: 'off' });
  const note = h('p', { class: 'muted small', style: 'min-height:1.5rem;margin-top:.5rem' });
  const submit = async () => {
    try {
      await api.enter(input.value);
      await ctx.refreshStatus();
      route();
    } catch (err) {
      note.textContent = (err as Error).message;
    }
  };
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  root.append(h('div', { class: 'page', style: 'max-width:26rem' },
    h('div', { class: 'panel frame card-pad', style: 'margin-top:4rem' },
      h('h2', { class: 'block-title', style: 'margin-bottom:.5rem' }, icon(KeyRound, 20), '접속 코드'),
      h('p', { class: 'muted', style: 'margin-bottom:1rem' }, '이 AI-Talk의 주인이 정한 접속 코드를 적어 주세요.'),
      h('div', { class: 'row', style: 'flex-wrap:nowrap' }, input, h('button', { type: 'button', class: 'btn btn--primary', onclick: submit }, '들어가기')),
      note)));
  input.focus();
}

function route(): void {
  const hash = window.location.hash || '#/';
  if (cleanup) cleanup();
  cleanup = undefined;
  clear(view);
  if (needCode) { mountEnter(view); return; }
  const top = hash.startsWith('#/stage/') ? '' : hash;
  nav.querySelectorAll('.nav-link').forEach((a) => a.classList.toggle('is-active', a.getAttribute('href') === top));
  if (hash.startsWith('#/stage/')) cleanup = mountStage(view, hash.slice('#/stage/'.length), ctx);
  else if (hash === '#/personas') cleanup = mountPersonas(view, ctx);
  else if (hash === '#/history') cleanup = mountHistory(view, ctx);
  else if (hash === '#/settings') cleanup = mountSettings(view, ctx);
  else cleanup = mountNewDebate(view, ctx);
  window.scrollTo(0, 0);
}

window.addEventListener('hashchange', route);
ctx.refreshStatus().finally(route);
