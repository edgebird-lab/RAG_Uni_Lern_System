#!/usr/bin/env python3
"""Referenzdaten fuer den FSRS-Paritaetstest: zufaellige Bewertungsfolgen mit py-fsrs (wie die PC-App konfiguriert).
Aufruf (Repo-Root, mit .venv): .venv/bin/python android/eval/tools/make_fsrs_fixture.py"""
import json
import random
from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler, State

random.seed(11)
sch = Scheduler(desired_retention=0.9, maximum_interval=365, enable_fuzzing=False)


def ms(dt):
    return int(round(dt.timestamp() * 1000))


cases = []
for i in range(300):
    now = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=random.randint(0, 2000))
    card = Card(card_id=i, state=State.Learning, due=now)
    seq = []
    for _ in range(random.randint(3, 14)):
        r = random.choices([Rating.Again, Rating.Hard, Rating.Good, Rating.Easy], weights=[2, 2, 5, 1])[0]
        gap = random.choice([timedelta(seconds=random.randint(10, 600)), timedelta(minutes=random.randint(5, 90)),
                             timedelta(hours=random.randint(3, 30)), timedelta(days=random.randint(1, 60))])
        if random.random() < 0.5:
            now = max(now + gap, now + timedelta(seconds=1))
        else:
            now = max(card.due, now) + timedelta(seconds=random.randint(0, 3 * 86400))
        card, _ = sch.review_card(card, r, review_datetime=now)
        seq.append({"rating": int(r), "now": ms(now), "state": int(card.state), "step": card.step,
                    "stability": card.stability, "difficulty": card.difficulty, "due": ms(card.due)})
    cases.append(seq)
open("android/core/src/test/resources/srs/fsrs_fixture.json", "w").write(json.dumps(cases))
print(len(cases), "Folgen,", sum(len(c) for c in cases), "Bewertungen")

# Kopie fuer die Geraetetests (data/src/androidTest/assets/parity)
import shutil as _sh
_sh.copy('android/core/src/test/resources/srs/fsrs_fixture.json' if __import__('os').path.exists('android/core/src/test/resources/srs/fsrs_fixture.json') else str(ROOT / 'core/src/test/resources/srs/fsrs_fixture.json'), 'android/data/src/androidTest/assets/parity/' + 'fsrs_fixture.json')
