import sys
import os

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
import anthropic
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
    data = request.json or {}
    naver_id = data.get('naver_id', '').strip()
    naver_pw = data.get('naver_pw', '').strip()
    if not naver_id or not naver_pw:
        return jsonify({'success': False, 'error': 'ID와 비밀번호를 입력해주세요.'}), 400

    try:
        result = naver_bot.login_naver(naver_id, naver_pw)
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'detail': traceback.format_exc()}), 500


@app.route('/api/naver/status', methods=['GET'])
def naver_status():
    return jsonify(naver_bot.get_login_status())


@app.route('/api/naver/logout', methods=['POST'])
def naver_logout():
    return jsonify(naver_bot.logout_naver())


# ─── AI 블로그 글 생성 ───────────────────────────────────────

@app.route('/api/blog/generate', methods=['POST'])
def blog_generate():
    data = request.json or {}
    topic = data.get('topic', '').strip()
    keywords = data.get('keywords', '').strip()
    api_key = data.get('api_key', '').strip()
    style = data.get('style', '정보성')

    if not api_key:
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                api_key = json.load(f).get('claude_api_key', '').strip()
        except Exception:
            pass

    if not topic:
        return jsonify({'error': '주제를 입력해주세요.'}), 400
    if not api_key:
        return jsonify({'error': 'Claude API 키를 입력해주세요.'}), 400

    prompt = f"""네이버 블로그 글을 작성해주세요.

주제: {topic}
{"포함 키워드: " + keywords if keywords else ""}
글 스타일: {style}

작성 조건:
- 블로그 제목 1개 (매력적이고 검색에 유리한 제목)
- 본문은 1500~2000자 내외
- 소제목을 2~3개 사용해서 구조화
- 네이버 블로그 독자 친화적인 구어체
- 마지막에 자연스러운 마무리 문장

출력 형식:
[제목]
(제목 내용)

[본문]
(본문 내용)"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2048,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = message.content[0].text

        # 제목과 본문 분리
        title = ''
        body = raw
        if '[제목]' in raw and '[본문]' in raw:
            parts = raw.split('[본문]')
            body = parts[1].strip()
            title_part = parts[0].split('[제목]')
            if len(title_part) > 1:
                title = title_part[1].strip()
        elif '\n' in raw:
            lines = raw.strip().split('\n')
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()

        return jsonify({'success': True, 'title': title, 'body': body})

    except anthropic.AuthenticationError:
        return jsonify({'error': 'API 키가 올바르지 않습니다.'}), 401
    except Exception as e:
        return jsonify({'error': f'생성 오류: {str(e)}'}), 500


# ─── 블로그 업로드 ───────────────────────────────────────────

@app.route('/api/blog/upload', methods=['POST'])
def blog_upload():
    data = request.json or {}
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not title or not content:
        return jsonify({'success': False, 'error': '제목과 본문을 입력해주세요.'}), 400

    job_id = str(int(time.time()))
    upload_status[job_id] = {'status': 'running', 'message': '업로드 중...'}

    def run_upload():
        result = naver_bot.upload_draft(title, content)
        upload_status[job_id] = {
            'status': 'done' if result['success'] else 'error',
            'message': result.get('message') or result.get('error', '알 수 없는 오류')
        }

    thread = threading.Thread(target=run_upload)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'job_id': job_id})


@app.route('/api/blog/upload/status/<job_id>', methods=['GET'])
def upload_job_status(job_id):
    status = upload_status.get(job_id, {'status': 'not_found', 'message': '작업을 찾을 수 없습니다.'})
    return jsonify(status)


# ─── 지식인 질문 검색 ────────────────────────────────────────

@app.route('/api/jisikinn/search', methods=['POST'])
def jisikinn_search():
    data = request.json or {}
    keyword = data.get('keyword', '').strip()
    display = min(int(data.get('display', 20)), 100)

    if not keyword:
        return jsonify({'error': '키워드를 입력해주세요.'}), 400

    try:
        resp = requests.get(
            'https://openapi.naver.com/v1/search/kin.json',
            params={'query': keyword, 'display': display, 'sort': 'date'},
            headers={
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
            },
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        return jsonify({'items': result.get('items', []), 'total': result.get('total', 0)})

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
    data = request.json or {}
    question = data.get('question', '').strip()
    api_key = data.get('api_key', '').strip()
    answer_type = data.get('answer_type', 'blog')
    link = data.get('link', '').strip()

    if not api_key:
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                api_key = json.load(f).get('claude_api_key', '').strip()
        except Exception:
            pass

    if not question:
        return jsonify({'error': '질문 내용을 입력해주세요.'}), 400
    if not api_key:
        return jsonify({'error': 'Claude API 키를 입력해주세요.'}), 400
    if not link:
        return jsonify({'error': '링크를 입력해주세요.'}), 400

    if answer_type == 'blog':
        prompt = f"""너는 네이버 지식인에서 성실하게 답변하는 블로거야.
