import { Participant } from '../types';

export interface FixtureEntry extends Participant {
  /** Seconds per lap slower than the fastest entry. */
  paceOffsetS: number;
  /** Tyre degradation, seconds added per lap of stint age. */
  degPerLapS: number;
}

const RAW: [string, string, string, number, string, number, number][] = [
  ['VER', 'Max Verstappen', 'Red Bull Racing', 1, '#1E5BC6', 0.0, 0.045],
  ['NOR', 'Lando Norris', 'McLaren', 4, '#FF8000', 0.18, 0.042],
  ['LEC', 'Charles Leclerc', 'Ferrari', 16, '#E8002D', 0.31, 0.048],
  ['RUS', 'George Russell', 'Mercedes', 63, '#27F4D2', 0.44, 0.044],
  ['PIA', 'Oscar Piastri', 'McLaren', 81, '#FF8000', 0.52, 0.043],
  ['HAM', 'Lewis Hamilton', 'Ferrari', 44, '#E8002D', 0.67, 0.049],
  ['ANT', 'Andrea Antonelli', 'Mercedes', 12, '#27F4D2', 0.81, 0.046],
  ['ALO', 'Fernando Alonso', 'Aston Martin', 14, '#229971', 0.98, 0.051],
  ['TSU', 'Yuki Tsunoda', 'Red Bull Racing', 22, '#1E5BC6', 1.12, 0.047],
  ['GAS', 'Pierre Gasly', 'Alpine', 10, '#0093CC', 1.29, 0.052],
  ['HAD', 'Isack Hadjar', 'Racing Bulls', 6, '#6692FF', 1.41, 0.050],
  ['SAI', 'Carlos Sainz', 'Williams', 55, '#64C4FF', 1.58, 0.053],
  ['ALB', 'Alexander Albon', 'Williams', 23, '#64C4FF', 1.73, 0.051],
  ['HUL', 'Nico Hulkenberg', 'Kick Sauber', 27, '#52E252', 1.94, 0.055],
  ['OCO', 'Esteban Ocon', 'Haas', 31, '#B6BABD', 2.11, 0.054],
  ['LAW', 'Liam Lawson', 'Racing Bulls', 30, '#6692FF', 2.28, 0.052],
  ['STR', 'Lance Stroll', 'Aston Martin', 18, '#229971', 2.47, 0.056],
  ['BEA', 'Oliver Bearman', 'Haas', 87, '#B6BABD', 2.69, 0.055],
  ['BOR', 'Gabriel Bortoleto', 'Kick Sauber', 5, '#52E252', 2.94, 0.058],
  ['COL', 'Franco Colapinto', 'Alpine', 43, '#0093CC', 4.35, 0.061],
];

/** Twenty entries. The last is deliberately slow enough to be lapped. */
export const ROSTER: FixtureEntry[] = RAW.map(
  ([code, name, team, raceNumber, teamColor, paceOffsetS, degPerLapS]) => ({
    id: code,
    code,
    name,
    team,
    raceNumber,
    teamColor,
    paceOffsetS,
    degPerLapS,
  }),
);

export const byId = (id: string): FixtureEntry =>
  ROSTER.find((e) => e.id === id) ?? ROSTER[0];
