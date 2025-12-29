import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import os

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="위치 자동 보정 시스템", layout="wide")
st.title("🗺️ 강력한 자동 보정 경로 탐색")
st.write("바다에 뜨지 않도록 대한민국 내 모든 좌표계를 자동으로 대조하여 정확한 위치를 찾습니다.")

# 파일명 (수정 필요시 변경)
CSV_FILE_NAME = '20251229road_29최종.csv'

# -----------------------------------------------------------------------------
# 2. 상태 저장 (지도 유지용)
# -----------------------------------------------------------------------------
if 'map_view' not in st.session_state:
    st.session_state['map_view'] = False
if 's_place' not in st.session_state:
    st.session_state['s_place'] = None
if 'e_place' not in st.session_state:
    st.session_state['e_place'] = None

# -----------------------------------------------------------------------------
# 3. [핵심] 강력한 좌표 자동 변환 함수
# -----------------------------------------------------------------------------
# 대한민국에서 쓰이는 거의 모든 좌표계 리스트
crs_list = [
    "epsg:5179", # 도로명/네이버지도 (가장 흔함)
    "epsg:5174", # 구 지적도/다음지도 구버전
    "epsg:5181", # 카카오맵 (중부원점)
    "epsg:5186", # 공공데이터 (GRS80)
    "epsg:5187", # 동부원점
    "epsg:5178"  # K-1985
]

# 변환기들을 미리 딕셔너리로 준비
transformers = {crs: Transformer.from_crs(crs, "epsg:4326") for crs in crs_list}

def find_exact_korea_location(x, y):
    """
    입력된 x, y 숫자를 가능한 모든 좌표계와 순서(x,y / y,x)로 변환해보고
    '대한민국 영토' 안에 들어오는 정확한 값을 찾아냅니다.
    """
    for crs_name, transformer in transformers.items():
        # Case 1: (y, x) 순서 (pyproj 기본)
        try:
            lat, lon = transformer.transform(y, x)
            if 33.0 < lat < 38.9 and 124.5 < lon < 132.0:
                return lat, lon # 찾았다!
        except: pass

        # Case 2: (x, y) 순서 (데이터가 뒤집힌 경우)
        try:
            lat, lon = transformer.transform(x, y)
            if 33.0 < lat < 38.9 and 124.5 < lon < 132.0:
                return lat, lon # 찾았다!
        except: pass
            
    return None, None # 실패

# -----------------------------------------------------------------------------
# 4. 데이터 로드
# -----------------------------------------------------------------------------
@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        return pd.read_csv(file_path, encoding='cp949')
    except:
        return pd.read_csv(file_path, encoding='utf-8')

df = load_data(CSV_FILE_NAME)

if df is None:
    st.error(f"❌ '{CSV_FILE_NAME}' 파일을 찾을 수 없습니다.")
    st.stop()

# -----------------------------------------------------------------------------
# 5. 컬럼 자동 매핑 (설정창 없음)
# -----------------------------------------------------------------------------
cols = df.columns.tolist()

# 이름, X, Y 컬럼 추측
name_col = next((c for c in cols if '명' in c or '장소' in c), cols[0])
x_col = next((c for c in cols if 'X' in c or 'x' in c or '경도' in c), cols[1])
y_col = next((c for c in cols if 'Y' in c or 'y' in c or '위도' in c), cols[2])

# -----------------------------------------------------------------------------
# 6. UI 구성
# -----------------------------------------------------------------------------
st.divider()
c1, c2, c3 = st.columns([1, 1, 1])

with c1:
    in_start = st.selectbox("출발지", df[name_col].unique())
with c2:
    in_end = st.selectbox("도착지", df[name_col].unique())
with c3:
    st.write("") 
    st.write("") 
    if st.button("🚀 경로 탐색", use_container_width=True):
        st.session_state['map_view'] = True
        st.session_state['s_place'] = in_start
        st.session_state['e_place'] = in_end

# -----------------------------------------------------------------------------
# 7. 지도 출력 로직
# -----------------------------------------------------------------------------
if st.session_state['map_view']:
    try:
        s_val = st.session_state['s_place']
        e_val = st.session_state['e_place']

        s_row = df[df[name_col] == s_val].iloc[0]
        e_row = df[df[name_col] == e_val].iloc[0]

        # [자동 변환 실행]
        slat, slon = find_exact_korea_location(s_row[x_col], s_row[y_col])
        elat, elon = find_exact_korea_location(e_row[x_col], e_row[y_col])

        if slat is None or elat is None:
            st.error("⚠️ 좌표 변환 실패: 어떤 좌표계를 써도 한국 위치가 나오지 않습니다. 데이터 숫자를 확인해주세요.")
        else:
            # 중심점
            center_lat, center_lon = (slat + elat) / 2, (slon + elon) / 2
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

            # 마커 및 선
            folium.Marker([slat, slon], popup=f"출발: {s_val}", icon=folium.Icon(color="blue", icon="play")).add_to(m)
            folium.Marker([elat, elon], popup=f"도착: {e_val}", icon=folium.Icon(color="red", icon="stop")).add_to(m)
            folium.PolyLine([[slat, slon], [elat, elon]], color="blue", weight=5).add_to(m)

            st.success("✅ 위치 보정 완료! 정확한 지도 위치를 찾았습니다.")
            st_folium(m, width=800, height=500)
            
    except Exception as e:
        st.error(f"에러 발생: {e}")
