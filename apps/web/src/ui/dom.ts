import { createElement, Trash2, TriangleAlert, type IconNode } from 'lucide';

type Child = Node | string | number | null | undefined | false;

/** 작은 DOM 헬퍼. h('div', { class: 'a', onclick }, child...) */
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K, props?: Record<string, any> | null, ...children: (Child | Child[])[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'tip') el.dataset.tip = value;
    else if (key === 'html') el.innerHTML = value;
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else if (key === 'value' && 'value' in el) (el as any).value = value;
    else if (key === 'checked' || key === 'disabled' || key === 'selected') (el as any)[key] = !!value;
    else el.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

/** Lucide 아이콘. 직접 그리지 않고 세트에서 가져온다. */
export function icon(node: IconNode, size = 18, cls = ''): SVGElement {
  const svg = createElement(node, { width: size, height: size, 'stroke-width': 1.75 } as any);
  svg.classList.add('ico');
  if (cls) svg.classList.add(...cls.split(' '));
  svg.setAttribute('aria-hidden', 'true');
  return svg;
}

/** 빈 값(null, false)을 걸러 가며 자식을 붙인다. */
export function put(el: Element, ...children: (Child | Child[])[]): void {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : String(child));
  }
}

export function clear(el: Element): void {
  while (el.firstChild) el.removeChild(el.firstChild);
}

/* ---------- 툴팁: 마우스를 1초 이상 올려 두었을 때만 뜬다 ---------- */
let tipEl: HTMLElement | null = null;
let tipTimer = 0;
let tipTarget: HTMLElement | null = null;

function hideTip(): void {
  window.clearTimeout(tipTimer);
  tipTarget = null;
  tipEl?.classList.remove('is-on');
}

function showTip(target: HTMLElement): void {
  const text = target.dataset.tip;
  if (!text || !target.isConnected) return;
  if (!tipEl) {
    tipEl = h('div', { class: 'tip', role: 'tooltip' });
    document.body.append(tipEl);
  }
  tipEl.textContent = text;
  const rect = target.getBoundingClientRect();
  tipEl.classList.add('is-on');
  const box = tipEl.getBoundingClientRect();
  let left = rect.left + rect.width / 2 - box.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - box.width - 8));
  let top = rect.top - box.height - 8;
  if (top < 8) top = rect.bottom + 8;
  if (target.dataset.tipSide === 'left' && rect.left - box.width - 8 >= 8) {   // 긴 설명은 옆에 띄워 위아래 이웃을 가리지 않는다
    left = rect.left - box.width - 8;
    top = Math.max(8, Math.min(rect.top, window.innerHeight - box.height - 8));
  }
  tipEl.style.left = `${left}px`;
  tipEl.style.top = `${top}px`;
}

export function installTooltips(): void {
  document.addEventListener('mouseover', (e) => {
    const target = (e.target as HTMLElement).closest?.('[data-tip]') as HTMLElement | null;
    if (target === tipTarget) return;
    hideTip();
    if (!target) return;
    tipTarget = target;
    tipTimer = window.setTimeout(() => showTip(target), 1000);
  });
  document.addEventListener('mousedown', hideTip, true);
  document.addEventListener('keydown', hideTip, true);
  // 대상이 들어 있는 곳이 스크롤될 때만 숨긴다. 토론 중에는 대화창이 계속 흘러내리므로,
  // 아무 스크롤에나 숨기면 옆의 인물 칸에서는 툴팁이 뜰 틈이 없다
  document.addEventListener('scroll', (e) => {
    if (tipTarget && e.target instanceof Node && e.target.contains(tipTarget)) hideTip();
  }, true);
  window.addEventListener('blur', hideTip);
}

