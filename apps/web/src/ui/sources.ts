import { Link } from 'lucide';
import {
  displayTitle, groupByHost, parseCitations, type CitationRegistry, type Segment, type SourceEntry,
} from '../citations';
import { h, icon } from './dom';
import { loadTitles } from './sourceTitles';

/** 본문 속 번호 각주. 누르면 그 자료가 새 탭에서 열린다. */
export function citeLink(n: number, url: string): HTMLAnchorElement {
  return h('a', { class: 'fn', href: url, target: '_blank', rel: 'noopener noreferrer', 'aria-label': `출처 ${n}` }, `[${n}]`);
}

export function segmentNodes(segments: Segment[]): (Node | string)[] {
  return segments.map((s) => (s.kind === 'text' ? s.text : citeLink(s.n, s.url)));
}

/** 글을 각주가 달린 모양으로 그려 넣는다. 본문을 HTML로 해석하지 않는다. */
export function renderCited(target: HTMLElement, text: string, registry: CitationRegistry, streaming = false): void {
  target.append(...segmentNodes(parseCitations(text, registry, { streaming })));
}

function tipOf(entry: SourceEntry): string {
  const name = displayTitle(entry);
  return name === entry.url ? entry.url : `${name}\n${entry.url}`;
}

/** 호스트별로 묶은 출처 목록. 항목 앞의 번호는 본문의 각주 번호와 같다. */
export function sourceList(entries: SourceEntry[], registry: CitationRegistry): { root: HTMLElement; refresh: () => void } {
  const names = new Map<string, { link: HTMLAnchorElement; name: HTMLElement }>();
  const root = h('div', { class: 'srcs' }, groupByHost(entries).map((group) =>
    h('div', { class: 'srcs-group' },
      h('div', { class: 'srcs-host' }, group.host.replace(/^www\./, '')),
      group.items.map((entry) => {
        const name = h('span', { class: 'srcs-name' }, displayTitle(entry));
        const link = h('a', { class: 'srcs-item', href: entry.url, target: '_blank', rel: 'noopener noreferrer', tip: tipOf(entry) },
          h('span', { class: 'srcs-no' }, `[${entry.n}]`), name);
        names.set(entry.url, { link, name });
        return link;
      }))));
  let asked = false;
  /** 실제 탭 제목을 불러와 이름과 툴팁을 바꾼다. 번호와 링크는 그대로다. 실패하면 지금 표시를 둔다. */
  const refresh = () => {
    if (asked) return;
    asked = true;
    loadTitles(entries.map((e) => e.url)).then((titles) => {
      for (const entry of entries) {
        const title = titles.get(entry.url);
        if (!title) continue;
        registry.setPageTitle(entry.url, title);
        const row = names.get(entry.url);
        if (!row) continue;
        row.name.textContent = displayTitle(entry);
        row.link.dataset.tip = tipOf(entry);
      }
    }).catch(() => undefined);
  };
  return { root, refresh };
}

/**
 * 발언 끝에 붙는 링크 아이콘 버튼과, 누르면 아래에 펼쳐지는 목록.
 * 접혀 있는 동안에는 제목을 조회하지 않는다.
 */
export function sourceToggle(entries: SourceEntry[], registry: CitationRegistry): { button: HTMLButtonElement; panel: HTMLElement } {
  const panel = h('div', { class: 'src-panel hidden' });
  const button = h('button', { type: 'button', class: 'src-btn', tip: '출처 보기', 'aria-label': '출처 보기', 'aria-expanded': 'false' }, icon(Link, 15));
  let list: ReturnType<typeof sourceList> | null = null;
  button.addEventListener('click', () => {
    const open = panel.classList.toggle('hidden') === false;
    if (open) {
      if (!list) { list = sourceList(entries, registry); panel.append(list.root); }
      list.refresh();
    }
    const label = open ? '출처 접기' : '출처 보기';
    button.dataset.tip = label;
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-expanded', String(open));
    button.classList.toggle('is-on', open);
  });
  return { button, panel };
}
