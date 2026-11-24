"""推荐实验服务层测试（SQLite，仅依赖 SQLAlchemy 与标准库，可在容器内直接运行）。

运行：docker compose exec -T backend python tests/test_experiment_service.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix='.db')
os.environ.setdefault('DATABASE_URL', f'sqlite+pysqlite:///{_DB_PATH}')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6399/0')
os.environ.setdefault('JWT_SECRET', 'test-secret-test-secret-test-secret-0001')

from sqlalchemy import create_engine, event, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.config.database import Base  # noqa: E402
import src.config.database as dbcfg  # noqa: E402
from src.constants.enums import Group, TestState  # noqa: E402
from src.models.entities import Assignment, Course, Enrollment, User  # noqa: E402
from src.schemas.business import AssignmentInput, ExperimentInput  # noqa: E402
from src.services import experiment as ab  # noqa: E402

engine = create_engine(os.environ['DATABASE_URL'],
                       connect_args={'check_same_thread': False, 'timeout': 30})


@event.listens_for(engine, 'connect')
def _wal(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute('PRAGMA journal_mode=WAL')
    cur.execute('PRAGMA busy_timeout=30000')
    cur.close()


dbcfg.engine = engine
Session = dbcfg.Session = sessionmaker(engine, expire_on_commit=False)
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

failures = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        failures.append(name)


with Session() as db:
    user = User(email='analyst@hemu.demo', password_hash='x', role='analyst')
    db.add_all([Course(code='WOOD-11', title='木雕', seats=10, category='雕刻'),
                Course(code='LACQ-24', title='彩漆', seats=10, category='上漆')])
    db.add(user)
    db.commit()
    uid = user.id

# 1. 馆内均衡：20 个家庭进 A 馆，应 10/10
with Session() as db:
    user = db.get(User, uid)
    exp = ab.create_experiment(db, ExperimentInput(title='11月推荐实验',
                                                   course_a='WOOD-11', course_b='LACQ-24'), user)
    exp_id = exp['id']
    check('create experiment running', exp['state'] == TestState.RUNNING)
    for i in range(20):
        ab.assign_family(db, exp_id, AssignmentInput(family_key=f'A{i:02d}', venue='河湾老仓'), user)
    rows = db.execute(select(Assignment.group, func.count()).where(
        Assignment.experiment_id == exp_id, Assignment.first_venue == '河湾老仓'
    ).group_by(Assignment.group)).all()
    counts = dict(rows)
    check('venue A balanced 10/10', counts.get(Group.COMBO) == 10 and counts.get(Group.SINGLE) == 10, str(counts))

# 2. 跨馆同组 + first_venue 不变
with Session() as db:
    user = db.get(User, uid)
    first = ab.assign_family(db, exp_id, AssignmentInput(family_key='CROSS1', venue='望桥木校'), user)
    again = ab.assign_family(db, exp_id, AssignmentInput(family_key='CROSS1', venue='河湾老仓'), user)
    check('cross-venue same group', first['group'] == again['group'])
    check('cross-venue first_venue kept', again['first_venue'] == '望桥木校')
    check('reused flag on repeat', again['reused'] is True and first['reused'] is False)
    total = db.scalar(select(func.count()).select_from(Assignment).where(Assignment.family_key == 'CROSS1'))
    check('no duplicate assignment row', total == 1, f'rows={total}')

# B 馆独立均衡（含 CROSS1 共 11 个家庭，奇数样本差不超过 1）
with Session() as db:
    user = db.get(User, uid)
    for i in range(10):
        ab.assign_family(db, exp_id, AssignmentInput(family_key=f'B{i:02d}', venue='望桥木校'), user)
    rows = db.execute(select(Assignment.group, func.count()).where(
        Assignment.experiment_id == exp_id, Assignment.first_venue == '望桥木校'
    ).group_by(Assignment.group)).all()
    counts = dict(rows)
    check('venue B independent balance',
          abs(counts.get(Group.COMBO, 0) - counts.get(Group.SINGLE, 0)) <= 1, str(counts))

# 3. 并发：同家庭两线程同时登记，只能有一条记录且分组一致
race_errors = []


def race_register(family, venue, barrier, results, idx):
    try:
        with Session() as s:
            u = s.get(User, uid)
            barrier.wait()
            results[idx] = ab.assign_family(s, exp_id, AssignmentInput(family_key=family, venue=venue), u)
    except Exception as exc:  # noqa: BLE001
        race_errors.append(repr(exc))


for k in range(6):
    family = f'RACE{k}'
    barrier = threading.Barrier(2)
    results = [None, None]
    threads = [threading.Thread(target=race_register, args=(family, '河湾老仓', barrier, results, i)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with Session() as db:
        total = db.scalar(select(func.count()).select_from(Assignment).where(Assignment.family_key == family))
        same = results[0] and results[1] and results[0]['group'] == results[1]['group']
        check(f'race {family} single row', total == 1, f'rows={total} errors={race_errors}')
        check(f'race {family} same group returned', bool(same))
check('race no uncaught errors', not race_errors, str(race_errors))

# 4. 到期冻结
with Session() as db:
    user = db.get(User, uid)
    ended = ab.end_experiment(db, exp_id, '到期对账', user)
    check('experiment ended', ended['state'] == TestState.ENDED and ended['ended_at'])
    try:
        ab.assign_family(db, exp_id, AssignmentInput(family_key='LATE1', venue='河湾老仓'), user)
        check('frozen rejects new assignment', False)
    except Exception as exc:  # noqa: BLE001
        check('frozen rejects new assignment', getattr(exc, 'status_code', None) == 409)
    old = ab.assign_family(db, exp_id, AssignmentInput(family_key='A00', venue='河湾老仓'), user)
    check('repeat after end still idempotent', old['reused'] is True)
    try:
        ab.end_experiment(db, exp_id, '再次到期', user)
        check('double end rejected', False)
    except Exception as exc:  # noqa: BLE001
        check('double end rejected', getattr(exc, 'status_code', None) == 409)

# 5. 对账口径
with Session() as db:
    def enr(code, family, state, codes, venue='河湾老仓'):
        return Enrollment(code=code, venue=venue, state=state, codes=codes, family_key=family)

    db.add_all([
        enr('E-C1', 'C1', 'confirmed', ['WOOD-11', 'LACQ-24']),
        enr('E-C2', 'C2', 'confirmed', ['WOOD-11']),
        enr('E-C4', 'C4', 'cancelled', ['WOOD-11', 'LACQ-24']),
        enr('E-S1', 'S1', 'confirmed', ['WOOD-11', 'LACQ-24']),
        enr('E-M1A', 'M1', 'confirmed', ['WOOD-11']),
        enr('E-M1B', 'M1', 'confirmed', ['LACQ-24']),
    ])
    db.commit()

with Session() as db:
    user = db.get(User, uid)
    exp2 = ab.create_experiment(db, ExperimentInput(title='对账可控实验',
                                                    course_a='WOOD-11', course_b='LACQ-24'), user)
    e2 = exp2['id']
    plan = [
        ('C1', '河湾老仓', Group.COMBO), ('C2', '河湾老仓', Group.COMBO),
        ('C3', '河湾老仓', Group.COMBO), ('C4', '河湾老仓', Group.COMBO),
        ('S1', '河湾老仓', Group.SINGLE), ('M1', '河湾老仓', Group.SINGLE),
        ('S2', '河湾老仓', Group.SINGLE),
        ('X1', '望桥木校', Group.COMBO), ('X2', '望桥木校', Group.COMBO),  # 缺单课组
    ]
    for family, venue, group in plan:
        db.add(Assignment(experiment_id=e2, family_key=family, group=group, first_venue=venue))
    db.commit()
    report = ab.reconcile(db, e2)

v1 = next(r for r in report['rows'] if r['首次进组场馆'] == '河湾老仓')
v2 = next(r for r in report['rows'] if r['首次进组场馆'] == '望桥木校')
check('V1 combo denominator keeps all 4', v1['组合推荐家庭数'] == 4)
check('V1 combo co=1 (only C1)', v1['组合推荐联报数'] == 1 and v1['组合推荐联报率'] == 0.25)
check('V1 single co=2 (S1 + union M1)', v1['单课推荐联报数'] == 2)
check('V1 single rate 2/3', abs(v1['单课推荐联报率'] - 2 / 3) < 1e-4)
check('V1 no-enrollment families retained', v1['未报名家庭（组合/单课）'] == '1/1')
check('V1 cancelled family retained', v1['取消家庭（组合/单课）'] == '1/0')
check('V1 lift pp = -41.67', v1['联报率提升（百分点）'] == -41.67, str(v1))
check('V2 flagged insufficient', '样本不足' in v2['样本是否充足'] and v2['联报率提升（百分点）'] is None)
m = report['metrics']
check('overall totals 9 families', m['参与家庭总数'] == 9)
check('overall enough venues = 1/2', m['样本充足场馆数'] == 1 and m['场馆总数'] == 2)
check('overall combo rate 1/6', abs(m['组合推荐联报率'] - 1 / 6) < 1e-4)
check('overall single rate 2/3', abs(m['单课推荐联报率'] - 2 / 3) < 1e-4)

# 6. 唯一约束真实存在
with Session() as db:
    db.add(Assignment(experiment_id=e2, family_key='C1', group=Group.SINGLE, first_venue='x'))
    from sqlalchemy.exc import IntegrityError as IE
    try:
        db.flush()
        check('unique constraint enforced', False)
    except IE:
        db.rollback()
        check('unique constraint enforced', True)

# 7. 到期冻结：到期后再新增报名，对账报告不得变化
with Session() as db:
    user = db.get(User, uid)
    before = ab.reconcile(db, e2)
    check('running report not frozen', before['frozen'] is False)
    ab.end_experiment(db, e2, '到期封账', user)
    frozen_now = ab.reconcile(db, e2)
    check('ended report frozen flag', frozen_now['frozen'] is True)
    # 给一个原本未联报的组合组家庭补一份确认报名制造联报
    db.add(Enrollment(code='E-C3-LATE', venue='河湾老仓', state='confirmed',
                      codes=['WOOD-11', 'LACQ-24'], family_key='C3'))
    db.commit()
    after = ab.reconcile(db, e2)
    check('frozen metrics unchanged', after['metrics'] == frozen_now['metrics'])
    check('frozen rows unchanged', after['rows'] == frozen_now['rows'])

print()
print('FAILURES:', failures if failures else 'none')
sys.exit(1 if failures else 0)
