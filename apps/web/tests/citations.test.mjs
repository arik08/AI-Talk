// 각주와 출처 번호의 회귀 시험. TypeScript를 바로 읽는 Node.js가 필요하다: npm test
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  CitationRegistry, collectSources, displayTitle, groupByHost, isGenericTitle, normalizeUrl, parseCitations, plainText,
} from '../src/citations.ts';

const parse = (text, reg = new CitationRegistry(), streaming = false) => plainText(parseCitations(text, reg, { streaming }));

test('링크는 번호 각주가 되고 긴 주소는 본문에 남지 않는다', () => {
  const reg = new CitationRegistry();
  const out = parse('철강 수요가 늘었습니다 ([reuters.com](https://www.reuters.com/markets/%EC%B2%A0%EA%B0%95?utm_source=openai)).', reg);
  assert.equal(out, '철강 수요가 늘었습니다[1].');
  assert.equal(reg.list()[0].url, 'https://www.reuters.com/markets/%EC%B2%A0%EA%B0%95?utm_source=openai');
});

test('같은 주소는 같은 번호, 다른 주소는 다른 번호', () => {
  const out = parse('가 [A](https://a.example/1) 나 [B](https://b.example/2) 다 [A](https://a.example/1)');
  assert.equal(out, '가 A[1] 나 B[2] 다 A[1]');
});

test('번호는 발언이 달라도 토론 전체에서 이어진다', () => {
  const reg = new CitationRegistry();
  parse('첫 발언 [x](https://a.example/one)', reg);
  const second = parse('둘째 발언 [y](https://a.example/two) 그리고 [x](https://a.example/one)', reg);
  assert.equal(second, '둘째 발언 y[2] 그리고 x[1]');
  const again = new CitationRegistry();   // 새 토론은 번호를 새로 센다
  assert.equal(parse('[y](https://a.example/two)', again), 'y[1]');
});

test('이름과 주소 사이의 빈칸, 주소 안의 괄호, 링크 제목을 읽는다', () => {
  const reg = new CitationRegistry();
  const out = parse('위키 [문서] (https://ko.wikipedia.org/wiki/철(원소) "철 - 위키백과") 참고', reg);
  assert.equal(out, '위키 문서[1] 참고');
  assert.equal(reg.list()[0].url, 'https://ko.wikipedia.org/wiki/철(원소)');
  assert.equal(reg.list()[0].title, '철 - 위키백과');
});

test('http(s)가 아닌 링크는 각주로 만들지 않는다', () => {
  const reg = new CitationRegistry();
  assert.equal(parse('[눌러](javascript:alert(1)) 그리고 [파일](file:///c:/x)', reg), '[눌러](javascript:alert(1)) 그리고 [파일](file:///c:/x)');
  assert.equal(reg.size, 0);
  assert.equal(normalizeUrl('ftp://a.example'), '');
});

test('AI 내부 인용 표식은 숨기고 출처를 지어내지 않는다', () => {
  const reg = new CitationRegistry();
  assert.equal(parse('수출이 늘었습니다 citeturn1view0turn0search3.', reg), '수출이 늘었습니다.');
  assert.equal(parse('값이 올랐다 \uE200cite\uE202turn0search1\uE201 그리고 끝', reg), '값이 올랐다 그리고 끝');
  assert.equal(parse('보고서에 따르면【4†source】 그렇습니다', reg), '보고서에 따르면 그렇습니다');
  assert.equal(parse('【주최자 지시】는 그대로 둔다. return과 turnover도 그대로', reg), '【주최자 지시】는 그대로 둔다. return과 turnover도 그대로');
  assert.equal(reg.size, 0);
});

test('글자가 오는 중에는 닫히지 않은 링크와 표식을 보여 주지 않는다', () => {
  const reg = new CitationRegistry();
  const full = '수요가 늘었다 ([로이터](https://reuters.example/a%20b)). 다음 문장 citeturn2news1 끝';
  let shown = '';
  for (let i = 1; i <= full.length; i += 1) {
    shown = parse(full.slice(0, i), reg, true);
    assert.ok(!/https?:|\]\(|%20|turn\d/.test(shown), `${i}: ${shown}`);
  }
  assert.equal(shown, '수요가 늘었다[1]. 다음 문장 끝');
  assert.equal(reg.size, 1);   // 중간 조각이 따로 번호를 받지 않는다
});

