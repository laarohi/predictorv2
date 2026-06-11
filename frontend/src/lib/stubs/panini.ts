/**
 * Sparkline path geometry (used by PnSparkline).
 *
 * This module previously also held deterministic stub generators for
 * backend-pending Panini widgets (social signals, hot pick, bracket exposure,
 * underdog stats, steepest climb, bonus haul, live score, rank trajectory).
 * Those widgets were either cut or wired to real data, so the stubs were
 * removed — only the pure sparkline path helper remains.
 */

export interface SparklineOptions {
	width: number;
	height: number;
	padTop?: number;
	padBottom?: number;
	/** Horizontal inset in SVG units. Without it the first/last markers sit
	 *  exactly on the viewBox edge and get clipped to half-circles. */
	padX?: number;
}

/**
 * Build an SVG path string from rank values. Smaller rank = better, so we
 * invert the y-axis so a climbing player draws a falling line on screen.
 * Returns { linePath, fillPath, points } so consumers can render markers.
 */
export function sparklinePath(
	ranks: number[],
	maxRank: number,
	opts: SparklineOptions
): { linePath: string; fillPath: string; points: Array<[number, number]> } {
	const { width, height, padTop = 0.05, padBottom = 0.05, padX = 0 } = opts;
	if (ranks.length < 2) return { linePath: '', fillPath: '', points: [] };
	const points: Array<[number, number]> = ranks.map((r, i) => {
		const x = padX + (i / (ranks.length - 1)) * (width - 2 * padX);
		// Map rank → y: rank 1 is the top of the chart, rank maxRank the bottom.
		const norm = (r - 1) / Math.max(1, maxRank - 1);
		const y = padTop * height + norm * (1 - padTop - padBottom) * height;
		return [x, y];
	});
	const linePath = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
	const fillPath = `${linePath} L${width - padX},${height} L${padX},${height} Z`;
	return { linePath, fillPath, points };
}