/* ---------- 전체화면: 어느 화면에서든 마우스 우클릭으로 켜고 끈다. Esc로도 풀린다 ---------- */
export function installFullscreen(): void {
  let busy = false;   // 전환이 끝나기 전에 또 누른 것은 무시한다
  // 캡처 단계에서 문서 전체에 한 번만 건다. 상단 메뉴, 입력 칸, 팝업 위에서도 같게 동작하고 화면을 옮겨도 남는다
  document.addEventListener('contextmenu', (e) => {
    if (e.button !== 2) return;   // 메뉴 키와 Shift+F10은 브라우저의 메뉴를 그대로 둔다
    e.preventDefault();
    if (busy) return;
    const root = document.documentElement;   // 본문에 붙는 툴팁과 알림까지 함께 보이도록 문서 전체를 대상으로 한다
    if (!document.fullscreenEnabled || typeof root.requestFullscreen !== 'function') {
      toast('이 브라우저에서는 전체화면을 쓸 수 없습니다.', 'error');
      return;
    }
    busy = true;
    const going = document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen();
    Promise.resolve(going)
      .catch(() => toast('전체화면으로 바꾸지 못했습니다. 다시 눌러 주세요.', 'error'))
      .finally(() => { busy = false; });
  }, true);
}

/* ---------- 삭제 버튼: 휴지통 → 경고 아이콘 → 한 번 더 눌러야 지운다 ---------- */
export function deleteButton(onDelete: () => void, size = 18): HTMLButtonElement {
  let armed = false;
  let timer = 0;
  const btn = h('button', { class: 'btn btn--icon del', type: 'button', tip: '삭제', 'aria-label': '삭제' });
  const paint = () => {
    clear(btn);
    btn.append(icon(armed ? TriangleAlert : Trash2, size));
    btn.dataset.tip = armed ? '삭제 경고' : '삭제';
    btn.setAttribute('aria-label', armed ? '삭제 경고' : '삭제');
    btn.classList.toggle('is-armed', armed);
  };
  const disarm = () => {
    window.clearTimeout(timer);
    if (!armed) return;
    armed = false;
    paint();
  };
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!armed) {
      armed = true;
      paint();
      timer = window.setTimeout(disarm, 4000);
      return;
    }
    window.clearTimeout(timer);
    onDelete();
  });
  btn.addEventListener('blur', disarm);
  paint();
  return btn;
}

/* ---------- 알림 ---------- */
export function toast(message: string, kind: 'info' | 'error' = 'info'): void {
  let host = document.querySelector('.toasts');
  if (!host) {
    host = h('div', { class: 'toasts', 'aria-live': 'polite' });
    document.body.append(host);
  }
  const el = h('div', { class: `toast toast--${kind}` }, message);
  host.append(el);
  window.setTimeout(() => el.classList.add('is-out'), kind === 'error' ? 6000 : 3200);
  window.setTimeout(() => el.remove(), kind === 'error' ? 6400 : 3600);
}

export function fmtTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

export const USD_KRW = 1350;   // 서버의 고정 환율과 같다. 서버가 알려 주는 값이 있으면 그것을 쓴다

/**
 * 달러 금액을 원화로 적는다. 0.1원 미만은 0원, 0.1원 이상 1원 미만은 소수 한 자리, 1원 이상은 정수.
 */
export function fmtCost(usd: number, rate = USD_KRW): string {
  const won = Math.max(0, usd || 0) * rate;
  if (won < 0.1) return '0원';
  if (won < 1) {
    const one = Math.round(won * 10) / 10;
    return one >= 1 ? '1원' : `${one.toFixed(1)}원`;
  }
  return `${Math.round(won).toLocaleString()}원`;
}

/** 모델 단가(100만 토큰당)는 공개 요금표 그대로 달러로 적는다. 비용은 fmtCost로 원화. 예: $0.1, $2.5, $10 */
export function fmtUsd(usd: number): string {
  const value = Math.max(0, usd || 0);
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 3 })}`;
}

export function safeColor(value: string | undefined, fallback = '#E8C170'): string {
  return value && /^#[0-9a-fA-F]{6}$/.test(value) ? value : fallback;
}
