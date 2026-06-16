// Roaster sidecar (dev-only). A tiny HTTP server whose single job is to run the
// Claude Code CLI headless — on the user's SUBSCRIPTION (CLAUDE_CODE_OAUTH_TOKEN),
// never an API key — and hand the generated text back to the backend.
//
//   POST /roast  { "prompt": "..." }  ->  { "roast": "..." }
//   GET  /health                      ->  { "ok": true }
//
// The backend assembles the whole prompt; this process owns no domain logic.

const http = require('http');
const { spawn } = require('child_process');

const PORT = parseInt(process.env.PORT || '8787', 10);
const MODEL = (process.env.ROAST_MODEL || '').trim(); // empty => account default
const TIMEOUT_MS = parseInt(process.env.ROAST_TIMEOUT_MS || '90000', 10);

function runClaude(prompt) {
	return new Promise((resolve, reject) => {
		const args = ['-p', '--output-format', 'text'];
		if (MODEL) args.push('--model', MODEL);

		// Subscription (OAuth) auth must win — an API key in the env would take
		// precedence and silently bill a key instead of the Max plan.
		const env = { ...process.env };
		delete env.ANTHROPIC_API_KEY;

		const child = spawn('claude', args, { env, cwd: '/tmp' });
		let out = '';
		let err = '';
		const timer = setTimeout(() => {
			child.kill('SIGKILL');
			reject(new Error(`claude timed out after ${TIMEOUT_MS}ms`));
		}, TIMEOUT_MS);

		child.stdout.on('data', (d) => (out += d));
		child.stderr.on('data', (d) => (err += d));
		child.on('error', (e) => {
			clearTimeout(timer);
			reject(e);
		});
		child.on('close', (code) => {
			clearTimeout(timer);
			if (code === 0) resolve(out.trim());
			else reject(new Error(`claude exited ${code}: ${err.slice(0, 800)}`));
		});

		child.stdin.end(prompt);
	});
}

function send(res, status, obj) {
	res.writeHead(status, { 'Content-Type': 'application/json' });
	res.end(JSON.stringify(obj));
}

const server = http.createServer((req, res) => {
	if (req.method === 'GET' && req.url === '/health') return send(res, 200, { ok: true });

	if (req.method === 'POST' && req.url === '/roast') {
		let body = '';
		req.on('data', (c) => {
			body += c;
			if (body.length > 1_000_000) req.destroy(); // sanity cap
		});
		req.on('end', async () => {
			let prompt;
			try {
				prompt = JSON.parse(body).prompt;
			} catch {
				return send(res, 400, { error: 'invalid json' });
			}
			if (!prompt || typeof prompt !== 'string') return send(res, 400, { error: 'no prompt' });
			try {
				const roast = await runClaude(prompt);
				if (!roast) {
					console.error('roast: claude returned empty output');
					return send(res, 502, { error: 'empty roast' });
				}
				send(res, 200, { roast });
			} catch (e) {
				console.error('roast: claude failed —', String((e && e.message) || e));
				send(res, 500, { error: String((e && e.message) || e) });
			}
		});
		return;
	}

	send(res, 404, { error: 'not found' });
});

server.listen(PORT, () =>
	console.log(`roaster listening on :${PORT} (model=${MODEL || 'account default'})`)
);
