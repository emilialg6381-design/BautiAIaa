import os
import json
import re
import requests
import threading
import time
import uuid
from urllib.parse import quote
from flask import Flask, request, jsonify, Response, make_response
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='/static')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, 'static', 'images')
VIDEO_DIR = os.path.join(BASE_DIR, 'static', 'videos')
HISTORY_FILE = os.path.join(BASE_DIR, 'search_history.json')
for d in [IMAGE_DIR, VIDEO_DIR]:
    os.makedirs(d, exist_ok=True)

# ═════════════════════════════════════════════════════════
# TMDB
# ═════════════════════════════════════════════════════════
TMDB_KEY = "258519c3d82673fd9bd4186b2356ff27"
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"
_tmdb_cache = {}
_tmdb_cache_lock = threading.Lock()

def _img(path, size="w500"):
    if not path: return ""
    return TMDB_IMG + "/" + size + path

def _tmdb(url):
    try:
        return requests.get(url, timeout=10).json()
    except Exception as e:
        return {"status_code": 999, "status_message": str(e)}

# ═════════════════════════════════════════════════════════
# SOLOLATINO / PLAYWRIGHT
# ═════════════════════════════════════════════════════════
jobs = {}
jobs_lock = threading.Lock()
history_lock = threading.Lock()

PW_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
    "--disable-gpu", "--disable-blink-features=AutomationControlled"
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

try:
    from playwright.sync_api import sync_playwright
    PW_OK = True
except ImportError:
    PW_OK = False

SOLOLATINO = "https://sololatino.net"

PROXY_HEADERS = {
    'User-Agent': UA,
    'Referer': 'https://www.2embed.cc/',
    'Accept': 'text/html,application/xhtml+xml',
}

def _fix_urls(content, base):
    for attr in ['src="', "src='", 'href="', "href='", 'action="', "action='"]:
        content = content.replace(attr + '/', attr + base + '/')
    return content

def _format_sololatino_episode_url(series_url, season, episode):
    """
    Formats a SoloLatino series URL into a specific episode URL.
    
    Args:
        series_url: Base series URL (e.g., '/serie/el-maravillosamente-extrano-mundo-de-gumball')
        season: Season number (int or string)
        episode: Episode number (int or string)
    
    Returns:
        Formatted episode URL (e.g., '/serie/el-maravillosamente-extrano-mundo-de-gumball/temporada-1/episodio-1')
    """
    # Remove trailing slash if present
    series_url = series_url.rstrip('/')
    return f"{series_url}/temporada-{season}/episodio-{episode}"

