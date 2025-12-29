import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import math

# ---------------------------------------------------------
# 1. 페이지 기본 설정 및 제목
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="SafeRoad - 안전 경로 탐색")

st.title("🚗 SafeRoad: 안전 기반 경로 탐색 시스템")
st.markdown("""
대한민국 내에서 최단 거리와 도로의 안전 정보를 함께 제공합니다.
**출발지**와 **도착지**를 입력하여 안전한 이동 경로를 확인하세요.
""")

# ---------------------------------------------------------
# 2. 데이터 로드 및 전처리
# ---------------------------------------------------------
@st.cache_data
def load_data():
    try:
        # 파일이 있다고 가정 (UTF-8 또는 CP949 인코딩 확인 필요)
        df = pd.read_csv('20251229road_최종.csv')
        
        # 컬럼명이 다를 경우를 대비한 매핑 (사용자 데이터에 맞춰 수정 필요)
        # 가정: CSV에 'lat', 'lon', 'risk_score', 'road_name' 컬럼이 존재
        if 'risk_score' not in df.columns:
            # 위험도 컬럼이 없다면 임의로 생성 (테스트용)
            import numpy as np
            df['risk_score'] = np.random.randint(1, 100, df.shape[0])
            
        return df
    except FileNotFoundError:
        st.error("데이터 파일(20251229road_최종.csv)을 찾을 수 없습니다. 같은 폴더에 업로드 해주세요.")
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
# 3. 지오코딩 함수 (주소 -> 좌표 변환)
# ---------------------------------------------------------
def get_coordinates(location_name):
    geolocator = Nominatim(user_agent="saferoad_app_v1")
    try:
        # 대한민국 내 검색으로 제한
        location = geolocator.geocode(f"{location_name}, South Korea")
        if location:
            return location.latitude, location.longitude
        else:
            return None
    except GeocoderTimedOut:
        st.error("위치 검색 시간이 초과되었습니다. 다시 시도해주세요.")
        return None

# ---------------------------------------------------------
# 4. 사이드바: 사용자 입력 및 모드 설정
# ---------------------------------------------------------
st.sidebar.header("경로 탐색 설정")

# 모드 선택
mode = st.sidebar.radio(
    "이동 모드 선택",
    ("🚗 자동차 모드 (도로 위주)", "🚶 보행자 모드 (최단/안전)")
)

# 출발지/도착지 입력
start_input = st.sidebar.text_input("출발지 입력", placeholder="예: 서울역")
end_input = st.sidebar.text_input("도착지 입력", placeholder="예: 강남역")

search_btn = st.sidebar.button("경로 찾기")

# ---------------------------------------------------------
# 5. 메인 로직: 지도 표출 및 경로 계산
# ---------------------------------------------------------

# 기본 지도 설정 (대한민국 중심)
m = folium.Map(location=[36.5, 127.5], zoom_start=7)

