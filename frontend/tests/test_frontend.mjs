// 推荐实验页面渲染冒烟测试（Node 原生 ESM，无需浏览器）。
// 运行：node --experimental-loader ./loader.mjs test_frontend.mjs
const mem = new Map();
globalThis.sessionStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};

const pageUrl = new URL('../src/pages/experiments.js', import.meta.url);
const {experiments} = await import(pageUrl.pathname);

const reportRows = [
  {'首次进组场馆': '河湾老仓', '样本是否充足': '充足', '组合推荐家庭数': 4, '组合推荐联报数': 1, '组合推荐联报率': 0.25,
   '单课推荐家庭数': 3, '单课推荐联报数': 2, '单课推荐联报率': 0.6667, '联报率提升（百分点）': -41.67, '相对提升': -0.625,
   '未报名家庭（组合/单课）': '1/1', '取消家庭（组合/单课）': '1/0'},
  {'首次进组场馆': '槐里快闪', '样本是否充足': '样本不足（缺单课推荐）', '组合推荐家庭数': 3, '组合推荐联报数': 1, '组合推荐联报率': 0.3333,
   '单课推荐家庭数': 0, '单课推荐联报数': 0, '单课推荐联报率': null, '联报率提升（百分点）': null, '相对提升': null,
   '未报名家庭（组合/单课）': '1/0', '取消家庭（组合/单课）': '0/0'},
];
globalThis.__mock = {
  detail: {
    experiment: {id: 7, title: '11月推荐实验', course_a: 'WOOD-11', course_b: 'LACQ-24', state: 'running', note: '', ended_at: null},
    frozen: false,
    metrics: {'参与家庭总数': 7, '组合推荐联报率': 0.2857, '单课推荐联报率': 0.5, '联报率提升（百分点）': -21.43, '样本充足场馆数': 1, '场馆总数': 2},
    rows: reportRows,
    notes: ['分母为全部已登记分组的家庭。', '一份 confirmed 报名同时勾选两门目标课程即记为联报。'],
  },
  assignments: [
    {id: 1, experiment_id: 7, family_key: 'FAM-01', group: 'combo', group_label: '组合推荐', first_venue: '河湾老仓', reused: false, created_at: '2026-11-24T08:00:00'},
    {id: 2, experiment_id: 7, family_key: 'FAM-02', group: 'single', group_label: '单课推荐', first_venue: '河湾老仓', reused: true, created_at: '2026-11-24T08:05:00'},
  ],
};

const fail = [];
const ok = (name, cond, extra = '') => {
  console.log(cond ? 'PASS' : 'FAIL', name, extra);
  if (!cond) fail.push(name);
};

sessionStorage.setItem('hemu-session', JSON.stringify({role: 'analyst', token: 't'}));
const view = await experiments(7);
const html = view.html;
ok('renders heading', html.includes('推荐实验核查'));
ok('shows experiment title', html.includes('11月推荐实验'));
ok('shows combo rate formatted', html.includes('28.57%'));
ok('shows single rate formatted', html.includes('50.00%'));
ok('shows lift in pp', html.includes('-21.43 个百分点'));
ok('venue row present', html.includes('河湾老仓') && html.includes('槐里快闪'));
ok('insufficient sample labeled', html.includes('样本不足（缺单课推荐）'));
ok('null rate renders as undefined text', html.includes('未定义'));
ok('assignment table shows family', html.includes('FAM-01') && html.includes('组合推荐'));
ok('analyst sees assign form', html.includes('家庭分组登记') && html.includes('id="assign-form"'));
ok('analyst sees create card', html.includes('id="experiment-form"'));
ok('export button present', html.includes('id="experiment-export"'));
ok('manager-only end form hidden for analyst', !html.includes('id="end-form"'));
ok('notes rendered', html.includes('分母为全部已登记分组的家庭。'));
ok('bind is function', typeof view.bind === 'function');
ok('shows live preview badge', html.includes('实时预览（到期后冻结）'));

sessionStorage.setItem('hemu-session', JSON.stringify({role: 'viewer', token: 't'}));
const readonly = await experiments(7);
ok('viewer no assign form', !readonly.html.includes('id="assign-form"'));
ok('viewer no create card', !readonly.html.includes('id="experiment-form"'));
ok('viewer still sees report', readonly.html.includes('河湾老仓'));

sessionStorage.setItem('hemu-session', JSON.stringify({role: 'manager', token: 't'}));
const mgrView = await experiments(7);
ok('manager sees end form', mgrView.html.includes('id="end-form"'));

globalThis.__mock.emptyList = true;
const emptyView = await experiments(null);
ok('empty state message', emptyView.html.includes('先在右侧新建推荐实验'));

console.log('\nFAILURES:', fail.length ? fail : 'none');
process.exit(fail.length ? 1 : 0);
