import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer

# 페이지 설정
st.set_page_config(page_title="경로 탐색 및 지도 보기", layout="wide")

st.title("🗺️ 경로 탐색 및 지도 시각화")
st.write("파일을 업로드하고 출발지와 도착지를 선택하면, 거리 제한 없이 지도를 보여줍니다.")

# -----------------------------------------------------------------------------
# 1. 좌표 변환기 설정 (핵심 수정 사항)
# -----------------------------------------------------------------------------
# 한국 공공데이터(도로명주소 등)는 보통 'EPSG:5179' 좌표계를 씁니다.
# 만약 지도가 엉뚱한 곳(바다, 중국 등)을 가리키면 'epsg:5174' 또는 'epsg:5186'으로 바꿔보세요.
try:
    transformer = Transformer.from_crs("epsg:5179", "epsg:4326")
except Exception as e:
    st.error(f"좌표 변환기 설정 오류: {e}")
    st.stop()

def get_lat_lon(x, y):
    """
    TM좌표(미터 단위)를 위도(lat), 경도(lon)로 변환하는 함수
    """
    try:
        # pyproj transform은 보통 (y, x) 순서로 넣으면 (lat, lon)이 나옵니다.
        lat, lon = transformer.transform(y, x)
        return lat, lon
    except Exception as e:
        return None, None

# -----------------------------------------------------------------------------
# 2. 파일 업로드 및 데이터 로드
# -----------------------------------------------------------------------------
uploaded_file = st.file_uploader("엑셀 또는 CSV 파일을 업로드하세요", type=['xlsx', 'csv'])

if uploaded_file is not None:
    # 파일 확장자에 따라 읽기
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file, encoding='cp949') # 한글 깨짐 방지
    else:
        df = pd.read_excel(uploaded_file)
        
    st.write("### 데이터 미리보기")
    st.dataframe(df.head())

    # -------------------------------------------------------------------------
    # 3. 컬럼 선택 (사용자가 직접 좌표 컬럼을 지정하게 함)
    # -------------------------------------------------------------------------
    st.sidebar.header("설정")
    
    # 데이터프레임의 컬럼 목록
    columns = df.columns.tolist()
    
    # 장소 이름, X좌표, Y좌표 컬럼을 사용자가 선택
    name_col = st.sidebar.selectbox("장소명 컬럼 선택", columns, index=0)
    x_col = st.sidebar.selectbox("X 좌표(경도) 컬럼 선택", columns, index=1 if len(columns)>1 else 0)
    y_col = st.sidebar.selectbox("Y 좌표(위도) 컬럼 선택", columns, index=2 if len(columns)>2 else 0)

    # -------------------------------------------------------------------------
    # 4. 출발지 / 도착지 선택
    # -------------------------------------------------------------------------
    st.subheader("📍 출발지와 도착지 선택")
    
    col1, col2 = st.columns(2)
    with col1:
        start_place = st.selectbox("출발지 선택", df[name_col].unique(), key='start')
    with col2:
        end_place = st.selectbox("도착지 선택", df[name_col].unique(), key='end')

    # 선택한 장소의 행(Row) 데이터 가져오기
    start_row = df[df[name_col] == start_place].iloc[0]
    end_row = df[df[name_col] == end_place].iloc[0]

    # 경로 탐색 버튼
    if st.button("경로 탐색 및 지도 보기"):
        
        # ---------------------------------------------------------------------
        # 5. 좌표 변환 및 지도 그리기 (에러 해결 부분)
        # ---------------------------------------------------------------------
        
        # 원본 좌표 (큰 숫자)
        sx_raw, sy_raw = start_row[x_col], start_row[y_col]
        ex_raw, ey_raw = end_row[x_col], end_row[y_col]
        
        # [중요] 좌표 변환 수행 (TM -> 위경도)
        start_lat, start_lon = get_lat_lon(sx_raw, sy_raw)
        end_lat, end_lon = get_lat_lon(ex_raw, ey_raw)

        # 변환 성공 여부 확인
        if start_lat is None or end_lat is None:
            st.error("좌표 변환에 실패했습니다. 올바른 숫자 데이터인지 확인해주세요.")
        else:
            # 거리 계산 로직 (에러를 내는 대신 정보만 보여줌)
            st.success(f"✅ 경로 탐색 성공! (거리 제한 없음)")
            st.info(f"변환된 좌표 - 출발: ({start_lat:.5f}, {start_lon:.5f}) / 도착: ({end_lat:.5f}, {end_lon:.5f})")

            # 지도 중심 잡기 (중간 지점)
            center_lat = (start_lat + end_lat) / 2
            center_lon = (start_lon + end_lon) / 2
            
            # 지도 생성
            m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

            # 출발지 마커 (파란색)
            folium.Marker(
                [start_lat, start_lon],
                tooltip=start_place,
                popup=f"출발: {start_place}",
                icon=folium.Icon(color="blue", icon="play")
            ).add_to(m)

            # 도착지 마커 (빨간색)
            folium.Marker(
                [end_lat, end_lon],
                tooltip=end_place,
                popup=f"도착: {end_place}",
                icon=folium.Icon(color="red", icon="stop")
            ).add_to(m)

            # 경로 선 그리기
            folium.PolyLine(
                locations=[[start_lat, start_lon], [end_lat, end_lon]],
                color="blue",
                weight=4,
                opacity=0.7
            ).add_to(m)

            # Streamlit에 지도 출력
            st_folium(m, width=800, height=500)

else:
    st.info("좌측(또는 상단)에서 엑셀/CSV 데이터를 업로드해주세요.")
    
    # (테스트용) 파일 없을 때 예시 데이터 생성 로직
    st.divider()
    st.write("🔍 **테스트용 데이터 예시 (업로드할 파일 형식이 이래야 합니다)**")
    dummy_data = {
        '장소명': ['서울역', '강남역', '인천공항'],
        'X좌표': [953928.1234, 959321.5678, 928321.1111], # 예시 TM좌표
        'Y좌표': [1951023.4321, 1944123.9876, 1948321.2222]
    }
    st.dataframe(pd.DataFrame(dummy_data))
