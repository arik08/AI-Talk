/**
 * 발언 본문의 링크를 번호 각주로 바꾸고, 출처를 토론 전체에서 한 번호 체계로 관리한다.
 *
 * DOM을 쓰지 않는 순수 함수만 둔다 (Node에서 바로 시험한다: npm test).
 * - `[이름](URL)`, `([이름](URL))` → 각주 [n]. 같은 URL은 어느 발언에서 나와도 같은 번호다.
 * - `turn1view0` 같은 AI 내부 인용 표식은 실제 주소와 이을 수 없으므로 숨긴다. 출처를 지어내지 않는다.
 * - 글자가 흘러나오는 중에는 아직 닫히지 않은 링크를 보여 주지 않는다.
 */

export interface SourceEntry {
  n: number;          // 토론 전체에서 쓰는 각주 번호
  url: string;
  title: string;      // 검색 결과나 링크 이름으로 받은 제목 (없을 수 있다)
  page: string;       // 실제 페이지의 탭 제목 (조회에 성공했을 때만)
}

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'cite'; n: number; url: string };

/** http(s) 주소만 받는다. 그 밖의 것은 빈 문자열. 같은 글은 같은 키가 되도록 조각 표시(#...)는 뗀다. */
export function normalizeUrl(raw: string): string {
  const value = String(raw ?? '').trim();
  if (!/^https?:\/\/[^\s/]+/i.test(value)) return '';
  const hash = value.indexOf('#');
  return hash >= 0 ? value.slice(0, hash) : value;
}

