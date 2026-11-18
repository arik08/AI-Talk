/**
 * 발언 본문의 구조를 읽는다: 굵게, 목록, 표, 막대 그림.
 *
 * DOM을 쓰지 않는 순수 함수만 둔다 (Node에서 바로 시험한다: npm test).
 * 참가자는 대부분 줄글로 말하고, 근거를 늘어놓거나 수치를 견줄 때만 아래 표기를 쓴다.
 * - `**굵게**`
 * - 줄 앞의 `- ` 또는 `1. ` → 목록
 * - `| 가 | 나 |` 줄들 → 표 (첫 줄이 머리글, `|---|` 줄은 버린다)
 * - ```` ```chart ```` 블록 → 막대 그림. 안에는 `제목: …`, `단위: …`, `항목: 값` 줄
 * 글자가 흘러나오는 중(streaming)에는 아직 닫히지 않은 표기를 기호 그대로 보여 주지 않는다.
 */
import type { Segment } from './citations';

export type Inline =
  | { kind: 'text'; text: string; bold: boolean }
  | { kind: 'cite'; n: number; url: string };

export interface Bar { label: string; value: number; text: string }

export type Block =
  | { kind: 'para'; inlines: Inline[] }
  | { kind: 'list'; ordered: boolean; start: number; items: Inline[][] }
  | { kind: 'table'; head: Inline[][]; rows: Inline[][][] }
  | { kind: 'chart'; title: string; unit: string; bars: Bar[] };

const MARK = '\u0000';   // 각주가 놓일 자리: \0번호\0
const CHART_LANG = /^(chart|bar|bars|차트|막대|그래프)$/i;
const FENCE = /^\s*```\s*([^\s`]*)\s*$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*(\d{1,2})[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,4}\s+(.*)$/;
const TABLE_ROW = /^\s*\|/;

function inlines(text: string, urls: Map<number, string>, streaming: boolean, bold = false): Inline[] {
  let src = text;
  if (streaming) src = src.replace(/\*$/, '');   // 끝에 걸친 '*'는 '**'가 될 수 있다
  const marks = src.split('**').length - 1;
  let literal = !streaming && marks % 2 === 1 ? marks : -1;   // 짝이 없는 마지막 '**'는 글자로 둔다
  const out: Inline[] = [];
  const push = (part: string, isBold: boolean) => {
    part.split(new RegExp(`${MARK}(\\d+)${MARK}`)).forEach((piece, index) => {
      if (index % 2) {
        const n = Number(piece);
        out.push({ kind: 'cite', n, url: urls.get(n) ?? '' });
      } else if (piece) {
        const last = out[out.length - 1];
        if (last && last.kind === 'text' && last.bold === isBold) last.text += piece;
        else out.push({ kind: 'text', text: piece, bold: isBold });
      }
    });
  };
  let on = bold;
  let seen = 0;
  src.split('**').forEach((part, index) => {
    if (index > 0) {
      seen += 1;
      if (seen === literal) { push('**', on); literal = -1; } else on = !on;
    }
    push(part, on || bold);
  });
  return out;
}

function cells(line: string): string[] {
  const parts = line.trim().split('|').map((c) => c.trim());
  if (parts[0] === '') parts.shift();
  if (parts.length && parts[parts.length - 1] === '') parts.pop();
  return parts;
}

const isRule = (row: string[]) => row.length > 0 && row.every((c) => /^[:\-\s]*$/.test(c)) && row.some((c) => c.includes('-'));

function chart(lines: string[]): Block {
  let title = '';
  let unit = '';
  const bars: Bar[] = [];
  for (const raw of lines) {
    const line = raw.replace(new RegExp(`${MARK}\\d+${MARK}`, 'g'), '').replace(/\*\*/g, '').replace(/^\s*[-*•]\s+/, '').trim();
    const m = /^(.+?)\s*[:：]\s*(.*)$/.exec(line);
    if (!m) continue;
    const [, key, rest] = m;
    if (/^(제목|title)$/i.test(key)) { title = rest; continue; }
    if (/^(단위|unit)$/i.test(key)) { unit = rest; continue; }
    const num = /-?\d[\d,]*(?:\.\d+)?/.exec(rest);
    if (!num) continue;
    const value = Number(num[0].replace(/,/g, ''));
    if (Number.isFinite(value)) bars.push({ label: key, value, text: rest });
  }
  return { kind: 'chart', title, unit, bars };
}

