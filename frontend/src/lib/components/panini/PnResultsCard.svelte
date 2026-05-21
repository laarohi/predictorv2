<script lang="ts">
	// Desktop variant of the Results & Fixtures match card.
	// Mobile lives in PnResultsCardMobile — both feed off the same breakdown.
	import PnFlag from './PnFlag.svelte';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import { stageLabel, stageShort, type MatchBreakdown } from '$lib/utils/matchBreakdown';
	import type { Fixture, MatchPrediction } from '$types';
	import type { ScoringConfig } from '$api/competition';

	export let fixture: Fixture;
	export let prediction: MatchPrediction | undefined;
	export let breakdown: MatchBreakdown;
	export let config: ScoringConfig;
	/** Right-side metadata in the card header — typically "GROUPS · 18:00"
	 *  in date view, the kickoff date in group view, etc. */
	export let metaRight: string = '';

	$: stateLabel = (() => {
		const s = breakdown.state;
		if (s === 'finished') return 'FT';
		if (s === 'live')
			return fixture.minute != null ? `LIVE · ${fixture.minute}'` : 'LIVE';
		if (s === 'locked') return formatLockIn(fixture.time_until_lock);
		return 'OPEN';
	})();

	function formatLockIn(secs: number | null): string {
		if (secs == null || secs <= 0) return 'LOCK';
		const m = Math.floor(secs / 60);
		const s = Math.floor(secs % 60);
		if (m >= 60) {
			const h = Math.floor(m / 60);
			return `LOCK · ${h}h ${m % 60}m`;
		}
		return `LOCK · ${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	function fmtTime(iso: string): string {
		return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}

	function pillIcon(state: string): string {
		if (state.startsWith('hit-rarity')) return '★';
		if (state === 'miss') return '✗';
		if (state.startsWith('potential')) return '?';
		if (state === 'none') return '–';
		return '✓';
	}
	function pillPts(pts: number): string {
		if (pts === 0) return '0';
		return pts > 0 ? `+${pts}` : `${pts}`;
	}

	$: homeWon =
		fixture.score && fixture.score.home_score > fixture.score.away_score;
	$: awayWon =
		fixture.score && fixture.score.away_score > fixture.score.home_score;
</script>

<div class={'pn-rs-card ' + breakdown.state}>
	<div class="ch">
		<span class="grp">
			{#if fixture.group}
				Group <em>{fixture.group}</em>
			{:else}
				<em>{stageShort(fixture.stage)}</em> {stageLabel(fixture.stage)}
			{/if}
		</span>
		<span class="venue">{metaRight}</span>
		<span class={'state-pill ' + (breakdown.state === 'finished' ? 'ft' : breakdown.state)}>
			{stateLabel}
		</span>
	</div>

	<div class="scoreline">
		<div class={'team' + (awayWon ? ' lost' : homeWon ? ' won' : '')}>
			<span class="fl"><PnFlag code={teamCode(fixture.home_team)} w={42} h={28} /></span>
			<span class="nm">{displayTeamName(fixture.home_team)}</span>
		</div>

		<div class="centre">
			{#if breakdown.state === 'finished' && fixture.score}
				<div class="scorebox">
					{fixture.score.home_score}–{fixture.score.away_score}
					<span class="lbl">Full Time</span>
				</div>
			{:else if breakdown.state === 'live' && fixture.score}
				<div class="scorebox live">
					{fixture.score.home_score}–{fixture.score.away_score}
					<span class="lbl">● {fixture.minute != null ? fixture.minute + "'" : 'LIVE'}</span>
				</div>
			{:else}
				<div class="scorebox upcoming">
					<span class="vs">VS</span>
					<span class="lbl">{fmtTime(fixture.kickoff)}</span>
				</div>
			{/if}
			{#if prediction}
				<div class={'ypick ' + breakdown.ypickClass}>
					<span>{breakdown.ypickLabel}</span>
					<b>{prediction.home_score}–{prediction.away_score}</b>
				</div>
			{/if}
		</div>

		<div class={'team' + (homeWon ? ' lost' : awayWon ? ' won' : '')}>
			<span class="fl"><PnFlag code={teamCode(fixture.away_team)} w={42} h={28} /></span>
			<span class="nm">{displayTeamName(fixture.away_team)}</span>
		</div>
	</div>

	<div class={'pn-rs-bd ' + breakdown.tier}>
		<div class={'pill ' + breakdown.outcomePill.state}>
			<span class="pts">
				<span class="ic">{pillIcon(breakdown.outcomePill.state)}</span>{pillPts(
					breakdown.outcomePill.pts
				)}
			</span>
			<span class="lab">{breakdown.outcomePill.lab}</span>
		</div>
		<div class={'pill ' + breakdown.scorePill.state}>
			<span class="pts">
				<span class="ic">{pillIcon(breakdown.scorePill.state)}</span>{pillPts(
					breakdown.scorePill.pts
				)}
			</span>
			<span class="lab">{breakdown.scorePill.lab}</span>
		</div>
		{#if config.mode !== 'fixed'}
			<div class={'pill ' + breakdown.rarityPill.state}>
				<span class="pts">
					<span class="ic">{pillIcon(breakdown.rarityPill.state)}</span>{pillPts(
						breakdown.rarityPill.pts
					)}
				</span>
				<span class="lab">{breakdown.rarityPill.lab}</span>
			</div>
		{/if}
		<div class="total">
			<span class="v">{breakdown.totalDisplay}</span>
			<span class="lab">{breakdown.totalLabel}</span>
		</div>
	</div>
</div>
