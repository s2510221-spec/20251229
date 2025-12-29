import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import os

# -----------------------------------------------------------------------------
# 1. 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="경로 탐색 시스템", layout="wide")
st.title("🗺️ 도로 경로 탐색 시스템")

# 깃허브(같은 폴더)에 있는 파일명
CSV_FILE_NAME = '20251229road_29최종.csv'

# -----------------------------------------------------------------------------
# 2. Session State 초기화 (지도가 사라지지 않게 하는 핵심!)
# -----------------------------------------------------------------------------
# 'map_view'라는 변수를 브라우저에 저장해서 기억시킵니다.
if 'map_view' not in st.session_state:
    st.session_state['map_view'] = False
if 's_place' not in st.session_state:
    st.session_state['s_place'] = None
if 'e_place' not in st.session_state:
    st.session_state['e_place'] = None

# -----------------------------------------------------------------------------
# 3. 좌표 변환기 및 데이터 로드
# -----------------------------------------------------------------------------
try:
    transformer = Transformer.from_crs("epsg:5179", "epsg:4326")
except Exception as e:
    st.error(f"좌표 변환 모듈 오류: {e}")
    st.stop()

def get_lat_lon(x, y):
    try:
        lat, lon = transformer.transform(y, x)
        return lat, lon
    except:
        return None, None

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
    st.error(f"❌ '{CSV_FILE_NAME}' 파일을 찾을 수 없습니다.")
    st.stop()

# -------------------------------------------------------------------------
# 4. 사이드바 설정 (컬럼 매핑)
# -------------------------------------------------------------------------
st.sidebar.header("🔧 데이터 컬럼 설정")
columns = df.columns.tolist()

# 컬럼 자동 찾기 시도
default_name_idx = next((i for i, c in enumerate(columns) if '명' in c or '장소' in c), 0)
default_x_idx = next((i for i, c in enumerate(columns) if 'X' in c or 'x' in c or '경도' in c), 1)
default_y_idx = next((i for i, c in enumerate(columns) if 'Y' in c or 'y' in c or '위도' in c), 2)

name_col = st.sidebar.selectbox("장소명 컬럼", columns, index=default_name_idx)
x_col = st.sidebar.selectbox("X좌표(경도) 컬럼", columns, index=default_x_idx)
y_col = st.sidebar.selectbox("Y좌표(위도) 컬럼", columns, index=default_y_idx)

# -------------------------------------------------------------------------
# 5. UI 및 지도 로직
# -------------------------------------------------------------------------
st.divider()
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    # 사용자 선택 값을 임시 변수에 담습니다.
    input_start = st.selectbox("출발지 선택", df[name_col].unique())
with col2:
    input_end = st.selectbox("도착지 선택", df[name_col].unique())
with col3:
    st.write("") 
    st.write("") 
    # 버튼을 누르면 Session State를 업데이트합니다.
    if st.button("🚀 경로 탐색 시작", use_container_width=True):
        st.session_state['map_view'] = True       # 지도를 보여줘라! 라고 상태 저장
        st.session_state['s_place'] = input_start # 선택한 출발지 저장
        st.session_state['e_place'] = input_end   # 선택한 도착지 저장

# -------------------------------------------------------------------------
# 6. 지도 그리기 (if st.button 안에 넣지 않고 밖으로 뺌)
# -------------------------------------------------------------------------
# 'map_view'가 True일 때만 실행 (버튼 눌렀던 기록이 있으면 실행)
if st.session_state['map_view']:
    
    # 저장된 출발/도착지로 데이터 찾기
    start_place = st.session_state['s_place']
    end_place = st.session_state['e_place']
    
    start_row = df[df[name_col] == start_place].iloc[0]
    end_row = df[df[name_col] == end_place].iloc[0]

    # 좌표 변환
    sx_raw, sy_raw = start_row[x_col], start_row[y_col]
    ex_raw, ey_raw = end_row[x_col], end_row[y_col]
    
    start_lat, start_lon = get_lat_lon(sx_raw, sy_raw)
    end_lat, end_lon = get_lat_lon(ex_raw, ey_raw)

    if start_lat is None or end_lat is None:
        st.error("좌표 변환 실패: 데이터 형식을 확인해주세요.")
    else:
        # 중심점 계산
        center_lat = (start_lat + end_lat) / 2
        center_lon = (start_lon + end_lon) / 2

        # 지도 생성
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

        # 마커 추가
        folium.Marker(
            [start_lat, start_lon],
            popup=f"출발: {start_place}",
            tooltip=start_place,
            icon=folium.Icon(color="blue", icon="play")
        ).add_to(m)

        folium.Marker(
            [end_lat, end_lon],
            popup=f"도착: {end_place}",
            tooltip=end_place,
            icon=folium.Icon(color="red", icon="stop")
        ).add_to(m)

        # 선 그리기
        folium.PolyLine(
            locations=[[start_lat, start_lon], [end_lat, end_lon]],
            color="blue",
            weight=5,
            opacity=0.7
        ).add_to(m)

        st.success(f"✅ 경로 탐색 완료: {start_place} → {end_place}")
        
        # 지도 출력
        st_folium(m, width=800, height=500)
