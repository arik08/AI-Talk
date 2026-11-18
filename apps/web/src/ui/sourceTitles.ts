import { api } from '../api';

/**
 * 출처 페이지의 실제 탭 제목을 서버에 물어 온다.
 * 같은 주소는 한 번만 묻는다: 진행 중인 요청과 받은 결과를 함께 쓴다. 실패하면 빈 문자열.
 */
const BATCH = 20;   // 서버가 한 번에 받는 주소 수
const cache = new Map<string, Promise<string>>();

export function loadTitles(urls: string[]): Promise<Map<string, string>> {
  const fresh = Array.from(new Set(urls)).filter((url) => !cache.has(url));
  for (let i = 0; i < fresh.length; i += BATCH) {
    const batch = fresh.slice(i, i + BATCH);
    const asked = api.sourceTitles(batch).then((res) => res.titles ?? {}).catch(() => ({} as Record<string, string>));
    for (const url of batch) cache.set(url, asked.then((titles) => String(titles[url] ?? '')));
  }
  return Promise.all(urls.map(async (url) => [url, await cache.get(url)!] as const)).then((rows) => new Map(rows));
}

/** 시험용: 기억해 둔 결과를 비운다. */
export function forgetTitles(): void {
  cache.clear();
}
