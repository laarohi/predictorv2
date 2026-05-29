import { describe, expect, it } from 'vitest';

import { sparklinePath } from './panini';

describe('sparklinePath', () => {
	it('returns empty paths for < 2 points', () => {
		expect(sparklinePath([5], 32, { width: 100, height: 20 })).toEqual({
			linePath: '',
			fillPath: '',
			points: []
		});
	});

	it('starts with M and uses L for subsequent points', () => {
		const { linePath, points } = sparklinePath([1, 2, 3], 5, { width: 100, height: 20 });
		expect(linePath.startsWith('M')).toBe(true);
		expect(linePath.split('L').length).toBe(3); // "M..L..L.."
		expect(points).toHaveLength(3);
	});

	it('places the first x at 0 and last x at width', () => {
		const { points } = sparklinePath([1, 2, 3, 4], 10, { width: 100, height: 20 });
		expect(points[0][0]).toBe(0);
		expect(points[3][0]).toBe(100);
	});

	it('closes the fill path back to the origin', () => {
		const { fillPath } = sparklinePath([1, 5], 10, { width: 100, height: 20 });
		expect(fillPath.endsWith('Z')).toBe(true);
		expect(fillPath).toContain('L100,20');
		expect(fillPath).toContain('L0,20');
	});
});
