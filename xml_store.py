import xml.etree.ElementTree as ET
import os
import uuid
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

def _path(filename):
    return os.path.join(DATA_DIR, filename)

def _load(filename, root_tag):
    p = _path(filename)
    if not os.path.exists(p):
        ET.ElementTree(ET.Element(root_tag)).write(p)
    return ET.parse(p)

def _save(tree, filename):
    tree.write(_path(filename), xml_declaration=True, encoding='utf-8')

# ── USERS ─────────────────────────────────────────────────────────────────────

def find_user(username):
    tree = _load('Users.xml', 'Users')
    for u in tree.getroot().findall('User'):
        if u.findtext('Username', '').lower() == username.lower():
            return {
                'username': u.findtext('Username'),
                'password': u.findtext('Password'),
                'joined':   u.findtext('Joined', ''),
            }
    return None

def add_user(username, hashed_password):
    tree = _load('Users.xml', 'Users')
    u = ET.SubElement(tree.getroot(), 'User')
    ET.SubElement(u, 'Username').text = username
    ET.SubElement(u, 'Password').text = hashed_password
    ET.SubElement(u, 'Joined').text = datetime.now().strftime('%Y-%m-%d')
    _save(tree, 'Users.xml')

def get_all_users():
    tree = _load('Users.xml', 'Users')
    return [u.findtext('Username') for u in tree.getroot().findall('User')]

# ── SHELF ENTRIES ─────────────────────────────────────────────────────────────
# Each entry: id, username, game_id, game_title, cover_url, shelf,
#             rating (optional), platform (optional), review (optional),
#             private_notes (optional), added_date

def _entries_tree():
    return _load('Entries.xml', 'Entries')

def get_user_shelf(username, shelf=None):
    tree = _entries_tree()
    entries = []
    for e in tree.getroot().findall('Entry'):
        if e.findtext('Username', '').lower() != username.lower():
            continue
        if shelf and e.findtext('Shelf') != shelf:
            continue
        entries.append(_entry_dict(e))
    return sorted(entries, key=lambda x: x['added_date'], reverse=True)

def get_all_public_entries(shelf=None):
    """For a public discover/recent page."""
    tree = _entries_tree()
    entries = []
    for e in tree.getroot().findall('Entry'):
        if shelf and e.findtext('Shelf') != shelf:
            continue
        entries.append(_entry_dict(e))
    return sorted(entries, key=lambda x: x['added_date'], reverse=True)

def get_entry(entry_id):
    tree = _entries_tree()
    for e in tree.getroot().findall('Entry'):
        if e.findtext('Id') == entry_id:
            return _entry_dict(e)
    return None

def get_user_entry_for_game(username, game_id):
    tree = _entries_tree()
    for e in tree.getroot().findall('Entry'):
        if (e.findtext('Username', '').lower() == username.lower() and
                e.findtext('GameId') == str(game_id)):
            return _entry_dict(e)
    return None

def add_entry(username, game_id, game_title, cover_url, shelf,
              rating=None, platform=None, review=None, private_notes=None):
    tree = _entries_tree()
    root = tree.getroot()
    # Remove existing entry for same user+game if exists
    for e in root.findall('Entry'):
        if (e.findtext('Username', '').lower() == username.lower() and
                e.findtext('GameId') == str(game_id)):
            root.remove(e)
            break
    entry = ET.SubElement(root, 'Entry')
    ET.SubElement(entry, 'Id').text          = str(uuid.uuid4())[:8]
    ET.SubElement(entry, 'Username').text    = username
    ET.SubElement(entry, 'GameId').text      = str(game_id)
    ET.SubElement(entry, 'GameTitle').text   = game_title
    ET.SubElement(entry, 'CoverUrl').text    = cover_url or ''
    ET.SubElement(entry, 'Shelf').text       = shelf
    ET.SubElement(entry, 'Rating').text      = str(rating) if rating else ''
    ET.SubElement(entry, 'Platform').text    = platform or ''
    ET.SubElement(entry, 'Review').text      = review or ''
    ET.SubElement(entry, 'PrivateNotes').text = private_notes or ''
    ET.SubElement(entry, 'AddedDate').text   = datetime.now().strftime('%Y-%m-%d')
    _save(tree, 'Entries.xml')

def remove_entry(username, game_id):
    tree = _entries_tree()
    root = tree.getroot()
    for e in root.findall('Entry'):
        if (e.findtext('Username', '').lower() == username.lower() and
                e.findtext('GameId') == str(game_id)):
            root.remove(e)
            _save(tree, 'Entries.xml')
            return True
    return False

