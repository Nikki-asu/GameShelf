from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from functools import wraps
import requests as http
import os, time
from hash_util import hash_string, hash_password, check_password
import xml_store as db

app = Flask(__name__)
app.secret_key = 'gameshelf-secret-change-in-prod'

PLATFORMS = ['PC', 'PlayStation 5', 'PlayStation 4', 'Xbox Series X/S',
             'Xbox One', 'Nintendo Switch', 'Meta Quest', 'iOS', 'Android', 'Other']
SHELVES = ['Playing', 'Want to Play', 'Finished']


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            flash('Log in to do that.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

# ── IGDB API ──────────────────────────────────────────────────────────────────

IGDB_CLIENT_ID     = os.environ.get('IGDB_CLIENT_ID', '')
IGDB_CLIENT_SECRET = os.environ.get('IGDB_CLIENT_SECRET', '')
IGDB_BASE          = 'https://api.igdb.com/v4'

_igdb_token       = None
_igdb_token_expiry = 0

def igdb_token():
    global _igdb_token, _igdb_token_expiry
    if _igdb_token and time.time() < _igdb_token_expiry - 300:
        return _igdb_token
    r = http.post('https://id.twitch.tv/oauth2/token', params={
        'client_id':     IGDB_CLIENT_ID,
        'client_secret': IGDB_CLIENT_SECRET,
        'grant_type':    'client_credentials',
    }, timeout=8)
    data = r.json()
    _igdb_token        = data['access_token']
    _igdb_token_expiry = time.time() + data['expires_in']
    return _igdb_token

def igdb_headers():
    return {
        'Client-ID':     IGDB_CLIENT_ID,
        'Authorization': f'Bearer {igdb_token()}',
        'Content-Type':  'text/plain',
    }

def igdb_cover_url(cover_id):
    if not cover_id:
        return ''
    return f'https://images.igdb.com/igdb/image/upload/t_cover_big/{cover_id}.jpg'

def igdb_search(query, page=1):
    try:
        offset = (page - 1) * 12
        body = f'''
            search "{query}";
            fields name, cover.image_id, first_release_date, genres.name,
                   aggregated_rating, involved_companies.company.name,
                   involved_companies.developer;
            limit 12;
            offset {offset};
            where version_parent = null;
        '''
        r = http.post(f'{IGDB_BASE}/games', headers=igdb_headers(), data=body, timeout=8)
        games = r.json()
        results = []
        for g in games:
            year = ''
            if g.get('first_release_date'):
                year = str(time.strftime('%Y', time.gmtime(g['first_release_date'])))
            results.append({
                'id':        g['id'],
                'title':     g['name'],
                'cover_url': igdb_cover_url(g.get('cover', {}).get('image_id') if g.get('cover') else None),
                'released':  year,
                'rating':    round(g.get('aggregated_rating', 0) / 20, 1) if g.get('aggregated_rating') else 0,
                'genres':    ', '.join(x['name'] for x in g.get('genres', [])[:2]),
            })
        return results, len(results)
    except Exception as ex:
        print(f'IGDB search error: {ex}')
        return [], 0

def igdb_game(game_id):
    try:
        body = f'''
            fields name, cover.image_id, first_release_date, genres.name,
                   aggregated_rating, summary,
                   involved_companies.company.name, involved_companies.developer;
            where id = {game_id};
        '''
        r = http.post(f'{IGDB_BASE}/games', headers=igdb_headers(), data=body, timeout=8)
        games = r.json()
        if not games:
            return None
        g = games[0]
        year = ''
        if g.get('first_release_date'):
            year = str(time.strftime('%Y', time.gmtime(g['first_release_date'])))
        devs = [c['company']['name'] for c in g.get('involved_companies', [])
                if c.get('developer') and c.get('company')][:2]
        return {
            'id':          g['id'],
            'title':       g['name'],
            'cover_url':   igdb_cover_url(g.get('cover', {}).get('image_id') if g.get('cover') else None),
            'released':    year,
            'description': (g.get('summary') or '')[:600],
            'genres':      ', '.join(x['name'] for x in g.get('genres', [])[:3]),
            'developers':  ', '.join(devs),
            'rating':      round(g.get('aggregated_rating', 0) / 20, 1) if g.get('aggregated_rating') else 0,
        }
    except Exception as ex:
        print(f'IGDB game error: {ex}')
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
    results, total = (igdb_search(query, page) if query else ([], 0))
    return render_template('search.html', results=results,
                           query=query, page=page, total=total)

@app.route('/game/<int:game_id>')
def game(game_id):
    # First check if we have it in our own XML (fallback)
    all_entries = db.get_all_public_entries()
    reviews = [e for e in all_entries if e['game_id'] == str(game_id) and e['review']]

    info = igdb_game(game_id)

    # Graceful fallback — build info from existing shelf data if API fails
    if not info:
        existing = next((e for e in all_entries if e['game_id'] == str(game_id)), None)
        if existing:
            info = {
                'id':          game_id,
                'title':       existing['game_title'],
                'cover_url':   existing['cover_url'],
                'released':    '',
                'description': '',
                'genres':      '',
                'developers':  '',
                'rating':      0,
            }
        else:
            flash('Game not found.', 'danger')
            return redirect(url_for('search'))

    # Backfill cover URL into any existing XML entries that are missing it
    if info and info.get('cover_url'):
        db.backfill_cover(game_id, info['cover_url'])

    user_entry = None
    if session.get('username'):
        user_entry = db.get_user_entry_for_game(session['username'], game_id)

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
            rating = round(r, 1) if 0 < r <= 5 else None
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
        if user and check_password(password, user['password']):
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
        db.add_user(username, hash_password(password))
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

@app.route('/arcade')
def arcade():
    return render_template('arcade.html')

GENRE_IDS = {
    'action':    12,
    'rpg':       12,   # will override below
    'horror':    None,
    'indie':     32,
    'adventure': 31,
    'racing':    10,
    'puzzle':    9,
    'strategy':  15,
}

GENRE_IGDB_IDS = {
    'action':    [12],
    'rpg':       [12, 11],
    'horror':    [12],   # use theme 19 for horror
    'indie':     [32],
    'adventure': [31],
    'racing':    [10],
    'puzzle':    [9],
    'strategy':  [15],
}

GENRE_THEMES = {
    'horror': 19,  # IGDB theme ID for horror
}

@app.route('/arcade/genre')
def arcade_genre():
    genre = request.args.get('genre', '').lower()
    page  = int(request.args.get('page', 1))
    offset = (page - 1) * 12

    try:
        genre_ids = GENRE_IGDB_IDS.get(genre, [12])
        theme_id  = GENRE_THEMES.get(genre)

        if theme_id:
            where = f'themes = ({theme_id}) & version_parent = null & cover != null'
        else:
            genre_list = ', '.join(str(g) for g in genre_ids)
            where = f'genres = ({genre_list}) & version_parent = null & cover != null'

        body = f'''
            fields name, cover.image_id, first_release_date, genres.name, aggregated_rating;
            where {where};
            sort aggregated_rating desc;
            limit 12;
            offset {offset};
        '''
        r = http.post(f'{IGDB_BASE}/games', headers=igdb_headers(), data=body, timeout=8)
        games = r.json()
        results = []
        for g in games:
            year = ''
            if g.get('first_release_date'):
                year = str(time.strftime('%Y', time.gmtime(g['first_release_date'])))
            results.append({
                'id':          g['id'],
                'title':       g['name'],
                'cover_url':   igdb_cover_url(g.get('cover', {}).get('image_id') if g.get('cover') else None),
                'released':    year,
                'genres':      ', '.join(x['name'] for x in g.get('genres', [])[:2]),
                'description': '',
                'rating':      round(g.get('aggregated_rating', 0) / 20, 1) if g.get('aggregated_rating') else 0,
            })
        return jsonify({'results': results, 'total': len(results) + offset + (1 if len(results) == 12 else 0)})
    except Exception as ex:
        print(f'IGDB arcade error: {ex}')
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

if __name__ == '__main__':
    app.run(debug=True)