/** 각주로 나눈 본문을 구조가 있는 덩어리들로 읽는다. */
export function parseSpeech(segments: Segment[], opts: { streaming?: boolean } = {}): Block[] {
  const streaming = !!opts.streaming;
  const urls = new Map<number, string>();
  const flat = segments.map((s) => {
    if (s.kind === 'text') return s.text.split(MARK).join('');
    urls.set(s.n, s.url);
    return `${MARK}${s.n}${MARK}`;
  }).join('');
  const lines = flat.split('\n');
  const blocks: Block[] = [];
  let para: string[] = [];
  const flushPara = () => {
    const text = para.join('\n');
    para = [];
    if (text.trim()) blocks.push({ kind: 'para', inlines: inlines(text, urls, streaming) });
  };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const fence = FENCE.exec(line);
    if (fence) {
      let end = i + 1;
      while (end < lines.length && !FENCE.test(lines[end])) end += 1;
      const body = lines.slice(i + 1, end);
      const made = CHART_LANG.test(fence[1]) ? chart(body) : null;
      flushPara();
      if (made && made.kind === 'chart' && (made.bars.length || streaming)) {
        if (made.bars.length || made.title) blocks.push(made);
      } else if (body.join('\n').trim()) {
        blocks.push({ kind: 'para', inlines: inlines(body.join('\n'), urls, streaming) });
      }
      i = end + 1;
      continue;
    }
    if (TABLE_ROW.test(line)) {
      const rows: string[][] = [];
      while (i < lines.length && TABLE_ROW.test(lines[i])) { rows.push(cells(lines[i])); i += 1; }
      const body = rows.filter((r) => !isRule(r) && r.length);
      flushPara();
      if (body.length) {
        const cell = (c: string) => inlines(c, urls, streaming);
        blocks.push({ kind: 'table', head: body[0].map(cell), rows: body.slice(1).map((r) => r.map(cell)) });
      }
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    if (bullet || numbered) {
      const ordered = !!numbered;
      const start = numbered ? Number(numbered[1]) : 1;
      const items: Inline[][] = [];
      while (i < lines.length) {
        const m = ordered ? NUMBERED.exec(lines[i]) : BULLET.exec(lines[i]);
        if (!m) break;
        items.push(inlines(ordered ? m[2] : m[1], urls, streaming));
        i += 1;
      }
      flushPara();
      blocks.push({ kind: 'list', ordered, start, items });
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {   // 제목 기호는 쓰지 말라고 했지만, 오면 굵은 한 줄로 받는다
      flushPara();
      blocks.push({ kind: 'para', inlines: inlines(heading[1], urls, streaming, true) });
    } else if (!line.trim()) {
      flushPara();
    } else {
      para.push(line);
    }
    i += 1;
  }
  flushPara();
  return blocks;
}

const inlineText = (items: Inline[]) => items.map((s) => (s.kind === 'text' ? s.text : `[${s.n}]`)).join('');

/** 구조를 뺀 글자만 (비교와 시험에 쓴다). */
export function speechText(blocks: Block[]): string {
  return blocks.map((b) => {
    if (b.kind === 'para') return inlineText(b.inlines);
    if (b.kind === 'list') return b.items.map((it, k) => `${b.ordered ? `${b.start + k}.` : '-'} ${inlineText(it)}`).join('\n');
    if (b.kind === 'table') return [b.head, ...b.rows].map((r) => r.map(inlineText).join(' | ')).join('\n');
    return [b.title, ...b.bars.map((x) => `${x.label}: ${x.text}`)].filter(Boolean).join('\n');
  }).join('\n');
}

/** 구조가 하나도 없는, 줄글 한 덩어리인지. */
export function isPlain(blocks: Block[]): boolean {
  return blocks.length <= 1 && blocks.every((b) => b.kind === 'para');
}
