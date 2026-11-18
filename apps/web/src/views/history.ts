import { Copy, Download, Hourglass, ListOrdered, Play } from 'lucide';
import { api } from '../api';
import { createAvatar } from '../avatar/avatar';
import type { AppContext } from '../main';
import { copyText, recordToMarkdown } from '../export';
import type { DebateSummary } from '../types';
import { clear, deleteButton, fmtCost, fmtTime, h, icon, safeColor, toast } from '../ui/dom';

const STATE: Record<string, string> = { ended: '끝남', running: '진행 중', paused: '멈춤', error: '오류로 멈춤', aborted: '중단됨', failed: '실패', interrupted: '끊김 · 이어 할 수 있음' };

export function mountHistory(root: HTMLElement, ctx: AppContext): () => void {
  const list = h('div', { class: 'hist' });
  root.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', null, h('h1', null, '지난 토론'), h('p', null, '끝난 토론은 자동으로 저장됩니다. 눌러서 같은 박자로 다시 볼 수 있습니다.'))),
    list));

  async function exportMd(id: string): Promise<void> {
    try {
      const rec = await api.debate(id);
      const blob = new Blob([recordToMarkdown(rec)], { type: 'text/markdown' });
      const a = h('a', { href: URL.createObjectURL(blob), download: `${rec.config.topic.slice(0, 30).replace(/[\\/:*?"<>|]/g, '')}.md` });
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) { toast((err as Error).message, 'error'); }
  }

  async function copyMd(id: string): Promise<void> {
    try {
      const rec = await api.debate(id);
      const ok = await copyText(recordToMarkdown(rec));
      toast(ok ? (rec.minutes ? '대화 내용과 회의록을 복사했습니다.' : '회의록이 아직 없어 대화 내용만 복사했습니다.') : '복사하지 못했습니다.', ok ? 'info' : 'error');
    } catch (err) { toast((err as Error).message, 'error'); }
  }

  function paint(items: DebateSummary[]): void {
    clear(list);
    if (!items.length) {
      list.append(h('div', { class: 'empty' }, h('h3', null, '아직 토론 기록이 없습니다'),
        h('p', null, '첫 토론을 시작해 보세요.'),
        h('button', { type: 'button', class: 'btn btn--primary', style: 'margin-top:1rem', onclick: () => ctx.go('#/') }, icon(Play, 18), '새 토론')));
      return;
    }
    items.forEach((d, i) => {
      const avs = h('div', { class: 'hist-avs' }, d.participants.slice(0, 6).map((p) => {
        const av = createAvatar(p.avatar, safeColor(p.color), 36);
        av.classList.add('is-still');
        av.dataset.tip = p.name;
        return av;
      }));
      list.append(h('div', { class: 'hist-row', style: `animation-delay:${Math.min(i, 12) * 40}ms`, onclick: () => ctx.go(`#/stage/${d.id}`) },
        h('div', { style: 'min-width:0' }, h('div', { class: 'hist-topic' }, d.topic),
          h('div', { class: 'hist-meta' },
            h('span', null, d.created.replace('T', ' ').slice(0, 16)),
            h('span', null, STATE[d.state] ?? d.state),
            h('span', { class: 'row', style: 'gap:.25rem' }, icon(ListOrdered, 14), `${d.turns}턴`),
            h('span', { class: 'row', style: 'gap:.25rem' }, icon(Hourglass, 14), fmtTime(d.seconds)),
            d.cost ? h('span', null, fmtCost(d.cost)) : null)),
        avs,
        h('div', { class: 'row', style: 'gap:.125rem', onclick: (e: MouseEvent) => e.stopPropagation() },
          h('button', { type: 'button', class: 'btn btn--icon', tip: '대화 + 회의록 복사', 'aria-label': '대화와 회의록 복사', onclick: () => copyMd(d.id) }, icon(Copy, 18)),
          h('button', { type: 'button', class: 'btn btn--icon', tip: '마크다운으로 내보내기', 'aria-label': '마크다운으로 내보내기', onclick: () => exportMd(d.id) }, icon(Download, 18)),
          deleteButton(async () => {
            try { await api.deleteDebate(d.id); load(); } catch (err) { toast((err as Error).message, 'error'); }
          }))));
    });
  }

  async function load(): Promise<void> {
    try { paint(await api.debates()); } catch (err) { toast((err as Error).message, 'error'); }
  }
  load();
  return () => undefined;
}
