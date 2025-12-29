import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import os

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="대한민국 도로 경로 탐색", layout="wide")
st.title("🇰🇷 대한민국 도로 경로 탐색 시스템")

# 깃허브 리포지토리 내 파일명
CSV_FILE_NAME = '20251229road_29최종.csv'

# -----------------------------------------------------------------------------
# 2. Session State 초기화 (지도가 사라지지 않게 유지)
# -----------------------------------------------------------------------------
if 'map_view' not in st.session_state:
    st.session_state['map_view'] = False
if 's_place' not in st.session_state:
    st.session_state['s_place'] = None
if 'e_place' not in st.session_state:
    st.session_state['e_place'] = None

# -----------------------------------------------------------------------------
# 3. 데이터 로드 함수
# -----------------------------------------------------------------------------
@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_csv(file_path, encoding='cp949')
    except:
        df = pd.read_csv(file_path, encoding='utf-8')
    return df

df = load_data(CSV_FILE_NAME)

if df is None:
    st.error(f"❌ '{CSV_FILE_NAME}' 파일을 찾을 수 없습니다. 파일명을 확인해주세요.")
    st.stop()

# -----------------------------------------------------------------------------
# 4. 사이드바 설정 (좌표계 선택 기능 추가)
# -----------------------------------------------------------------------------
st.sidebar.header("🔧 설정 (좌표 보정)")

st.sidebar.write("### 1. 좌표계 선택 (중요)")
st.sidebar.info("지도가 엉뚱한 곳(바다/해외)에 뜬다면 아래 옵션을 바꿔보세요.")

# 대한민국 주요 좌표계 리스트
crs_options = {
    "EPSG:5179 (도로명/네이버지도/GRS80)": "epsg:5179",
    "EPSG:5174 (구 지적도/Bessel/중부원점)": "epsg:5174",
    "EPSG:5186 (GRS80/중부원점)": "epsg:5186",
    "EPSG:5181 (카카오맵/중부원점)": "epsg:5181"
}

selected_crs_name = st.sidebar.selectbox("좌표계 선택", list(crs_options.keys()), index=1) 
# index=1 (5174)를 기본값으로 설정해봅니다. (5179가 아니었으므로)
target_crs = crs_options[selected_crs_name]

# 좌표 변환기 생성
try:
    transformer = Transformer.from_crs(target_crs, "epsg:4326")
except Exception as e:
    st.error(f"좌표계 설정 오류: {e}")
    st.stop()

st.sidebar.write("### 2. 데이터 컬럼 매핑")
columns = df.columns.tolist()

# 컬럼 자동 찾기
default_name_idx = next((i for i, c in enumerate(columns) if '명' in c or '장소' in c), 0)
default_x_idx = next((i for i, c in enumerate(columns) if 'X' in c or 'x' in c or '경도' in c), 1)
default_y_idx = next((i for i, c in enumerate(columns) if 'Y' in c or 'y' in c or '위도' in c), 2)

name_col = st.sidebar.selectbox("장소명 컬럼", columns, index=default_name_idx)
x_col = st.sidebar.selectbox("X좌표 컬럼", columns, index=default_x_idx)
y_col = st.sidebar.selectbox("Y좌표 컬럼", columns, index=default_y_idx)

# X, Y 뒤집기 옵션 (가끔 데이터가 반대로 된 경우가 있음)
swap_xy = st.sidebar.checkbox("X와 Y 좌표 서로 바꾸기 (위치가 이상하면 체크)", value=False)

# -----------------------------------------------------------------------------
# 5. 좌표 변환 함수
# -----------------------------------------------------------------------------
def get_lat_lon(x, y):
    try:
        # X, Y 뒤집기 체크 시 순서 변경
        if swap_xy:
            input_x, input_y = y, x
        else:
            input_x, input_y = x, y
            
        # pyproj는 보통 (y, x) 순서로 넣어야 (lat, lon)이 나옵니다.
        # 좌표계에 따라 (x, y)로 넣어야 하는 경우도 있어, 지도가 이상하면 이 순서가 문제일 수 있습니다.
        lat, lon = transformer.transform(input_y, input_x)
        return lat, lon
    except:
        return None, None

# -----------------------------------------------------------------------------
# 6. 메인 화면 UI
# -----------------------------------------------------------------------------
st.divider()
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    input_start = st.selectbox("출발지 선택", df[name_col].unique())
with col2:
    input_end = st.selectbox("도착지 선택", df[name_col].unique())
with col3:
    st.write("") 
    st.write("") 
    if st.button("🚀 대한민국 경로 탐색", use_container_width=True):
        st.session_state['map_view'] = True
        st.session_state['s_place'] = input_start
        st.session_state['e_place'] = input_end

# -----------------------------------------------------------------------------
# 7. 지도 시각화
# -----------------------------------------------------------------------------
if st.session_state['map_view']:
    s_place = st.session_state['s_place']
    e_place = st.session_state['e_place']
    
    # 데이터 추출
    try:
        s_row = df[df[name_col] == s_place].iloc[0]
        e_row = df[df[name_col] == e_place].iloc[0]
        
        # 좌표 변환
        slat, slon = get_lat_lon(s_row[x_col], s_row[y_col])
        elat, elon = get_lat_lon(e_row[x_col], e_row[y_col])

        # 대한민국 좌표 범위 체크 (대략적인 사각 범위)
        # 위도: 33~39, 경도: 124~132 벗어나면 경고
        if not (33 < slat < 39 and 124 < slon < 132):
            st.warning(f"⚠️ 경고: 좌표가 대한민국을 벗어난 것 같습니다. ({slat:.2f}, {slon:.2f})")
            st.warning("왼쪽 사이드바에서 **'좌표계 선택'**을 다른 것(5174, 5186 등)으로 바꿔보세요.")
        
        # 지도 생성
        center_lat = (slat + elat) / 2
        center_lon = (slon + elon) / 2
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

        # 출발지
        folium.Marker([slat, slon], popup=f"출발: {s_place}", icon=folium.Icon(color="blue", icon="play")).add_to(m)
        # 도착지
        folium.Marker([elat, elon], popup=f"도착: {e_place}", icon=folium.Icon(color="red", icon="stop")).add_to(m)
        # 선
        folium.PolyLine([[slat, slon], [elat, elon]], color="blue", weight=5, opacity=0.7).add_to(m)

        st.success(f"경로 표시: {s_place} → {e_place}")
        st_folium(m, width=800, height=500)

    except Exception as e:
        st.error(f"지도 생성 중 오류 발생: {e}")
