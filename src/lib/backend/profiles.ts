export interface EgoProfile {
  entry: string;
  code: string;
  name: string;
  team: string;
  color: string;
  nationality: string;
}

export const EGO_PROFILES: EgoProfile[] = [
  ['1', 'NOR', 'Lando Norris', 'McLaren', '#FF8000', 'GB'],
  ['3', 'VER', 'Max Verstappen', 'Red Bull Racing', '#3671C6', 'NL'],
  ['5', 'BOR', 'Gabriel Bortoleto', 'Audi', '#F50537', 'BR'],
  ['6', 'HAD', 'Isack Hadjar', 'Red Bull Racing', '#3671C6', 'FR'],
  ['10', 'GAS', 'Pierre Gasly', 'Alpine', '#0093CC', 'FR'],
  ['11', 'PER', 'Sergio Perez', 'Cadillac', '#B6BABD', 'MX'],
  ['12', 'ANT', 'Kimi Antonelli', 'Mercedes', '#27F4D2', 'IT'],
  ['14', 'ALO', 'Fernando Alonso', 'Aston Martin', '#229971', 'ES'],
  ['16', 'LEC', 'Charles Leclerc', 'Ferrari', '#E8002D', 'MC'],
  ['18', 'STR', 'Lance Stroll', 'Aston Martin', '#229971', 'CA'],
  ['23', 'ALB', 'Alexander Albon', 'Williams', '#64C4FF', 'TH'],
  ['27', 'HUL', 'Nico Hulkenberg', 'Audi', '#F50537', 'DE'],
  ['30', 'LAW', 'Liam Lawson', 'Racing Bulls', '#6692FF', 'NZ'],
  ['31', 'OCO', 'Esteban Ocon', 'Haas F1 Team', '#B6BABD', 'FR'],
  ['41', 'LIN', 'Arvid Lindblad', 'Racing Bulls', '#6692FF', 'GB'],
  ['43', 'COL', 'Franco Colapinto', 'Alpine', '#0093CC', 'AR'],
  ['44', 'HAM', 'Lewis Hamilton', 'Ferrari', '#E8002D', 'GB'],
  ['55', 'SAI', 'Carlos Sainz', 'Williams', '#64C4FF', 'ES'],
  ['63', 'RUS', 'George Russell', 'Mercedes', '#27F4D2', 'GB'],
  ['77', 'BOT', 'Valtteri Bottas', 'Cadillac', '#B6BABD', 'FI'],
  ['81', 'PIA', 'Oscar Piastri', 'McLaren', '#FF8000', 'AU'],
  ['87', 'BEA', 'Oliver Bearman', 'Haas F1 Team', '#B6BABD', 'GB'],
].map(([entry, code, name, team, color, nationality]) => ({ entry, code, name, team, color, nationality }));

export interface DiagnosticTrackOption {
  event: string;
  label: string;
  circuit: string;
  country: string;
  laps: string;
  length: string;
  turns: string;
  lapRecord: string;
  mapUrl?: string;
}

const TRACKS: Record<string, DiagnosticTrackOption> = {
  'Australian Grand Prix': { event: 'Australian Grand Prix', label: 'Australia', circuit: 'Albert Park Circuit', country: 'AU', laps: '58', length: '5.278 km', turns: '14', lapRecord: '1:19.813', mapUrl: '/australia.jpg' },
  'Chinese Grand Prix': { event: 'Chinese Grand Prix', label: 'China', circuit: 'Shanghai International Circuit', country: 'CN', laps: '56', length: '5.451 km', turns: '16', lapRecord: '1:32.238', mapUrl: '/china.jpg' },
  'Japanese Grand Prix': { event: 'Japanese Grand Prix', label: 'Japan', circuit: 'Suzuka International Racing Course', country: 'JP', laps: '53', length: '5.807 km', turns: '18', lapRecord: '1:30.983', mapUrl: '/japan.jpg' },
  'Miami Grand Prix': { event: 'Miami Grand Prix', label: 'Miami', circuit: 'Miami International Autodrome', country: 'US', laps: '57', length: '5.412 km', turns: '19', lapRecord: '1:29.708', mapUrl: '/miami.jpg' },
  'Canadian Grand Prix': { event: 'Canadian Grand Prix', label: 'Canada', circuit: 'Circuit Gilles Villeneuve', country: 'CA', laps: '70', length: '4.361 km', turns: '14', lapRecord: '1:13.078', mapUrl: '/canada.jpg' },
  'Monaco Grand Prix': { event: 'Monaco Grand Prix', label: 'Monaco', circuit: 'Circuit de Monaco', country: 'MC', laps: '78', length: '3.337 km', turns: '19', lapRecord: '1:12.909', mapUrl: '/monaco.jpg' },
  'Barcelona Grand Prix': { event: 'Barcelona Grand Prix', label: 'Barcelona', circuit: 'Circuit de Barcelona-Catalunya', country: 'ES', laps: '66', length: '4.657 km', turns: '14', lapRecord: '1:16.330', mapUrl: '/barcelona.jpg' },
  'Austrian Grand Prix': { event: 'Austrian Grand Prix', label: 'Austria', circuit: 'Red Bull Ring', country: 'AT', laps: '71', length: '4.318 km', turns: '10', lapRecord: '1:05.619', mapUrl: '/austria.jpg' },
  'British Grand Prix': { event: 'British Grand Prix', label: 'Britain', circuit: 'Silverstone Circuit', country: 'GB', laps: '52', length: '5.891 km', turns: '18', lapRecord: '1:27.097', mapUrl: '/britain.jpg' },
  'Spanish Grand Prix': { event: 'Spanish Grand Prix', label: 'Madrid test', circuit: 'Madring', country: 'ES', laps: 'Qualifying only', length: 'Not race-validated', turns: 'Not race-validated', lapRecord: 'No race record' },
};

const QUALIFYING_EVENTS = ['Australian Grand Prix', 'Chinese Grand Prix', 'Japanese Grand Prix', 'Miami Grand Prix', 'Canadian Grand Prix', 'Monaco Grand Prix', 'Barcelona Grand Prix', 'Austrian Grand Prix', 'British Grand Prix', 'Spanish Grand Prix'];
const RACE_EVENTS = ['Miami Grand Prix', 'Barcelona Grand Prix', 'Austrian Grand Prix', 'British Grand Prix'];

export function sessionTracks(mode: 'qualifying' | 'full-race'): DiagnosticTrackOption[] {
  return (mode === 'qualifying' ? QUALIFYING_EVENTS : RACE_EVENTS).map((event) => TRACKS[event]);
}

export function admittedProfiles(entries: string[] | undefined): EgoProfile[] {
  if (!entries || entries.length === 0) return EGO_PROFILES;
  const admitted = new Set(entries);
  return EGO_PROFILES.filter((profile) => admitted.has(profile.entry));
}

export function egoProfile(entry: string): EgoProfile {
  return EGO_PROFILES.find((profile) => profile.entry === entry) ?? EGO_PROFILES[0];
}