def _entry_dict(e):
    return {
        'id':            e.findtext('Id', ''),
        'username':      e.findtext('Username', ''),
        'game_id':       e.findtext('GameId', ''),
        'game_title':    e.findtext('GameTitle', ''),
        'cover_url':     e.findtext('CoverUrl', ''),
        'shelf':         e.findtext('Shelf', ''),
        'rating':        e.findtext('Rating', ''),
        'platform':      e.findtext('Platform', ''),
        'review':        e.findtext('Review', ''),
        'private_notes': e.findtext('PrivateNotes', ''),
        'added_date':    e.findtext('AddedDate', ''),
    }

# ── SEED ──────────────────────────────────────────────────────────────────────

def seed_demo_user():
    from hash_util import hash_string
    if not find_user('demo'):
        add_user('demo', hash_string('demo123'))
        # Add a few shelf entries with real RAWG game ids + covers
        games = [
            (3498,  'Grand Theft Auto V',      'https://media.rawg.io/media/games/456/456dea5e1c7e3cd07060c14e96612001.jpg', 'Finished', '4.2', 'PC',    'A classic. The world still holds up.',  ''),
            (4200,  'Portal 2',                'https://media.rawg.io/media/games/328/3283617cb7d75d67257fc58339188742.jpg', 'Finished', '5.0', 'PC',    'Perfect game. No notes.',               ''),
            (13536, 'Portal',                  'https://media.rawg.io/media/games/7fa/7fa0b586293c5861ee32490e953a4996.jpg', 'Finished', '4.8', 'PC',    'Short but flawless.',                   ''),
            (28,    'Red Dead Redemption 2',   'https://media.rawg.io/media/games/511/5118aff5091cb3efec399c808f8c598f.jpg', 'Playing',  '',    'PC',    '',                                      'Act 2 currently. Taking my time.'),
            (41494, 'Celeste',                 'https://media.rawg.io/media/games/594/594574c3b1c6de968f83f610b29c5bed.jpg', 'Want to Play', '', '',  '',                                      ''),
        ]
        for gid, title, cover, shelf, rating, platform, review, notes in games:
            add_entry('demo', gid, title, cover, shelf, rating or None, platform or None, review or None, notes or None)

# ── COMMUNITY ─────────────────────────────────────────────────────────────────

def get_recent_reviews(limit=20):
    """All entries with a written review, newest first."""
    tree = _entries_tree()
    results = [_entry_dict(e) for e in tree.getroot().findall('Entry')
               if e.findtext('Review', '').strip()]
    return sorted(results, key=lambda x: x['added_date'], reverse=True)[:limit]

def get_site_ratings():
    """Games with ratings on GameShelf, sorted by rating count then avg."""
    tree = _entries_tree()
    games = {}
    for e in tree.getroot().findall('Entry'):
        gid = e.findtext('GameId', '')
        if not gid:
            continue
        if gid not in games:
            games[gid] = {
                'game_id':   gid,
                'title':     e.findtext('GameTitle', ''),
                'cover_url': e.findtext('CoverUrl', ''),
                'ratings':   [],
                'reviews':   [],
            }
        rating = e.findtext('Rating', '').strip()
        if rating:
            try:
                games[gid]['ratings'].append(float(rating))
            except ValueError:
                pass
        if e.findtext('Review', '').strip():
            games[gid]['reviews'].append(_entry_dict(e))

    result = []
    for g in games.values():
        if g['ratings']:
            g['avg']   = round(sum(g['ratings']) / len(g['ratings']), 1)
            g['count'] = len(g['ratings'])
            result.append(g)
    return sorted(result, key=lambda x: (x['count'], x['avg']), reverse=True)

def get_most_reviewed():
    """Games with the most written reviews, up to 12."""
    tree = _entries_tree()
    games = {}
    for e in tree.getroot().findall('Entry'):
        if not e.findtext('Review', '').strip():
            continue
        gid = e.findtext('GameId', '')
        if gid not in games:
            games[gid] = {
                'game_id':      gid,
                'title':        e.findtext('GameTitle', ''),
                'cover_url':    e.findtext('CoverUrl', ''),
                'review_count': 0,
                'ratings':      [],
                'avg':          None,
            }
        games[gid]['review_count'] += 1
        rating = e.findtext('Rating', '').strip()
        if rating:
            try:
                games[gid]['ratings'].append(float(rating))
            except ValueError:
                pass
    for g in games.values():
        if g['ratings']:
            g['avg'] = round(sum(g['ratings']) / len(g['ratings']), 1)
    return sorted(games.values(), key=lambda x: x['review_count'], reverse=True)[:12]
