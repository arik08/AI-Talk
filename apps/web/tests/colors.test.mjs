// 참가자 색이 겹치지 않게 고르기의 회귀 시험: npm test
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { TOO_CLOSE, colorGap, spreadColors } from '../src/colors.ts';

const PALETTE = ['#E0764A', '#5FB6A8', '#8FA8E8', '#C98BD9', '#9CC766', '#E36F8A', '#5FA8D8', '#D9A441', '#C9B38A', '#7FD1C0'];

test('서로 다른 색은 그대로 둔다', () => {
  const own = ['#E0764A', '#5FB6A8', '#C98BD9'];
  assert.deepEqual(spreadColors(own, PALETTE), own);
});

test('같은 색이면 뒤쪽 사람만 바꾼다', () => {
  const out = spreadColors(['#E0764A', '#C9B38A', '#C9B38A'], PALETTE);
  assert.deepEqual(out.slice(0, 2), ['#E0764A', '#C9B38A']);
  assert.notEqual(out[2], '#C9B38A');
  assert.ok(colorGap(out[2], out[0]) >= TOO_CLOSE && colorGap(out[2], out[1]) >= TOO_CLOSE);
});

test('비슷한 색도 바꾼다', () => {
  const out = spreadColors(['#8FA8E8', '#5FA8D8'], PALETTE);
  assert.equal(out[0], '#8FA8E8');
  assert.ok(colorGap(out[0], out[1]) >= TOO_CLOSE);
});

test('빈 자리는 건너뛰고, 여러 명이 겹쳐도 서로 다르게 나눈다', () => {
  const out = spreadColors(['#C9B38A', null, '#C9B38A', '#C9B38A', '#C9B38A'], PALETTE);
  assert.equal(out[1], null);
  const colors = out.filter(Boolean);
  for (let i = 0; i < colors.length; i += 1) for (let j = i + 1; j < colors.length; j += 1) assert.ok(colorGap(colors[i], colors[j]) >= TOO_CLOSE);
});
