import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math

# ---------------------------------------------------------
# 1. 페이지 기본 설정 및 제목
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="SafeRoad - 데이터 기반 경로 탐색")

st.title("🚗 SafeRoad: 데이터 기반 안전 경로 탐색")
st.markdown("""
보유한 데이터 내에서 **출발지**와 **도착지**를 선택하여 최단 경로와 안전 정보를 확인하세요.
""")

# ---------------------------------------------------------
# 2. 데이터 로드 및 전처리
# ---------------------------------------------------------
@st.cache_data
def load_data():
    try:
        # CSV 파일 로드 (한글 깨짐 방지를 위해 encoding='cp949' 또는 'utf-8-sig' 시도 권장)
        # 예시 데이터 구조: road_name(장소명), lat(위도), lon(경도), risk_score(위험도)
        df = pd.read_csv('20251229road_최종.csv')
        
        # 필수 컬럼 확인 및 예외처리
        required_cols = ['lat', 'lon']
        for col in required_cols:
            if col not in df.columns:
                st.error(f"데이터 파일에 '{col}' 컬럼이 없습니다.")
                return pd.DataFrame()

        # 장소 이름 컬럼이 없으면 임의로 생성 (실제 데이터에 'road_name'이 있다면 이 부분은 건너뜀)
        if 'road_name' not in df.columns:
            # 테스트를 위해 임시 이름 생성 (실제 사용시에는 데이터에 이름 컬럼이 있어야 함)
            df['road_name'] = [f"지점_{i}" for i in range(len(df))]
        
        # 위험도 컬럼이 없으면 임의 생성
        if 'risk_score' not in df.columns:
            import numpy as np
            df['risk_score'] = np.random.randint(1, 100, df.shape[0])
            
        return df
    except FileNotFoundError:
        st.error("데이터 파일(20251229road_최종.csv)을 찾을 수 없습니다. 폴더에 업로드 해주세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

df = load_data()

# 위험도 수치를 단계로 변환하는 함수
def get_risk_level(score):
    if score < 30:
        return "안전 (Green)", "green"
    elif score < 70:
        return "주의 (Orange)", "orange"
    else:
        return "위험 (Red)", "red"

# ---------------------------------------------------------
# 3. 사이드바: 장소 선택 및 모드 설정
# ---------------------------------------------------------
st.sidebar.header("📍 경로 탐색 설정")

# 모드 선택
mode = st.sidebar.radio(
    "이동 모드 선택",
    ("🚗 자동차 모드 (도로 위주)", "🚶 보행자 모드 (최단/안전)")
)

# [핵심 변경] 데이터에서 장소 목록 추출 (중복 제거 및 정렬)
if not df.empty:
    location_list = sorted(df['road_name'].unique().tolist())
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("출발지/도착지 선택")
    st.sidebar.caption("💡 목록을 클릭하고 키보드로 이름을 입력하면 빠르게 검색됩니다.")
    
    # selectbox를 사용하여 검색 기능 제공
    start_point_name = st.sidebar.selectbox("출발지 선택", location_list, index=0)
    # 도착지는 출발지와 다른 곳을 기본값으로 하기 위해 index=1 (데이터가 2개 이상일 때)
    default_end_index = 1 if len(location_list) > 1 else 0
    end_point_name = st.sidebar.selectbox("도착지 선택", location_list, index=default_end_index)
    
    search_btn = st.sidebar.button("경로 분석 시작")
else:
    st.sidebar.error("데이터가 없습니다.")
    start_point_name = None
    end_point_name = None
    search_btn = False

# ---------------------------------------------------------
# 4. 메인 로직: 선택된 장소 좌표 찾기 및 지도 표출
# ---------------------------------------------------------

# 기본 지도 (대한민국 중심)
m = folium.Map(location=[36.5, 127.5], zoom_start=7)

if search_btn and not df.empty:
    if start_point_name == end_point_name:
        st.warning("출발지와 도착지가 같습니다. 다른 장소를 선택해주세요.")
    else:
        # 데이터프레임에서 선택된 이름에 해당하는 좌표 정보 가져오기
        start_row = df[df['road_name'] == start_point_name].iloc[0]
        end_row = df[df['road_name'] == end_point_name].iloc[0]
        
        start_coords = (start_row['lat'], start_row['lon'])
        end_coords = (end_row['lat'], end_row['lon'])

        with st.spinner(f"'{start_point_name}'에서 '{end_point_name}'까지 경로 분석 중..."):
            
            # 1. 지도 중심 이동
            mid_lat = (start_coords[0] + end_coords[0]) / 2
            mid_lon = (start_coords[1] + end_coords[1]) / 2
            m.location = [mid_lat, mid_lon]
            m.zoom_start = 12

            # 2. 마커 추가 (데이터에 있는 정확한 위치)
            folium.Marker(
                start_coords, 
                popup=f"출발: {start_point_name}", 
                tooltip="출발지",
                icon=folium.Icon(color="blue", icon="play")
            ).add_to(m)
            
            folium.Marker(
                end_coords, 
                popup=f"도착: {end_point_name}", 
                tooltip="도착지",
                icon=folium.Icon(color="red", icon="stop")
            ).add_to(m)

            # 3. 경로 그리기 (직선 시각화)
            line_color = "blue" if "자동차" in mode else "green"
            folium.PolyLine(
                locations=[start_coords, end_coords],
                color=line_color,
                weight=5,
                dash_array='10' if "보행자" in mode else None,
                opacity=0.7
            ).add_to(m)

            # 4. 주변 위험 데이터 시각화 (범위 필터링)
            # 출발-도착 좌표를 포함하는 사각형 영역 설정
            lat_min, lat_max = min(start_coords[0], end_coords[0]), max(start_coords[0], end_coords[0])
            lon_min, lon_max = min(start_coords[1], end_coords[1]), max(start_coords[1], end_coords[1])
            
            # 검색 범위 여유값 (버퍼)
            buffer = 0.02  
            mask = (df['lat'] >= lat_min - buffer) & (df['lat'] <= lat_max + buffer) & \
                   (df['lon'] >= lon_min - buffer) & (df['lon'] <= lon_max + buffer)
            nearby_data = df[mask]

            count_danger = 0
            
            if "자동차" in mode:
                # 자동차: 모든 위험 요소 표시
                for idx, row in nearby_data.iterrows():
                    level_text, color = get_risk_level(row['risk_score'])
                    # 출발/도착지는 제외하고 표시
                    if row['road_name'] not in [start_point_name, end_point_name]:
                        folium.CircleMarker(
                            location=[row['lat'], row['lon']],
                            radius=6,
                            color=color,
                            fill=True,
                            fill_opacity=0.7,
                            popup=f"{row['road_name']} (위험도: {level_text})"
                        ).add_to(m)
                        if color == "red": count_danger += 1
            else:
                # 보행자: 고위험 지역만 경고 표시
                high_risks = nearby_data[nearby_data['risk_score'] >= 70]
                for idx, row in high_risks.iterrows():
                    if row['road_name'] not in [start_point_name, end_point_name]:
                        folium.Marker(
                            location=[row['lat'], row['lon']],
                            icon=folium.Icon(color="red", icon="exclamation-sign"),
                            tooltip=f"주의: {row['road_name']}"
                        ).add_to(m)
                        count_danger += 1

            if count_danger > 0:
                st.toast(f"경로 주변에 주의할 구간이 {count_danger}곳 있습니다!", icon="⚠️")

# 지도 출력
st_data = st_folium(m, width="100%", height=600)

# ---------------------------------------------------------
# 5. 하단 분석 정보
# ---------------------------------------------------------
if search_btn and not df.empty:
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info(f"📍 **출발**: {start_point_name}")
    with col2:
        st.success(f"🚩 **도착**: {end_point_name}")
    with col3:
        # 거리 계산 (Haversine 공식 대신 간단한 유클리드 거리 근사치 사용)
        dist = math.sqrt((start_coords[0]-end_coords[0])**2 + (start_coords[1]-end_coords[1])**2) * 111
        st.metric(label="직선 거리", value=f"{dist:.2f} km")

    # 출발/도착지의 안전 정보 표시
    s_score = start_row['risk_score']
    e_score = end_row['risk_score']
    
    st.subheader("지점별 안전 등급")
    c1, c2 = st.columns(2)
    c1.markdown(f"**출발지 안전도**: {get_risk_level(s_score)[0]}")
    c2.markdown(f"**도착지 안전도**: {get_risk_level(e_score)[0]}")
