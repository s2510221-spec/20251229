import streamlit as st
import pandas as pd
import osmnx as ox
import networkx as nx
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from scipy.spatial import cKDTree
import numpy as np
import os  # <--- 이 부분이 추가되었습니다.

# ---------------------------------------------------------
# 1. 설정 및 데이터 로드
# ---------------------------------------------------------
st.set_page_config(page_title="안전 경로 네비게이터", layout="wide")

@st.cache_data
def load_data(file_path):
    """
    사용자의 도로 안전 데이터를 로드합니다.
    파일이 없을 경우를 대비한 예외처리가 포함되어 있습니다.
    """
    # os 모듈이 import 되어 있어야 이 줄이 작동합니다.
    if not os.path.exists(file_path):
        st.error(f"데이터 파일({file_path})을 찾을 수 없습니다. 프로젝트 폴더(app.py와 같은 위치)에 파일을 넣어주세요.")
        # 파일이 없을 때 앱이 멈추지 않도록 빈 데이터프레임 반환
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(file_path)
        # CSV 파일 로드 성공
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

# 데이터 파일 이름 (사용자 지정)
DATA_FILE = "20251229road_29최종.csv"
risk_data = load_data(DATA_FILE)

# 지오코더 설정 (주소 -> 좌표 변환)
geolocator = Nominatim(user_agent="safe_route_app_kr")

# ---------------------------------------------------------
# 2. 유틸리티 함수 (좌표변환, 그래프 다운로드)
# ---------------------------------------------------------
def get_coordinates(address):
    """주소를 입력받아 (위도, 경도)를 반환합니다. 한국 한정 검색."""
    try:
        # 정확도를 위해 'South Korea'를 검색어에 추가
        loc = geolocator.geocode(f"{address}, South Korea", timeout=10)
        if loc:
            return loc.latitude, loc.longitude
        return None
    except (GeocoderTimedOut, Exception):
        return None

@st.cache_resource
def get_graph(start_coords, end_coords, mode):
    """
    출발지와 도착지를 포함하는 범위의 도로망 그래프를 다운로드합니다.
    Streamlit Cloud 메모리 절약을 위해 전체 지도가 아닌 Bounding Box만 가져옵니다.
    """
    # 여유 반경 설정 (단위: degree, 약 0.01 ~ 1km)
    margin = 0.01 
    north = max(start_coords[0], end_coords[0]) + margin
    south = min(start_coords[0], end_coords[0]) - margin
    east = max(start_coords[1], end_coords[1]) + margin
    west = min(start_coords[1], end_coords[1]) - margin

    network_type = 'drive' if mode == '자동차 모드' else 'walk'
    
    try:
        # 사용자 정의 필터로 그래프 다운로드 (bbox 방식)
        G = ox.graph_from_bbox(north, south, east, west, network_type=network_type, simplify=True)
        return G
    except Exception as e:
        return None

def match_risk_data(G, route, risk_df):
    """
    계산된 경로 주변의 위험도 데이터를 매칭합니다.
    경로상의 노드와 CSV 데이터의 가장 가까운 점을 찾습니다.
    """
    if risk_df.empty or route is None:
        return []

    # 경로상의 노드 좌표 추출
    route_nodes = []
    for node_id in route:
        node = G.nodes[node_id]
        route_nodes.append((node['y'], node['x'])) # lat, lon

    # 데이터프레임 컬럼 확인 및 매핑 (사용자 데이터에 맞게 조정 필요)
    # 기본적으로 'lat', 'lon', 'risk_score' 컬럼이 있다고 가정
    # 만약 에러가 난다면 이 부분에서 컬럼명을 확인해야 합니다.
    lat_col = 'lat'
    lon_col = 'lon'
    risk_col = 'risk_score'
    desc_col = 'desc'

    # CSV에 해당 컬럼이 있는지 확인
    if lat_col not in risk_df.columns or lon_col not in risk_df.columns:
        # 컬럼이 없을 경우 매칭하지 않고 빈 리스트 반환 (에러 방지)
        return []

    # CSV 데이터 좌표 KDTree 생성 (빠른 검색용)
    data_coords = list(zip(risk_df[lat_col], risk_df[lon_col]))
    tree = cKDTree(data_coords)
    
    route_risks = []
    # 각 경로 포인트에서 가장 가까운 위험 데이터 찾기 (반경 50m 이내)
    dists, idxs = tree.query(route_nodes, k=1, distance_upper_bound=0.0005) # 약 50m
    
    for i, (dist, idx) in enumerate(zip(dists, idxs)):
        if dist != float('inf'): # 매칭된 데이터가 있으면
            info = risk_df.iloc[idx]
            route_risks.append({
                'lat': route_nodes[i][0],
                'lon': route_nodes[i][1],
                'risk': info.get(risk_col, 0),
                'desc': info.get(desc_col, '정보 없음')
            })
    return route_risks

