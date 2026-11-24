"""A/B 实验：组合推荐（combo）与单课推荐（single）的家庭随机分组与联报对账。

口径要点
--------
1. 家庭先随机领组再选课；同一家庭跨馆使用同一组，全局只保留一条分组记录。
2. 分组在「首次进组的场馆」维度保持两组尽量均衡：新家庭进入其登记场馆时，
   选择该馆当前人数较少的一组，计数持平则由加密哈希决定，避免请求到达顺序带来的偏好。
3. 并发登记以唯一约束兜底：IntegrityError 后回滚并回读最早登记成功的分组，
   重试不会产生第二条分组记录。
4. 到期对账以分组记录为分母，没有有效报名或报名已取消的家庭仍留在分母中。
5. 一份有效（confirmed）报名同时勾选两门目标课程即记该家庭联报。
6. 按首次进组场馆比较两组联报率；任一馆缺任一组即标记「样本不足」，不计算差值。
"""
import hashlib
import secrets
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.constants.enums import Group, TestState
from src.models.entities import Assignment, Course, Enrollment, Experiment
from src.services.business import audit

GROUP_LABELS = {Group.COMBO: '组合推荐', Group.SINGLE: '单课推荐'}

_SALT = secrets.token_hex(16)


def _tie_break(family_key: str) -> Group:
    """计数持平时的确定性随机：哈希决定，并混入进程级随机盐避免可预测。"""
    digest = hashlib.sha256((_SALT + family_key).encode()).hexdigest()
    return Group.COMBO if int(digest, 16) % 2 == 0 else Group.SINGLE


def _choose_group(db, experiment_id: int, venue: str, family_key: str) -> Group:
    """按首次进组场馆的两组人数选较少者，持平则随机。"""
    rows = db.execute(
        select(Assignment.group, func.count())
        .where(Assignment.experiment_id == experiment_id, Assignment.first_venue == venue)
        .group_by(Assignment.group)
    ).all()
    counts = {Group.COMBO: 0, Group.SINGLE: 0}
    for name, count in rows:
        counts[Group(name)] = count
    if counts[Group.COMBO] < counts[Group.SINGLE]:
        return Group.COMBO
    if counts[Group.SINGLE] < counts[Group.COMBO]:
        return Group.SINGLE
    return _tie_break(family_key)


def create_experiment(db, data, user):
    codes = {data.course_a, data.course_b}
    if set(db.scalars(select(Course.code).where(Course.code.in_(codes)))) != codes:
        raise HTTPException(422, '请选择课程目录中的两门课程')
    item = Experiment(title=data.title, course_a=data.course_a, course_b=data.course_b,
                      state=TestState.RUNNING, author_id=user.id)
    db.add(item)
    db.flush()
    audit(db, user, 'experiment_create', item.id)
    db.commit()
    return _experiment_record(item)


def assign_family(db, experiment_id: int, data, user):
    """登记家庭分组。幂等：已登记家庭（含跨馆）直接返回原分组。"""
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, '找不到实验')
    existing = db.scalar(select(Assignment).where(
        Assignment.experiment_id == experiment_id, Assignment.family_key == data.family_key))
    if existing:
        # 并发或重试：沿用最早登记成功的分组，不新增记录，first_venue 也不改变。
        return _assignment_record(existing, reused=True)
    if experiment.state != TestState.RUNNING:
        raise HTTPException(409, '实验已到期，分组登记已冻结')

    group = _choose_group(db, experiment_id, data.venue, data.family_key)
    item = Assignment(experiment_id=experiment_id, family_key=data.family_key,
                      group=group, first_venue=data.venue)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        # 并发下另一请求已抢先登记：回滚后回读，沿用最早成功的分组。
        db.rollback()
        winner = db.scalar(select(Assignment).where(
            Assignment.experiment_id == experiment_id, Assignment.family_key == data.family_key))
        if winner:
            return _assignment_record(winner, reused=True)
        raise HTTPException(409, '分组登记冲突，请重试')
    audit(db, user, 'assignment_create', f'{experiment_id}:{data.family_key}')
    db.commit()
    return _assignment_record(item, reused=False)


