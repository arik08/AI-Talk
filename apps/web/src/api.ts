import type { DebateRecord, DebateSummary, Persona, Status } from './types';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error('서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인하세요.');
  }
  if (!res.ok) {
    let detail = `요청이 실패했습니다 (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch { /* 본문이 JSON이 아니면 기본 문구를 쓴다 */ }
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return res.json() as Promise<T>;
}

/**
 * 오래 걸리는 일의 중간 결과를 받는다. 서버가 한 줄에 JSON 하나씩 흘려보내고, 마지막 줄이 결과(done)나 오류(error)다.
 * 중간 줄은 onItem으로 넘기고 결과를 돌려준다.
 */
async function stream<T>(path: string, init: RequestInit, onItem: (item: any) => void): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error('서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인하세요.');
  }
  if (!res.ok || !res.body) {
    let detail = `요청이 실패했습니다 (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch { /* 본문이 JSON이 아니면 기본 문구를 쓴다 */ }
    throw Object.assign(new Error(detail), { status: res.status });
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let done: T | null = null;
  const take = (line: string) => {
    if (!line.trim()) return;
    const item = JSON.parse(line);
    if (item.type === 'error') throw new Error(item.message || '요청이 실패했습니다.');
    if (item.type === 'done') done = item as T;
    else onItem(item);
  };
  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch {
      throw new Error('받는 도중에 서버와의 연결이 끊겼습니다.');
    }
    buffer += decoder.decode(chunk.value ?? new Uint8Array(), { stream: !chunk.done });
    const lines = buffer.split('\n');
    buffer = chunk.done ? '' : lines.pop() ?? '';
    for (const line of lines) take(line);
    if (chunk.done) break;
  }
  if (!done) throw new Error('받는 도중에 서버와의 연결이 끊겼습니다.');
  return done;
}

export interface CostResult { cost: number; cost_parts: Record<string, number> }

const json = (body: unknown): RequestInit => ({
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

export const api = {
  status: () => request<Status>('/api/status'),
  setProvider: (name: string) => request<Status>('/api/provider', json({ name })),
  enter: (code: string) => request<{ ok: boolean }>('/api/enter', json({ code })),
  personas: () => request<Persona[]>('/api/personas'),
  savePersona: (p: Persona) => request<Persona>('/api/personas', json(p)),
  deletePersona: (id: string) => request<{ ok: boolean }>(`/api/personas/${id}`, { method: 'DELETE' }),
  importPersonas: (items: unknown[]) => request<{ added: number }>('/api/personas/import', json(items)),
  draftPersona: (hint: string) => request<Partial<Persona>>('/api/personas/draft', json({ hint })),
  cast: (body: { topic: string; concept?: string; tone?: string; count: number; policy: string; fixed: Partial<Persona>[]; materials: string; model?: string; effort?: string }) =>
    request<{ personas: Partial<Persona>[]; cost?: number }>('/api/cast', json(body)),
  /** 새로 만들지 않고 보관함의 인물 가운데 주제에 맞는 사람을 골라, 입장만 주제에 맞춰 받는다. */
  castLibrary: (body: { topic: string; concept?: string; tone?: string; count: number; policy: string; picked?: string[]; materials: string; model?: string; effort?: string }) =>
    request<{ personas: Persona[]; cost?: number; library: number; asked: number }>('/api/cast/library', json(body)),
  uploadMaterial: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<{ name: string; text: string; chars: number; tokens: number }>('/api/materials', { method: 'POST', body: form });
  },
  startDebate: (config: unknown) => request<{ id: string }>('/api/debates', json(config)),
  debates: () => request<DebateSummary[]>('/api/debates'),
  debate: (id: string) => request<DebateRecord>(`/api/debates/${id}`),
  deleteDebate: (id: string) => request<{ ok: boolean }>(`/api/debates/${id}`, { method: 'DELETE' }),
  /** 서버가 꺼지거나 중단되어 끝까지 가지 못한 토론을 이어 간다. */
  resumeDebate: (id: string) => request<{ id: string }>(`/api/debates/${id}/resume`, { method: 'POST' }),
  /** 회의록을 (다시) 쓴다. 쓰이는 대로 onPartial로 지금까지의 회의록이 온다. */
  minutes: (id: string, onPartial: (minutes: any) => void) =>
    stream<CostResult & { minutes: any }>(`/api/debates/${id}/minutes`, { method: 'POST' }, (item) => { if (item.minutes) onPartial(item.minutes); }),
  /** 누가 더 설득력 있었는지 판정을 받는다. 쓰이는 대로 onPartial로 온다. */
  verdict: (id: string, onPartial: (verdict: any) => void) =>
    stream<CostResult & { verdict: any }>(`/api/debates/${id}/verdict`, { method: 'POST' }, (item) => { if (item.verdict) onPartial(item.verdict); }),
  /** 끝난 토론에 대해 묻는다. 답이 쓰이는 대로 onText로 조각이 온다. */
  ask: (id: string, question: string, onText: (piece: string) => void) =>
    stream<CostResult & { qa: any[] }>(`/api/debates/${id}/ask`, json({ question }), (item) => { if (item.type === 'delta') onText(String(item.text ?? '')); }),
  /** 출처 페이지의 실제 탭 제목. 한 번에 20개까지. 조회하지 못한 주소는 빈 문자열로 온다. */
  sourceTitles: (urls: string[]) => request<{ titles: Record<string, string> }>('/api/source-titles', json({ urls })),
  control: (id: string, action: string, value?: unknown) =>
    request<{ state: string }>(`/api/debates/${id}/control`, json({ action, value })),
};
