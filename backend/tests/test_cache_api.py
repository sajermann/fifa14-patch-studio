"""The cache folder of the settings screen: its size, and clearing only what the app makes again."""
import os

from f14api import settings


def _write(*parts, size):
    path = os.path.join(settings.CACHE_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'x' * size)
    return path


def test_size_and_clearing_leave_the_originals_and_imports(client):
    before = client.get('/api/cache').json()
    built = [_write('build', 'ab', 'entry1.zip', size=1000), _write('build', 'cd', 'entry2.zip', size=500),
             _write('images', 'token', 'team_1_0.png', size=200)]
    kept = [_write('originals', 'extra_test.sqlite', size=300), _write('share', 'staging', 'p.zip', size=50)]
    info = client.get('/api/cache').json()
    assert info['folder'] == settings.CACHE_DIR
    assert info['bytes'] == before['bytes'] + 2050 and info['files'] == before['files'] + 5
    assert info['clearable_bytes'] == before['clearable_bytes'] + 1700
    assert info['clearable_files'] == before['clearable_files'] + 3

    r = client.post('/api/cache/clear')
    assert r.status_code == 200, r.text
    assert r.json() == {'files': info['clearable_files'], 'bytes': info['clearable_bytes'], 'failed': 0}
    assert not any(os.path.exists(p) for p in built) and all(os.path.exists(p) for p in kept)
    assert not os.path.exists(os.path.join(settings.CACHE_DIR, 'build'))
    after = client.get('/api/cache').json()
    assert after['clearable_bytes'] == 0 and after['clearable_files'] == 0
    prog = client.get('/api/cache/progress').json()
    assert prog['running'] is False and prog['done'] == prog['total'] == info['clearable_files']
    assert prog['bytes_done'] == prog['bytes_total'] == info['clearable_bytes'] and 'elapsed' in prog
    for p in kept:
        os.remove(p)
    assert client.get('/api/status').json()['game']['state'] == 'ready'  # the game still works from its originals


def test_not_while_a_build_runs(client, monkeypatch):
    from f14api import main
    monkeypatch.setattr(main.jobs, 'view', lambda: {'state': 'running', 'kind': 'build'})
    r = client.post('/api/cache/clear')
    assert r.status_code == 409 and r.json()['detail']['code'] == 'busy'