아래 질문에 답변을 작성해줘.

질문: {question}

[답변 전략]
1. 질문자의 상황에 먼저 공감하는 한 줄로 시작
2. 핵심 정보를 성실하게 제공 (300~400자)
3. 마지막에 자연스럽게 블로그 링크 삽입
   - 링크 앞 문장은 "더 자세한 내용은 제가 직접 정리해둔 글이 있으니 참고하세요 :)"처럼 부드럽게
   - 링크: {link}

[주의사항]
- 광고처럼 보이면 절대 안 됨
- 링크는 답변의 보너스처럼 자연스럽게
- 구어체, 친근한 말투
- 이모티콘(이모지) 절대 사용 금지
- ** 같은 마크다운 기호 절대 사용 금지
- 답변 본문만 출력 (제목, 설명 없이)"""

    else:
        prompt = f"""너는 네이버 지식인에서 제품을 직접 써본 경험자로서 답변하는 사람이야.
아래 질문에 답변을 작성해줘.

질문: {question}

[답변 전략]
1. 질문자의 고민에 공감하는 한 줄로 시작
2. 제품 고를 때 봐야 할 기준을 성실하게 설명 (200~300자)
3. 자연스럽게 "저도 이거 쓰는데" 식으로 경험담 연결
4. 구매 링크를 편의 제공 느낌으로 삽입
   - 예: "혹시 필요하시면 제가 쓰는 거 링크 남겨드릴게요"
   - 링크: {link}

[주의사항]
- 절대 광고처럼 보이면 안 됨
- 제품명 직접 언급보다 경험담 위주로
- 구어체, 친근한 말투
- 이모티콘(이모지) 절대 사용 금지
- ** 같은 마크다운 기호 절대 사용 금지
- 답변 본문만 출력 (제목, 설명 없이)"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': prompt}]
        )
        answer = message.content[0].text.strip()
        return jsonify({'success': True, 'answer': answer})

    except anthropic.AuthenticationError:
        return jsonify({'error': 'API 키가 올바르지 않습니다.'}), 401
    except Exception as e:
        return jsonify({'error': f'생성 오류: {str(e)}'}), 500


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
    data = request.json or {}
    question_url = data.get('question_url', '').strip()
    answer = data.get('answer', '').strip()

    if not question_url or not answer:
        return jsonify({'success': False, 'error': '질문 URL과 답변 내용을 입력해주세요.'}), 400

    job_id = str(int(time.time()))
    jisikinn_upload_status[job_id] = {'status': 'running', 'message': '답변 등록 중...'}

    def run_upload():
        result = naver_bot.upload_jisikinn_answer(question_url, answer)
        jisikinn_upload_status[job_id] = {
            'status': 'done' if result['success'] else 'error',
            'message': result.get('message') or result.get('error', '알 수 없는 오류')
        }

    thread = threading.Thread(target=run_upload)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'job_id': job_id})


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
