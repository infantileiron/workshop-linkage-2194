// Mock 前端 API：返回测试夹具数据（在调用时读取，避免导入时序问题）。
export const api = {
  experimentList: async () => globalThis.__mock?.emptyList
    ? [] : [{id: 7, title: '11月推荐实验', state: 'running'}],
  experiment: async () => globalThis.__mock.detail,
  assignments: async () => globalThis.__mock.assignments ?? [],
  courses: async () => [
    {code: 'WOOD-11', title: '木雕浅刻'},
    {code: 'LACQ-24', title: '木片彩漆'},
  ],
  createExperiment: async d => ({id: 99, ...d}),
  assign: async (id, d) => ({family_key: d.family_key, group_label: '组合推荐', first_venue: d.venue, reused: false}),
  endExperiment: async () => ({}),
  experimentExport: async () => ({size: 1}),
};
