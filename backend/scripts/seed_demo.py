import json
from sqlalchemy import func, select

from src.config.database import Base, Session, engine
from src.constants.enums import Group, Role, Status, TestState
from src.models.entities import Analysis, Assignment, Course, Enrollment, Experiment, User
from src.services.business import record
from src.utils.security import password_hash

COURSES = [('WOOD-11','木雕浅刻',22,'雕刻'), ('LACQ-24','木片彩漆',20,'上漆'),
           ('JOIN-06','榫卯入门',18,'木构'), ('SAND-18','研磨封蜡',16,'饰面')]
VENUES = [('河湾老仓', (30,30,30,10)), ('望桥木校', (3,17,17,63)), ('槐里快闪', (1,1,0,2))]


def _family_code(venue_idx, number):
    return f'FAM-{venue_idx:02d}-{number:03d}'


def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in Role:
            email = f'{role}@hemu.demo'
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, role=role, password_hash=password_hash('Woodwork2026!')))
        known = set(db.scalars(select(Course.code)))
        db.add_all(Course(code=code, title=title, seats=seats, category=category)
                   for code, title, seats, category in COURSES if code not in known)
        registered = set(db.scalars(select(Enrollment.code)))
        family_counter = {}
        for idx, (venue, counts) in enumerate(VENUES, 1):
            number = 0
            for selection, count in zip((['WOOD-11','LACQ-24'], ['WOOD-11'], ['LACQ-24'], []), counts):
                for _ in range(count):
                    number += 1
                    family_counter[idx] = family_counter.get(idx, 0) + 1
                    family = _family_code(idx, family_counter[idx])
                    code = f'NOV-{idx:02d}-{number:03d}'
                    if code not in registered:
                        courses = selection + (['JOIN-06'] if number % 5 == 0 else [])
                        db.add(Enrollment(code=code, venue=venue, state='confirmed',
                                          codes=courses, family_key=family))
            code = f'NOV-{idx:02d}-X01'
            if code not in registered:
                family_counter[idx] = family_counter.get(idx, 0) + 1
                db.add(Enrollment(code=code, venue=venue, state='cancelled',
                                  codes=['WOOD-11','LACQ-24'],
                                  family_key=_family_code(idx, family_counter[idx])))
        db.flush()
        title = '11 月周末 · 木雕与上漆联报复核'
        if not db.scalar(select(Analysis).where(Analysis.title == title)):
            owner = db.scalar(select(User).where(User.role == Role.ANALYST))
            db.add(Analysis(title=title, status=Status.QUEUED, author_id=owner.id,
                            parameters={'course_a':'WOOD-11','course_b':'LACQ-24','min_venue_n':12},
                            snapshot=[record(row) for row in db.scalars(select(Enrollment).order_by(Enrollment.id))],
                            result=None))

        # 预置一个进行中的推荐实验，并让台账家庭按馆内均衡领组（确定性演示数据）。
        exp_title = '11 月周末 · 组合推荐联报实验'
        experiment = db.scalar(select(Experiment).where(Experiment.title == exp_title))
        if not experiment:
            owner = db.scalar(select(User).where(User.role == Role.ANALYST))
            experiment = Experiment(title=exp_title, course_a='WOOD-11', course_b='LACQ-24',
                                    state=TestState.RUNNING, author_id=owner.id)
            db.add(experiment)
            db.flush()
            venue_balance = {}
            for row in db.scalars(select(Enrollment).where(Enrollment.family_key != '').order_by(Enrollment.id)):
                exists = db.scalar(select(Assignment).where(
                    Assignment.experiment_id == experiment.id,
                    Assignment.family_key == row.family_key))
                if exists:
                    continue
                combo_n, single_n = venue_balance.get(row.venue, (0, 0))
                group = Group.COMBO if combo_n <= single_n else Group.SINGLE
                venue_balance[row.venue] = (combo_n + (group == Group.COMBO),
                                            single_n + (group == Group.SINGLE))
                db.add(Assignment(experiment_id=experiment.id, family_key=row.family_key,
                                  group=group, first_venue=row.venue))
        db.commit()
        return {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                for model in (User, Course, Enrollment, Analysis, Experiment, Assignment)}


if __name__ == '__main__':
    print(json.dumps(seed(), sort_keys=True))