def end_experiment(db, experiment_id: int, note: str, user):
    experiment = db.scalar(select(Experiment).where(Experiment.id == experiment_id).with_for_update())
    if not experiment:
        raise HTTPException(404, '找不到实验')
    if experiment.state == TestState.ENDED:
        raise HTTPException(409, '实验已到期')
    experiment.state = TestState.ENDED
    experiment.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if note:
        experiment.note = note
    # 到期即冻结对账结果，之后报名台账的增改不再影响已签发的报告。
    snapshot = _compute_report(db, experiment)
    experiment.result = {'metrics': snapshot['metrics'], 'rows': snapshot['rows'], 'notes': snapshot['notes']}
    audit(db, user, 'experiment_end', experiment_id)
    db.commit()
    return _experiment_record(experiment)


def _family_enrollments(db):
    """聚合每个家庭在两门目标课上的有效勾选。

    取该家庭所有 confirmed 报名的并集；cancelled 报名不计入有效勾选。
    返回 family_key -> set(课程编号)。
    """
    rows = db.scalars(select(Enrollment).where(Enrollment.family_key != '')).all()
    picked = defaultdict(set)
    for row in rows:
        if row.state != 'confirmed':
            continue
        picked[row.family_key].update(row.codes)
    return picked


def reconcile(db, experiment_id: int):
    """联报对账报告。实验进行中返回实时预览；到期后返回到期时冻结的快照。"""
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, '找不到实验')
    if experiment.state == TestState.ENDED and experiment.result:
        return {
            'experiment': _experiment_record(experiment),
            'metrics': experiment.result['metrics'],
            'rows': experiment.result['rows'],
            'notes': experiment.result['notes'],
            'frozen': True,
        }
    report = _compute_report(db, experiment)
    report['frozen'] = False
    return report


def _compute_report(db, experiment):
    """按首次进组馆比较两组联报率（实时口径）。"""
    target = {experiment.course_a, experiment.course_b}
    picked = _family_enrollments(db)

    assignments = db.scalars(select(Assignment).where(
        Assignment.experiment_id == experiment.id).order_by(Assignment.id)).all()

    # 场馆 -> 分组 -> 统计桶 {分母, 联报数, 无有效报名数, 取消家庭数}
    venues = defaultdict(lambda: {
        Group.COMBO: {'n': 0, 'co': 0, 'no_enrollment': 0, 'cancelled': 0},
        Group.SINGLE: {'n': 0, 'co': 0, 'no_enrollment': 0, 'cancelled': 0},
    })
    cancelled_families = _cancelled_family_set(db)

    for item in assignments:
        group = Group(item.group)
        bucket = venues[item.first_venue][group]
        bucket['n'] += 1
        selection = picked.get(item.family_key, set())
        if not selection:
            if item.family_key in cancelled_families:
                bucket['cancelled'] += 1
            else:
                bucket['no_enrollment'] += 1
        if target.issubset(selection):
            bucket['co'] += 1

    rows = []
    for venue in sorted(venues):
        per_group = venues[venue]
        missing = [GROUP_LABELS[g] for g in (Group.COMBO, Group.SINGLE) if per_group[g]['n'] == 0]
        sufficient = not missing
        row = {'首次进组场馆': venue, '样本是否充足': '充足' if sufficient else '样本不足（缺%s）' % '、'.join(missing)}
        for group in (Group.COMBO, Group.SINGLE):
            stat = per_group[group]
            rate = round(stat['co'] / stat['n'], 4) if stat['n'] else None
            row[f'{GROUP_LABELS[group]}家庭数'] = stat['n']
            row[f'{GROUP_LABELS[group]}联报数'] = stat['co']
            row[f'{GROUP_LABELS[group]}联报率'] = rate
        if sufficient:
            combo_rate = per_group[Group.COMBO]['co'] / per_group[Group.COMBO]['n']
            single_rate = per_group[Group.SINGLE]['co'] / per_group[Group.SINGLE]['n']
            row['联报率提升（百分点）'] = round((combo_rate - single_rate) * 100, 2)
            row['相对提升'] = round((combo_rate - single_rate) / single_rate, 4) if single_rate else None
        else:
            row['联报率提升（百分点）'] = None
            row['相对提升'] = None
        # 诊断列：分母里未转化的家庭仍保留可追溯。
        row['未报名家庭（组合/单课）'] = f"{per_group[Group.COMBO]['no_enrollment']}/{per_group[Group.SINGLE]['no_enrollment']}"
        row['取消家庭（组合/单课）'] = f"{per_group[Group.COMBO]['cancelled']}/{per_group[Group.SINGLE]['cancelled']}"
        rows.append(row)

    overall = _overall(venues)
    return {
        'experiment': _experiment_record(experiment),
        'metrics': overall,
        'rows': rows,
        'notes': [
            '分母为全部已登记分组的家庭；没有有效报名或仅取消报名的家庭仍计入分母。',
            '一份 confirmed 报名同时勾选两门目标课程即记为联报；多份报名取课程并集。',
            '按家庭首次进组的场馆分层；任一馆缺少任一组时标记样本不足，不计算该馆提升。',
        ],
    }


