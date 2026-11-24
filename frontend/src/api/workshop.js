import {send} from './client.js';
export const api = {
  login: data => send('/auth/login', data),
  courses: input => send('/courses', input),
  enrollments: (input, venue) => send('/enrollments' + (venue ? `?venue=${encodeURIComponent(venue)}` : ''), input),
  analyses: input => send('/analyses', input),
  analysis: id => send(`/analyses/${id}`),
  publish: (id, note) => send(`/analyses/${id}/publish`, {note}),
  export: id => send(`/analyses/${id}/export`, undefined, true),
  experimentList: () => send('/experiments'),
  experiment: id => send(`/experiments/${id}`),
  experimentExport: id => send(`/experiments/${id}/export`, undefined, true),
  createExperiment: data => send('/experiments', data),
  assignments: id => send(`/experiments/${id}/assignments`),
  assign: (id, data) => send(`/experiments/${id}/assignments`, data),
  endExperiment: (id, note) => send(`/experiments/${id}/end`, {note}),
};
