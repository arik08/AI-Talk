import { parseCitations, type CitationRegistry, type Segment } from '../citations';
import { isPlain, parseSpeech, type Block, type Inline } from '../speechMarkup';
import { h } from './dom';
import { citeLink } from './sources';

/** 글자 하나가 언제 나타날지. 밀리초 뒤(음수면 이미 나타나는 중), null이면 움직임 없이 그린다. */
export type CharDelay = (index: number) => number | null;

interface Pen { index: number; delay?: CharDelay }

function drawText(target: HTMLElement, text: string, pen: Pen): void {
  let plain = '';
  for (const ch of Array.from(text)) {
    const delay = pen.delay ? pen.delay(pen.index) : null;
    pen.index += 1;
    if (delay === null) { plain += ch; continue; }
    if (plain) { target.append(plain); plain = ''; }
    target.append(h('span', { class: 'ch', style: `animation-delay:${Math.round(delay)}ms` }, ch));
  }
  if (plain) target.append(plain);
}

function drawInlines(target: HTMLElement, items: Inline[], pen: Pen): void {
  for (const item of items) {
    if (item.kind === 'cite') { if (item.url) target.append(citeLink(item.n, item.url)); continue; }
    if (!item.bold) { drawText(target, item.text, pen); continue; }
    const strong = h('strong');
    drawText(strong, item.text, pen);
    target.append(strong);
  }
}

const fmtNum = (n: number) => n.toLocaleString('ko-KR', { maximumFractionDigits: 2 });

function drawBlock(block: Block, pen: Pen): HTMLElement {
  if (block.kind === 'para') {
    const p = h('div', { class: 'sp-p' });
    drawInlines(p, block.inlines, pen);
    return p;
  }
  if (block.kind === 'list') {
    const list = h(block.ordered ? 'ol' : 'ul', { class: 'sp-list', start: block.ordered && block.start !== 1 ? block.start : null });
    for (const item of block.items) {
      const li = h('li');
      drawInlines(li, item, pen);
      list.append(li);
    }
    return list;
  }
  if (block.kind === 'table') {
    const row = (cells: Inline[][], tag: 'th' | 'td') => h('tr', null, cells.map((cell) => {
      const el = h(tag, tag === 'th' ? { scope: 'col' } : null);
      drawInlines(el, cell, pen);
      return el;
    }));
    return h('div', { class: 'sp-table-wrap' },
      h('table', { class: 'sp-table' }, h('thead', null, row(block.head, 'th')), h('tbody', null, block.rows.map((r) => row(r, 'td')))));
  }
  // 막대 그림: 항목마다 가로 막대 하나. 값은 막대 옆에 그대로 적는다 (색만으로 읽게 하지 않는다)
  const max = Math.max(...block.bars.map((b) => Math.abs(b.value)), 0) || 1;
  const caption = [block.title, block.unit ? `(${block.unit})` : ''].filter(Boolean).join(' ');
  return h('figure', { class: 'sp-chart' },
    caption ? h('figcaption', null, caption) : null,
    h('div', { class: 'sp-bars', role: 'list' }, block.bars.map((bar) =>
      h('div', { class: 'sp-bar', role: 'listitem', tip: `${bar.label}: ${bar.text}` },
        h('span', { class: 'sp-bar-label' }, bar.label),
        h('span', { class: 'sp-bar-track' },
          h('i', { style: `--v:${(Math.abs(bar.value) / max).toFixed(4)}` }),
          h('span', { class: 'sp-bar-val' }, /[^\d\s.,-]/.test(bar.text) ? bar.text : fmtNum(bar.value)))))));
}

/** 읽어 둔 덩어리들이 화면에서 차지하는 글자 수 (막대 그림은 세지 않는다). */
export function speechLength(blocks: Block[]): number {
  const count = (items: Inline[]) => items.reduce((sum, s) => sum + (s.kind === 'text' ? Array.from(s.text).length : 0), 0);
  return blocks.reduce((sum, b) => {
    if (b.kind === 'para') return sum + count(b.inlines);
    if (b.kind === 'list') return sum + b.items.reduce((a, it) => a + count(it), 0);
    if (b.kind === 'table') return sum + [b.head, ...b.rows].reduce((a, r) => a + r.reduce((c, cell) => c + count(cell), 0), 0);
    return sum;
  }, 0);
}

/**
 * 읽어 둔 덩어리들을 그려 넣는다. 본문을 HTML로 해석하지 않는다.
 * 돌려주는 것은 마지막 문장 옆에 무언가(끊김 표시, 출처 버튼)를 붙일 자리다.
 */
export function drawSpeech(target: HTMLElement, blocks: Block[], delay?: CharDelay): HTMLElement {
  const pen: Pen = { index: 0, delay };
  target.classList.toggle('sp-rich', !isPlain(blocks));
  if (isPlain(blocks)) {   // 줄글뿐이면 예전처럼 바로 넣는다
    if (blocks[0]?.kind === 'para') drawInlines(target, blocks[0].inlines, pen);
    return target;
  }
  let tail = target;
  for (const block of blocks) {
    const el = drawBlock(block, pen);
    target.append(el);
    tail = block.kind === 'para' ? el : target;
  }
  return tail;
}

/** 발언 글을 각주와 구조(굵게, 목록, 표, 막대 그림)가 있는 모양으로 그려 넣는다. */
export function renderSpeech(target: HTMLElement, text: string, registry: CitationRegistry): HTMLElement {
  return drawSpeech(target, parseSpeech(parseCitations(text, registry)));
}

export function speechBlocks(segments: Segment[], streaming: boolean): Block[] {
  return parseSpeech(segments, { streaming });
}
