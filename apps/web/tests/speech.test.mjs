// 발언의 구조(굵게, 목록, 표, 막대 그림) 읽기의 회귀 시험: npm test
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { CitationRegistry, parseCitations } from '../src/citations.ts';
import { isPlain, parseSpeech, speechText } from '../src/speechMarkup.ts';

const read = (text, streaming = false) => parseSpeech(parseCitations(text, new CitationRegistry(), { streaming }), { streaming });

test('줄글뿐인 발언은 한 덩어리로 남는다', () => {
  const blocks = read('그건 좀 다르죠.\n제가 본 현실은 정반대였거든요.');
  assert.equal(isPlain(blocks), true);
  assert.equal(speechText(blocks), '그건 좀 다르죠.\n제가 본 현실은 정반대였거든요.');
});

test('굵게는 기호 없이 굵은 글이 된다', () => {
  const [para] = read('핵심은 **비용**입니다.');
  assert.deepEqual(para.inlines, [
    { kind: 'text', text: '핵심은 ', bold: false }, { kind: 'text', text: '비용', bold: true }, { kind: 'text', text: '입니다.', bold: false }]);
  assert.equal(speechText(read('짝이 없는 ** 표시')), '짝이 없는 ** 표시');
});

test('목록: 점 목록과 번호 목록, 앞뒤의 말은 따로 남는다', () => {
  const blocks = read('이유는 셋입니다.\n- 비용이 듭니다\n- **시간**이 없습니다\n- 사람이 없죠\n그래서 반대합니다.');
  assert.deepEqual(blocks.map((b) => b.kind), ['para', 'list', 'para']);
  assert.equal(blocks[1].ordered, false);
  assert.equal(blocks[1].items.length, 3);
  const numbered = read('1. 첫째\n2. 둘째')[0];
  assert.equal(numbered.ordered, true);
  assert.equal(numbered.items.length, 2);
  assert.equal(isPlain(read('2024년 3.5% 올랐고 - 이건 사실입니다')), true);   // 줄 가운데의 기호는 목록이 아니다
});

test('표: 첫 줄이 머리글이고 구분 줄은 버린다', () => {
  const [table] = read('| 기준 | 원전 | 태양광 |\n|---|---|---|\n| 건설 기간 | 10년 | 2년 |\n| 가동률 | 높음 | 낮음 |');
  assert.equal(table.kind, 'table');
  assert.equal(table.head.length, 3);
  assert.equal(table.rows.length, 2);
  assert.equal(speechText([table]).split('\n')[1], '건설 기간 | 10년 | 2년');
});

test('막대 그림: 제목, 단위, 항목과 값을 읽는다', () => {
  const [lead, chart] = read('수치로 보시죠.\n```chart\n제목: 연도별 판매량\n단위: 만 대\n2022년: 12\n2023년: 1,800.5\n메모\n```');
  assert.equal(lead.kind, 'para');
  assert.equal(chart.kind, 'chart');
  assert.equal(chart.title, '연도별 판매량');
  assert.equal(chart.unit, '만 대');
  assert.deepEqual(chart.bars.map((b) => [b.label, b.value]), [['2022년', 12], ['2023년', 1800.5]]);
  assert.equal(read('```chart\n숫자가 없는 줄\n```')[0].kind, 'para');   // 읽을 값이 없으면 글로 둔다
});

test('각주는 구조 안에서도 번호로 남는다', () => {
  const blocks = read('- 수요가 늘었습니다 ([reuters.com](https://www.reuters.com/a))\n- 값이 올랐죠');
  assert.equal(speechText(blocks), '- 수요가 늘었습니다[1]\n- 값이 올랐죠');
});

test('흘러나오는 중에는 닫히지 않은 표기를 기호로 보여 주지 않는다', () => {
  assert.equal(speechText(read('핵심은 **비용', true)), '핵심은 비용');
  assert.equal(read('핵심은 **비용', true)[0].inlines[1].bold, true);
  assert.equal(speechText(read('핵심은 *', true)), '핵심은 ');
  const table = read('| 기준 | 원전 |\n|--', true)[0];
  assert.equal(table.kind, 'table');
  assert.equal(table.rows.length, 0);
  const chart = read('보시죠.\n```chart\n제목: 판매량\n2022년: 1', true)[1];
  assert.equal(chart.kind, 'chart');
  assert.equal(chart.bars[0].value, 1);
});
