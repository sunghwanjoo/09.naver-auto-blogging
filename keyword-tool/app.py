import sys
import os

# Vercel 서버리스 환경에서 같은 디렉터리의 naver_bot 모듈을 찾을 수 있도록 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── PyInstaller 번들 SSL 인증서 경로 강제 설정 (반드시 requests import 전에 실행) ──
if getattr(sys, 'frozen', False):
    _cert = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
    if not os.path.exists(_cert):
        # collect_all('certifi')가 certifi 패키지 내부에 포함한 경우 시도
        import glob as _glob
        _candidates = _glob.glob(os.path.join(sys._MEIPASS, '**', 'cacert.pem'), recursive=True)
        if _candidates:
            _cert = _candidates[0]
    if os.path.exists(_cert):
        os.environ['REQUESTS_CA_BUNDLE'] = _cert
        os.environ['SSL_CERT_FILE'] = _cert
        os.environ['CURL_CA_BUNDLE'] = _cert
        try:
            import certifi as _certifi
            _certifi.where = lambda: _cert
            if hasattr(_certifi, 'core'):
                _certifi.core.where = lambda: _cert
        except Exception:
            pass
    else:
        # cacert.pem이 번들에 없는 경우 — certifi.where()가 잘못된 경로를 반환하지 못하도록 패치
        # 환경변수도 잘못된 경로로 세팅되어 있으면 제거
        for _ev in ('REQUESTS_CA_BUNDLE', 'SSL_CERT_FILE', 'CURL_CA_BUNDLE'):
            os.environ.pop(_ev, None)
        try:
            import certifi as _certifi
            import ssl as _ssl
            # Python ssl 모듈의 기본 CA 경로 사용 (Windows 인증서 저장소 등)
            _sys_ca = _ssl.get_default_verify_paths().cafile
            if _sys_ca and os.path.exists(_sys_ca):
                _certifi.where = lambda: _sys_ca
                if hasattr(_certifi, 'core'):
                    _certifi.core.where = lambda: _sys_ca
            else:
                # ssl 기본 CA도 없으면 certifi.where()를 None 반환으로 막음
                # requests는 None이면 자체 ssl 컨텍스트(Windows 인증서 저장소)를 사용
                _certifi.where = lambda: None
                if hasattr(_certifi, 'core'):
                    _certifi.core.where = lambda: None
        except Exception:
            pass

import time
import json
import hashlib
import hmac
import base64
import threading
import webbrowser
import uuid
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
import naver_bot

# 서버 실행마다 새 세션 토큰 생성 → 브라우저 localStorage 자동 초기화
SESSION_TOKEN = str(uuid.uuid4())


