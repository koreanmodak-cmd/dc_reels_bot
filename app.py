import os
import requests
from bs4 import BeautifulSoup
import warnings
import time

warnings.filterwarnings("ignore")
import google.generativeai as genai

# ==========================================
# 1. 설정 (보안 환경변수 및 모델)
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
AVAILABLE_MODEL = 'gemini-3.8-flash'
model = genai.GenerativeModel(AVAILABLE_MODEL)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

# ==========================================
# 텔레그램 메세지 전송 함수
# ==========================================
def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레그램 토큰 또는 Chat ID가 설정되지 않았습니다.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload)
        if res.status_code != 200:
            # 마크다운 파싱 에러 시 일반 텍스트로 재시도
            payload.pop("parse_mode")
            requests.post(url, json=payload)
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 실패: {e}")

# ==========================================
# 2. 크롤링 함수 (오늘자 상위 4개 수집)
# ==========================================
def get_top_posts():
    print("🔄 디시인사이드 실시간 베스트 '오늘자' 데이터 수집 중...")
    all_posts = []
    page = 1
    max_pages = 5
    keep_going = True
    
    while keep_going and page <= max_pages:
        pc_url = f"https://gall.dcinside.com/board/lists/?id=dcbest&page={page}"
        try:
            res = requests.get(pc_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('tr.ub-content')
            if not rows:
                break
                
            for row in rows:
                num_td = row.select_one('td.gall_num')
                if num_td and num_td.text.strip() in ['설문', '공지', '뉴스']:
                    continue
                
                date_td = row.select_one('td.gall_date')
                if not date_td or ':' not in date_td.text.strip():
                    keep_going = False
                    continue
                
                title_a = row.select_one('td.gall_tit a')
                if not title_a or 'reply_numbox' in title_a.get('class', []):
                    continue
                    
                post_title = title_a.text.strip()
                href = title_a.get('href', '')
                if not href or 'javascript' in href:
                    continue
                
                link = "https://gall.dcinside.com" + href if href.startswith('/') else href
                
                reply_a = row.select_one('a.reply_numbox')
                reply_count = int(reply_a.text.strip().replace('[', '').replace(']', '')) if reply_a and reply_a.text.strip().replace('[', '').replace(']', '').isdigit() else 0
                
                views_td = row.select_one('td.gall_count')
                views_count = int(views_td.text.strip().replace(',', '')) if views_td and views_td.text.strip().replace(',', '').isdigit() else 0
                
                all_posts.append({
                    'title': post_title,
                    'link': link,
                    'views': views_count,
                    'replies': reply_count
                })
        except Exception:
            break
        page += 1
        time.sleep(1)
        
    if not all_posts:
        return []

    sorted_by_views = sorted(all_posts, key=lambda x: x['views'], reverse=True)
    top_views = sorted_by_views[:2]
    
    sorted_by_replies = sorted(all_posts, key=lambda x: x['replies'], reverse=True)
    top_replies = [p for p in sorted_by_replies if p not in top_views][:2]
            
    return top_views + top_replies

def get_post_content(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        content_element = soup.select_one('div.write_div') or soup.select_one('div.thum-txt') or soup.select_one('div.gallview_contents')
        if content_element:
            return content_element.text.strip()
    except Exception:
        pass
    return ""

def generate_reels_script(title, content, post_type=""):
    focus_point = "엄청난 조회수를 기록한 핫이슈입니다. 충격적이고 흥미롭게 쓰세요." if "조회수" in post_type else "논란과 토론이 뜨거운 글입니다. 시청자의 댓글 작성을 유도하세요."
    prompt = f"""
    당신은 인스타그램 릴스 조회수를 폭발시키는 전문 대본 작가입니다.
    아래 게시글을 바탕으로 60초 이내 릴스 대본을 작성해주세요.

    [제목]: {title}
    [내용]: {content}
    [포인트]: {focus_point}

    [작성 규칙]:
    1. 원문을 그대로 쓰지 말고 자극적이고 흥미로운 말투로 재창작하세요.
    2. 닉네임이나 개인정보는 삭제하세요.
    3. 첫 3초는 강렬한 후킹 문장으로 시작하세요.
    4. [효과음] 지시어 없이 AI 성우가 읽을 텍스트만 작성하세요.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 생성 오류: {e}"

# ==========================================
# 3. 메인 실행
# ==========================================
if __name__ == "__main__":
    top_posts = get_top_posts()
    
    if not top_posts:
        send_telegram_message("⚠️ 오늘자 디시인사이드 인기글을 찾지 못했습니다.")
        exit()
        
    start_msg = f"🔥 *[오늘자 최정예 릴스 대본 4개 도착]*\n총 {len(top_posts)}개의 대본 생성을 시작합니다.\n"
    send_telegram_message(start_msg)
    
    for index, post in enumerate(top_posts):
        post_type = "🔥 조회수 탑 랭커" if index < 2 else "💬 댓글 폭발 랭커"
        content = get_post_content(post['link'])
        
        if len(content) < 20:
            content = f"제목 '{post['title']}'을 기반으로 상상력을 발휘해 재미있는 썰을 풀어주세요."
            
        script = generate_reels_script(post['title'], content, post_type)
        
        telegram_text = (
            f"🎬 *[{index+1}/4] {post_type}*\n"
            f"*제목:* {post['title']}\n"
            f"📊 (조회수: {post['views']} | 댓글: {post['replies']})\n"
            f"🔗 [원문보기]({post['link']})\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{script}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(telegram_text)
        print(telegram_text)
        time.sleep(2)
        
    print("✅ 텔레그램 전송 완료!")