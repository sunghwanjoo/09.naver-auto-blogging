import time
import random
import pickle
import os
import pyperclip
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

def _data_dir():
    """쿠키 등 런타임 파일은 exe 옆에 저장 (frozen 여부 무관)"""
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

COOKIES_FILE = os.path.join(_data_dir(), 'naver_cookies.pkl')
LOGIN_INFO_FILE = os.path.join(_data_dir(), 'naver_login.pkl')


def rand_sleep(min_sec=0.3, max_sec=1.2):
    """랜덤 대기"""
    time.sleep(random.uniform(min_sec, max_sec))


def rand_paste(driver, text):
    """랜덤 방식으로 붙여넣기 (매번 다른 패턴)"""
    method = random.choice(['chunk', 'full', 'chunk'])  # chunk 비중 높임

    if method == 'full':
        # 한 번에 전체 붙여넣기
        pyperclip.copy(text)
        rand_sleep(0.2, 0.6)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        rand_sleep(0.5, 1.0)

    else:
        # 랜덤 크기 청크로 나눠서 붙여넣기
        lines = text.split('\n')
        # 랜덤하게 2~4줄씩 묶어서 붙여넣기
        i = 0
        while i < len(lines):
            chunk_size = random.randint(2, 5)
            chunk = '\n'.join(lines[i:i + chunk_size])
            pyperclip.copy(chunk)
            rand_sleep(0.1, 0.4)
            ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            rand_sleep(0.4, 1.1)
            i += chunk_size


