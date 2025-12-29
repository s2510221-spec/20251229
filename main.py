import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import os

# -----------------------------------------------------------------------------
# 1. 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="스마트 경로 탐색", layout="wide")
st.title("🗺️ 자동 보정 경로 탐색 시스템")
st.write("복잡한 설정 없이 출발/도착지만 선택하세요. 시스템이 자동으로 한국 위치를 찾아냅니다.")

# 깃허브(같은 폴더)에 있는 파일명
CSV_FILE_NAME = '20251229road_29최종.csv'

# -----------------------------------------------------------------------------
# 2. Session State (지도 유지용)
# -----------------------------------------------------------------------------
if 'map_view' not in st.session_state:
    st.session_state['map_view'] = False
if 's_place' not in st.session_state:
    st.session_state['s_place'] = None
if 'e_place' not in st.session_state:
    st.session_state['e_place'] = None

# -----------------------------------------------------------------------------
# 3. "스마트" 좌표 변환 로직 (핵심 수정 부분)
# -----------------------------------------------------------------------------
# 한국에서 가장 많이 쓰는 두 가지 좌표계 미리 준비
trans_5179 = Transformer.from_crs("epsg:5179", "epsg:4326") # 도로명/공공데이터
trans_5174 = Transformer.from_crs("epsg:5174", "epsg:4326") # 구 지적도

def get_best_korea_location(x, y):
    """
    들어온 x, y 숫자를 가지고 5179도 적용해보고 5174도 적용해봅니다.
    변환된 결과가 '대한민국 영역(위도 33~39, 경도 124~132)' 안에 들어오면
    그 값을 즉시 반환합니다. (자동 감지)
    """
    candidates = [
        (trans_5179, y, x),  # 1순위: 5179 정방향 (가장 흔함)
        (trans_5174, y, x),  # 2순위: 5174 정방향 (옛날 데이터)
        (trans_5179, x, y),  # 3순위: 5179 뒤집힘 (X,Y 바뀐 경우)
        (trans_5174, x, y),  # 4순위: 5174 뒤집힘
    ]

    for transformer, val1, val2 in candidates:
        try:
            lat, lon = transformer.transform(val1, val2)
            # 대한민국 유효 범위 체크 (위도 33~39, 경도 124~133)
            if 33.0 < lat < 39.0 and 124.0 < lon < 133.0:
                return lat, lon # 한국 땅 위에 떨어지면 바로 채택!
        except:
            continue
            
    return None, None # 맞는 좌표계를 못 찾음

# -----------------------------------------------------------------------------
# 4. 데이터 로드
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
    st.error(f"❌ 파일을 찾을 수 없습니다: {CSV_FILE_NAME}")
    st.stop()

# -----------------------------------------------------------------------------
# 5. 컬럼 자동 매핑 (설정창 없앰)
# -----------------------------------------------------------------------------
columns = df.columns.tolist()

# 이름, X, Y가 들어간 컬럼을 코드가 알아서 찾습니다.
name_col = next((c for c in columns if '명' in c or '장소' in c), columns[0])
x_col = next((c for c in columns if 'X' in c or 'x' in c or '경도' in c), columns[1])
y_col = next((c for c in columns if 'Y' in c or 'y' in c or '위도' in c), columns[2])

# -----------------------------------------------------------------------------
# 6. 사용자 선택 UI
# -----------------------------------------------------------------------------
st.divider()
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    input_start = st.selectbox("출발지", df[name_col].unique())
with col2:
    input_end = st.selectbox("도착지", df[name_col].unique())
with col3:
    st.write("") 
    st.write("") 
    # 버튼 클릭
    if st.button("🚀 경로 탐색 (자동 보정)", use_container_width=True):
        st.session_state['map_view'] = True
        st.session_state['s_place'] = input_start
        st.session_state['e_place'] = input_end

# -----------------------------------------------------------------------------
# 7. 지도 그리기
# -----------------------------------------------------------------------------
if st.session_state['map_view']:
    s_place = st.session_state['s_place']
    e_place = st.session_state['e_place']
    
    try:
        # 데이터 찾기
        s_row = df[df[name_col] == s_place].iloc[0]
        e_row = df[df[name_col] == e_place].iloc[0]
        
        # [자동 변환 함수 사용]
        slat, slon = get_best_korea_location(s_row[x_col], s_row[y_col])
        elat, elon = get_best_korea_location(e_row[x_col], e_row[y_col])

        # 변환 결과 확인
        if slat is None or elat is None:
            st.error("⚠️ 좌표 변환 실패: 데이터가 대한민국 좌표 범위를 벗어납니다.")
        else:
            # 지도 중심
            center_lat = (slat + elat) / 2
            center_lon = (slon + elon) / 2
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

            # 출발/도착 마커
            folium.Marker([slat, slon], popup=f"출발: {s_place}", icon=folium.Icon(color="blue", icon="play")).add_to(m)
            folium.Marker([elat, elon], popup=f"도착: {e_place}", icon=folium.Icon(color="red", icon="stop")).add_to(m)
            
            # 경로 선
            folium.PolyLine([[slat, slon], [elat, elon]], color="blue", weight=5, opacity=0.7).add_to(m)

            st.success(f"✅ 위치 확인 완료! (자동으로 좌표계를 보정하여 한국 위치를 찾았습니다)")
            st_folium(m, width=800, height=500)

    except Exception as e:
        st.error(f"시스템 오류: {e}")
