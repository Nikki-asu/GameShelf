import os
import uuid
from datetime import date
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

# Render sets DATABASE_URL for you if you add a Render Postgres instance,
# but here we're pointing it at Supabase instead — set DATABASE_URL in
# Render's Environment tab to your Supabase connection string.
DATABASE_URL = os.environ.get('DATABASE_URL')

_pool = SimpleConnectionPool(1, 5, DATABASE_URL, sslmode='require') if DATABASE_URL else None


@contextmanager
def _cursor():
    if _pool is None:
        raise RuntimeError('DATABASE_URL is not set — add it in Render > Environment.')
    conn = _pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def init_db():
    """Call once at startup — creates tables if they don't exist yet."""
    with _cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                joined   DATE DEFAULT CURRENT_DATE
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id             TEXT PRIMARY KEY,
                username       TEXT NOT NULL,
                game_id        TEXT NOT NULL,
                game_title     TEXT,
                cover_url      TEXT,
                shelf          TEXT,
                rating         TEXT,
                platform       TEXT,
                review         TEXT,
                private_notes  TEXT,
                added_date     DATE DEFAULT CURRENT_DATE
            );
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_entries_username ON entries (username);')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_entries_gameid ON entries (game_id);')


# ── USERS ─────────────────────────────────────────────────────────────────────