def create_driver(headless=False):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def human_type(element, text):
    """사람처럼 랜덤 딜레이로 타이핑"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.03, 0.12))


def login_naver(naver_id, naver_pw):
    """네이버 로그인 후 쿠키 저장"""
    driver = create_driver(headless=False)
    try:
        driver.get('https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com')
        wait = WebDriverWait(driver, 15)

        # ID 입력
        id_input = wait.until(EC.presence_of_element_located((By.ID, 'id')))
        id_input.click()
        rand_sleep(0.2, 0.5)
        human_type(id_input, naver_id)
        rand_sleep(0.3, 0.7)

        # PW 입력
        pw_input = driver.find_element(By.ID, 'pw')
        pw_input.click()
        rand_sleep(0.2, 0.5)
        human_type(pw_input, naver_pw)
        rand_sleep(0.3, 0.7)

        # 로그인 클릭
        driver.find_element(By.ID, 'log.login').click()
        rand_sleep(3.5, 5.0)

        current_url = driver.current_url

        # 로그인 성공 여부 확인
        if 'nid.naver.com' in current_url and 'login' in current_url:
            driver.quit()
            return {'success': False, 'error': '로그인 실패. ID/PW를 확인하거나 캡차가 발생했을 수 있습니다.'}

        # 쿠키 저장
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'wb') as f:
            pickle.dump(cookies, f)

        # 로그인 정보 저장 (블로그 ID 확인용)
        blog_id = _get_blog_id(driver, naver_id)
        with open(LOGIN_INFO_FILE, 'wb') as f:
            pickle.dump({'naver_id': naver_id, 'blog_id': blog_id}, f)

        driver.quit()
        return {'success': True, 'naver_id': naver_id, 'blog_id': blog_id}

    except Exception as e:
        try:
            driver.quit()
        except:
            pass
        return {'success': False, 'error': str(e)}


def _get_blog_id(driver, naver_id):
    """블로그 ID 가져오기 - 네이버 ID와 블로그 ID는 동일"""
    try:
        driver.get(f'https://blog.naver.com/{naver_id}')
        time.sleep(2)
        url = driver.current_url
        # 정상 블로그 페이지면 URL에 naver_id 포함
        if naver_id.lower() in url.lower():
            return naver_id
    except:
        pass
    return naver_id  # fallback: 네이버 ID 그대로 사용


def get_login_status():
    """로그인 상태 확인"""
    if not os.path.exists(COOKIES_FILE) or not os.path.exists(LOGIN_INFO_FILE):
        return {'logged_in': False}
    try:
        with open(LOGIN_INFO_FILE, 'rb') as f:
            info = pickle.load(f)
        return {'logged_in': True, 'naver_id': info.get('naver_id'), 'blog_id': info.get('blog_id')}
    except:
        return {'logged_in': False}


def logout_naver():
    """로그아웃 (쿠키 삭제)"""
    for f in [COOKIES_FILE, LOGIN_INFO_FILE]:
        if os.path.exists(f):
            os.remove(f)
    return {'success': True}


def upload_draft(title, content):
    """블로그 임시저장 - 사람처럼 복사붙여넣기"""
    if not os.path.exists(COOKIES_FILE):
        return {'success': False, 'error': '로그인이 필요합니다.'}

    driver = create_driver(headless=False)
    try:
        # 쿠키 로드
        driver.get('https://www.naver.com')
        rand_sleep(0.8, 1.5)
        with open(COOKIES_FILE, 'rb') as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except:
                pass
        driver.refresh()
        rand_sleep(1.5, 2.5)

        # 블로그 글쓰기 페이지 이동
        driver.get('https://blog.naver.com/PostWriteForm.naver')
        rand_sleep(3.5, 5.5)

        wait = WebDriverWait(driver, 20)

        # ── 제목 입력 (랜덤 복붙) ──
        try:
            title_area = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div.se-title-input[contenteditable="true"]')
            ))
        except:
            title_area = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[placeholder="제목"], .se-title-input')
            ))

        title_area.click()
        rand_sleep(0.4, 0.9)
        pyperclip.copy(title)
        rand_sleep(0.2, 0.5)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        rand_sleep(0.6, 1.2)

        # ── 본문으로 이동 ──
        title_area.send_keys(Keys.TAB)
        rand_sleep(0.4, 0.8)

        try:
            content_area = driver.find_element(By.CSS_SELECTOR, 'div.se-main-container')
            content_area.click()
        except:
            pass
        rand_sleep(0.4, 0.9)

        # ── 본문 랜덤 붙여넣기 ──
        rand_paste(driver, content)

        # ── 임시저장 버튼 클릭 ──
        rand_sleep(0.8, 1.5)
        saved = False
        save_selectors = [
            '//button[contains(text(), "임시저장")]',
            '//button[contains(@class, "save")]',
            '//*[contains(text(), "임시저장")]',
        ]
        for selector in save_selectors:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                btn.click()
                saved = True
                break
            except:
                continue

        rand_sleep(1.5, 2.5)

        if not saved:
            return {'success': False, 'error': '임시저장 버튼을 찾지 못했습니다. 수동으로 저장해주세요.'}

        # 확인 팝업 처리
        try:
            confirm = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "확인")]'))
            )
            confirm.click()
        except:
            pass

        rand_sleep(1.5, 2.5)
        driver.quit()
        return {'success': True, 'message': '임시저장 완료!'}

    except Exception as e:
        try:
            driver.quit()
        except:
            pass
        return {'success': False, 'error': str(e)}


def upload_jisikinn_answer(question_url, answer):
    """지식인 질문에 답변 등록"""
    if not os.path.exists(COOKIES_FILE):
        return {'success': False, 'error': '로그인이 필요합니다.'}

    driver = create_driver(headless=False)
    try:
        # 쿠키 로드
        driver.get('https://www.naver.com')
        rand_sleep(0.8, 1.5)
        with open(COOKIES_FILE, 'rb') as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except:
                pass
        driver.refresh()
        rand_sleep(1.5, 2.5)

        # 지식인 질문 페이지 이동
        driver.get(question_url)
        rand_sleep(3.0, 5.0)

        wait = WebDriverWait(driver, 20)

        # 답변 입력 영역 찾기 (여러 셀렉터 시도)
        answer_area = None
        answer_selectors = [
            (By.CSS_SELECTOR, 'textarea.se-input-viewer'),
            (By.CSS_SELECTOR, '.answer_write_area textarea'),
            (By.CSS_SELECTOR, '#writeArea textarea'),
            (By.CSS_SELECTOR, 'textarea[placeholder*="답변"]'),
            (By.CSS_SELECTOR, '.kin-editor-holder'),
            (By.CSS_SELECTOR, 'div.se-content[contenteditable="true"]'),
        ]

        for by, selector in answer_selectors:
            try:
                answer_area = wait.until(EC.element_to_be_clickable((by, selector)))
                break
            except:
                continue

        if not answer_area:
            driver.quit()
            return {'success': False, 'error': '답변 입력창을 찾지 못했습니다. URL을 확인해주세요.'}

        answer_area.click()
        rand_sleep(0.5, 1.0)

        # 답변 붙여넣기
        rand_paste(driver, answer)
        rand_sleep(1.0, 2.0)

        # 등록 버튼 클릭
        submitted = False
        submit_selectors = [
            '//button[contains(text(), "답변등록")]',
            '//button[contains(text(), "등록")]',
            '//input[@value="답변등록"]',
            '//*[contains(@class, "btn_answer") and contains(text(), "등록")]',
        ]
        for selector in submit_selectors:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                btn.click()
                submitted = True
                break
            except:
                continue

        rand_sleep(2.0, 3.5)

        if not submitted:
            driver.quit()
            return {'success': False, 'error': '답변 등록 버튼을 찾지 못했습니다. 수동으로 등록해주세요.'}

        driver.quit()
        return {'success': True, 'message': '답변 등록 완료!'}

    except Exception as e:
        try:
            driver.quit()
        except:
            pass
        return {'success': False, 'error': str(e)}


def fetch_question_content(url):
    """지식인 질문 페이지에서 제목과 본문 전문을 가져옴 (모바일 requests)"""
    import re
    import requests as req
    from bs4 import BeautifulSoup

    try:
        # desktop URL에서 dirId, docId 추출 후 모바일 URL로 변환
        dir_id = re.search(r'dirId=(\d+)', url)
        doc_id = re.search(r'docId=(\d+)', url)
        if not dir_id or not doc_id:
            return {'error': 'URL에서 dirId/docId를 찾을 수 없습니다.'}

        mobile_url = f"https://m.kin.naver.com/mobile/qna/detail.nhn?dirId={dir_id.group(1)}&docId={doc_id.group(1)}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Referer': 'https://m.kin.naver.com/',
        }
        r = req.get(mobile_url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        title = ''
        body = ''

        # 제목: QnaEnd_contentArea 안의 첫 번째 의미있는 텍스트
        content_area = soup.find(class_=lambda c: c and any('contentArea' in x or 'titleArea' in x for x in c))
        if content_area:
            lines = [l.strip() for l in content_area.get_text('\n').split('\n') if l.strip()]
            skip = {'Q&A', 'NEW', 'NAVER', '지식iN', '지식인', 'eXpert', '홈', 'CHOiCE', '답변하기'}
            for line in lines:
                if len(line) > 5 and line not in skip:
                    title = line
                    break

        # 본문: [class*="questionDetail"] CSS 셀렉터
        detail = soup.select_one('[class*="questionDetail"]')
        if detail:
            body = detail.get_text(separator='\n', strip=True)

        # 제목 못 찾으면 <title> 태그 사용
        if not title:
            t = soup.find('title')
            if t:
                title = t.get_text(strip=True).replace('네이버 지식iN', '').strip()

        return {'title': title, 'body': body}

    except Exception as e:
        return {'error': str(e)}
