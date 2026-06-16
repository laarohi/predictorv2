# Roaster sidecar: Node + the Claude Code CLI, used headless to write the Daily
# Drop roast on the user's subscription. Debian (glibc) base, NOT alpine — the
# CLI ships native helpers (ripgrep) that misbehave on musl.
FROM node:20-bookworm-slim

# The `claude` binary. Pinned major line; bump deliberately.
RUN npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force

WORKDIR /app
COPY server.js .

ENV PORT=8787
EXPOSE 8787

CMD ["node", "server.js"]
