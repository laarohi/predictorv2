/**
 * Team-name display helpers.
 *
 * Knockout fixtures whose teams haven't been determined yet are seeded with
 * placeholder strings of the form "slot:<stage>:<external_id>:<side>". These
 * are unique (so the upsert by external_id stays sound) but useless to show
 * to a user. This module centralises the detection + formatting so every
 * rendering site shows a consistent "TBD" instead.
 */

const SLOT_PREFIX = 'slot:';

/**
 * Returns true if the given team string is a synthesised placeholder
 * for an unresolved knockout fixture.
 */
export function isPlaceholderTeam(name: string | null | undefined): boolean {
	return typeof name === 'string' && name.startsWith(SLOT_PREFIX);
}

/**
 * Format a team name for display. Placeholder slot strings render as "TBD";
 * real names pass through unchanged.
 */
export function displayTeamName(name: string | null | undefined): string {
	if (!name) return 'TBD';
	if (isPlaceholderTeam(name)) return 'TBD';
	return name;
}