test('스트리밍 중 대괄호로 끝나는 보통 글은 링크가 아니면 다시 나타난다', () => {
  assert.equal(parse('목록 [가', undefined, true), '목록 ');
  assert.equal(parse('목록 [가] 다음', undefined, true), '목록 [가] 다음');
  assert.equal(parse('목록 [가]', undefined, false), '목록 [가]');
});

test('출처는 호스트별로 묶고 같은 주소는 한 번만 둔다', () => {
  const reg = new CitationRegistry();
  const cited = collectSources('본문 [a](https://news.example/a)', [
    { url: 'https://news.example/a', title: '기사 A' }, { url: 'https://news.example/b', title: '기사 B' },
    { url: 'https://other.example/c', title: '' }, { url: 'mailto:x@y.z', title: '메일' },
  ], reg);
  assert.deepEqual(cited.map((e) => e.n), [1, 2, 3]);
  const groups = groupByHost(cited);
  assert.deepEqual(groups.map((g) => [g.host, g.items.length]), [['news.example', 2], ['other.example', 1]]);
});

test('조각 표시만 다른 주소는 같은 자료로 본다', () => {
  const reg = new CitationRegistry();
  assert.equal(parse('[a](https://a.example/p#one) [b](https://a.example/p#two)', reg), 'a[1] b[1]');
});

test('뜻 없는 이름 대신 한글 인코딩을 푼 주소를 보여 준다', () => {
  const reg = new CitationRegistry();
  const entry = reg.register('https://news.example/%EC%B2%A0%EA%B0%95/2026?q=%EC%88%98%EC%B6%9C', '자료 2');
  assert.equal(displayTitle(entry), '철강/2026?q=수출');
  for (const name of ['', '자료 3', '사이트', 'news.example', 'www.news.example', 'https://news.example/x', 'Source 1']) {
    assert.ok(isGenericTitle(name, 'https://news.example/x'), name);
  }
  assert.ok(!isGenericTitle('철강 수출 3분기 급증', 'https://news.example/x'));
  assert.equal(displayTitle(reg.register('https://plain.example/', '')), 'plain.example');
});

test('뒤늦게 온 실제 제목은 이름만 보완하고 번호는 그대로다', () => {
  const reg = new CitationRegistry();
  const first = reg.register('https://news.example/a', 'news.example');
  reg.register('https://news.example/b', '');
  const later = reg.register('https://news.example/a', '철강 수출 급증');
  assert.equal(later.n, first.n);
  assert.equal(displayTitle(later), '철강 수출 급증');
  reg.register('https://news.example/a', '다른 제목');   // 이미 뜻이 있는 제목은 덮어쓰지 않는다
  assert.equal(displayTitle(later), '철강 수출 급증');
});

test('실제 탭 제목은 검색 결과 제목보다 우선하고 번호와 주소는 유지된다', () => {
  const reg = new CitationRegistry();
  const entry = reg.register('https://news.example/a', '검색 결과 제목');
  reg.setPageTitle('https://news.example/a#top', '  실제 기사 제목 |\n 뉴스룸 ');
  assert.equal(displayTitle(entry), '실제 기사 제목 | 뉴스룸');
  assert.equal(entry.n, 1);
  assert.equal(entry.url, 'https://news.example/a');
  reg.setPageTitle('https://news.example/a', '');   // 조회 실패(빈 제목)는 지금 표시를 바꾸지 않는다
  assert.equal(displayTitle(entry), '실제 기사 제목 | 뉴스룸');
  reg.setPageTitle('https://unknown.example/', '없는 주소');
  assert.equal(reg.size, 1);
});

test('다시 보면 같은 기록에서 같은 번호가 나온다', () => {
  const speeches = ['가 [1](https://a.example/1)', '나 [2](https://b.example/2) [1](https://a.example/1)', '다 [3](https://c.example/3)'];
  const run = () => {
    const reg = new CitationRegistry();
    return speeches.map((s) => parse(s, reg)).join('|');
  };
  assert.equal(run(), run());
  assert.equal(run(), '가[1]|나[2][1]|다[3]');
});