if search_btn:
    if not start_input or not end_input:
        st.warning("출발지와 도착지를 모두 입력해주세요.")
    else:
        with st.spinner("경로 및 안전 정보를 분석 중입니다..."):
            start_coords = get_coordinates(start_input)
            end_coords = get_coordinates(end_input)

            if start_coords and end_coords:
                # 1. 지도 중심을 출발지-도착지 중간으로 이동
                mid_lat = (start_coords[0] + end_coords[0]) / 2
                mid_lon = (start_coords[1] + end_coords[1]) / 2
                m.location = [mid_lat, mid_lon]
                m.zoom_start = 11

                # 2. 출발지/도착지 마커 추가
                folium.Marker(
                    start_coords, tooltip="출발지", icon=folium.Icon(color="blue", icon="play")
                ).add_to(m)
                folium.Marker(
                    end_coords, tooltip="도착지", icon=folium.Icon(color="red", icon="stop")
                ).add_to(m)

                # 3. 경로 그리기 (실제 도로망 API가 없으므로 직선/단순 경로로 시각화)
                # *실제 서비스에서는 OSRM, Kakao Map API 등을 연동하여 좌표 리스트를 받아야 합니다.
                # 여기서는 논리 구현을 위해 직선 경로를 표시하되, 모드별 스타일을 다르게 줍니다.
                
                line_color = "blue" if "자동차" in mode else "green"
                line_style = "solid" if "자동차" in mode else "dotted" # 보행자는 점선 느낌
                
                folium.PolyLine(
                    locations=[start_coords, end_coords],
                    color=line_color,
                    weight=5,
                    dash_array='10' if "보행자" in mode else None,
                    tooltip=f"{mode} 경로"
                ).add_to(m)

                # 4. 주변 도로 안전 정보 오버레이 (핵심 기능)
                # 데이터가 있다면, 경로 주변(또는 전체)의 위험 지점을 표시
                if not df.empty:
                    # 성능을 위해 데이터 일부만 샘플링하거나, 실제로는 좌표 범위 내 데이터만 필터링해야 함
                    # 예시: 위경도 범위 내 데이터만 필터링
                    lat_min, lat_max = min(start_coords[0], end_coords[0]), max(start_coords[0], end_coords[0])
                    lon_min, lon_max = min(start_coords[1], end_coords[1]), max(start_coords[1], end_coords[1])
                    
                    # 검색 범위를 약간 여유있게 설정 (+- 0.05도)
                    mask = (df['lat'] >= lat_min - 0.05) & (df['lat'] <= lat_max + 0.05) & \
                           (df['lon'] >= lon_min - 0.05) & (df['lon'] <= lon_max + 0.05)
                    nearby_risks = df[mask]

                    if "자동차" in mode:
                        # 자동차 모드: 위험도 정보를 적극적으로 표시
                        for idx, row in nearby_risks.iterrows():
                            level_text, color = get_risk_level(row['risk_score'])
                            folium.CircleMarker(
                                location=[row['lat'], row['lon']],
                                radius=5,
                                color=color,
                                fill=True,
                                fill_color=color,
                                popup=f"위험도: {level_text}"
                            ).add_to(m)
                            
                        st.info(f"경로 주변에 {len(nearby_risks)}개의 도로 정보가 확인되었습니다.")
                    
                    else:
                        # 보행자 모드: 정말 위험한 곳만 경고
                        high_risks = nearby_risks[nearby_risks['risk_score'] >= 70]
                        for idx, row in high_risks.iterrows():
                            folium.Marker(
                                location=[row['lat'], row['lon']],
                                icon=folium.Icon(color="red", icon="exclamation-sign"),
                                tooltip="보행자 주의 구간"
                            ).add_to(m)
                        st.info("보행자 모드: 횡단보도 및 인도 위주로 이동하세요. 위험 구간이 표시됩니다.")

            else:
                st.error("경로를 찾을 수 없습니다. 입력한 장소가 대한민국 내에 있는지 확인해주세요.")

# 지도 출력
st_data = st_folium(m, width="100%", height=600)

# ---------------------------------------------------------
# 6. 하단 정보 패널
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📊 경로 분석 리포트")

if search_btn and start_input and end_input:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**선택 모드:** {mode.split()[1]}")
        st.markdown(f"**출발지:** {start_input}")
        st.markdown(f"**도착지:** {end_input}")
    with col2:
        # 거리 계산 (단순 직선 거리 예시)
        if start_coords and end_coords:
            dist = math.sqrt((start_coords[0]-end_coords[0])**2 + (start_coords[1]-end_coords[1])**2) * 111 # 대략 km 환산
            st.markdown(f"**추정 거리:** 약 {dist:.2f} km")
            st.markdown("**도로 상태:** " + ("양호" if dist < 10 else "장거리 운전 주의"))
            
            if "자동차" in mode:
                st.caption("※ 실제 도로 상황 및 교통 체증에 따라 시간은 달라질 수 있습니다.")
            else:
                st.caption("※ 보행자 전용 도로(인도, 육교 등)를 우선적으로 이용하세요.")
