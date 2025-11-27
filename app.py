import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import re

REQUIRED_PREFIX = "https://gf2-h5.haoplay.com/der-strandurlaub/kr/share?invite_token="


# =========================
# 기본 설정
# =========================
DB_PATH = "comments.db"
RESET_SECONDS = 300  # 5분 = 300초

st.set_page_config(page_title="소녀전선2 망명 이벤트 공유", page_icon="💬")
st.title("센타우레이시 스킨 이벤트 (DB 버전)")
st.write(f"아카라이브 소녀전선2:망명채널 / 문제발생시 @Caleo01 호출")

# =========================
# DB 관련 함수
# =========================
@st.cache_resource
def get_connection():
    """SQLite 연결 + 테이블 초기화 (앱 전체에서 1번만 실행)"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # 댓글 테이블
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    # 메타 정보 테이블 (여기에 cycle_start 저장)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )

    conn.commit()
    return conn


def get_cycle_start(conn) -> datetime:
    """5분 주기 시작 시간(cycle_start)을 가져오거나, 없으면 지금으로 생성"""
    cur = conn.cursor()
    cur.execute("SELECT value FROM meta WHERE key = 'cycle_start';")
    row = cur.fetchone()

    if row is None:
        now = datetime.utcnow()
        cur.execute(
            "INSERT INTO meta (key, value) VALUES ('cycle_start', ?);",
            (now.isoformat(),),
        )
        conn.commit()
        return now

    return datetime.fromisoformat(row["value"])


def reset_comments_if_needed(conn):
    """
    5분이 지났으면 댓글 전체 삭제 후 cycle_start를 갱신.
    반환값:
        cycle_start (datetime), elapsed_seconds (float), reset_happened (bool)
    """
    cur = conn.cursor()
    cycle_start = get_cycle_start(conn)
    now = datetime.utcnow()
    elapsed = (now - cycle_start).total_seconds()

    if elapsed >= RESET_SECONDS:
        # 댓글 전체 삭제
        cur.execute("DELETE FROM comments;")
        # cycle_start 현재 시간으로 갱신
        cur.execute(
            "UPDATE meta SET value = ? WHERE key = 'cycle_start';",
            (now.isoformat(),),
        )
        conn.commit()
        return now, elapsed, True

    return cycle_start, elapsed, False


def add_comment(conn, username: str, content: str):
    """DB에 댓글 추가"""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO comments (username, content, created_at)
        VALUES (?, ?, ?);
        """,
        (username, content, datetime.utcnow().isoformat()),
    )
    conn.commit()


def get_comments(conn):
    """최근 댓글 목록 가져오기 (최신 순 정렬)"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, username, content, created_at
        FROM comments
        ORDER BY id DESC;
        """
    )
    return cur.fetchall()

def get_all_urls(conn):
    """DB에 있는 모든 댓글에서 URL들을 추출해 set으로 반환"""
    cur = conn.cursor()
    cur.execute("SELECT content FROM comments;")
    rows = cur.fetchall()

    all_urls = set()
    for row in rows:
        content = row["content"]
        urls = extract_urls(content)
        all_urls.update(urls)
    return all_urls

# =========================
# 유틸 함수 (링크 처리 등)
# =========================
def linkify(text: str) -> str:
    """
    댓글 내용에서 http:// 또는 https:// 로 시작하는 URL을 찾아
    [url](url) 형태의 마크다운 링크로 변환.
    """
    url_pattern = re.compile(r'(https?://[^\s]+)')

    def _repl(match):
        url = match.group(1)
        return f"[{url}]({url})"

    return url_pattern.sub(_repl, text)


def format_time_str(iso_str: str) -> str:
    """
    ISO 형식 시간 문자열(UTC 기준)을 HH:MM:SS 로 표시.
    (단순히 형식만 맞춰주고, 타임존 변환까지는 하지 않음)
    """
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime("%H:%M:%S")

def extract_urls(text: str):
    """
    텍스트에서 http:// 또는 https:// 로 시작하는 URL들을 모두 추출해서
    중복 제거 후 리스트로 반환
    """
    url_pattern = re.compile(r'(https?://[^\s]+)')
    return list(set(url_pattern.findall(text)))

# =========================
# 메인 로직
# =========================
conn = get_connection()

# 5분 지났으면 자동 초기화
cycle_start, elapsed, reset_happened = reset_comments_if_needed(conn)

if reset_happened:
    st.info("⏱ 5분이 지나서 댓글이 자동으로 초기화되었습니다.")

# 남은 시간 표시
remaining = int(RESET_SECONDS - elapsed)
if remaining < 0:
    remaining = 0
m, s = divmod(remaining, 60)
st.write(f"다음 전체 초기화까지 남은 시간: **{m}분 {s}초**")

st.caption("※ 이 페이지를 여는 모든 사용자가 같은 댓글판을 공유합니다.")

st.markdown("---")

# =========================
# 댓글 작성 폼
# =========================
st.subheader("댓글 작성")

with st.form("comment_form", clear_on_submit=True):
    username = st.text_input("닉네임", placeholder="닉네임을 입력하세요 (비워두면 '익명')")
    content = st.text_area(
        "댓글 내용",
        placeholder=(
            "댓글을 입력하세요.\n"
            "반드시 아래 형식의 링크 중 하나 이상을 포함해야 합니다.\n"
            "예) https://gf2-h5.haoplay.com/der-strandurlaub/kr/share?invite_token=XXXX"
        ),
    )
    submitted = st.form_submit_button("등록")

    if submitted:
        if not content.strip():
            st.warning("댓글 내용을 입력해주세요!")
        else:
            # 1️⃣ 새 댓글에서 URL 추출
            new_urls = extract_urls(content)

            # 2️⃣ 그 중에서 우리가 원하는 초대 링크만 필터링
            gf_links = [u for u in new_urls if u.startswith(REQUIRED_PREFIX)]

            # 3️⃣ 필수 링크(해당 prefix)가 하나도 없으면 에러
            if not gf_links:
                st.error(
                    "잘못된 초대 링크 입니다"
                )
            else:
                # 🔹 이미 사용된 초대 링크(동일 URL) 재사용 금지하고 싶다면:
                #    DB에서 모든 URL을 가져와서, 이번에 입력한 gf_links와 비교
                existing_urls = get_all_urls(conn)
                duplicated = [u for u in gf_links if u in existing_urls]

                if duplicated:
                    st.error(
                        "이미 다른 댓글에서 사용된 초대 링크는 다시 사용할 수 없습니다.\n\n"
                        + "\n".join(f"- {u}" for u in duplicated)
                    )
                else:
                    # 4️⃣ 여기까지 통과하면 댓글 등록
                    if not username.strip():
                        username = "익명"
                    add_comment(conn, username.strip(), content.strip())
                    st.success("댓글이 등록되었습니다!")

st.markdown("---")

# =========================
# 댓글 목록 표시
# =========================
st.subheader("댓글 목록 (모든 사용자 공용)")

rows = get_comments(conn)

if not rows:
    st.write("아직 댓글이 없습니다. 첫 댓글을 남겨보세요")
else:
    for row in rows:
        username = row["username"]
        content = row["content"]
        created_at_iso = row["created_at"]
        time_str = format_time_str(created_at_iso)

        # 링크 자동 변환
        content_with_links = linkify(content)

        st.markdown(
            f"""
**{username}** · *{time_str}*  

> {content_with_links}
            """,
            unsafe_allow_html=False,
        )
        st.markdown("---")