def resource_path(rel):
    """PyInstaller 번들 내부 리소스 경로"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


app = Flask(__name__, template_folder=resource_path('templates'))

CUSTOMER_ID = '2071405'
API_KEY = '010000000069aa1e72ec9c93499e21d65385abd10c747268db82462757fd989310e48a27a9'
SECRET_KEY = 'AQAAAABpqh5y7JyTSZ4h1lOFq9EMWu086e2klJpIwe+VhCgeag=='
BASE_URL = 'https://api.searchad.naver.com'

NAVER_CLIENT_ID = 'p5_lbliQ3TbHdQvERlcJ'
NAVER_CLIENT_SECRET = 'rJgAOskYL0'

# 업로드 작업 상태 저장
upload_status = {}

# exe 실행 시 sys.executable 기준, 소스 실행 시 __file__ 기준으로 config.json 경로 설정
if getattr(sys, 'frozen', False):
    CONFIG_FILE = os.path.join(os.path.dirname(sys.executable), 'config.json')
else:
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


def generate_signature(timestamp, method, uri):
    message = f"{timestamp}.{method}.{uri}"
    hashed = hmac.new(SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hashed.digest()).decode('utf-8')


def get_headers(method, uri):
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri)
    return {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': API_KEY,
        'X-Customer': CUSTOMER_ID,
        'X-Signature': signature
    }


# ─── 설정 저장/불러오기 ──────────────────────────────────────

@app.route('/api/config', methods=['GET'])
def get_config():
    if not os.path.exists(CONFIG_FILE):
        return jsonify({})
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({})


@app.route('/api/config', methods=['POST'])
def save_config():
    data = request.json or {}
    existing = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update({k: v for k, v in data.items() if v})
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return jsonify({'success': True})


# ─── 키워드 조회 ───────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/session', methods=['GET'])
def get_session():
    return jsonify({'token': SESSION_TOKEN})


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    return jsonify({'error': f'서버 오류: {str(e)}', 'detail': traceback.format_exc()}), 500


@app.errorhandler(404)
def handle_404(e):
    return jsonify({'error': '요청한 경로를 찾을 수 없습니다.'}), 404


@app.route('/api/keywords', methods=['GET'])
def get_keywords():
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'error': '키워드를 입력해주세요.'}), 400

    uri = '/keywordstool'
    params = {
        'hintKeywords': keyword.replace(' ', ''),
        'showDetail': '1'
    }

    try:
        resp = requests.get(
            BASE_URL + uri,
            params=params,
            headers=get_headers('GET', uri),
            timeout=10
        )
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            return jsonify({'error': f'API 응답 파싱 오류 (HTTP {resp.status_code}): {resp.text[:200]}'}), 500

        results = []
        for item in data.get('keywordList', []):
            try:
                pc = item.get('monthlyPcQcCnt', 0)
                mobile = item.get('monthlyMobileQcCnt', 0)
                pc = 10 if pc == '< 10' else int(pc)
                mobile = 10 if mobile == '< 10' else int(mobile)
                results.append({
                    'keyword': item.get('relKeyword', ''),
                    'pc': pc,
                    'mobile': mobile,
                    'total': pc + mobile,
                    'competition': item.get('compIdx', '-'),
                    'pcCtr': item.get('monthlyAvePcCtr', 0),
                    'mobileCtr': item.get('monthlyAveMobileCtr', 0),
                })
            except (ValueError, TypeError):
                continue

        results.sort(key=lambda x: x['total'], reverse=True)
        return jsonify({'keywords': results})

    except requests.exceptions.HTTPError as e:
        try:
            err_json = e.response.json()
            msg = err_json.get('message') or err_json.get('error') or str(e)
        except Exception:
            msg = f'HTTP {e.response.status_code}: {e.response.text[:200]}'
        return jsonify({'error': f'네이버 API 오류: {msg}'}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({'error': '네이버 API 서버에 연결할 수 없습니다. 네트워크를 확인해주세요.'}), 503
    except requests.exceptions.Timeout:
        return jsonify({'error': '네이버 API 요청 시간이 초과되었습니다. 다시 시도해주세요.'}), 504
    except Exception as e:
        import traceback
        return jsonify({'error': f'키워드 조회 오류: {str(e)}', 'detail': traceback.format_exc()}), 500


# ─── 네이버 로그인 ───────────────────────────────────────────

@app.route('/api/naver/login', methods=['POST'])
def naver_login():
    return jsonify({'success': False, 'error': '유료버전입니다. 문의: jusingsing@naver.com'}), 402


@app.route('/api/naver/status', methods=['GET'])
def naver_status():
    return jsonify(naver_bot.get_login_status())


@app.route('/api/naver/logout', methods=['POST'])
def naver_logout():
    return jsonify(naver_bot.logout_naver())


# ─── AI 블로그 글 생성 ───────────────────────────────────────

@app.route('/api/blog/generate', methods=['POST'])
def blog_generate():
    return jsonify({'error': '유료버전입니다. 문의: jusingsing@naver.com'}), 402


# ─── 블로그 업로드 ───────────────────────────────────────────

@app.route('/api/blog/upload', methods=['POST'])
def blog_upload():
    return jsonify({'success': False, 'error': '유료버전입니다. 문의: jusingsing@naver.com'}), 402


@app.route('/api/blog/upload/status/<job_id>', methods=['GET'])
def upload_job_status(job_id):
    status = upload_status.get(job_id, {'status': 'not_found', 'message': '작업을 찾을 수 없습니다.'})
    return jsonify(status)


# ─── 지식인 질문 검색 ────────────────────────────────────────

def _jisikinn_title_filter(items, keyword):
    """제목에 검색어 첫 단어(또는 첫 글자)가 없는 항목 제거."""
    import re

    # 공백이 있으면 첫 단어, 없으면 첫 글자 사용
    parts = keyword.split()
    first_word = parts[0] if len(parts) > 1 else keyword[0]

    filtered = []
    for item in items:
        raw_title = item.get('title', '')
        title = re.sub(r'<[^>]+>', '', raw_title)
        if first_word in title:
            filtered.append(item)
    return filtered


@app.route('/api/jisikinn/search', methods=['POST'])
def jisikinn_search():
    data = request.json or {}
    keyword = data.get('keyword', '').strip()
    display = min(int(data.get('display', 20)), 100)
    start = max(1, int(data.get('start', 1)))

    if not keyword:
        return jsonify({'error': '키워드를 입력해주세요.'}), 400

    try:
        resp = requests.get(
            'https://openapi.naver.com/v1/search/kin.json',
            params={'query': keyword, 'display': display, 'sort': 'date', 'start': start},
            headers={
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
            },
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        items = result.get('items', [])
        filtered = _jisikinn_title_filter(items, keyword)
        return jsonify({
            'items': filtered,
            'total': result.get('total', 0),
            'fetched': len(items),
            'filtered_out': len(items) - len(filtered),
            'next_start': start + display
        })

    except requests.exceptions.HTTPError as e:
        try:
            msg = e.response.json().get('errorMessage', str(e))
        except Exception:
            msg = f'HTTP {e.response.status_code}'
        return jsonify({'error': f'네이버 API 오류: {msg}'}), 502
    except Exception as e:
        return jsonify({'error': f'검색 오류: {str(e)}'}), 500


# ─── 지식인 질문 전문 가져오기 ───────────────────────────────

@app.route('/api/jisikinn/fetch_question', methods=['POST'])
def fetch_question():
    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL을 입력해주세요.'}), 400

    result = naver_bot.fetch_question_content(url)
    if 'error' in result:
        return jsonify({'error': f'페이지 로딩 오류: {result["error"]}'}), 500
    if not result.get('title') and not result.get('body'):
        return jsonify({'error': '질문 내용을 가져올 수 없습니다.'}), 400
    return jsonify(result)


# ─── AI 지식인 답변 생성 ─────────────────────────────────────

@app.route('/api/jisikinn/generate', methods=['POST'])
def jisikinn_generate():
    return jsonify({'error': '유료버전입니다. 문의: jusingsing@naver.com'}), 402


# ─── OG 미리보기 ──────────────────────────────────────────────
@app.route('/api/og_preview', methods=['POST'])
def og_preview():
    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL을 입력해주세요.'}), 400
    try:
        import requests as req
        from bs4 import BeautifulSoup
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        r = req.get(url, headers=headers, timeout=8)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        def og(prop):
            tag = soup.find('meta', property=f'og:{prop}') or soup.find('meta', attrs={'name': f'og:{prop}'})
            return tag['content'].strip() if tag and tag.get('content') else ''

        image = og('image')
        title = og('title') or (soup.title.string.strip() if soup.title else '')
        description = og('description')

        return jsonify({'image': image, 'title': title, 'description': description})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── 지식인 업로드 ────────────────────────────────────────────

jisikinn_upload_status = {}


@app.route('/api/jisikinn/upload', methods=['POST'])
def jisikinn_upload():
    return jsonify({'success': False, 'error': '유료버전입니다. 문의: jusingsing@naver.com'}), 402


@app.route('/api/jisikinn/upload/status/<job_id>', methods=['GET'])
def jisikinn_upload_job_status(job_id):
    status = jisikinn_upload_status.get(job_id, {'status': 'not_found', 'message': '작업을 찾을 수 없습니다.'})
    return jsonify(status)


if __name__ == '__main__':
    import traceback

    log_path = os.path.join(os.path.expanduser('~'), 'NaverBlogTool_error.log')

    try:
        from waitress import serve

        def _open_browser():
            import urllib.request
            for _ in range(40):
                time.sleep(0.1)
                try:
                    urllib.request.urlopen('http://127.0.0.1:8080/', timeout=1)
                    webbrowser.open('http://localhost:8080')
                    return
                except Exception:
                    pass
        threading.Thread(target=_open_browser, daemon=True).start()

        serve(app, host='127.0.0.1', port=8080)

    except Exception:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(traceback.format_exc())
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, f'오류 발생\n\n로그 파일: {log_path}', 'NaverBlogTool 오류', 0x10)
