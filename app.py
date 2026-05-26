from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from functools import wraps
import requests as http
from hash_util import hash_string
import xml_store as db

app = Flask(__name__)
app.secret_key = 'gameshelf-secret-change-in-prod'

PLATFORMS = ['PC', 'PlayStation 5', 'PlayStation 4', 'Xbox Series X/S',
             'Xbox One', 'Nintendo Switch', 'Meta Quest', 'iOS', 'Android', 'Other']
SHELVES = ['Playing', 'Want to Play', 'Finished']

with app.app_context():
    db.seed_demo_user()

# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            flash('Log in to do that.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

# ── RAWG API ──────────────────────────────────────────────────────────────────

RAWG_BASE = 'https://api.rawg.io/api'
RAWG_KEY  = 'YOUR_RAWG_KEY'  # free at rawg.io — or omit for limited access

def rawg_search(query, page=1):
    try:
        params = {'search': query, 'page_size': 12, 'page': page}
        if RAWG_KEY != 'YOUR_RAWG_KEY':
            params['key'] = RAWG_KEY
        r = http.get(f'{RAWG_BASE}/games', params=params, timeout=6)
        data = r.json()
        results = []
        for g in data.get('results', []):
            results.append({
                'id':        g['id'],
                'title':     g['name'],
                'cover_url': g.get('background_image') or '',
                'released':  g.get('released', '')[:4] if g.get('released') else '',
                'rating':    round(g.get('rating', 0), 1),
                'genres':    ', '.join(x['name'] for x in g.get('genres', [])[:2]),
            })
        return results, data.get('count', 0)
    except Exception:
        return [], 0

def rawg_game(game_id):
    try:
        params = {}
        if RAWG_KEY != 'YOUR_RAWG_KEY':
            params['key'] = RAWG_KEY
        r = http.get(f'{RAWG_BASE}/games/{game_id}', params=params, timeout=6)
        g = r.json()
        return {
            'id':          g['id'],
            'title':       g['name'],
            'cover_url':   g.get('background_image') or '',
            'released':    g.get('released', '')[:4] if g.get('released') else '',
            'description': g.get('description_raw', '')[:600],
            'genres':      ', '.join(x['name'] for x in g.get('genres', [])[:3]),
            'developers':  ', '.join(x['name'] for x in g.get('developers', [])[:2]),
            'rating':      round(g.get('rating', 0), 1),
        }
    except Exception:
        return None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    recent_finished = db.get_all_public_entries(shelf='Finished')[:8]
    recent_playing  = db.get_all_public_entries(shelf='Playing')[:8]
    return render_template('index.html',
                           recent_finished=recent_finished,
                           recent_playing=recent_playing)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    page  = int(request.args.get('page', 1))
    results, total = (rawg_search(query, page) if query else ([], 0))
    return render_template('search.html', results=results,
                           query=query, page=page, total=total)

@app.route('/game/<int:game_id>')
def game(game_id):
    info = rawg_game(game_id)
    if not info:
        flash('Game not found.', 'danger')
        return redirect(url_for('search'))
    user_entry = None
    if session.get('username'):
        user_entry = db.get_user_entry_for_game(session['username'], game_id)
    # Recent public reviews for this game
    all_entries = db.get_all_public_entries()
    reviews = [e for e in all_entries if e['game_id'] == str(game_id) and e['review']]
    return render_template('game.html', info=info, user_entry=user_entry,
                           reviews=reviews, platforms=PLATFORMS, shelves=SHELVES)

@app.route('/game/<int:game_id>/add', methods=['POST'])
@login_required
def add_to_shelf(game_id):
    shelf         = request.form.get('shelf')
    rating        = request.form.get('rating') or None
    platform      = request.form.get('platform') or None
    review        = request.form.get('review') or None
    private_notes = request.form.get('private_notes') or None
    title         = request.form.get('game_title', '')
    cover_url     = request.form.get('cover_url', '')

    if rating:
        try:
            r = float(rating)
            if not (0 < r <= 5):
                rating = None
            else:
                rating = round(r, 1)
        except ValueError:
            rating = None

    db.add_entry(session['username'], game_id, title, cover_url,
                 shelf, rating, platform, review, private_notes)
    flash(f'Added to {shelf}!', 'success')
    return redirect(url_for('game', game_id=game_id))