def _proxy_embed(urls):
    for url in urls:
        try:
            resp = requests.get(url, headers=PROXY_HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 500:
                return _fix_urls(resp.text, "https://www.2embed.cc")
        except Exception:
            continue
    return None

def _save_history(item):
    """Guarda item en historial de búsqueda"""
    try:
        with history_lock:
            history = []
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            # Evitar duplicados
            history = [h for h in history if h.get('title') != item.get('title')]
            item['timestamp'] = datetime.now().isoformat()
            history.insert(0, item)
            history = history[:100]
            
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

def _load_history():
    """Carga historial de búsqueda"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []

# ═════════════════════════════════════════════════════════
# 2EMBED PROXY (Sub mode)
# ═════════════════════════════════════════════════════════

@app.route('/embed/movie/<imdb_id>')
def embed_movie(imdb_id):
    c = _proxy_embed([
        f"https://www.2embed.cc/embed/{imdb_id}",
        f"https://www.2embed.skin/embed/{imdb_id}"
    ])
    return Response(c, content_type='text/html; charset=utf-8') if c else ("Not found", 404)

@app.route('/embed/tv/<imdb_id>')
def embed_tv(imdb_id):
    s = request.args.get('s', '1')
    e = request.args.get('e', '1')
    c = _proxy_embed([
        f"https://www.2embed.cc/embedtv/{imdb_id}&s={s}&e={e}",
        f"https://www.2embed.skin/embedtv/{imdb_id}&s={s}&e={e}"
    ])
    return Response(c, content_type='text/html; charset=utf-8') if c else ("Not found", 404)

# ═════════════════════════════════════════════════════════
# TMDB SEARCH
# ═════════════════════════════════════════════════════════

@app.route('/api/tmdb-search')
def tmdb_search():
    q = request.args.get('q', '').strip()
    t = request.args.get('type', '').strip()
    p = request.args.get('page', '1').strip()
    if len(q) < 2:
        return jsonify({"success": False, "error": "Minimo 2 caracteres"}), 400

    ck = f"ts:{q.lower()}:{t}:{p}"
    with _tmdb_cache_lock:
        if ck in _tmdb_cache:
            return jsonify(_tmdb_cache[ck])

    if t == 'movie':
        ep = f"{TMDB_BASE}/search/movie?api_key={TMDB_KEY}&query={quote(q)}&page={p}"
    elif t == 'series':
        ep = f"{TMDB_BASE}/search/tv?api_key={TMDB_KEY}&query={quote(q)}&page={p}"
    else:
        ep = f"{TMDB_BASE}/search/multi?api_key={TMDB_KEY}&query={quote(q)}&page={p}"

    r = _tmdb(ep)
    if r.get('status_code', 200) != 200:
        res = {"success": False, "error": r.get('status_message', 'Error TMDB')}
        with _tmdb_cache_lock:
            _tmdb_cache[ck] = res
        return jsonify(res)

    items = []
    for it in r.get('results', []):
        mt = it.get('media_type', '')
        if t == 'movie' or (not t and mt == 'movie'):
            items.append({
                'tmdb_id': it['id'],
                'title': it.get('title', ''),
                'poster': _img(it.get('poster_path')),
                'year': (it.get('release_date') or '')[:4],
                'type': 'movie',
                'vote': it.get('vote_average', 0)
            })
        elif t == 'series' or (not t and mt == 'tv'):
            items.append({
                'tmdb_id': it['id'],
                'title': it.get('name', ''),
                'poster': _img(it.get('poster_path')),
                'year': (it.get('first_air_date') or '')[:4],
                'type': 'series',
                'vote': it.get('vote_average', 0)
            })

    res = {
        "success": True,
        "results": items,
        "total": r.get('total_results', 0),
        "page": int(p),
        "total_pages": r.get('total_pages', 1)
    }
    with _tmdb_cache_lock:
        _tmdb_cache[ck] = res
    return jsonify(res)

# ═════════════════════════════════════════════════════════
# TMDB DETAIL
# ═════════════════════════════════════════════════════════

@app.route('/api/tmdb-detail')
def tmdb_detail():
    tid = request.args.get('tmdb_id', '').strip()
    mt = request.args.get('media_type', '').strip()
    if not tid:
        return jsonify({"success": False, "error": "TMDB ID requerido"}), 400

    ck = f"td:{tid}:{mt}"
    with _tmdb_cache_lock:
        if ck in _tmdb_cache:
            return jsonify(_tmdb_cache[ck])

    if mt == 'movie':
        ep = f"{TMDB_BASE}/movie/{tid}?api_key={TMDB_KEY}&append_to_response=external_ids"
    else:
        ep = f"{TMDB_BASE}/tv/{tid}?api_key={TMDB_KEY}&append_to_response=external_ids"

    r = _tmdb(ep)
    if r.get('status_code', 200) != 200:
        res = {"success": False, "error": r.get('status_message', 'Error TMDB')}
        with _tmdb_cache_lock:
            _tmdb_cache[ck] = res
        return jsonify(res)

    ext = r.get('external_ids', {})
    genres = [g['name'] for g in r.get('genres', [])]

    detail = {
        'tmdb_id': int(tid),
        'imdbID': ext.get('imdb_id', ''),
        'Title': r.get('title') or r.get('name', ''),
        'Year': (r.get('release_date') or r.get('first_air_date') or '')[:4],
        'Runtime': str(r['runtime']) + ' min' if r.get('runtime') else '',
        'Genre': ', '.join(genres),
        'Plot': r.get('overview', ''),
        'Poster': _img(r.get('poster_path')),
        'Type': mt,
        'Vote': r.get('vote_average', 0),
        'totalSeasons': r.get('number_of_seasons', 1) if mt == 'series' else None
    }

    res = {"success": True, "detail": detail}
    with _tmdb_cache_lock:
        _tmdb_cache[ck] = res
    return jsonify(res)

# ═════════════════════════════════════════════════════════
# TMDB EPISODES
# ═════════════════════════════════════════════════════════

@app.route('/api/tmdb-episodes')
def tmdb_episodes():
    tid = request.args.get('tmdb_id', '').strip()
    s = request.args.get('season', '1').strip()
    if not tid or not s:
        return jsonify({"success": False, "error": "TMDB ID y season requeridos"}), 400

    ck = f"te:{tid}:{s}"
    with _tmdb_cache_lock:
        if ck in _tmdb_cache:
            return jsonify(_tmdb_cache[ck])

    ep_url = f"{TMDB_BASE}/tv/{tid}/season/{s}?api_key={TMDB_KEY}"
    r = _tmdb(ep_url)
    if r.get('status_code', 200) != 200:
        res = {"success": False, "error": r.get('status_message', 'Error TMDB')}
        with _tmdb_cache_lock:
            _tmdb_cache[ck] = res
        return jsonify(res)

    eps = []
    for ep in r.get('episodes', []):
        eps.append({
            'Episode': str(ep.get('episode_number', 0)),
            'Title': ep.get('name', ''),
            'Plot': ep.get('overview', ''),
            'Image': _img(ep.get('still_path'), 'w300'),
            'AirDate': ep.get('air_date', '')
        })

    total_s = r.get('season_number', 1)
    
    try:
        tv_r = _tmdb(f"{TMDB_BASE}/tv/{tid}?api_key={TMDB_KEY}")
        total_s = tv_r.get('number_of_seasons', total_s)
    except:
        pass

    res = {
        "success": True,
        "episodes": eps,
        "totalSeasons": total_s
    }
    with _tmdb_cache_lock:
        _tmdb_cache[ck] = res
    return jsonify(res)

# ═════════════════════════════════════════════════════════
# SOLOLATINO / PLAYWRIGHT TASKS
# ═════════════════════════════════════════════════════════

class SoloLatinoTask:
    def __init__(self, job_id, action, **kw):
        self.job_id = job_id
        self.action = action
        self.kw = kw
        self.browser = None
        self.page = None

    def _prog(self, msg):
        """Actualiza progreso del job"""
        with jobs_lock:
            if self.job_id in jobs:
                jobs[self.job_id]['progress'] = msg

    def run(self):
        """Ejecuta la tarea"""
        if not PW_OK:
            with jobs_lock:
                jobs[self.job_id] = {
                    "state": "error",
                    "error": "Playwright no disponible"
                }
            return

        try:
            with sync_playwright() as pw:
                self._prog("Iniciando navegador...")
                self.browser = pw.chromium.launch(args=PW_ARGS, headless=False)
                self.page = self.browser.new_page(
                    user_agent=UA,
                    viewport={"width": 1920, "height": 1080}
                )
                self.page.add_init_script("""() => {
                    Object.defineProperty(navigator, 'webdriver', {get: () => false});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                }""")
                
                # Block ads and trackers at the request level
                def handle_route(route):
                    url = route.request.url.lower()
                    # Block common ad/tracker domains and unnecessary resources
                    block_patterns = [
                        'doubleclick.net', 'adservice.google', 'googlesyndication', 'google-analytics',
                        'analytics.', 'tracking.', 'adsystem', 'adserver', 'advertise', 'sponsor',
                        '.xml', 'fonts.gstatic'
                    ]
                    if any(p in url for p in block_patterns):
                        return route.abort()
                    return route.continue_()
                
                self.page.route("**/*", handle_route)

                if self.action == "search":
                    self._search(self.page)
                elif self.action == "movie":
                    self._movie(self.page)
                elif self.action == "series":
                    self._series(self.page)
                elif self.action == "episode":
                    self._episode(self.page)

        except Exception as e:
            with jobs_lock:
                jobs[self.job_id] = {
                    "state": "error",
                    "error": str(e)
                }
        finally:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()

    # ── BUSQUEDA ────────────────────────────────────────
    def _search(self, page):
        q = self.kw.get('query', '')
        self._prog("Navegando a SoloLatino...")
        search_url = SOLOLATINO + "/buscar?q=" + quote(q.replace(' ', '%20'))
        
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        self._prog("Esperando resultados...")
        page.wait_for_timeout(2500)

        try:
            page.wait_for_selector('.movies-grid', timeout=8000)
        except:
            with jobs_lock:
                jobs[self.job_id].update({"state": "done", "results": []})
            return

        page.wait_for_timeout(1500)

        # Extraer resultados
        results = page.evaluate("""() => {
            const grid = document.querySelector('.movies-grid');
            if (!grid) return [];
            
            const items = [];
            const cards = grid.querySelectorAll('.card');
            
            for (const card of cards) {
                const link = card.querySelector('a');
                const img = card.querySelector('.card__poster');
                const titleEl = card.querySelector('.card__title');
                const yearEl = card.querySelector('.card__year');
                const ratingEl = card.querySelector('.card__rating');
                const badge = card.querySelector('.badge');
                
                if (!link || !titleEl) continue;
                
                items.push({
                    url: link.href || '',
                    poster: img ? img.src : '',
                    title: titleEl.textContent.trim(),
                    year: yearEl ? yearEl.textContent.trim() : '',
                    rating: ratingEl ? ratingEl.textContent.replace('★', '').trim() : '',
                    type: badge ? (badge.textContent.toLowerCase().includes('dibujos') ? 'series' : 
                                   badge.textContent.toLowerCase().includes('película') ? 'movie' : 'series') : 'series',
                    badge: badge ? badge.textContent.trim() : ''
                });
            }
            return items;
        }""")

        # Limpiar URLs
        clean = []
        for item in results:
            u = item.get('url', '')
            if u.startswith(SOLOLATINO):
                u = u[len(SOLOLATINO):]
            item['url'] = u
            clean.append(item)

        with jobs_lock:
            jobs[self.job_id].update({"state": "done", "results": clean})

    # ── PELICULA ────────────────────────────────────────
    def _movie(self, page):
        url = SOLOLATINO + self.kw['url']
        self._prog("Accediendo a pelicula...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        embed = self._wait_for_iframe(page, 18)
        if not embed:
            raise Exception("No se encontro el reproductor de la pelicula")

        with jobs_lock:
            jobs[self.job_id].update({"state": "done", "embed_url": embed})

    # ── SERIE (episodios) ───────────────────────────────
    def _series(self, page):
        url = SOLOLATINO + self.kw['url']
        self._prog("Cargando serie...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Clickear tab "Episodios"
        try:
            ep_tab = page.locator('[data-tab-btn="episodios"]').first
            ep_tab.click(timeout=8000)
            page.wait_for_timeout(2000)
        except:
            self._prog("Tab de episodios no encontrado, intentando continuar...")

        # Esperar paneles de temporada
        try:
            page.wait_for_selector('[data-season-panel]', timeout=10000)
        except:
            raise Exception("No se encontraron episodios para esta serie")

        page.wait_for_timeout(1500)

        # Extraer TODOS los episodios de TODAS las temporadas
        episodes = page.evaluate("""() => {
            const out = [];
            const panels = document.querySelectorAll('[data-season-panel]');
            for (const panel of panels) {
                const seasonNum = parseInt(panel.getAttribute('data-season-panel')) || 1;
                const epLinks = panel.querySelectorAll('a.ep-item');
                for (const link of epLinks) {
                    const thumb = link.querySelector('.ep-thumb');
                    const numEl = link.querySelector('.ep-num');
                    const titleEl = link.querySelector('.text-sm.font-semibold');
                    const descEl = link.querySelector('.line-clamp-2');
                    const allSmall = link.querySelectorAll('p.text-xs');
                    let dateEl = null;
                    for (const el of allSmall) {
                        if (el !== descEl) dateEl = el;
                    }
                    const epNum = numEl ? numEl.textContent.replace('E', '').trim() : '0';
                    const rawTitle = titleEl ? titleEl.textContent : '';
                    const cleanTitle = rawTitle.replace(/[\\u2068\\u2069\\u200e\\u200f\\u200c\\u200d]/g, '').trim();
                    out.push({
                        season: seasonNum,
                        episode: parseInt(epNum) || 0,
                        title: cleanTitle,
                        thumb: thumb ? thumb.src : '',
                        description: descEl ? descEl.textContent.trim() : '',
                        date: dateEl ? dateEl.textContent.trim() : '',
                        url: link.href || ''
                    });
                }
            }
            return out;
        }""")

        title = page.evaluate("""() => {
            const h1 = document.querySelector('h1');
            return h1 ? h1.textContent.trim() : '';
        }""")

        clean = []
        for ep in episodes:
            u = ep['url']
            if u.startswith(SOLOLATINO):
                u = u[len(SOLOLATINO):]
            ep['url'] = u
            if ep['episode'] > 0:
                clean.append(ep)

        seasons = sorted(list(set(ep['season'] for ep in clean)))

        with jobs_lock:
            jobs[self.job_id].update({
                "state": "done",
                "episodes": clean,
                "series_title": title,
                "seasons": seasons
            })

    # ── EPISODIO (iframe con autoplay) ───────────────────────────────
    def _episode(self, page):
        url = SOLOLATINO + self.kw['url']
        self._prog(f"Cargando episodio: {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # Print current URL for debugging
        current_url = page.url
        self._prog(f"URL actual: {current_url}")

        # Try to click the play button if it exists
        try:
            play_btn = page.locator('button.play-button, .play-btn, [class*="play"], .btn-play').first
            if play_btn.is_visible(timeout=3000):
                play_btn.click(timeout=5000)
                page.wait_for_timeout(3000)
                self._prog("Play button clicked")
        except Exception as e:
            self._prog(f"No play button found or error: {e}, continuing...")

        # Wait a bit more for the iframe to load after clicking play
        page.wait_for_timeout(4000)
        
        embed = self._wait_for_iframe(page, 25)
        if not embed:
            raise Exception(f"No se encontro el reproductor del episodio. URL: {current_url}")

        with jobs_lock:
            jobs[self.job_id].update({"state": "done", "embed_url": embed})

    # ── HELPERS ─────────────────────────────────────────
    def _wait_for_iframe(self, page, max_loops=18):
        """Espera hasta max_loops segundos por un iframe con src valido."""
        for i in range(max_loops):
            page.wait_for_timeout(1000)
            self._prog(f"Buscando reproductor... ({i+1}s)")
            embed = page.evaluate("""() => {
                const frames = document.querySelectorAll('iframe');
                for (const f of frames) {
                    const src = f.src || '';
                    // Check for player domains like pelisserieshoy, embed, etc.
                    if (src.length > 20 && 
                        !src.includes('about:blank') && 
                        !src.includes('javascript:') &&
                        !src.includes('sololatino.net')) {
                        return src;
                    }
                }
                // If no direct player found, check for nested iframes or data attributes
                for (const f of frames) {
                    const src = f.src || '';
                    if (src.length > 20 && !src.includes('about:blank') && !src.includes('javascript:')) {
                        // Try to get the actual player from inside this iframe's content
                        // or return the src if it looks like a player URL
                        if (src.includes('player.') || src.includes('embed.') || src.includes('f/')) {
                            return src;
                        }
                    }
                }
                return null;
            }""")
            if embed:
                return embed
        return None


def _latino_job(action, **kw):
    """Crea un job de SoloLatino y lo lanza en un thread daemon."""
    jid = str(uuid.uuid4())
    with jobs_lock:
        jobs[jid] = {"state": "pending", "progress": "Iniciando..."}
    threading.Thread(target=SoloLatinoTask(jid, action, **kw).run, daemon=True).start()
    return jid

# ── API endpoints ──

@app.route('/api/cuevana-status')
def latino_status():
    return jsonify({"available": PW_OK})

@app.route('/api/job-status/<job_id>')
def job_status(job_id):
    with jobs_lock:
        j = jobs.get(job_id)
        if j:
            return jsonify(dict(j))
    return jsonify({"state": "pending", "progress": "Conectando con el worker..."}), 200

@app.route('/api/cuevana-search', methods=['POST'])
def latino_search():
    q = (request.json or {}).get('query', '').strip()
    if not q: return jsonify({"error": "Query vacia"}), 400
    return jsonify({"job_id": _latino_job("search", query=q)})

@app.route('/api/cuevana-movie', methods=['POST'])
def latino_movie():
    u = (request.json or {}).get('url', '').strip()
    if not u: return jsonify({"error": "URL vacia"}), 400
    return jsonify({"job_id": _latino_job("movie", url=u)})

@app.route('/api/cuevana-series', methods=['POST'])
def latino_series():
    u = (request.json or {}).get('url', '').strip()
    if not u: return jsonify({"error": "URL vacia"}), 400
    # Check if it's a movie URL or series URL
    # Movie URLs typically don't have temporada/episodio patterns
    if 'temporada' not in u.lower() and 'episodio' not in u.lower():
        # It might be a movie, treat it as such
        return jsonify({"job_id": _latino_job("movie", url=u)})
    return jsonify({"job_id": _latino_job("series", url=u)})

@app.route('/api/cuevana-episode', methods=['POST'])
def latino_episode():
    data = request.json or {}
    series_url = data.get('series_url', '').strip()
    season = data.get('season', '1')
    episode = data.get('episode', '1')
    
    if not series_url:
        # Fallback to old behavior with url parameter
        u = data.get('url', '').strip()
        if not u:
            return jsonify({"error": "URL vacia"}), 400
        return jsonify({"job_id": _latino_job("episode", url=u)})
    
    # Format the episode URL properly
    formatted_url = _format_sololatino_episode_url(series_url, season, episode)
    return jsonify({"job_id": _latino_job("episode", url=formatted_url)})

@app.route('/api/history')
def get_history():
    return jsonify({"history": _load_history()})

# ═════════════════════════════════════════════════════════
# STATUS + INDEX
# ═════════════════════════════════════════════════════════

@app.route('/status')
def get_status():
    active = {}
    with jobs_lock:
        for jid, j in jobs.items():
            if j.get("state") not in ("done", "error"):
                active[jid] = dict(j)
    history = []
    for folder, t in [(IMAGE_DIR, "image"), (VIDEO_DIR, "video")]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                p = os.path.join(folder, f)
                if os.path.isfile(p):
                    history.append({"url": f"/static/{t}s/{f}", "filename": f, "type": t, "time": os.path.getctime(p)})
    history.sort(key=lambda x: x.get("time", 0), reverse=True)
    return jsonify({"active_jobs": active, "history": history})

@app.route('/')
def index():
    with open(os.path.join(BASE_DIR, 'templates', 'index.html'), 'r', encoding='utf-8') as f:
        content = f.read()
    resp = make_response(content)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    resp.headers['X-Frame-Options'] = 'ALLOWALL'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

if __name__ == '__main__':
    print("MODO DESARROLLO")
    print(f"Playwright disponible: {PW_OK}")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
