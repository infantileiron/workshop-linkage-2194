/** @typedef {{id: number, code: string, title: string, category: string, seats: number}} Course */
/** @typedef {{id: number, code: string, venue: string, state: string, codes: string[], family_key: string}} Enrollment */
/** @typedef {{id: number, title: string, status: string, note: string, parameters: object, result?: object}} Analysis */
/** @typedef {{id: number, title: string, course_a: string, course_b: string, state: string, note: string, ended_at: string|null}} Experiment */
/** @typedef {{id: number, experiment_id: number, family_key: string, group: string, group_label: string, first_venue: string, reused: boolean}} Assignment */