@app.route('/game/<int:game_id>/remove', methods=['POST'])
@login_required
def remove_from_shelf(game_id):
    db.remove_entry(session['username'], game_id)
    flash('Removed from shelf.', 'info')
    return redirect(url_for('game', game_id=game_id))

@app.route('/user/<username>')
def profile(username):
    user = db.find_user(username)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('index'))
    is_owner = session.get('username', '').lower() == username.lower()
    shelves = {}
    for shelf in SHELVES:
        shelves[shelf] = db.get_user_shelf(username, shelf)
    return render_template('profile.html', user=user, shelves=shelves,
                           is_owner=is_owner, shelf_names=SHELVES)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        user = db.find_user(username)
        if user and user['password'].upper() == hash_string(password).upper():
            session['username'] = user['username']
            return redirect(request.args.get('next') or url_for('profile', username=user['username']))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        if not username or not password:
            flash('Both fields required.', 'danger')
            return render_template('register.html')
        if db.find_user(username):
            flash('Username taken.', 'danger')
            return render_template('register.html')
        db.add_user(username, hash_string(password))
        session['username'] = username
        flash('Welcome to GameShelf!', 'success')
        return redirect(url_for('profile', username=username))
    return render_template('register.html')

@app.route('/theme/toggle', methods=['POST'])
def theme_toggle():
    from flask import make_response
    current = request.cookies.get('ThemeMode', 'Dark')
    new_theme = 'Light' if current == 'Dark' else 'Dark'
    resp = make_response(redirect(request.referrer or url_for('index')))
    resp.set_cookie('ThemeMode', new_theme, max_age=60*60*24*365)
    return resp

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/arcade')
def arcade():
    return render_template('arcade.html')

GENRE_SLUGS = {
    'action':    ('action',                 None),
    'rpg':       ('role-playing-games-rpg', None),
    'horror':    (None,                     'horror'),
    'indie':     ('indie',                  None),
    'adventure': ('adventure',              None),
    'racing':    ('racing',                 None),
    'puzzle':    ('puzzle',                 None),
    'strategy':  ('strategy',               None),
}

@app.route('/arcade/genre')
def arcade_genre():
    genre = request.args.get('genre', '').lower()
    page  = int(request.args.get('page', 1))
    slug, tag = GENRE_SLUGS.get(genre, ('action', None))
    try:
        params = {'page_size': 12, 'page': page, 'ordering': '-rating'}
        if RAWG_KEY != 'YOUR_RAWG_KEY':
            params['key'] = RAWG_KEY
        if tag:
            params['tags'] = tag
        else:
            params['genres'] = slug
        r = http.get(f'{RAWG_BASE}/games', params=params, timeout=8)
        data = r.json()
        results = [{
            'id':          g['id'],
            'title':       g['name'],
            'cover_url':   g.get('background_image') or '',
            'released':    (g.get('released') or '')[:4],
            'genres':      ', '.join(x['name'] for x in g.get('genres', [])[:2]),
            'description': (g.get('description_raw') or '')[:200],
            'rating':      round(g.get('rating', 0), 1),
        } for g in data.get('results', [])]
        return jsonify({'results': results, 'total': data.get('count', 0)})
    except Exception as ex:
        return jsonify({'results': [], 'total': 0, 'error': str(ex)})

@app.route('/board')
def board():
    recent_reviews = db.get_recent_reviews(20)
    top_rated      = db.get_site_ratings()[:12]
    most_reviewed  = db.get_most_reviewed()
    return render_template('board.html',
                           recent_reviews=recent_reviews,
                           top_rated=top_rated,
                           most_reviewed=most_reviewed)
