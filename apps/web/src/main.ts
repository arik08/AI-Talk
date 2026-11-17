import '@fontsource/noto-sans-kr/400.css';
import '@fontsource/noto-sans-kr/500.css';
import '@fontsource/noto-sans-kr/600.css';
import '@fontsource/noto-serif-kr/500.css';
import '@fontsource/noto-serif-kr/600.css';
import '@fontsource/noto-serif-kr/700.css';
import '@fontsource/cinzel/700.css';
import './styles/app.css';
import './styles/avatar.css';

import { History, MessagesSquare, Settings, Users } from 'lucide';
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
    } catch {
      ctx.status = null;
    }
    const s = ctx.status;
    prov.classList.toggle('is-off', !s?.ready);
    prov.querySelector('span')!.textContent = s
      ? `${PROVIDER_LABEL[s.provider] ?? s.provider}${s.ready ? '' : ' · 준비 안 됨'}`
      : '서버 연결 안 됨';
    return s;
  },
  go(hash) { window.location.hash = hash; },
};

let cleanup: (() => void) | void;

function route(): void {
  const hash = window.location.hash || '#/';
  if (cleanup) cleanup();
  cleanup = undefined;
  clear(view);
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