def find_user(username):
    with _cursor() as cur:
        cur.execute('SELECT username, password, joined FROM users WHERE lower(username) = lower(%s)', (username,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            'username': row['username'],
            'password': row['password'],
            'joined':   row['joined'].isoformat() if row['joined'] else '',
        }


def add_user(username, hashed_password):
    with _cursor() as cur:
        cur.execute(
            'INSERT INTO users (username, password, joined) VALUES (%s, %s, %s)',
            (username, hashed_password, date.today())
        )


def get_all_users():
    with _cursor() as cur:
        cur.execute('SELECT username FROM users')
        return [r['username'] for r in cur.fetchall()]


# ── SHELF ENTRIES ─────────────────────────────────────────────────────────────

def _row_to_entry(r):
    return {
        'id':            r['id'],
        'username':      r['username'],
        'game_id':       r['game_id'],
        'game_title':    r['game_title'] or '',
        'cover_url':     r['cover_url'] or '',
        'shelf':         r['shelf'] or '',
        'rating':        r['rating'] or '',
        'platform':      r['platform'] or '',
        'review':        r['review'] or '',
        'private_notes': r['private_notes'] or '',
        'added_date':    r['added_date'].isoformat() if r['added_date'] else '',
    }


def get_user_shelf(username, shelf=None):
    with _cursor() as cur:
        if shelf:
            cur.execute(
                'SELECT * FROM entries WHERE lower(username) = lower(%s) AND shelf = %s ORDER BY added_date DESC',
                (username, shelf)
            )
        else:
            cur.execute(
                'SELECT * FROM entries WHERE lower(username) = lower(%s) ORDER BY added_date DESC',
                (username,)
            )
        return [_row_to_entry(r) for r in cur.fetchall()]


def get_all_public_entries(shelf=None):
    with _cursor() as cur:
        if shelf:
            cur.execute('SELECT * FROM entries WHERE shelf = %s ORDER BY added_date DESC', (shelf,))
        else:
            cur.execute('SELECT * FROM entries ORDER BY added_date DESC')
        return [_row_to_entry(r) for r in cur.fetchall()]


def get_entry(entry_id):
    with _cursor() as cur:
        cur.execute('SELECT * FROM entries WHERE id = %s', (entry_id,))
        row = cur.fetchone()
        return _row_to_entry(row) if row else None


def get_user_entry_for_game(username, game_id):
    with _cursor() as cur:
        cur.execute(
            'SELECT * FROM entries WHERE lower(username) = lower(%s) AND game_id = %s',
            (username, str(game_id))
        )
        row = cur.fetchone()
        return _row_to_entry(row) if row else None


def add_entry(username, game_id, game_title, cover_url, shelf,
              rating=None, platform=None, review=None, private_notes=None):
    with _cursor() as cur:
        # Remove existing entry for same user+game, matching old xml_store behavior
        cur.execute(
            'DELETE FROM entries WHERE lower(username) = lower(%s) AND game_id = %s',
            (username, str(game_id))
        )
        cur.execute('''
            INSERT INTO entries (id, username, game_id, game_title, cover_url, shelf,
                                  rating, platform, review, private_notes, added_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            str(uuid.uuid4())[:8], username, str(game_id), game_title, cover_url or '', shelf,
            str(rating) if rating else '', platform or '', review or '', private_notes or '',
            date.today()
        ))


def remove_entry(username, game_id):
    with _cursor() as cur:
        cur.execute(
            'DELETE FROM entries WHERE lower(username) = lower(%s) AND game_id = %s',
            (username, str(game_id))
        )
        return cur.rowcount > 0


def backfill_cover(game_id, cover_url):
    with _cursor() as cur:
        cur.execute(
            "UPDATE entries SET cover_url = %s WHERE game_id = %s AND (cover_url IS NULL OR cover_url = '')",
            (cover_url, str(game_id))
        )


# ── SEED ──────────────────────────────────────────────────────────────────────

def seed_demo_user():
    from hash_util import hash_password
    if not find_user('demo'):
        add_user('demo', hash_password('demo123'))
        games = [
            (1020,  'Grand Theft Auto V',    '', 'Finished',     '4.2', 'PC', 'A classic. The open world still holds up years later.', ''),
            (12249, 'Portal 2',              '', 'Finished',     '5.0', 'PC', 'Perfect game. The co-op alone is worth it.',             ''),
            (12248, 'Portal',                '', 'Finished',     '4.8', 'PC', 'Short but absolutely flawless.',                        ''),
            (25076, 'Red Dead Redemption 2', '', 'Playing',      '',    'PC', '',                                                      'Act 2 currently. Taking my time.'),
            (34783, 'Celeste',               '', 'Want to Play', '',    '',  '',                                                      ''),
        ]
        for gid, title, cover, shelf, rating, platform, review, notes in games:
            add_entry('demo', gid, title, cover, shelf, rating or None, platform or None, review or None, notes or None)


# ── COMMUNITY ─────────────────────────────────────────────────────────────────

def get_recent_reviews(limit=20):
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM entries WHERE review IS NOT NULL AND review != '' ORDER BY added_date DESC LIMIT %s",
            (limit,)
        )
        return [_row_to_entry(r) for r in cur.fetchall()]


def get_site_ratings():
    with _cursor() as cur:
        cur.execute("SELECT * FROM entries")
        rows = cur.fetchall()
    games = {}
    for r in rows:
        gid = r['game_id']
        if not gid:
            continue
        if gid not in games:
            games[gid] = {
                'game_id':   gid,
                'title':     r['game_title'] or '',
                'cover_url': r['cover_url'] or '',
                'ratings':   [],
                'reviews':   [],
            }
        rating = (r['rating'] or '').strip()
        if rating:
            try:
                games[gid]['ratings'].append(float(rating))
            except ValueError:
                pass
        if (r['review'] or '').strip():
            games[gid]['reviews'].append(_row_to_entry(r))

    result = []
    for g in games.values():
        if g['ratings']:
            g['avg']   = round(sum(g['ratings']) / len(g['ratings']), 1)
            g['count'] = len(g['ratings'])
            result.append(g)
    return sorted(result, key=lambda x: (x['count'], x['avg']), reverse=True)


def get_most_reviewed():
    with _cursor() as cur:
        cur.execute("SELECT * FROM entries WHERE review IS NOT NULL AND review != ''")
        rows = cur.fetchall()
    games = {}
    for r in rows:
        gid = r['game_id']
        if gid not in games:
            games[gid] = {
                'game_id':      gid,
                'title':        r['game_title'] or '',
                'cover_url':    r['cover_url'] or '',
                'review_count': 0,
                'ratings':      [],
                'avg':          None,
            }
        games[gid]['review_count'] += 1
        rating = (r['rating'] or '').strip()
        if rating:
            try:
                games[gid]['ratings'].append(float(rating))
            except ValueError:
                pass
    for g in games.values():
        if g['ratings']:
            g['avg'] = round(sum(g['ratings']) / len(g['ratings']), 1)
    return sorted(games.values(), key=lambda x: x['review_count'], reverse=True)[:12]
