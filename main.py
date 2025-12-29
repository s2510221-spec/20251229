import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import os

# -----------------------------------------------------------------------------
# 1. 기본 설정 및 파일명 지정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="경로 탐색 시스템", layout="wide")
st.title("🗺️ 도로 경로 탐색 시스템")

# 깃허브(같은 폴더)에 있는 파일명
CSV_FILE_NAME = '20251229road_29최종.csv'

# -----------------------------------------------------------------------------
# 2. 좌표 변환기 설정 (TM좌표 -> 위도/경도)
# -----------------------------------------------------------------------------
# 한국 도로명주소/공공데이터는 보통 'EPSG:5179'를 사용합니다.
# 만약 지도가 엉뚱한 위치(바다 등)에 찍히면 'epsg:5174'로 변경해보세요.
try:
    transformer = Transformer.from_crs("epsg:5179", "epsg:4326")
except Exception as e:
    st.error(f"좌표 변환 모듈 설정 실패: {e}")
    st.stop()

def get_lat_lon(x, y):
    """
    TM좌표(미터 단위)를 위도(lat), 경도(lon)로 변환
    """
    try:
        # pyproj transform은 (y, x) 순서로 넣으면 (lat, lon)이 반환됩니다.
        lat, lon = transformer.transform(y, x)
        return lat, lon
    except:
        return None, None

# -----------------------------------------------------------------------------
# 3. 데이터 로드 (자동 읽기)
# -----------------------------------------------------------------------------
@st.cache_data  # 데이터 로딩 속도 향상을 위해 캐시 사용
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    
    # 한글 파일은 보통 cp949 또는 euc-kr 인코딩
    try:
        df = pd.read_csv(file_path, encoding='cp949')
    except:
        df = pd.read_csv(file_path, encoding='utf-8') # utf-8 시도
    return df

# 파일 불러오기 시도
df = load_data(CSV_FILE_NAME)

if df is None:
    st.error(f"❌ '{CSV_FILE_NAME}' 파일을 찾을 수 없습니다.")
    st.warning("GitHub 리포지토리에 파일이 정확한 이름으로 업로드되어 있는지 확인해주세요.")
    st.stop()
else:
    st.success(f"📂 데이터 파일 로드 완료: {CSV_FILE_NAME}")
    
    # 데이터 미리보기 (접기 가능)
    with st.expander("데이터 미리보기"):
        st.dataframe(df.head())

    # -------------------------------------------------------------------------
    # 4. 컬럼 매핑 (자동으로 읽었더라도 어떤 게 좌표인지 지정 필요)
    # -------------------------------------------------------------------------
    st.sidebar.header("🔧 설정")
    st.sidebar.info("데이터의 어떤 컬럼이 장소명과 좌표인지 선택해주세요.")
    
    columns = df.columns.tolist()
    
    # 기본적으로 '장소', '명칭', 'X', 'Y' 같은 단어가 포함된 컬럼을 자동으로 찾으려 시도
    default_name_idx = next((i for i, c in enumerate(columns) if '명' in c or '장소' in c), 0)
    default_x_idx = next((i for i, c in enumerate(columns) if 'X' in c or 'x' in c or '경도' in c), 1)
    default_y_idx = next((i for i, c in enumerate(columns) if 'Y' in c or 'y' in c or '위도' in c), 2)

    name_col = st.sidebar.selectbox("장소명(이름) 컬럼", columns, index=default_name_idx)
    x_col = st.sidebar.selectbox("X좌표 컬럼 (TM X)", columns, index=default_x_idx)
    y_col = st.sidebar.selectbox("Y좌표 컬럼 (TM Y)", columns, index=default_y_idx)

    # -------------------------------------------------------------------------
    # 5. 경로 탐색 UI
    # -------------------------------------------------------------------------
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        start_place = st.selectbox("출발지 선택", df[name_col].unique())
    with col2:
        end_place = st.selectbox("도착지 선택", df[name_col].unique())
    with col3:
        st.write("") # 여백용
        st.write("") 
        search_btn = st.button("🚀 경로 탐색 시작", use_container_width=True)

    # -------------------------------------------------------------------------
    # 6. 지도 시각화 (버튼 클릭 시)
    # -------------------------------------------------------------------------
    if search_btn:
        # 선택한 장소의 데이터 행 추출
        start_row = df[df[name_col] == start_place].iloc[0]
        end_row = df[df[name_col] == end_place].iloc[0]

        # 원본 좌표 가져오기 (파일에 있는 큰 숫자)
        sx_raw, sy_raw = start_row[x_col], start_row[y_col]
        ex_raw, ey_raw = end_row[x_col], end_row[y_col]

        # 좌표 변환 (핵심!)
        start_lat, start_lon = get_lat_lon(sx_raw, sy_raw)
        end_lat, end_lon = get_lat_lon(ex_raw, ey_raw)

        if start_lat is None or end_lat is None:
            st.error("좌표 변환 실패: 좌표 데이터가 숫자가 아니거나 형식이 잘못되었습니다.")
        else:
            # 중심점 계산
            center_lat = (start_lat + end_lat) / 2
            center_lon = (start_lon + end_lon) / 2

            # 지도 생성
            m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

            # 출발지 마커
            folium.Marker(
                [start_lat, start_lon],
                popup=f"출발: {start_place}",
                tooltip=start_place,
                icon=folium.Icon(color="blue", icon="play")
            ).add_to(m)

            # 도착지 마커
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

            st.success("경로 탐색 완료!")
            
            # 지도 출력
            st_folium(m, width=800, height=500)