# ---------------------------------------------------------
# 3. UI 및 메인 로직
# ---------------------------------------------------------
st.title("🚗🛡️ 안전 경로 네비게이터 (South Korea)")
st.markdown("""
이 앱은 **최단 거리**를 기반으로 하되, 도로의 **안전 정보(위험도)**를 함께 시각화하여 
운전자와 보행자의 안전한 이동을 돕습니다.
""")

# 사이드바: 입력 컨트롤
st.sidebar.header("설정 및 입력")
mode = st.sidebar.radio("이동 수단 선택", ["자동차 모드", "보행자 모드"])

start_input = st.sidebar.text_input("출발지 (예: 서울역)", "서울시청")
end_input = st.sidebar.text_input("도착지 (예: 강남역)", "광화문")

search_btn = st.sidebar.button("경로 탐색 시작")

# 설명 영역
col1, col2 = st.columns(2)
with col1:
    st.info(f"**현재 모드:** {mode}")
    if mode == '자동차 모드':
        st.write("🛣️ 차량 진입 가능 도로 위주 안내 + 도로 위험도 표시")
    else:
        st.write("🚶 인도, 횡단보도 포함 최단 거리 + 보행자 안전 정보")

# ---------------------------------------------------------
# 4. 경로 탐색 실행
# ---------------------------------------------------------
if search_btn:
    with st.spinner('위치 정보를 확인하고 경로를 계산 중입니다...'):
        # 1. 지오코딩
        start_coords = get_coordinates(start_input)
        end_coords = get_coordinates(end_input)

        if not start_coords or not end_coords:
            st.error("❌ 출발지 또는 도착지의 위치를 찾을 수 없습니다. 정확한 도로명 주소나 주요 건물명을 입력해주세요.")
        else:
            # 2. 그래프 다운로드 및 경로 계산
            G = get_graph(start_coords, end_coords, mode)
            
            if G is None:
                st.error("⚠️ 해당 지역의 도로 정보를 가져올 수 없거나 너무 먼 거리입니다. (메모리 제한으로 인해 가까운 지역만 검색 가능)")
            else:
                # 시작/종료점의 가장 가까운 노드 찾기
                orig_node = ox.distance.nearest_nodes(G, start_coords[1], start_coords[0])
                dest_node = ox.distance.nearest_nodes(G, end_coords[1], end_coords[0])

                try:
                    # 최단 경로 계산 (Dijkstra)
                    route = nx.shortest_path(G, orig_node, dest_node, weight='length')
                    
                    # 경로 길이 계산
                    route_len = nx.path_weight(G, route, weight='length')
                    
                    # 3. 위험도 매칭
                    matched_risks = match_risk_data(G, route, risk_data)

                    # 4. 지도 시각화
                    m = folium.Map(location=start_coords, zoom_start=14)
                    
                    # 경로 그리기
                    # 자동차는 파란색 실선, 보행자는 초록색 점선 스타일
                    line_color = 'blue' if mode == '자동차 모드' else 'green'
                    line_style = '10, 10' if mode == '보행자 모드' else None
                    
                    ox.plot_route_folium(G, route, m, color=line_color, weight=5, opacity=0.7, dash_array=line_style)

                    # 출발/도착 마커
                    folium.Marker(start_coords, tooltip="출발", icon=folium.Icon(color='green', icon='play')).add_to(m)
                    folium.Marker(end_coords, tooltip="도착", icon=folium.Icon(color='red', icon='stop')).add_to(m)

                    # 5. 위험/안전 정보 오버레이 (성공 지표 시각화)
                    safe_count = 0
                    danger_count = 0
                    
                    for info in matched_risks:
                        risk = info['risk']
                        # 위험도가 높으면 빨간 원, 낮으면 파란 원
                        color = 'red' if risk >= 50 else 'blue'
                        radius = 10 if risk >= 50 else 5
                        
                        if risk >= 50: danger_count += 1
                        else: safe_count += 1

                        folium.CircleMarker(
                            location=[info['lat'], info['lon']],
                            radius=radius,
                            color=color,
                            fill=True,
                            fill_color=color,
                            tooltip=f"위험도: {risk} / {info['desc']}"
                        ).add_to(m)

                    # 결과 출력
                    st.success(f"✅ 경로 탐색 완료! (총 거리: {route_len/1000:.2f} km)")
                    
                    # 통계 지표
                    st.metric(label="탐지된 위험/주의 구간 수", value=f"{danger_count} 곳")
                    
                    if danger_count > 0:
                        st.warning("⚠️ 경로 상에 주의가 필요한 구간이 있습니다. 지도상의 빨간 점을 확인하세요.")

                    # 지도 표시
                    st_folium(m, width=725, height=500)

                except nx.NetworkXNoPath:
                    st.error("❌ 경로를 찾을 수 없습니다. (도로가 연결되어 있지 않거나 너무 먼 거리)")
                except Exception as e:
                    st.error(f"❌ 시스템 오류 발생: {e}")

else:
    # 초기 화면 지도 표시 (서울 중심)
    m_default = folium.Map(location=[37.5665, 126.9780], zoom_start=11)
    st_folium(m_default, width=725, height=500)
