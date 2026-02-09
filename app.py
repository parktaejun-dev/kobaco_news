import streamlit as st
import pandas as pd
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import re
import time

# -----------------------------------------------------------------------------
# 1. UI/UX 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KOBACO 영업정책팀 모닝 브리핑",
    layout="wide",
    page_icon="📰"
)

# 헤더 섹션
st.title(f"KOBACO 영업정책팀 모닝 브리핑 📰")
st.markdown(f"**{datetime.now().strftime('%Y년 %m월 %d일')}** - 오늘도 힘찬 하루 되세요!")
st.divider()

# -----------------------------------------------------------------------------
# 2. 사이드바 설정 (설정 영역)
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 설정")

# 키워드 관리
default_keywords = "방송광고, 미디어렙법, 어드레서블 TV, OTT 광고, KAI 지수"
keywords_input = st.sidebar.text_area(
    "검색 키워드 (쉼표로 구분)",
    value=default_keywords,
    height=100
)
# 리스트로 변환 (공백 제거)
keywords = [k.strip() for k in keywords_input.split(',') if k.strip()]

# 수신자 리스트 연동 (구글 스프레드시트)
st.sidebar.subheader("📧 수신자 리스트")
sheet_url = st.sidebar.text_input(
    "구글 스프레드시트 URL",
    placeholder="https://docs.google.com/spreadsheets/d/..."
)

@st.cache_data(ttl=600)  # 데이터 캐싱 (10분)
def load_recipients(url):
    """
    구글 시트 URL을 받아 Pandas DataFrame으로 반환.
    URL이 없거나 에러 발생 시 더미 데이터를 반환.
    """
    dummy_data = pd.DataFrame({
        '이름': ['테스트유저'],
        '이메일': ['test@example.com']
    })

    if not url:
        return dummy_data, "URL 미입력 (테스트 모드)"

    try:
        # /edit... 부분을 /export?format=csv 로 변환
        csv_url = re.sub(r'/edit.*', '/export?format=csv', url)

        # 데이터 로드
        df = pd.read_csv(csv_url)

        # 필수 컬럼 확인
        if '이름' not in df.columns or '이메일' not in df.columns:
            return dummy_data, "컬럼명 오류 ('이름', '이메일' 필요)"

        return df, "로드 성공"
    except Exception as e:
        return dummy_data, f"로드 실패: {e}"

recipients_df, status_msg = load_recipients(sheet_url)

# 로드 상태 표시
if status_msg == "로드 성공":
    st.sidebar.success(f"수신자 {len(recipients_df)}명 로드 완료")
else:
    st.sidebar.warning(f"상태: {status_msg}")

with st.sidebar.expander("수신자 명단 미리보기"):
    st.dataframe(recipients_df)

# -----------------------------------------------------------------------------
# 3. 뉴스 수집 및 표시 (메인 화면)
# -----------------------------------------------------------------------------
def get_news(keyword):
    """
    구글 뉴스 RSS를 통해 키워드별 최신 기사 3개를 가져옴.
    """
    # URL 인코딩은 feedparser가 내부적으로 처리하거나, f-string으로 넣어도 대부분 동작하지만
    # 안전하게 urllib를 쓸 수도 있음. 여기선 f-string 사용.
    rss_url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)

    articles = []
    # 상위 3개만 추출
    for entry in feed.entries[:3]:
        articles.append({
            'title': entry.title,
            'link': entry.link,
            'published': entry.published,
            'summary': entry.get('summary', '') # 요약이 없을 수도 있음
        })
    return articles

# 이메일 본문 생성을 위한 저장소
email_content_html = f"<h2>📅 {datetime.now().strftime('%Y년 %m월 %d일')} 뉴스 브리핑</h2><hr>"

# 메인 화면 뉴스 카드 배치
if keywords:
    for kw in keywords:
        st.subheader(f"🔍 {kw}")
        articles = get_news(kw)

        # 이메일 본문에 섹션 추가
        email_content_html += f"<h3>[{kw}]</h3><ul>"

        if not articles:
            st.info("관련된 최신 기사가 없습니다.")
            email_content_html += "<li>기사 없음</li>"
        else:
            # 3단 컬럼 배치
            cols = st.columns(3)
            for idx, article in enumerate(articles):
                # 컬럼 인덱스 순환 (0, 1, 2)
                col = cols[idx % 3]

                with col:
                    # 카드 스타일링 (컨테이너 사용)
                    with st.container(border=True):
                        st.markdown(f"**{article['title']}**")
                        # 날짜 포맷팅 시도 (복잡하면 원본 문자열 사용)
                        st.caption(article['published'])
                        st.link_button("기사 보기", article['link'])

                # 이메일 본문에 기사 추가
                email_content_html += f"<li><a href='{article['link']}'><b>{article['title']}</b></a><br><small>{article['published']}</small></li>"

        email_content_html += "</ul><br>"
        st.markdown("---")
else:
    st.warning("키워드를 입력해주세요.")

# -----------------------------------------------------------------------------
# 4. 이메일 자동 발송 기능
# -----------------------------------------------------------------------------
st.header("📩 뉴스레터 발송")

with st.expander("발송 설정", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        sender_email = st.text_input("보내는 사람 구글 이메일", placeholder="example@gmail.com")
    with col2:
        sender_password = st.text_input("앱 비밀번호 (App Password)", type="password", help="구글 계정 설정 > 보안 > 앱 비밀번호에서 생성된 16자리 코드")

    send_btn = st.button("뉴스레터 일괄 발송 🚀", type="primary")

if send_btn:
    if not sender_email or not sender_password:
        st.error("이메일과 앱 비밀번호를 입력해주세요.")
    else:
        # 진행률 표시줄
        progress_bar = st.progress(0, text="발송 준비 중...")
        status_text = st.empty()

        try:
            # SMTP 서버 연결
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)

            total_recipients = len(recipients_df)

            for i, row in recipients_df.iterrows():
                recipient_name = row.get('이름', '구독자')
                recipient_email = row.get('이메일', '')

                if not recipient_email or '@' not in str(recipient_email):
                    continue

                # 메일 구성
                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = recipient_email
                msg['Subject'] = f"[KOBACO 브리핑] {datetime.now().strftime('%Y-%m-%d')} 뉴스레터"

                # 개인화된 인사말 + 뉴스 본문
                greeting = f"<p>안녕하세요, <b>{recipient_name}</b>님.<br>오늘의 주요 뉴스 브리핑입니다.</p><br>"
                full_body = greeting + email_content_html

                msg.attach(MIMEText(full_body, 'html'))

                # 발송
                server.sendmail(sender_email, recipient_email, msg.as_string())

                # 진행률 업데이트
                progress = (i + 1) / total_recipients
                progress_bar.progress(progress, text=f"{recipient_name}님에게 발송 중... ({i+1}/{total_recipients})")
                time.sleep(0.1) # 시각적 효과를 위한 짧은 대기

            server.quit()

            progress_bar.progress(1.0, text="발송 완료!")
            st.balloons()
            st.success(f"총 {total_recipients}명에게 뉴스레터를 성공적으로 발송했습니다.")

        except smtplib.SMTPAuthenticationError:
            st.error("로그인 실패! 이메일 주소나 앱 비밀번호를 확인해주세요.")
        except Exception as e:
            st.error(f"발송 중 오류 발생: {e}")
