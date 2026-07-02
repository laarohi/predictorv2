<script lang="ts">
	/**
	 * Team-centric bracket-pick "run bars" for the profile page.
	 *
	 * A bracket is fully described by one predicted depth per team (picking a
	 * team for the final implies every earlier round), so instead of per-stage
	 * tag clouds this renders one row per team with paired Phase I / Phase II
	 * bars spanning to their predicted depth — the two phases sit directly on
	 * top of each other, and each segment is coloured by what actually
	 * happened: proven (team reached it), busted (team was out before it, ✖ at
	 * the death point), or still in play.
	 *
	 * Teams whose only pick is "gets out of the group" (R32-only) carry no
	 * depth information and collapse into a compact footer strip, as do the
	 * Phase-1 group-winner picks.
	 */
	import type { PointsLogEvent, ProfileQualEntry } from '$types';
	import { STAGE_IDX, type TeamFate } from '$lib/utils/bracketFate';
	import { teamCode } from '$lib/utils/teamCodes';
	import PnFlag from '$components/panini/PnFlag.svelte';

	export let phase1Stages: Record<string, string[]>;
	export let phase2Stages: Record<string, string[]>;
	export let fate: TeamFate;
	/** Advance-kind points-log events — per-team banked advancement points.
	 *  Null when the points log couldn't be loaded (points column hides). */
	export let advanceEvents: PointsLogEvent[] | null;
	export let qualLedger: ProfileQualEntry[];

	const COLS: Array<[string, string]> = [
		['round_of_32', 'R32'],
		['round_of_16', 'R16'],
		['quarter_final', 'QF'],
		['semi_final', 'SF'],
		['final', 'FIN'],
		['winner', 'WIN']
	];
	const R16_IDX = STAGE_IDX.round_of_16;

	/** team → deepest predicted stage index for one phase's stage map. */
	function depths(stages: Record<string, string[]>, minIdx: number): Map<string, number> {
		const out = new Map<string, number>();
		for (const [stage, teams] of Object.entries(stages)) {
			const idx = STAGE_IDX[stage];
			if (!idx || idx < minIdx) continue;
			for (const t of teams) out.set(t, Math.max(out.get(t) ?? 0, idx));
		}
		return out;
	}

	$: p1Depth = depths(phase1Stages, STAGE_IDX.round_of_32);
	// Phase 2 re-picks start at R16 — the R32 line-up is published, not predicted.
	$: p2Depth = depths(phase2Stages, R16_IDX);
	$: hasP2 = p2Depth.size > 0;

	$: pointsByTeam = (() => {
		if (!advanceEvents) return null;
		const m = new Map<string, number>();
		for (const e of advanceEvents) {
			if (e.team) m.set(e.team, (m.get(e.team) ?? 0) + e.points);
		}
		return m;
	})();

	// The points log is the scoring engine's own view of each team's fate, so
	// where it's available it OVERRIDES the fixture-derived fate — the bars can
	// then never disagree with the points sitting next to them. (Qualification
	// via the best-thirds cut lives in standings math, not in any fixture, so
	// fixture-only fate can lag or — on synthetic dev data — contradict it.)
	$: evReached = (() => {
		const m = new Map<string, number>();
		for (const e of advanceEvents ?? []) {
			if (!e.team || e.is_miss || !e.stage) continue;
			const idx = STAGE_IDX[e.stage];
			if (idx) m.set(e.team, Math.max(m.get(e.team) ?? 0, idx));
		}
		return m;
	})();
	$: evDead = (() => {
		const s = new Set<string>();
		for (const e of advanceEvents ?? []) {
			if (e.team && e.is_miss) s.add(e.team);
		}
		return s;
	})();

	/** How deep the team actually got (stage index; 0 = never left the group). */
	function reachedIdx(team: string): number {
		let max = evReached.get(team) ?? 0;
		for (const [stage, teams] of fate.reached) {
			const idx = STAGE_IDX[stage];
			if (idx && teams.has(team)) max = Math.max(max, idx);
		}
		return max;
	}
	function isDead(team: string): boolean {
		if (evDead.has(team)) return true;
		const out = fate.outAt.get(team);
		// A fixture-derived death below the engine-confirmed depth is stale —
		// ignore it rather than paint a qualified team as dead.
		return out !== undefined && out >= (evReached.get(team) ?? 0);
	}

	/** R32 fate with the engine overlay applied (strips + fallbacks). */
	function r32State(team: string): 'in' | 'out' | 'tbd' {
		if (reachedIdx(team) >= STAGE_IDX.round_of_32) return 'in';
		if (isDead(team)) return 'out';
		return 'tbd';
	}

	// Teams with real depth picks (beyond R32 in either phase), deepest first.
	$: deepTeams = (() => {
		const teams = new Set<string>();
		for (const [t, d] of p1Depth) if (d >= R16_IDX) teams.add(t);
		for (const t of p2Depth.keys()) teams.add(t);
		return [...teams].sort((a, b) => {
			const da = Math.max(p1Depth.get(a) ?? 0, p2Depth.get(a) ?? 0);
			const db = Math.max(p1Depth.get(b) ?? 0, p2Depth.get(b) ?? 0);
			if (db !== da) return db - da;
			const pa = pointsByTeam?.get(a) ?? 0;
			const pb = pointsByTeam?.get(b) ?? 0;
			if (pb !== pa) return pb - pa;
			return a.localeCompare(b);
		});
	})();

	// Picked to get out of the group, never deeper (in either phase).
	$: r32Only = [...p1Depth.entries()]
		.filter(([t, d]) => d < R16_IDX && (p2Depth.get(t) ?? 0) < R16_IDX && !deepTeams.includes(t))
		.map(([t]) => t)
		.sort((a, b) => stripRank(r32State(a)) - stripRank(r32State(b)) || a.localeCompare(b));

	function stripRank(f: 'in' | 'out' | 'tbd'): number {
		return f === 'in' ? 0 : f === 'tbd' ? 1 : 2;
	}

	$: r32OnlyHits = r32Only.filter((t) => r32State(t) === 'in').length;
	$: r32OnlyPts = pointsByTeam
		? r32Only.reduce((n, t) => n + (pointsByTeam?.get(t) ?? 0), 0)
		: null;

	// --- Group-winner picks strip -------------------------------------------
	// Exact finishing spot from the qualification ledger where available
	// (it covers every team the user scored on); fate-based fallback otherwise.
	$: ledgerPos = (() => {
		const m = new Map<string, number>();
		for (const entry of qualLedger) {
			for (const t of entry.teams) m.set(t.team, t.actual_position);
		}
		return m;
	})();
	type WinnerState = 'won' | 'qual' | 'out' | 'tbd';
	function winnerState(team: string): WinnerState {
		const pos = ledgerPos.get(team);
		if (pos === 1) return 'won';
		if (pos != null) return 'qual';
		const f = r32State(team);
		return f === 'in' ? 'qual' : f === 'out' ? 'out' : 'tbd';
	}
	const WINNER_RANK: Record<WinnerState, number> = { won: 0, qual: 1, tbd: 2, out: 3 };
	const WINNER_MARK: Record<WinnerState, string> = { won: '✓', qual: '~', out: '✖', tbd: '·' };
	$: groupWinners = [...(phase1Stages.group ?? [])].sort(
		(a, b) => WINNER_RANK[winnerState(a)] - WINNER_RANK[winnerState(b)] || a.localeCompare(b)
	);
	$: groupWinnersHit = groupWinners.filter((t) => winnerState(t) === 'won').length;

	type SegState = 'void' | 'hit' | 'dead' | 'open';
	/** Segment states for one bar spanning startIdx..depth across all 6 columns. */
	function segments(team: string, startIdx: number, depth: number | undefined): SegState[] {
		const reached = reachedIdx(team);
		const dead = isDead(team);
		return COLS.map(([stage]) => {
			const idx = STAGE_IDX[stage];
			if (!depth || idx < startIdx || idx > depth) return 'void';
			if (idx <= reached) return 'hit';
			return dead ? 'dead' : 'open';
		});
	}
	/** Column index of the ✖ marker (first dead segment), or -1. */
	function deathCol(segs: SegState[]): number {
		return segs.indexOf('dead');
	}

	function fmtPts(team: string): string {
		const p = pointsByTeam?.get(team) ?? 0;
		return p > 0 ? `+${p}` : '·';
	}
