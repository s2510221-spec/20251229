import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
import os

# ---------------------------------------------------------
# 1. 페이지 설정 및 제목
# ---------------------------------------------------------
st.set_page_config(
    page_title="Road Insight - 안전 경로 탐색",
    page_icon="🚗",
    layout="wide"
)

st.title("🛣️ Road Insight")
st.markdown("""
**최단 거리 및 도로 안전 정보 제공 시스템** 자동차와 보행자에게 최적의 경로와 도로 위험도 정보를 제공합니다.
""")

# ---------------------------------------------------------
# 2. 데이터 로드 및 전처리 함수
# ---------------------------------------------------------
@st.cache_data
def load_data(file_path):
    # 파일 존재 여부 확인
    if not os.path.exists(file_path):
        return None

    try:
        # 인코딩: 윈도우(cp949) 또는 맥/리눅스(utf-8) 시도
        try:
            df = pd.read_csv(file_path, encoding='cp949')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='utf-8')
        
        # 전처리: 좌표가 문자로 되어있거나 #N/A인 경우를 대비해 숫자로 강제 변환
        # errors='coerce'는 숫자가 아닌 값을 NaN(빈값)으로 바꿔줌
        df['x좌표'] = pd.to_numeric(df['x좌표'], errors='coerce')
        df['y좌표'] = pd.to_numeric(df['y좌표'], errors='coerce')
        
        # 좌표(x, y)가 둘 다 있는 행만 남기기 (지도 표시에 필수)
        df_clean = df.dropna(subset=['x좌표', 'y좌표']).copy()
        
        # 인덱스 초기화
        df_clean.reset_index(drop=True, inplace=True)
        
        return df_clean

    except Exception as e:
        st.error(f"데이터를 불러오는 중 에러가 발생했습니다: {e}")
        return pd.DataFrame()

# 파일명 설정 (깃허브에 올린 파일명과 정확히 일치해야 함)
DATA_FILE = '20251229road_.csv'
df = load_data(DATA_FILE)

# ---------------------------------------------------------
# 3. 데이터 로드 실패 시 중단
# ---------------------------------------------------------
if df is None:
    st.error(f"❌ '{DATA_FILE}' 파일을 찾을 수 없습니다.")
    st.warning("GitHub 저장소에 csv 파일이 함께 업로드되었는지 확인해주세요.")
    st.stop()

if df.empty:
    st.warning("⚠️ 유효한 좌표 데이터가 없습니다. CSV 파일의 'x좌표', 'y좌표' 컬럼을 확인해주세요.")
    st.stop()

# ---------------------------------------------------------
# 4. 사이드바: 모드 선택 및 경로 설정
# ---------------------------------------------------------
st.sidebar.header("⚙️ 설정")

mode = st.sidebar.radio(
    "이동 모드 선택",
    ("🚗 자동차 모드 (Car)", "🚶 보행자 모드 (Walk)")
)

# 노드 선택 옵션 생성 (이름 + ID)
node_options = df.apply(lambda row: f"{row['노드명']} (ID:{row['노드id']})", axis=1).tolist()

st.sidebar.subheader("경로 탐색")
start_node_str = st.sidebar.selectbox("출발지 선택", node_options)
# 목적지는 기본적으로 리스트의 마지막 항목으로 설정하여 바로 경로가 보이게 함
end_node_str = st.sidebar.selectbox("목적지 선택", node_options, index=len(node_options)-1 if len(node_options)>1 else 0)

# 선택된 항목의 인덱스 찾기
start_idx = node_options.index(start_node_str)
end_idx = node_options.index(end_node_str)

start_row = df.iloc[start_idx]
end_row = df.iloc[end_idx]

# ---------------------------------------------------------
# 5. 메인 기능: 지도 시각화 및 정보 표시
# ---------------------------------------------------------
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader(f"🗺️ 경로 안내 ({mode})")
    
    # 지도 중심: 출발지와 목적지의 중간
    center_lat = (start_row['y좌표'] + end_row['y좌표']) / 2
    center_lon = (start_row['x좌표'] + end_row['x좌표']) / 2
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14)

    # 출발지 마커
    folium.Marker(
        [start_row['y좌표'], start_row['x좌표']],
        popup=f"출발: {start_row['노드명']}",
        tooltip="출발지",
        icon=folium.Icon(color='blue', icon='play')
    ).add_to(m)

    # 목적지 마커
    folium.Marker(
        [end_row['y좌표'], end_row['x좌표']],
        popup=f"도착: {end_row['노드명']}",
        tooltip="목적지",
        icon=folium.Icon(color='red', icon='flag')
    ).add_to(m)

    # 경로 스타일 설정
    line_color = 'blue' if "Car" in mode else 'green'
    line_style = 'solid' if "Car" in mode else 'dashed' # 보행자는 점선 느낌

    locations = [
        [start_row['y좌표'], start_row['x좌표']],
        [end_row['y좌표'], end_row['x좌표']]
    ]
    
    folium.PolyLine(
        locations,
        color=line_color,
        weight=5,
        opacity=0.8,
        dash_array='10' if line_style == 'dashed' else None,
        tooltip=f"{mode} 경로"
    ).add_to(m)

    # 스트림릿에 지도 그리기
    st_folium(m, width="100%", height=500)

with col2:
    st.subheader("ℹ️ 상세 정보")
    
    # 단순 거리 계산 (좌표 차이) - 실제 거리와는 차이가 있음
    dist_val = math.sqrt((start_row['x좌표']-end_row['x좌표'])**2 + (start_row['y좌표']-end_row['y좌표'])**2)
    
    # 출발지와 목적지 동일 여부 체크
    if start_node_str == end_node_str:
        st.error("출발지와 목적지가 같습니다.")
    else:
        st.success("경로 탐색 완료")

    st.markdown("---")
    st.write(f"**📍 목적지: {end_row['노드명']}**")
    
    # 데이터가 없을 경우를 대비해 .get() 사용
    risk = end_row.get('교차로위험수준', '정보 없음')
    grade = end_row.get('교차로안전등급', '정보 없음')
    
    st.metric(label="안전 등급", value=str(grade))
    st.metric(label="위험도 수치", value=str(risk))

    if "Car" in mode:
        st.warning("🚗 운전자 주의")
        st.caption("해당 도로는 차량 통행이 많을 수 있습니다. 안전 거리를 확보하세요.")
    else:
        st.info("🚶 보행자 팁")
        st.caption("횡단보도 이용 시 주변을 잘 살피세요.")

# ---------------------------------------------------------
# 6. 하단 데이터 확인용 (접기/펴기)
# ---------------------------------------------------------
with st.expander("📊 원본 데이터 확인하기"):
    st.dataframe(df)
