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
  minutes: (id: string) => request<{ minutes: any; cost: number; cost_parts: Record<string, number> }>(`/api/debates/${id}/minutes`, { method: 'POST' }),
  /** 출처 페이지의 실제 탭 제목. 한 번에 20개까지. 조회하지 못한 주소는 빈 문자열로 온다. */
  sourceTitles: (urls: string[]) => request<{ titles: Record<string, string> }>('/api/source-titles', json({ urls })),
  control: (id: string, action: string, value?: unknown) =>
    request<{ state: string }>(`/api/debates/${id}/control`, json({ action, value })),
};
