/** 참가자 색이 서로 비슷해 보이지 않게 고른다. 화면과 무관한 계산만 있다. */

/** #RRGGBB를 OKLab으로. 눈에 보이는 색 차이가 좌표 사이의 거리와 비슷해지는 색 공간이다. */
function oklab(hex: string): [number, number, number] {
  const lin = [1, 3, 5].map((at) => {
    const v = parseInt(hex.slice(at, at + 2), 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const l = Math.cbrt(0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2]);
  const m = Math.cbrt(0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2]);
  const s = Math.cbrt(0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2]);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

/** 두 색이 얼마나 달라 보이는지. 0이면 같은 색이다. */
export function colorGap(a: string, b: string): number {
  const [x, y] = [oklab(a), oklab(b)];
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
}

/** 이보다 가까우면 작은 아바타 테두리에서 같은 색으로 보인다 */
export const TOO_CLOSE = 0.075;

/**
 * 앞에서부터 차례로 색을 정한다. 자기 색이 앞사람 누구와도 비슷하지 않으면 그대로 쓰고,
 * 비슷하면 팔레트에서 앞사람들의 색과 가장 멀리 떨어진 색으로 바꾼다. 빈 자리(null)는 건너뛴다.
 */
export function spreadColors(own: (string | null)[], palette: readonly string[]): (string | null)[] {
  const used: string[] = [];
  const nearest = (c: string) => Math.min(...used.map((u) => colorGap(c, u)));
  return own.map((color) => {
    if (!color) return null;
    let pick = color;
    if (used.length && nearest(color) < TOO_CLOSE) {
      pick = palette.reduce((best, c) => (nearest(c) > nearest(best) ? c : best), color);
    }
    used.push(pick);
    return pick;
  });
}
