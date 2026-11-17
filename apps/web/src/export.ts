import { INTENT_LABEL, TONE_LABEL, type DebateRecord } from './types';
import { fmtCost, fmtTime } from './ui/dom';

/** 회의록을 마크다운으로. */
export function minutesToMarkdown(m: any): string[] {
  const lines: string[] = ['## 회의록', '', `### ${m.title}`, '', '#### 전체 흐름', '', m.overview, ''];
  const list = (title: string, items: string[]) => {
    lines.push(`#### ${title}`, '');
    if (items?.length) items.forEach((it) => lines.push(`- ${it}`));
    else lines.push('- 없음');
    lines.push('');
  };
  if (m.timeline?.length) {
    lines.push('#### 시간대별 흐름', '');
    for (const t of m.timeline) {
      lines.push(`- **${t.time} (${t.turns}) ${t.phase}**: ${t.summary}`);
      for (const issue of t.issues ?? []) lines.push(`  - ${issue}`);
    }
    lines.push('');
  }
  list('안건', m.agenda);
  lines.push('#### 주요 논의', '');
  for (const d of m.discussions ?? []) {
    lines.push(`##### ${d.topic}`, '');
    for (const pt of d.points ?? []) lines.push(`- **${pt.name}**: ${pt.point}`);
    lines.push('');
  }
  list('합의 사항', m.agreements);
  list('미결 사항', m.open_issues);
  list('후속 조치', m.follow_ups);
  lines.push('#### 맺음', '', m.conclusion, '');
  return lines;
}

/**
 * 토론 하나를 마크다운 한 덩어리로 만든다. 회의록(있으면) + 요약 + 대화 내용 전체 + 출처.
 * 다른 프로그램에 붙여 넣어 보고서를 만들 때 쓴다.
 */
export function recordToMarkdown(rec: DebateRecord): string {
  const cfg = rec.config;
  const people = (cfg.participants as any[]).map((p) => `${p.name}(${p.title})`);
  if (rec.moderator) people.unshift('진행자');
  const lines: string[] = [`# ${cfg.topic}`, '',
    `- 일시: ${rec.created.replace('T', ' ')}`,
    `- 참석자: ${people.join(', ')}`];
  if (cfg.concept) lines.push(`- 설정: ${cfg.concept}`);
  if (cfg.tone && cfg.tone !== 'default') lines.push(`- 분위기: ${TONE_LABEL[cfg.tone] ?? cfg.tone}`);
  lines.push(`- 분량: ${rec.turns ?? rec.speeches.length}턴, 토론 시계 ${fmtTime(rec.seconds ?? 0)}`);
  if (rec.cost) lines.push(`- 예상 비용: ${fmtCost(rec.cost)} (1달러 1,350원으로 계산)`);
  lines.push('');

  if (rec.minutes) lines.push(...minutesToMarkdown(rec.minutes));
  if (rec.summary) {
    lines.push('## 요약', '', rec.summary.headline, '');
    for (const c of rec.summary.consensus ?? []) lines.push(`- 동의: ${c}`);
    for (const it of rec.summary.issues ?? []) {
      lines.push('', `### 쟁점: ${it.issue}`, '');
      for (const pos of it.positions ?? []) lines.push(`- **${pos.name}**: ${pos.position}`);
    }
    lines.push('', `> ${rec.summary.takeaway}`, '');
  }

  lines.push('## 대화 내용', '');
  const sources = new Map<string, string>();
  for (const s of rec.speeches ?? []) {
    const label = INTENT_LABEL[s.kind === 'free' ? s.intent : s.kind] ?? '';
    const notes = [label, s.interject ? '끼어들기' : '', s.cut ? '말이 끊김' : ''].filter(Boolean).join(', ');
    lines.push(`**[${s.id}] ${s.name}**${notes ? ` (${notes})` : ''}`, '', s.text, '');
    for (const src of s.sources ?? []) sources.set(src.url, src.title);
  }
  if (sources.size) {
    lines.push('## 출처', '');
    sources.forEach((title, url) => lines.push(`- ${title || url}: ${url}`));
    lines.push('');
  }
  return lines.join('\n');
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.cssText = 'position:fixed;left:-9999px;top:0';
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    area.remove();
    return ok;
  }
}
