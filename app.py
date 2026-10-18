import os
import requests
from bs4 import BeautifulSoup
import warnings
import time

warnings.filterwarnings("ignore")
import google.generativeai as genai

# ==========================================
# 1. 설정
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or "본인의_GEMINI_API_KEY"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "본인의_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "본인의_TELEGRAM_CHAT_ID"

genai.configure(api_key=GEMINI_API_KEY)
AVAILABLE_MODEL = 'gemini-3.8-flash'
model = genai.GenerativeModel(AVAILABLE_MODEL)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

# ==========================================
# [요구사항 5] 텔레그램 /on, /off 상태 확인
# ==========================================
def check_bot_status():
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN.startswith("본인"):
        return True
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        res = requests.get(url, timeout=10).json()
        
        if res.get("ok") and res.get("result"):
            # 가장 최근에 보낸 명령어부터 거꾸로 확인
            for update in reversed(res["result"]):
                msg = update.get("message", {})
                if str(msg.get("chat", {}).get("id")) == str(TELEGRAM_CHAT_ID):
                    text = msg.get("text", "").strip().lower()
                    if text == "/off":
                        print("⏸️ [상태] 사용자가 /off를 입력했습니다. 오늘 자동화를 건너뜁니다.")
                        return False
                    elif text == "/on":
                        print("▶️ [상태] 사용자가 /on을 입력했습니다. 자동화를 시작합니다.")
                        return True
    except Exception as e:
        print(f"상태 확인 중 에러: {e}")
        
    return True # 기본값은 무조건 ON

# ==========================================
# 텔레그램 메세지 전송 함수
# ==========================================
def send_telegram_message(text, use_markdown=True):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    
    if use_markdown:
        payload["parse_mode"] = "Markdown"
        
    try:
        res = requests.post(url, json=payload, timeout=10)
        # 마크다운 에러 시 텍스트로 재시도
        if res.status_code != 200 and use_markdown:
            payload.pop("parse_mode")
            requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

# ==========================================
# 2. 크롤링 함수 ([요구사항 1] 오늘 날짜만 엄격하게 수집)
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
                
                # 날짜에 ':'(시간)이 없으면 어제 글이므로 즉시 크롤링 전체 중단
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

# ==========================================
# 3. AI 대본 생성 ([요구사항 3, 4] 프롬프트 최적화 & 페르소나 부여)
# ==========================================
def generate_reels_script(title, content, post_type=""):
    prompt = f"""
    당신은 도파민 중독자들을 홀리는 100만 유튜버이자 쇼츠/릴스 전문 대본 작가입니다.
    아래 커뮤니티 글을 바탕으로 Vrew 같은 영상 제작 AI에 바로 붙여넣을 수 있는 [대본 세트]를 만드세요.

    [원문 제목]: {title}
    [원문 내용]: {content}

    [대본 작성 절대 규칙]:
    1. 말투: 친절함은 버리세요. 친한 동네 형/오빠가 어이없는 썰을 풀어주듯, 찰지고 트렌디하게 팩트폭행을 날리세요. (예: "야, 니들 이거 봤냐?", "와 이건 진짜 선넘었지;")
    2. 엔딩: 지루하게 질문으로 끝내지 마세요. 시청자가 벙찌는 반전 결말, 혹은 강렬한 한 줄 평으로 킹받게 마무리하세요.
    3. 구조: Vrew에 바로 붙여넣기 좋게, 상단에 '이미지 프롬프트'를 적고 하단에 '나레이션'만 순수하게 적어주세요.

    [출력 양식] (반드시 이 양식을 지켜주세요. 복사해서 바로 쓸 겁니다)

    [영상 프롬프트: 어두운 방, 충격받은 표정의 사람 등 영상 배경에 들어갈 키워드 1~2줄]

    (여기서부터 나레이션 대본)
    야 릴스 넘기지 마봐. 오늘 진짜 어이없는 거 보여줄게. ...
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 생성 오류: {e}"

# ==========================================
# 4. 메인 실행 ([요구사항 2] 텔레그램 메시지 구조 단순화)
# ==========================================
if __name__ == "__main__":
    # 상태 체크 로직 실행 (/off 시 즉시 종료)
    if not check_bot_status():
        send_telegram_message("⏸️ 봇이 오프 모드입니다. 오늘자 대본 생성을 건너뜁니다.")
        exit()

    top_posts = get_top_posts()
    
    if not top_posts:
        send_telegram_message("⚠️ 오늘자 디시인사이드 인기글을 찾지 못했습니다.")
        exit()
        
    # [1] 첫 번째 메시지: 오늘자 요약 정보만 전송
    summary_msg = f"🔥 *[오늘자 최정예 릴스 요약]*\n\n"
    for i, p in enumerate(top_posts):
        summary_msg += f"{i+1}. [{p['title']}]({p['link']})\n(👀조회: {p['views']} | 💬댓글: {p['replies']})\n\n"
    summary_msg += "👇 아래에서 원하는 대본을 꾹 눌러 복사하세요 👇"
    
    send_telegram_message(summary_msg, use_markdown=True)
    time.sleep(2)
    
    # [2] 이어지는 네 메시지: 오직 '대본'만 1개씩 전송
    for index, post in enumerate(top_posts):
        post_type = "🔥 조회수 탑 랭커" if index < 2 else "💬 댓글 폭발 랭커"
        content = get_post_content(post['link'])
        
        if len(content) < 20:
            content = f"제목 '{post['title']}'을 기반으로 상상력을 발휘해 재미있는 썰을 풀어주세요."
            
        script = generate_reels_script(post['title'], content, post_type)
        
        # 제목이나 장식 없이 순수 생성된 대본만 전송 (복사하기 쉽도록 마크다운 미적용)
        send_telegram_message(script, use_markdown=False)
        time.sleep(3)
        
    print("\n✅ 오늘자 최정예 릴스 대본 4개 전송 완료!")