/** URL의 `//`와 다음 `/` 사이. 묶음의 기준이다. */
export function hostOf(url: string): string {
  const m = /^https?:\/\/([^/?#]+)/i.exec(url);
  return m ? m[1].toLowerCase() : '';
}

function decode(text: string): string {
  try { return decodeURIComponent(text); } catch { return text; }
}

const GENERIC = /^(자료|출처|참고|링크|사이트|웹사이트|기사|source|sources|link|site|website|ref|reference)\s*\d*$/i;

/** 내용을 알 수 없는 이름인지: 비었거나, 주소·도메인 그대로이거나, '자료 2' 같은 것. */
export function isGenericTitle(title: string, url = ''): boolean {
  const t = String(title ?? '').trim();
  if (!t || !/\p{L}/u.test(t)) return true;   // 글자가 없는 이름: '1', '[2]' 같은 번호뿐인 것
  if (/^https?:\/\//i.test(t)) return true;
  if (GENERIC.test(t)) return true;
  if (/^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(t)) return true;   // example.com, news.example.co.kr/path
  const host = hostOf(url).replace(/^www\./, '');
  return !!host && t.toLowerCase().replace(/^www\./, '') === host;
}

/** 제목이 없을 때 대신 보여 줄 글: 한글 인코딩을 푼 경로와 쿼리. 제목을 지어내지 않는다. */
export function pathLabel(url: string): string {
  const m = /^https?:\/\/[^/?#]+(.*)$/i.exec(url);
  const rest = decode(m ? m[1] : '').replace(/^\/+|\/+$/g, '');
  return rest || hostOf(url).replace(/^www\./, '');
}

/** 목록에 보여 줄 이름: 실제 탭 제목 > 뜻이 있는 제목 > 풀어 쓴 주소. */
export function displayTitle(entry: SourceEntry): string {
  if (entry.page) return entry.page;
  if (!isGenericTitle(entry.title, entry.url)) return entry.title.trim();
  return pathLabel(entry.url);
}

/** 토론 하나의 출처 번호표. URL마다 번호 하나. */
export class CitationRegistry {
  private byUrl = new Map<string, SourceEntry>();

  /** 처음 보는 주소면 다음 번호를 준다. 뒤늦게 뜻이 있는 제목이 오면 제목만 보완하고 번호는 그대로 둔다. */
  register(rawUrl: string, title = ''): SourceEntry | null {
    const url = normalizeUrl(rawUrl);
    if (!url) return null;
    const name = String(title ?? '').trim();
    const known = this.byUrl.get(url);
    if (known) {
      if (name && isGenericTitle(known.title, url) && !isGenericTitle(name, url)) known.title = name;
      return known;
    }
    const entry: SourceEntry = { n: this.byUrl.size + 1, url, title: name, page: '' };
    this.byUrl.set(url, entry);
    return entry;
  }

  /** 실제 페이지의 탭 제목. 검색 결과 제목보다 우선한다. 번호와 주소는 바뀌지 않는다. */
  setPageTitle(rawUrl: string, title: string): void {
    const entry = this.byUrl.get(normalizeUrl(rawUrl));
    const name = String(title ?? '').replace(/\s+/g, ' ').trim();
    if (entry && name) entry.page = name;
  }

  get(rawUrl: string): SourceEntry | undefined { return this.byUrl.get(normalizeUrl(rawUrl)); }
  list(): SourceEntry[] { return Array.from(this.byUrl.values()); }
  get size(): number { return this.byUrl.size; }
  clear(): void { this.byUrl.clear(); }
}

/* ---------- 링크 읽기 ---------- */

interface Link { end: number; label: string; url: string; title: string }

/** text[start]가 '['일 때 마크다운 링크 하나를 읽는다. 링크가 아니면 null. */
function readLink(text: string, start: number): Link | null {
  let i = start + 1;
  let depth = 1;
  for (; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '\n') return null;
    if (ch === '[') depth += 1;
    else if (ch === ']') { depth -= 1; if (depth === 0) break; }
  }
  if (i >= text.length) return null;
  const label = text.slice(start + 1, i);
  i += 1;
  while (text[i] === ' ' || text[i] === '\t') i += 1;   // 이름과 주소 사이에 빈칸이 끼는 경우
  if (text[i] !== '(') return null;
  i += 1;
  while (text[i] === ' ' || text[i] === '\t') i += 1;
  let url = '';
  if (text[i] === '<') {
    const close = text.indexOf('>', i);
    if (close < 0) return null;
    url = text.slice(i + 1, close);
    i = close + 1;
  } else {
    const from = i;
    let paren = 0;   // 주소 안의 괄호: 짝이 맞는 동안은 주소의 일부다
    for (; i < text.length; i += 1) {
      const ch = text[i];
      if (ch === '(') paren += 1;
      else if (ch === ')') { if (paren === 0) break; paren -= 1; }
      else if (/\s/.test(ch)) break;
    }
    url = text.slice(from, i);
  }
  while (text[i] === ' ' || text[i] === '\t') i += 1;
  let title = '';
  if (text[i] === '"' || text[i] === "'") {   // 선택 항목인 링크 제목
    const quote = text[i];
    const close = text.indexOf(quote, i + 1);
    if (close < 0) return null;
    title = text.slice(i + 1, close);
    i = close + 1;
    while (text[i] === ' ' || text[i] === '\t') i += 1;
  }
  if (text[i] !== ')') return null;
  return { end: i + 1, label: label.trim(), url, title: title.trim() };
}

/* ---------- AI 내부 인용 표식 ---------- */
const MARK_TOKEN = '(?:turn\\d+[a-z_]+\\d+)';
const INTERNAL = new RegExp([
  '[\\uE200-\\uE2FF][^\\uE200-\\uE2FF\\n]*(?:[\\uE200-\\uE2FF][^\\uE200-\\uE2FF\\n]*)*[\\uE200-\\uE2FF]',   // 사용자 정의 영역 글자로 감싼 묶음
  '[\\uE200-\\uE2FF]',
  `(?<![A-Za-z])(?:cite)?${MARK_TOKEN}+`,                // citeturn1view0, turn0search3turn0news1
  '【\\d+[^】\\n]*†[^】\\n]*】',                           // 【4†source】
].join('|'), 'g');
const INTERNAL_TAIL = new RegExp([
  '[\\uE200-\\uE2FF][^\\n]*$',
  '(?<![A-Za-z])(?:cite)?(?:turn\\d+[a-z_]*\\d*)+$',
  '(?<![A-Za-z])cite$',
  '【\\d+[^】\\n]*$',
].join('|'));

function stripInternal(text: string, streaming: boolean): string {
  let out = text.replace(INTERNAL, '');
  if (streaming) out = out.replace(INTERNAL_TAIL, '');
  return out;
}

/** 글자가 오는 중일 때: 아직 닫히지 않은 링크의 시작 위치. 없으면 -1. */
function openLinkStart(text: string): number {
  const at = text.lastIndexOf('[');
  if (at < 0) return -1;
  const tail = text.slice(at);
  if (tail.includes('\n') || tail.length > 600) return -1;
  if (readLink(text, at)) return -1;                          // 이미 닫힌 링크
  const open = /^\[[^\]]*$/.test(tail)                        // [이름
    || /^\[[^\]]*\][ \t]*$/.test(tail)                         // [이름]  (주소가 올 수 있다)
    || /^\[[^\]]*\][ \t]*\([ \t]*\S*$/.test(tail)              // [이름](http://...
    || /^\[[^\]]*\][ \t]*\([ \t]*\S+[ \t]+(["'][^"']*["']?[ \t]*)?$/.test(tail);   // [이름](주소 "제목
  if (!open) return -1;
  return at > 0 && text[at - 1] === '(' ? at - 1 : at;   // ([이름](… 의 여는 괄호까지 숨긴다
}

const DROP_LABEL = /^(여기|링크|원문|출처|here|link|source)$/i;

/**
 * 본문을 글과 각주로 나눈다. 링크의 주소는 번호표에 올린다.
 * streaming이 참이면 끝에 걸친 미완성 링크와 표식을 숨긴다.
 */
export function parseCitations(raw: string, registry: CitationRegistry, opts: { streaming?: boolean } = {}): Segment[] {
  const streaming = !!opts.streaming;
  let text = String(raw ?? '');
  if (streaming) {
    const cut = openLinkStart(text);
    if (cut >= 0) text = text.slice(0, cut);
  }
  const segments: Segment[] = [];
  let buf = '';
  const flush = () => {
    if (!buf) return;
    const clean = stripInternal(buf, false);
    if (clean) {
      const last = segments[segments.length - 1];
      if (last && last.kind === 'text') last.text += clean;
      else segments.push({ kind: 'text', text: clean });
    }
    buf = '';
  };
  let i = 0;
  while (i < text.length) {
    if (text[i] !== '[') { buf += text[i]; i += 1; continue; }
    const link = readLink(text, i);
    const entry = link ? registry.register(link.url, link.title || link.label) : null;
    if (!link || !entry) { buf += text[i]; i += 1; continue; }
    let end = link.end;
    const wrapped = buf.endsWith('(') && text[end] === ')';   // ([이름](URL)) 꼴
    if (wrapped) { buf = buf.slice(0, -1); end += 1; }
    // 이름이 문장의 일부일 때만 글로 남긴다. 사이트 이름이나 주소뿐이면 번호만 둔다
    const keep = !wrapped && link.label && !isGenericTitle(link.label, entry.url) && !DROP_LABEL.test(link.label);
    if (keep) buf += link.label;
    else buf = buf.replace(/[ \t]+$/, '');
    flush();
    const last = segments[segments.length - 1];
    if (!(last && last.kind === 'cite' && last.n === entry.n)) segments.push({ kind: 'cite', n: entry.n, url: entry.url });
    i = end;
  }
  if (streaming) buf = stripInternal(buf, true);
  flush();
  // 표식을 지운 자리에 남는 군더더기 빈칸
  for (const seg of segments) {
    if (seg.kind === 'text') seg.text = seg.text.replace(/[ \t]{2,}/g, ' ').replace(/[ \t]+([.,!?。])/g, '$1');
  }
  return segments.filter((s) => s.kind === 'cite' || s.text);
}

/** 발언 하나의 출처: 본문에 나온 순서대로, 그다음 프로바이더가 준 목록. 같은 주소는 한 번만. */
export function collectSources(text: string, listed: { url: string; title?: string }[] | undefined,
  registry: CitationRegistry): SourceEntry[] {
  const seen = new Set<string>();
  const out: SourceEntry[] = [];
  const add = (entry: SourceEntry | null) => {
    if (entry && !seen.has(entry.url)) { seen.add(entry.url); out.push(entry); }
  };
  for (const seg of parseCitations(text, registry)) if (seg.kind === 'cite') add(registry.get(seg.url) ?? null);
  for (const s of listed ?? []) add(registry.register(s?.url ?? '', s?.title ?? ''));
  return out;
}

/** 호스트별로 묶는다. 같은 호스트의 다른 경로는 따로 남는다. 처음 나온 순서를 지킨다. */
export function groupByHost(entries: SourceEntry[]): { host: string; items: SourceEntry[] }[] {
  const groups = new Map<string, SourceEntry[]>();
  for (const entry of entries) {
    const host = hostOf(entry.url);
    if (!groups.has(host)) groups.set(host, []);
    groups.get(host)!.push(entry);
  }
  return Array.from(groups, ([host, items]) => ({ host, items }));
}

/** 각주를 뺀 글자만 (비교와 시험에 쓴다). */
export function plainText(segments: Segment[]): string {
  return segments.map((s) => (s.kind === 'text' ? s.text : `[${s.n}]`)).join('');
}
