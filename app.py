import streamlit as st
import pandas as pd
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
import re
import time
from time import mktime
from urllib.parse import quote_plus
import io

# -----------------------------------------------------------------------------
# 1. UI/UX 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KOBACO 영업정책팀 모닝 브리핑",
    layout="wide",
    page_icon="📰"
)

# 세션 상태 초기화
if 'news_data' not in st.session_state:
    st.session_state['news_data'] = []
if 'data_collected' not in st.session_state:
    st.session_state['data_collected'] = False

def get_news(keyword, start_date, end_date):
    """
    구글 뉴스 RSS를 통해 키워드별 기사를 가져오고 날짜로 필터링함.
    """
    encoded_keyword = quote_plus(keyword.strip())
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)

    articles = []
    # 상위 30개 추출 (필터링을 위해 범위를 늘림)
    for entry in feed.entries[:30]:
        try:
            # RSS 날짜 파싱 (struct_time -> date)
            pub_date = datetime.fromtimestamp(mktime(entry.published_parsed)).date()
        except (AttributeError, TypeError):
            continue

        # 날짜 필터링
        if start_date <= pub_date <= end_date:
            articles.append({
                'keyword': keyword,
                'title': entry.title,
                'link': entry.link,
                'published': entry.published,
                'pub_date': pub_date,
                'summary': entry.get('summary', '')
            })
    return articles

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

# -----------------------------------------------------------------------------
# 수집 설정 (날짜 및 버튼)
# -----------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("📅 수집 기간 설정")

col_date1, col_date2 = st.sidebar.columns(2)
with col_date1:
    start_date = st.sidebar.date_input("시작일", value=datetime.now().date())
with col_date2:
    end_date = st.sidebar.date_input("종료일", value=datetime.now().date())

col_btn1, col_btn2 = st.sidebar.columns(2)
with col_btn1:
    collect_btn = st.sidebar.button("뉴스 수집 시작", type="primary")
with col_btn2:
    clear_btn = st.sidebar.button("데이터 초기화")

# 데이터 초기화 로직
if clear_btn:
    st.session_state['news_data'] = []
    st.session_state['data_collected'] = False
    st.rerun()

# 뉴스 수집 로직
if collect_btn:
    st.session_state['news_data'] = []  # 기존 데이터 초기화
    st.session_state['data_collected'] = True

    if not keywords:
        st.sidebar.error("키워드를 입력해주세요.")
    else:
        status_text = st.sidebar.empty()
        status_text.text("수집 시작...")

        all_articles = []
        progress_bar = st.sidebar.progress(0)

        for i, kw in enumerate(keywords):
            status_text.text(f"'{kw}' 수집 중...")
            items = get_news(kw, start_date, end_date)
            all_articles.extend(items)
            progress_bar.progress((i + 1) / len(keywords))

        st.session_state['news_data'] = all_articles
        status_text.text("수집 완료!")
        progress_bar.empty()
        st.rerun()

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

# 이메일 본문 생성을 위한 저장소
email_content_html = f"<h2>📅 {datetime.now().strftime('%Y년 %m월 %d일')} 뉴스 브리핑</h2><hr>"

# 메인 화면 뉴스 카드 배치
if not st.session_state['data_collected']:
    st.info("좌측 사이드바에서 '뉴스 수집 시작' 버튼을 눌러주세요.")
else:
    if not keywords:
        st.warning("키워드를 입력해주세요.")
    else:
        # ---------------------------------------------------------------------
        # 데이터 다운로드 (엑셀 / 마크다운)
        # ---------------------------------------------------------------------
        if st.session_state['news_data']:
            df = pd.DataFrame(st.session_state['news_data'])
            # 필요한 컬럼만 선택 및 정렬
            cols_to_export = ['keyword', 'title', 'pub_date', 'link', 'summary']
            # 컬럼이 존재하는지 확인 (안전장치)
            cols_to_export = [c for c in cols_to_export if c in df.columns]
            df_export = df[cols_to_export]

            col_dl1, col_dl2 = st.columns(2)

            # 1. 엑셀 다운로드
            with col_dl1:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False)

                st.download_button(
                    label="📥 엑셀 다운로드",
                    data=buffer.getvalue(),
                    file_name=f"news_briefing_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # 2. 마크다운 다운로드
            with col_dl2:
                md_text = f"# 📅 {datetime.now().strftime('%Y년 %m월 %d일')} 뉴스 브리핑\n\n"
                for kw in keywords:
                    kw_articles = [item for item in st.session_state['news_data'] if item['keyword'] == kw]
                    md_text += f"## 🔍 {kw}\n\n"
                    if not kw_articles:
                        md_text += "- 기사 없음\n"
                    else:
                        for article in kw_articles:
                            md_text += f"- **[{article['title']}]({article['link']})** ({article['pub_date']})\n"
                    md_text += "\n---\n\n"

                st.download_button(
                    label="📥 마크다운 다운로드",
                    data=md_text,
                    file_name=f"news_briefing_{datetime.now().strftime('%Y%m%d')}.md",
                    mime="text/markdown"
                )

            st.divider()

        for kw in keywords:
            st.subheader(f"🔍 {kw}")

            # 현재 키워드에 해당하는 기사 필터링
            articles = [item for item in st.session_state['news_data'] if item['keyword'] == kw]

            # 이메일 본문에 섹션 추가
            email_content_html += f"<h3>[{kw}]</h3><ul>"

            if not articles:
                st.info("설정된 기간 내 관련된 기사가 없습니다.")
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