</script>

{#if deepTeams.length > 0 || r32Only.length > 0 || groupWinners.length > 0}
	<div class="runs">
		<div class="legend">
			<span><i class="sw hit"></i>banked</span>
			<span><i class="sw open"></i>in play</span>
			<span><i class="sw dead">✖</i>busted</span>
			{#if hasP2}<span class="phases">bar I pre-tournament · II re-pick</span>{/if}
		</div>
		{#if !hasP2 && deepTeams.length > 0}
			<p class="carrynote">
				No Phase II re-pick — the Phase I bracket carried forward at Phase II point values.
			</p>
		{/if}

		{#if deepTeams.length > 0}
			<div class="hdr" class:nopts={!pointsByTeam}>
				<span class="lbl"></span>
				<div class="cols">
					{#each COLS as [key, label] (key)}<span>{label}</span>{/each}
				</div>
				{#if pointsByTeam}<span class="pts">PTS</span>{/if}
			</div>

			{#each deepTeams as team (team)}
				{@const s1 = segments(team, STAGE_IDX.round_of_32, p1Depth.get(team))}
				{@const s2 = segments(team, R16_IDX, p2Depth.get(team))}
				{@const showP2 = hasP2}
				<div class="team" class:nopts={!pointsByTeam}>
					<span class="lbl">
						<PnFlag code={teamCode(team)} w={16} h={12} />
						<span class="code">{teamCode(team)}</span>
					</span>
					<div class="bars">
						<div class="bar">
							<span class="ph">I</span>
							<div class="cols">
								{#if p1Depth.has(team)}
									{#each s1 as seg, i (COLS[i][0])}
										<span class="seg {seg}">{#if i === deathCol(s1)}✖{/if}</span>
									{/each}
								{:else}
									<span class="nopick">not picked</span>
								{/if}
							</div>
						</div>
						{#if showP2}
							<div class="bar">
								<span class="ph">II</span>
								<div class="cols">
									{#if p2Depth.has(team)}
										{#each s2 as seg, i (COLS[i][0])}
											<span class="seg {seg}">{#if i === deathCol(s2)}✖{/if}</span>
										{/each}
									{:else}
										<span class="nopick">not re-picked</span>
									{/if}
								</div>
							</div>
						{/if}
					</div>
					{#if pointsByTeam}
						<span class="pts" class:zero={(pointsByTeam.get(team) ?? 0) === 0}>{fmtPts(team)}</span>
					{/if}
				</div>
			{/each}
		{/if}

		{#if r32Only.length > 0}
			<div class="strip">
				<div class="striphead">
					<span>R32 only · {r32OnlyHits}/{r32Only.length} qualified</span>
					{#if r32OnlyPts !== null && r32OnlyPts > 0}<span class="sp">+{r32OnlyPts} pts</span>{/if}
				</div>
				<div class="tags">
					{#each r32Only as team (team)}
						{@const f = r32State(team)}
						<span class="mini {f}">
							<b>{f === 'in' ? '✓' : f === 'out' ? '✖' : '·'}</b>
							<PnFlag code={teamCode(team)} w={13} h={10} />{teamCode(team)}
						</span>
					{/each}
				</div>
			</div>
		{/if}

		{#if groupWinners.length > 0}
			<div class="strip">
				<div class="striphead">
					<span>Group winner picks · {groupWinnersHit}/{groupWinners.length} won their group</span>
					<span class="sp">~ qualified anyway</span>
				</div>
				<div class="tags">
					{#each groupWinners as team (team)}
						{@const st = winnerState(team)}
						<span class="mini {st === 'won' ? 'in' : st === 'qual' ? 'part' : st === 'out' ? 'out' : 'tbd'}">
							<b>{WINNER_MARK[st]}</b>
							<PnFlag code={teamCode(team)} w={13} h={10} />{teamCode(team)}
						</span>
					{/each}
				</div>
			</div>
		{/if}
	</div>
{/if}

<style>
	.runs {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.carrynote {
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 10px;
	}
	.legend {
		display: flex;
		align-items: center;
		gap: 14px;
		flex-wrap: wrap;
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-2);
		margin-bottom: 12px;
	}
	.legend span {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}
	.legend .phases {
		margin-left: auto;
		color: var(--ink-3);
	}
	.sw {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 16px;
		height: 11px;
		font-size: 8px;
		font-style: normal;
	}
	.sw.hit {
		background: var(--green);
		border: 1.5px solid var(--ink);
	}
	.sw.open {
		background: var(--paper-2);
		border: 1.5px dashed var(--ink-3);
	}
	.sw.dead {
		background: rgba(200, 40, 31, 0.14);
		border: 1.5px solid rgba(200, 40, 31, 0.45);
		color: var(--red);
		font-weight: 700;
	}

	/* Shared row scaffolding: label | track | points */
	.hdr,
	.team {
		display: grid;
		grid-template-columns: 60px 1fr 46px;
		gap: 10px;
		align-items: center;
	}
	.hdr.nopts,
	.team.nopts {
		grid-template-columns: 60px 1fr;
	}
	.hdr {
		margin-bottom: 6px;
	}
	.hdr .cols,
	.bar .cols {
		display: grid;
		grid-template-columns: repeat(6, 1fr);
		gap: 3px;
	}
	.hdr .cols span {
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.1em;
		text-align: center;
		color: var(--ink-3);
	}
	.hdr .pts {
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.1em;
		text-align: right;
		color: var(--ink-3);
	}

	.team {
		padding: 7px 0;
		border-top: 1px solid var(--paper-3);
	}
	.team .lbl {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.team .code {
		font-family: var(--mono);
		font-weight: 700;
		font-size: 12px;
		color: var(--ink);
	}
	.bars {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.bar {
		display: grid;
		grid-template-columns: 12px 1fr;
		gap: 5px;
		align-items: center;
	}
	.bar .ph {
		font-family: var(--mono);
		font-size: 8px;
		letter-spacing: 0.05em;
		color: var(--ink-3);
		text-align: right;
	}
	.seg {
		height: 13px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 9px;
		line-height: 1;
	}
	.seg.void {
		background: transparent;
	}
	.seg.hit {
		background: var(--green);
		border: 1.5px solid var(--ink);
	}
	.seg.open {
		background: var(--paper-2);
		border: 1.5px dashed var(--ink-3);
	}
	.seg.dead {
		background: rgba(200, 40, 31, 0.14);
		border: 1.5px solid rgba(200, 40, 31, 0.45);
		color: var(--red);
		font-weight: 700;
	}
	.nopick {
		grid-column: 1 / -1;
		font-family: var(--mono);
		font-size: 9px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		align-self: center;
	}
	.team .pts {
		font-family: var(--display);
		font-size: 15px;
		text-align: right;
		color: var(--green);
	}
	.team .pts.zero {
		color: var(--ink-3);
	}

	/* Footer strips */
	.strip {
		margin-top: 14px;
		border-top: 2px solid var(--paper-3);
		padding-top: 10px;
	}
	.striphead {
		display: flex;
		justify-content: space-between;
		gap: 10px;
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--ink-2);
		margin-bottom: 8px;
	}
	.striphead .sp {
		color: var(--ink-3);
	}
	.tags {
		display: flex;
		flex-wrap: wrap;
		gap: 5px;
	}
	.mini {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-family: var(--mono);
		font-size: 10.5px;
		font-weight: 700;
		padding: 2px 7px;
		border: 1.5px solid var(--ink);
		background: var(--paper-2);
		color: var(--ink);
	}
	.mini b {
		font-size: 9px;
	}
	.mini.in {
		border-color: var(--green);
	}
	.mini.in b {
		color: var(--green);
	}
	.mini.part {
		border-color: var(--gold);
	}
	.mini.part b {
		color: var(--gold);
	}
	.mini.out {
		border-color: rgba(200, 40, 31, 0.55);
		opacity: 0.6;
	}
	.mini.out b {
		color: var(--red);
	}
	.mini.tbd {
		border-color: var(--ink-3);
		color: var(--ink-2);
	}

	@media (max-width: 460px) {
		.hdr,
		.team {
			grid-template-columns: 50px 1fr 38px;
			gap: 7px;
		}
		.hdr.nopts,
		.team.nopts {
			grid-template-columns: 50px 1fr;
		}
		.team .code {
			font-size: 11px;
		}
		.team .pts {
			font-size: 13px;
		}
		.seg {
			height: 11px;
		}
	}
</style>
