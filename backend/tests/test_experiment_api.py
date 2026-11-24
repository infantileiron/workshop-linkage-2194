"""推荐实验 HTTP 端到端测试（FastAPI TestClient + 内存外 SQLite）。

依赖 httpx（FastAPI TestClient）。本地或容器内安装测试依赖后运行：
    pip install httpx
    docker compose exec -T backend python tests/test_experiment_api.py
缺少 httpx 时本脚本以「跳过」结束，不影响其它测试。
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_FD, _DB_PATH = tempfile.mkstemp(suffix='.db')
os.environ['DATABASE_URL'] = f'sqlite+pysqlite:///{_DB_PATH}'
os.environ['REDIS_URL'] = 'redis://localhost:6399/0'
os.environ['JWT_SECRET'] = 'test-secret-test-secret-test-secret-0002'
os.environ['SEED_DEMO'] = 'false'

try:
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
except ImportError:
    print('SKIP: 需要 httpx 才能运行 HTTP 端到端测试（pip install httpx）')
    sys.exit(0)

from sqlalchemy import event, func, select  # noqa: E402

from src.config.database import Base, Session, engine  # noqa: E402
from src.main import app  # noqa: E402
from src.models.entities import Assignment, Course, User  # noqa: E402
from src.utils.security import password_hash  # noqa: E402


@event.listens_for(engine, 'connect')
def _pragma(conn, _):
    cur = conn.cursor()
    cur.execute('PRAGMA journal_mode=WAL')
    cur.execute('PRAGMA busy_timeout=30000')
    cur.close()


Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

with Session() as db:
    db.add_all([
        User(email='analyst@hemu.demo', role='analyst', password_hash=password_hash('pw')),
        User(email='manager@hemu.demo', role='manager', password_hash=password_hash('pw')),
        User(email='viewer@hemu.demo', role='viewer', password_hash=password_hash('pw')),
        Course(code='WOOD-11', title='木雕浅刻', seats=22, category='雕刻'),
        Course(code='LACQ-24', title='木片彩漆', seats=20, category='上漆'),
    ])
    db.commit()

client = TestClient(app)
failures = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        failures.append(name)


def login(email):
    r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
    assert r.status_code == 200, r.text
    return {'Authorization': f"Bearer {r.json()['token']}"}


auth = login('analyst@hemu.demo')
mgr = login('manager@hemu.demo')
viewer = login('viewer@hemu.demo')

check('unauthenticated rejected', client.get('/api/experiments').status_code == 401)
check('viewer cannot create experiment',
      client.post('/api/experiments', headers=viewer,
                  json={'title': 'x实验', 'course_a': 'WOOD-11', 'course_b': 'LACQ-24'}).status_code == 403)

r = client.post('/api/experiments', headers=auth,
                json={'title': 'x', 'course_a': 'WOOD-11', 'course_b': 'WOOD-11'})
check('same course rejected 422', r.status_code == 422)
r = client.post('/api/experiments', headers=auth,
                json={'title': '11月推荐实验', 'course_a': 'WOOD-11', 'course_b': 'LACQ-24'})
check('create experiment 201', r.status_code == 201, r.text)
exp_id = r.json()['id']
check('new experiment running', r.json()['state'] == 'running')

r = client.post('/api/experiments', headers=auth,
                json={'title': '坏实验', 'course_a': 'WOOD-11', 'course_b': 'NOPE-9'})
check('unknown course rejected 422', r.status_code == 422)

r = client.post(f'/api/experiments/{exp_id}/assignments', headers=auth,
                json={'family_key': 'FAM-01', 'venue': '河湾老仓'})
check('assign 201', r.status_code == 201, r.text)
first_group = r.json()['group']
check('assign not reused first time', r.json()['reused'] is False)
r2 = client.post(f'/api/experiments/{exp_id}/assignments', headers=auth,
                 json={'family_key': 'FAM-01', 'venue': '望桥木校'})
check('repeat assign idempotent', r2.status_code == 201 and r2.json()['group'] == first_group
      and r2.json()['reused'] is True and r2.json()['first_venue'] == '河湾老仓')

r = client.post(f'/api/experiments/{exp_id}/assignments', headers=auth,
                json={'family_key': '坏家庭!', 'venue': '河湾老仓'})
check('bad family key 422', r.status_code == 422)
r = client.post(f'/api/experiments/{exp_id}/assignments', headers=viewer,
                json={'family_key': 'FAM-02', 'venue': '河湾老仓'})
check('viewer cannot assign 403', r.status_code == 403)

# 并发 HTTP：同家庭两个请求同时到达
barrier = threading.Barrier(2)
outcome = []


def concurrent_assign():
    barrier.wait()
    outcome.append(client.post(f'/api/experiments/{exp_id}/assignments', headers=auth,
                               json={'family_key': 'FAM-RACE', 'venue': '河湾老仓'}))


threads = [threading.Thread(target=concurrent_assign) for _ in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check('concurrent both 201', all(o.status_code == 201 for o in outcome), [o.status_code for o in outcome])
check('concurrent same group', outcome[0].json()['group'] == outcome[1].json()['group'])
with Session() as db:
    n = db.scalar(select(func.count()).select_from(Assignment).where(Assignment.family_key == 'FAM-RACE'))
check('concurrent single DB row', n == 1, f'rows={n}')

r = client.post('/api/enrollments', headers=auth,
                json={'code': 'NOV-99-001', 'venue': '河湾老仓', 'state': 'confirmed', 'codes': ['WOOD-11']})
check('enrollment without family 422', r.status_code == 422, r.text)
r = client.post('/api/enrollments', headers=auth,
                json={'code': 'NOV-99-001', 'venue': '河湾老仓', 'state': 'confirmed',
                      'codes': ['WOOD-11', 'LACQ-24'], 'family_key': 'FAM-01'})
check('enrollment with family 201', r.status_code == 201, r.text)

r = client.post(f'/api/experiments/{exp_id}/end', headers=auth, json={'note': '到期对账封账'})
check('analyst cannot end 403', r.status_code == 403)
r = client.post(f'/api/experiments/{exp_id}/end', headers=mgr, json={'note': '到期对账封账'})
check('manager ends 200', r.status_code == 200 and r.json()['state'] == 'ended', r.text)
r = client.post(f'/api/experiments/{exp_id}/assignments', headers=auth,
                json={'family_key': 'FAM-LATE', 'venue': '河湾老仓'})
check('frozen new assignment 409', r.status_code == 409, r.text)
r = client.post(f'/api/experiments/{exp_id}/assignments', headers=auth,
                json={'family_key': 'FAM-01', 'venue': '河湾老仓'})
check('frozen repeat still idempotent', r.status_code == 201 and r.json()['reused'] is True)
r = client.post(f'/api/experiments/{exp_id}/end', headers=mgr, json={'note': '再来一次'})
check('double end 409', r.status_code == 409)

r = client.get(f'/api/experiments/{exp_id}', headers=viewer)
check('reconcile 200', r.status_code == 200, r.text)
body = r.json()
check('reconcile has rows and metrics', 'rows' in body and 'metrics' in body and body['rows'])
check('metrics include lift', '联报率提升（百分点）' in body['metrics'])

r = client.get(f'/api/experiments/{exp_id}/assignments', headers=auth)
check('list assignments 200', r.status_code == 200 and len(r.json()) == 2, str(len(r.json())))
r = client.get('/api/experiments', headers=auth)
check('list experiments', r.status_code == 200 and any(x['id'] == exp_id for x in r.json()))

r = client.get(f'/api/experiments/{exp_id}/export', headers=viewer)
check('experiment csv 200', r.status_code == 200 and r.headers['content-type'].startswith('text/csv'), r.text[:80])
check('csv has utf8 bom and venue', r.content.startswith(b'\xef\xbb\xbf') and '河湾老仓'.encode() in r.content)
check('csv filename header', f'experiment-{exp_id}.csv' in r.headers.get('content-disposition', ''))
check('missing experiment 404', client.get('/api/experiments/9999', headers=auth).status_code == 404)

print()
print('FAILURES:', failures if failures else 'none')
sys.exit(1 if failures else 0)
