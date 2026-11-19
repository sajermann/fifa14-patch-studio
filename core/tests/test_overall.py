from f14mod.overall import compute_overall


def _row(position, value, **extra):
    cols = ('gkreflexes', 'gkhandling', 'gkdiving', 'gkpositioning', 'gkkicking', 'reactions', 'finishing', 'positioning',
            'headingaccuracy', 'shotpower', 'dribbling', 'ballcontrol', 'volleys', 'longshots', 'acceleration',
            'sprintspeed', 'strength', 'shortpassing', 'vision', 'longpassing', 'marking', 'standingtackle')
    return {'preferredposition1': position, 'internationalrep': 1, **{c: value for c in cols}, **extra}


def test_flat_attributes_give_that_overall():
    assert compute_overall(_row(25, 80)) == 80  # ST
    assert compute_overall(_row(0, 70)) == 70   # GK


def test_weights_follow_the_position():
    row = _row(25, 50, finishing=99)  # finishing weighs 20 for a striker, 0 for a goalkeeper
    assert compute_overall(row) == 60
    assert compute_overall({**row, 'preferredposition1': 0}) == 50


def test_reputation_bonus_and_cap():
    assert compute_overall(_row(25, 80, internationalrep=5)) == 83
    assert compute_overall(_row(25, 60, internationalrep=3)) == 61


def test_not_a_playing_position():
    assert compute_overall(_row(28, 80)) is None