def _cancelled_family_set(db):
    rows = db.scalars(select(Enrollment.family_key).where(
        Enrollment.state == 'cancelled', Enrollment.family_key != '')).all()
    return set(rows)


def _overall(venues):
    totals = {Group.COMBO: {'n': 0, 'co': 0}, Group.SINGLE: {'n': 0, 'co': 0}}
    enough_venues = 0
    for per_group in venues.values():
        sufficient = all(per_group[g]['n'] > 0 for g in (Group.COMBO, Group.SINGLE))
        if sufficient:
            enough_venues += 1
        for group in (Group.COMBO, Group.SINGLE):
            totals[group]['n'] += per_group[group]['n']
            totals[group]['co'] += per_group[group]['co']

    def rate(group):
        return round(totals[group]['co'] / totals[group]['n'], 4) if totals[group]['n'] else None

    combo_rate = rate(Group.COMBO)
    single_rate = rate(Group.SINGLE)
    lift_pp = round((combo_rate - single_rate) * 100, 2) if combo_rate is not None and single_rate is not None else None
    return {
        '参与家庭总数': totals[Group.COMBO]['n'] + totals[Group.SINGLE]['n'],
        '组合推荐联报率': combo_rate,
        '单课推荐联报率': single_rate,
        '联报率提升（百分点）': lift_pp,
        '样本充足场馆数': enough_venues,
        '场馆总数': len(venues),
    }


def list_experiments(db):
    items = db.scalars(select(Experiment).order_by(Experiment.id.desc())).all()
    return [_experiment_record(item) for item in items]


def list_assignments(db, experiment_id: int):
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(404, '找不到实验')
    items = db.scalars(select(Assignment).where(
        Assignment.experiment_id == experiment_id).order_by(Assignment.id)).all()
    return [_assignment_record(item, reused=False) for item in items]


def _experiment_record(item):
    return {
        'id': item.id, 'title': item.title, 'course_a': item.course_a, 'course_b': item.course_b,
        'state': item.state, 'note': item.note,
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'ended_at': item.ended_at.isoformat() if item.ended_at else None,
    }


def _assignment_record(item, reused):
    return {
        'id': item.id, 'experiment_id': item.experiment_id, 'family_key': item.family_key,
        'group': item.group, 'group_label': GROUP_LABELS[Group(item.group)],
        'first_venue': item.first_venue, 'reused': reused,
        'created_at': item.created_at.isoformat() if item.created_at else None,
    }
