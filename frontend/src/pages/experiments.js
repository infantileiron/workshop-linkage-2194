import {api} from '../api/workshop.js';
import {heading} from '../components/common/layout.js';
import {metrics} from '../components/common/metrics.js';
import {table} from '../components/common/table.js';
import {testStates} from '../constants/enums.js';
import {onForm} from '../hooks/forms.js';
import {canWrite, session} from '../stores/session.js';
import {h} from '../utils/html.js';

function pct(value) {
  if (value === null || value === undefined) return '未定义';
  return `${(value * 100).toFixed(2)}%`;
}

function liftText(value) {
  if (value === null || value === undefined) return '样本不足';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value} 个百分点`;
}

// 跨整页 refresh 保留一次的操作反馈（重渲染后读取并清除）。
let flashMessage = '';

export async function experiments(id) {
  const [list, courseList] = await Promise.all([api.experimentList(), api.courses()]);
  const currentId = id || list[0]?.id || null;
  const detail = currentId ? await api.experiment(currentId) : null;
  const assignmentRows = currentId ? await api.assignments(currentId) : [];
  const isManager = session()?.role === 'manager';

  const sidebar = `<aside class="sheet"><h2>推荐实验</h2><ul class="runs">${
    list.map(x => `<li><a href="#experiments/${x.id}">${h(x.title)}</a><span>${h(testStates[x.state])}</span></li>`).join('')
    || '<li>暂无实验，先新建一组。</li>'}</ul></aside>`;

  const courseOptions = selected => courseList
    .map(x => `<option value="${h(x.code)}" ${x.code === selected ? 'selected' : ''}>${h(x.title)} · ${h(x.code)}</option>`).join('');

  const createCard = canWrite() ? `
    <section class="sheet tools"><h2>新建推荐实验</h2><form id="experiment-form">
      <label>实验名称<input name="title" required value="周末组合推荐联报实验"></label>
      <label>首门课<select name="course_a">${courseOptions('WOOD-11')}</select></label>
      <label>次门课<select name="course_b">${courseOptions('LACQ-24')}</select></label>
      <button type="submit">创建实验并开放领组</button><p role="alert"></p></form></section>` : '';

  let main = '<div class="empty">先在右侧新建推荐实验，家庭即可随机领取组合或单课推荐。</div>';

  if (detail) {
    const exp = detail.experiment;
    const ended = exp.state === 'ended';
    const report = detail;
    const rows = report.rows;
    const reportColumns = rows[0] ? Object.keys(rows[0]) : [];
    const reportTable = rows.length ? table(
      reportColumns,
      rows.map(row => reportColumns.map(key => {
        if (key.includes('联报率')) return pct(row[key]);
        if (key.includes('提升')) return liftText(row[key]);
        return row[key];
      }))
    ) : '<p class="empty">还没有家庭领组，暂无分层数据。</p>';

    const assignCard = canWrite() ? `
      <section class="sheet ${ended ? 'locked' : 'tools'}"><h2>家庭分组登记</h2>
      ${ended ? '<p class="state">实验已到期，分组冻结；已登记家庭的重复请求仍按原分组返回。</p>' : `
      <form id="assign-form">
        <label>家庭标识<input name="family_key" required pattern="[A-Za-z0-9_-]{2,64}" placeholder="FAM-01-007"></label>
        <label>进组场馆<input name="venue" required placeholder="河湾老仓"></label>
        <button type="submit">随机领组</button><p role="alert"></p>
        <p id="assign-result" class="assign-result" aria-live="polite">${h(flashMessage)}</p>
      </form>`}</section>` : '';

    main = `
      <h2>${h(exp.title)}</h2>
      <p class="state">${h(testStates[exp.state])} · ${h(exp.course_a)} × ${h(exp.course_b)}
        · ${report.frozen ? '对账快照已冻结' : '实时预览（到期后冻结）'}</p>
      ${metrics(report.metrics)}
      <p class="decision">组合推荐联报率 ${pct(report.metrics['组合推荐联报率'])}，单课推荐联报率 ${pct(report.metrics['单课推荐联报率'])}；
        多带来的联报率为 ${liftText(report.metrics['联报率提升（百分点）'])}。</p>
      <h3>按首次进组场馆的两组联报率</h3>${reportTable}
      <ul class="notes">${report.notes.map(note => `<li>${h(note)}</li>`).join('')}</ul>
      <button class="secondary" id="experiment-export">下载实验对账 CSV</button><p id="export-error" role="alert"></p>
      <h3>分组登记记录（${assignmentRows.length} 个家庭）</h3>
      ${table(['家庭标识', '分组', '首次进组场馆', '登记时间'],
        assignmentRows.map(x => [x.family_key, x.group_label, x.first_venue, (x.created_at || '').replace('T', ' ').slice(0, 19)]))}
      ${assignCard}
      ${isManager && !ended ? `
      <form id="end-form" class="end-form"><label>到期说明<input name="note" required minlength="3" placeholder="按计划到期，进入对账口径"></label>
        <button type="submit">到期并冻结分组</button><p role="alert"></p></form>` : ''}
      ${exp.note ? `<p class="signed">到期说明 · ${h(exp.note)}</p>` : ''}`;
  }

  return {
    html: heading('推荐实验核查', '家庭先随机领组再选课；同家庭跨馆同组，按首次进组馆保持两组均衡，到期后对账联报率。')
      + `<div class="workarea"><section class="sheet" id="experiment-view">${main}</section>
         <div class="side-stack">${sidebar}${createCard}</div></div>`,
    bind(root, refresh) {
      flashMessage = '';
      onForm(root.querySelector('#experiment-form'), async data => {
        const created = await api.createExperiment(data);
        location.hash = `#experiments/${created.id}`;
      });
      onForm(root.querySelector('#assign-form'), async data => {
        const result = await api.assign(currentId, data);
        flashMessage = `${result.family_key} → ${result.group_label}（首次进组：${result.first_venue}）${result.reused ? '，沿用已有分组' : ''}`;
        refresh();
      });
      onForm(root.querySelector('#end-form'), async data => {
        await api.endExperiment(currentId, data.note);
        refresh();
      });
      root.querySelector('#experiment-export')?.addEventListener('click', async () => {
        try {
          const url = URL.createObjectURL(await api.experimentExport(currentId));
          const link = document.createElement('a');
          link.href = url;
          link.download = `experiment-${currentId}.csv`;
          link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) { root.querySelector('#export-error').textContent = error.message; }
      });
    }
  };
}
