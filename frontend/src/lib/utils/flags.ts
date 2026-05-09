/**
 * Country name to ISO 3166-1 alpha-2 code mapping.
 * This is a pure lookup table for displaying country flags.
 *
 * The actual tournament teams and group assignments are configured
 * in the backend database/YAML config, not here.
 *
 * This file just needs country codes for any team that might appear.
 */
const countryCodeMap: Record<string, string> = {
	// ===== NORTH & CENTRAL AMERICA (CONCACAF) =====
	'USA': 'us',
	'United States': 'us',
	'Mexico': 'mx',
	'Canada': 'ca',
	'Costa Rica': 'cr',
	'Panama': 'pa',
	'Jamaica': 'jm',
	'Honduras': 'hn',
	'El Salvador': 'sv',
	'Guatemala': 'gt',
	'Haiti': 'ht',
	'Trinidad and Tobago': 'tt',
	'Curacao': 'cw',
	'Curaçao': 'cw',

	// ===== SOUTH AMERICA (CONMEBOL) =====
	'Brazil': 'br',
	'Argentina': 'ar',
	'Uruguay': 'uy',
	'Colombia': 'co',
	'Chile': 'cl',
	'Ecuador': 'ec',
	'Paraguay': 'py',
	'Peru': 'pe',
	'Venezuela': 've',
	'Bolivia': 'bo',

	// ===== EUROPE (UEFA) =====
	'Germany': 'de',
	'France': 'fr',
	'England': 'gb-eng',
	'Spain': 'es',
	'Italy': 'it',
	'Portugal': 'pt',
	'Netherlands': 'nl',
	'Belgium': 'be',
	'Croatia': 'hr',
	'Switzerland': 'ch',
	'Denmark': 'dk',
	'Austria': 'at',
	'Poland': 'pl',
	'Serbia': 'rs',
	'Ukraine': 'ua',
	'Turkey': 'tr',
	'Scotland': 'gb-sct',
	'Wales': 'gb-wls',
	'Czech Republic': 'cz',
	'Czechia': 'cz',
	'Sweden': 'se',
	'Norway': 'no',
	'Hungary': 'hu',
	'Romania': 'ro',
	'Greece': 'gr',
	'Ireland': 'ie',
	'Republic of Ireland': 'ie',
	'Northern Ireland': 'gb-nir',
	'Iceland': 'is',
	'Finland': 'fi',
	'Slovakia': 'sk',
	'Slovenia': 'si',
	'Albania': 'al',
	'North Macedonia': 'mk',
	'Bosnia': 'ba',
	'Bosnia and Herzegovina': 'ba',
	'Bosnia-Herzegovina': 'ba',
	'Montenegro': 'me',
	'Georgia': 'ge',
	'Armenia': 'am',
	'Azerbaijan': 'az',
	'Israel': 'il',
	'Russia': 'ru',
	'Cyprus': 'cy',
	'Kosovo': 'xk',
	'Luxembourg': 'lu',
	'Belarus': 'by',
	'Moldova': 'md',
	'Estonia': 'ee',
	'Latvia': 'lv',
	'Lithuania': 'lt',
	'Kazakhstan': 'kz',

	// ===== ASIA (AFC) =====
	'Japan': 'jp',
	'South Korea': 'kr',
	'Korea Republic': 'kr',
	'Australia': 'au',
	'Saudi Arabia': 'sa',
	'Iran': 'ir',
	'Qatar': 'qa',
	'Iraq': 'iq',
	'China': 'cn',
	'China PR': 'cn',
	'Indonesia': 'id',
	'Vietnam': 'vn',
	'Thailand': 'th',
	'Malaysia': 'my',
	'Uzbekistan': 'uz',
	'Jordan': 'jo',
	'Oman': 'om',
	'Bahrain': 'bh',
	'UAE': 'ae',
	'United Arab Emirates': 'ae',
	'Kuwait': 'kw',
	'Syria': 'sy',
	'Palestine': 'ps',
	'Lebanon': 'lb',
	'India': 'in',
	'Philippines': 'ph',
	'Singapore': 'sg',
	'North Korea': 'kp',
	'Kyrgyzstan': 'kg',
	'Tajikistan': 'tj',
	'Hong Kong': 'hk',
	'Turkmenistan': 'tm',
	'Yemen': 'ye',
	'Myanmar': 'mm',
	'Cambodia': 'kh',
	'Laos': 'la',
	'Nepal': 'np',
	'Bangladesh': 'bd',
	'Sri Lanka': 'lk',
	'Maldives': 'mv',
	'Brunei': 'bn',
	'Timor-Leste': 'tl',
	'Guam': 'gu',

	// ===== AFRICA (CAF) =====
	'Morocco': 'ma',
	'Nigeria': 'ng',
	'Senegal': 'sn',
	'Egypt': 'eg',
	'Cameroon': 'cm',
	'Ghana': 'gh',
	'South Africa': 'za',
	'Tunisia': 'tn',
	'Algeria': 'dz',
	'Ivory Coast': 'ci',
	"Cote d'Ivoire": 'ci',
	'Mali': 'ml',
	'Burkina Faso': 'bf',
	'Congo': 'cg',
	'DR Congo': 'cd',
	'Congo DR': 'cd',
	'Democratic Republic of the Congo': 'cd',
	'Zambia': 'zm',
	'Zimbabwe': 'zw',
	'Mozambique': 'mz',
	'Uganda': 'ug',
	'Kenya': 'ke',
	'Tanzania': 'tz',
	'Ethiopia': 'et',
	'Sudan': 'sd',
	'Libya': 'ly',
	'Equatorial Guinea': 'gq',
	'Gabon': 'ga',
	'Cape Verde': 'cv',
	'Cape Verde Islands': 'cv',
	'Benin': 'bj',
	'Togo': 'tg',
	'Niger': 'ne',
	'Mauritania': 'mr',
	'Guinea': 'gn',
	'Gambia': 'gm',
	'Sierra Leone': 'sl',
	'Liberia': 'lr',
	'Angola': 'ao',
	'Namibia': 'na',
	'Botswana': 'bw',
	'Madagascar': 'mg',
	'Comoros': 'km',
	'Rwanda': 'rw',
	'Burundi': 'bi',
	'Central African Republic': 'cf',
	'Chad': 'td',
	'Mauritius': 'mu',
	'South Sudan': 'ss',
	'Djibouti': 'dj',
	'Eritrea': 'er',
	'Somalia': 'so',
	'Seychelles': 'sc',
	'Guinea-Bissau': 'gw',
	'Eswatini': 'sz',
	'Swaziland': 'sz',
	'Lesotho': 'ls',
	'Malawi': 'mw',

	// ===== OCEANIA (OFC) =====
	'New Zealand': 'nz',
	'Papua New Guinea': 'pg',
	'Fiji': 'fj',
	'Solomon Islands': 'sb',
	'Tahiti': 'pf',
	'New Caledonia': 'nc',
	'Vanuatu': 'vu',
	'Samoa': 'ws',
	'Tonga': 'to',
	'American Samoa': 'as',
	'Cook Islands': 'ck',

	// ===== SPECIAL =====
	'TBD': '', // Placeholder for teams to be determined
};

/**
 * Get the flag image URL for a country
 * Uses flagcdn.com for reliable, fast flag delivery
 */
export function getFlagUrl(countryName: string, size: 'sm' | 'md' | 'lg' = 'sm'): string {
	const code = countryCodeMap[countryName];

	if (!code) {
		return '';
	}

	// flagcdn.com provides flags in various sizes
	const width = size === 'sm' ? 20 : size === 'md' ? 40 : 80;
	return `https://flagcdn.com/w${width}/${code}.png`;
}

/**
 * Get the country code for a country name
 */
export function getCountryCode(countryName: string): string {
	return countryCodeMap[countryName] || '';
}

/**
 * Check if a country has a known flag
 */
export function hasFlag(countryName: string): boolean {
	return !!countryCodeMap[countryName];
}
