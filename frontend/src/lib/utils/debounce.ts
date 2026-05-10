/**
 * Trailing-edge debounce. Returns a wrapped function that fires `fn`
 * once `ms` milliseconds have passed since the last call.
 *
 * `cancel()` discards a pending invocation. `flush()` invokes the pending
 * call immediately (with the most recent arguments) if one is queued.
 */
export function debounce<F extends (...args: any[]) => void>(
	fn: F,
	ms: number
): F & { cancel: () => void; flush: () => void } {
	let timer: ReturnType<typeof setTimeout> | null = null;
	let lastArgs: Parameters<F> | null = null;

	const wrapped = ((...args: Parameters<F>) => {
		lastArgs = args;
		if (timer !== null) clearTimeout(timer);
		timer = setTimeout(() => {
			timer = null;
			const a = lastArgs;
			lastArgs = null;
			if (a) fn(...a);
		}, ms);
	}) as F & { cancel: () => void; flush: () => void };

	wrapped.cancel = () => {
		if (timer !== null) clearTimeout(timer);
		timer = null;
		lastArgs = null;
	};

	wrapped.flush = () => {
		if (timer !== null) {
			clearTimeout(timer);
			timer = null;
			const a = lastArgs;
			lastArgs = null;
			if (a) fn(...a);
		}
	};

	return wrapped;
}
