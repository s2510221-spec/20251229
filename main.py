import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math

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
    try:
        # CSV 파일 읽기 (인코딩 주의: cp949 또는 utf-8)
        df = pd.read_csv(file_path, encoding='cp949')
        
        # 데이터 전처리: #N/A 처리를 위해 문자열을 NaN으로 변환 후 제거
        # 실제 데이터에 #N/A가 엑셀 오류 문자열로 들어가 있다고 가정
        cols_to_check = ['x좌표', 'y좌표', '노드명']
        
        # 숫자형으로 변환을 시도하고 에러나면 NaN 처리 (coerce)
        df['x좌표'] = pd.to_numeric(df['x좌표'], errors='coerce')
        df['y좌표'] = pd.to_numeric(df['y좌표'], errors='coerce')
        
        # 좌표가 없는 데이터(NaN) 제거 (이 과정이 없으면 지도 표시 불가)
        df_clean = df.dropna(subset=['x좌표', 'y좌표']).copy()
        
        # 인덱스 재설정
        df_clean.reset_index(drop=True, inplace=True)
        
        return df_clean
    except FileNotFoundError:
        st.error(f"'{file_path}' 파일을 찾을 수 없습니다. 같은 폴더에 위치시켜주세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

# 파일 로드 (파일명 확인 필수)
DATA_FILE = '20251229road_.csv'
df = load_data(DATA_FILE)

# ---------------------------------------------------------
# 3. 사이드바: 모드 선택 및 경로 설정
# ---------------------------------------------------------
st.sidebar.header("⚙️ 설정")

# 사용자 모드 분리
mode = st.sidebar.radio(
    "이동 모드 선택",
    ("🚗 자동차 모드 (Car)", "🚶 보행자 모드 (Walk)")
)

if df.empty:
    st.warning("데이터가 없거나 로드에 실패하여 기능을 사용할 수 없습니다.")
    st.stop()

# 출발지 및 목적지 선택 (노드명 기준)
# 노드명이 중복될 수 있으므로 ID와 함께 표시
node_options = df.apply(lambda row: f"{row['노드명']} (ID:{row['노드id']})", axis=1).tolist()

st.sidebar.subheader("경로 탐색")
start_node_str = st.sidebar.selectbox("출발지 선택", node_options)
end_node_str = st.sidebar.selectbox("목적지 선택", node_options, index=len(node_options)-1 if len(node_options)>1 else 0)

# 선택된 노드의 실제 데이터 가져오기
start_idx = node_options.index(start_node_str)
end_idx = node_options.index(end_node_str)

start_row = df.iloc[start_idx]
end_row = df.iloc[end_idx]

# ---------------------------------------------------------
# 4. 메인 기능: 지도 시각화 및 정보 표시
# ---------------------------------------------------------

# 4-1. 정보 표시 컨테이너
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader(f"🗺️ 경로 안내 ({mode})")
    
    # 지도 중심 설정 (출발지와 목적지의 중간 지점)
    center_lat = (start_row['y좌표'] + end_row['y좌표']) / 2
    center_lon = (start_row['x좌표'] + end_row['x좌표']) / 2
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

    # 출발지 마커 (파란색)
    folium.Marker(
        [start_row['y좌표'], start_row['x좌표']],
        popup=f"출발: {start_row['노드명']}",
        icon=folium.Icon(color='blue', icon='play')
    ).add_to(m)

    # 목적지 마커 (빨간색)
    folium.Marker(
        [end_row['y좌표'], end_row['x좌표']],
        popup=f"도착: {end_row['노드명']}",
        icon=folium.Icon(color='red', icon='flag')
    ).add_to(m)

    # 경로 그리기 (현재는 링크 데이터 부재로 직선 연결 - 추후 API 연동 시 실제 경로로 변경 가능)
    # 자동차 모드와 보행자 모드에 따라 선 스타일 변경
    line_color = 'blue' if mode == "🚗 자동차 모드 (Car)" else 'green'
    line_style = 'solid' if mode == "🚗 자동차 모드 (Car)" else 'dashed' # 보행자는 점선

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
        tooltip=f"{mode} 최단 경로"
    ).add_to(m)

    # 지도 출력
    st_folium(m, width="100%", height=500)

with col2:
    st.subheader("ℹ️ 상세 정보")
    
    # 거리 계산 (하버사인 공식 등 활용 가능하나 여기선 유클리드 거리 개념 단순화 표시)
    # 실제로는 좌표계 변환이 필요하지만 데모용으로 단순 차이 계산
    dist = math.sqrt((start_row['x좌표']-end_row['x좌표'])**2 + (start_row['y좌표']-end_row['y좌표'])**2)
    
    st.info(f"**선택 모드:** {mode}")
    
    # 예외 처리: 출발지와 목적지가 같을 경우
    if start_node_str == end_node_str:
        st.error("출발지와 목적지가 동일합니다.")
    else:
        st.success("경로 탐색 완료!")

    st.markdown("---")
    st.write("**📍 목적지 도로 정보**")
    
    # 데이터프레임의 컬럼명에 맞춰 정보 매핑 (CSV 파일 헤더 기준)
    # 안전등급, 위험수준 등 파일에 있는 정보를 표시
    risk_level = end_row.get('교차로위험수준', '정보 없음')
    safety_grade = end_row.get('교차로안전등급', '정보 없음')
    
    st.metric(label="목적지 안전 등급", value=str(safety_grade))
    st.metric(label="위험도 수치", value=f"{risk_level}")

    # 자동차 모드일 때만 보여주는 추가 위험 정보
    if "Car" in mode:
        st.warning("⚠️ 운전자 주의 사항")
        st.write(f"- 사고 위험도: {risk_level}")
        st.write("- 급정지 빈도: 높음(예시 데이터)")
    else:
        st.success("🚶 보행자 팁")
        st.write("- 횡단보도 이용 권장")
        st.write("- 도보 이동 시 안전함")

# ---------------------------------------------------------
# 5. 데이터 테이블 보기 (디버깅 및 상세 분석용)
# ---------------------------------------------------------
with st.expander("📊 원본 데이터 확인하기"):
    st.dataframe(df)
