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
import os

# ---------------------------------------------------------
# 1. 설정 및 데이터 로드
# ---------------------------------------------------------
st.set_page_config(page_title="안전 경로 네비게이터", layout="wide")

@st.cache_data
def load_data(file_path):
    """
    사용자의 도로 안전 데이터를 로드합니다.
    데이터 파일이 없을 경우 빈 데이터프레임을 반환합니다.
    """
    if not os.path.exists(file_path):
        st.error(f"데이터 파일({file_path})을 찾을 수 없습니다. 프로젝트 폴더에 파일을 넣어주세요.")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(file_path)
        # 데이터 전처리: 컬럼명 매핑 (사용자 CSV에 맞춰 수정 필요)
        # 예: '위도' -> 'lat', '경도' -> 'lon' 등이 필요할 수 있음
        # 여기서는 CSV에 lat, lon, desc(또는 장소명)이 있다고 가정합니다.
        
        # 장소 이름으로 쓸 컬럼 찾기 (없으면 좌표를 이름으로 생성)
        if 'desc' not in df.columns:
            if '장소명' in df.columns:
                df['desc'] = df['장소명']
            else:
                # 장소명이 없으면 좌표를 문자열로 만들어 사용
                df['desc'] = df.apply(lambda row: f"위치({row.get('lat',0):.4f}, {row.get('lon',0):.4f})", axis=1)
                
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

# 데이터 파일 이름
DATA_FILE = "20251229road_29최종.csv"
risk_data = load_data(DATA_FILE)

# 지오코더 설정 (주소 -> 좌표 변환용, 데이터 외 장소 검색시 필요)
geolocator = Nominatim(user_agent="safe_route_app_kr")

# ---------------------------------------------------------
# 2. 유틸리티 함수
# ---------------------------------------------------------
def get_coordinates_from_data(location_name, df):
    """데이터프레임에서 선택한 장소의 좌표를 반환합니다."""
    if df.empty:
        return None
    
    row = df[df['desc'] == location_name]
    if not row.empty:
        # 첫 번째 일치하는 행의 위도, 경도 반환
        return row.iloc[0]['lat'], row.iloc[0]['lon']
    return None

@st.cache_resource
def get_graph(start_coords, end_coords, mode):
    """
    출발지와 도착지 범위를 계산하여 도로망 그래프를 다운로드합니다.
    """
    # 여유 반경 설정 (단위: degree)
    margin = 0.015  # 범위를 조금 더 넓게 잡음
    north = max(start_coords[0], end_coords[0]) + margin
    south = min(start_coords[0], end_coords[0]) - margin
    east = max(start_coords[1], end_coords[1]) + margin
    west = min(start_coords[1], end_coords[1]) - margin

    network_type = 'drive' if mode == '자동차 모드' else 'walk'
    
    try:
        G = ox.graph_from_bbox(north, south, east, west, network_type=network_type, simplify=True)
        return G
    except Exception as e:
        return None

def match_risk_data(G, route, risk_df):
    """경로 주변의 위험도 데이터를 매칭합니다."""
    if risk_df.empty or route is None:
        return []

    route_nodes = []
    for node_id in route:
        node = G.nodes[node_id]
        route_nodes.append((node['y'], node['x'])) 

    # 필수 컬럼 확인
    if 'lat' not in risk_df.columns or 'lon' not in risk_df.columns:
        return []

    data_coords = list(zip(risk_df['lat'], risk_df['lon']))
    tree = cKDTree(data_coords)
    
    route_risks = []
    # 반경 50m (약 0.0005도) 이내 데이터 검색
    dists, idxs = tree.query(route_nodes, k=1, distance_upper_bound=0.0005)
    
    for i, (dist, idx) in enumerate(zip(dists, idxs)):
        if dist != float('inf'):
            info = risk_df.iloc[idx]
            route_risks.append({
                'lat': route_nodes[i][0],
                'lon': route_nodes[i][1],
                'risk': info.get('risk_score', 0),
                'desc': info.get('desc', '정보 없음')
            })
    return route_risks

# ---------------------------------------------------------
# 3. UI 및 메인 로직
# ---------------------------------------------------------
st.title("🚗🛡️ 안전 경로 네비게이터 (South Korea)")
st.markdown("데이터에 등록된 **장소 목록**에서 출발지와 도착지를 선택하여 안전한 경로를 탐색하세요.")

# 사이드바 설정
st.sidebar.header("설정 및 경로 선택")
mode = st.sidebar.radio("이동 수단", ["자동차 모드", "보행자 모드"])

# [수정됨] 텍스트 입력 대신 데이터 기반 선택 박스(Selectbox) 사용
if not risk_data.empty:
    location_list = risk_data['desc'].unique().tolist()
    # 선택 박스 생성
    start_select = st.sidebar.selectbox("출발지 선택", location_list, index=0)
    # 도착지는 출발지와 다르게 기본값 설정 (리스트에 2개 이상 있을 때)
    default_end_idx = 1 if len(location_list) > 1 else 0
    end_select = st.sidebar.selectbox("도착지 선택", location_list, index=default_end_idx)
else:
    st.sidebar.error("데이터 파일이 없거나 비어있어 장소 목록을 불러올 수 없습니다.")
    start_select = None
    end_select = None

search_btn = st.sidebar.button("경로 탐색 시작")

# 메인 화면 로직
if search_btn and start_select and end_select:
    if start_select == end_select:
        st.error("❌ 출발지와 도착지가 같습니다. 다른 장소를 선택해주세요.")
    else:
        with st.spinner(f"'{start_select}'에서 '{end_select}'까지 경로 계산 중..."):
            # 1. 선택된 장소의 좌표 가져오기
            start_coords = get_coordinates_from_data(start_select, risk_data)
            end_coords = get_coordinates_from_data(end_select, risk_data)

            if start_coords and end_coords:
                # 2. 그래프 다운로드 및 경로 계산
                G = get_graph(start_coords, end_coords, mode)
                
                if G is None:
                    st.error("⚠️ 지도 데이터를 가져올 수 없습니다. (두 지점 거리가 너무 멀거나 네트워크 오류)")
                else:
                    orig_node = ox.distance.nearest_nodes(G, start_coords[1], start_coords[0])
                    dest_node = ox.distance.nearest_nodes(G, end_coords[1], end_coords[0])

                    try:
                        route = nx.shortest_path(G, orig_node, dest_node, weight='length')
                        route_len = nx.path_weight(G, route, weight='length')
                        
                        # 3. 위험도 매칭 및 지도 생성
                        matched_risks = match_risk_data(G, route, risk_data)
                        
                        # 지도 중심 잡기 (출발지와 도착지의 중간 지점)
                        center_lat = (start_coords[0] + end_coords[0]) / 2
                        center_lon = (start_coords[1] + end_coords[1]) / 2
                        m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
                        
                        # 스타일 설정
                        line_color = 'blue' if mode == '자동차 모드' else 'green'
                        line_style = '10, 10' if mode == '보행자 모드' else None
                        
                        ox.plot_route_folium(G, route, m, color=line_color, weight=5, opacity=0.7, dash_array=line_style)

                        # 마커 추가
                        folium.Marker(start_coords, tooltip=f"출발: {start_select}", icon=folium.Icon(color='green', icon='play')).add_to(m)
                        folium.Marker(end_coords, tooltip=f"도착: {end_select}", icon=folium.Icon(color='red', icon='stop')).add_to(m)

                        # 위험 정보 표시
                        danger_count = 0
                        for info in matched_risks:
                            risk = info['risk']
                            color = 'red' if risk >= 50 else 'blue'
                            if risk >= 50: danger_count += 1
                            
                            folium.CircleMarker(
                                location=[info['lat'], info['lon']],
                                radius=5, color=color, fill=True, fill_color=color,
                                tooltip=f"{info['desc']} (위험도: {risk})"
                            ).add_to(m)

                        st.success(f"✅ 경로 탐색 완료! (거리: {route_len/1000:.2f} km)")
                        if danger_count > 0:
                            st.warning(f"⚠️ 경로 상에 위험도 높은 구간이 {danger_count}곳 있습니다.")
                        
                        st_folium(m, width=800, height=500)

                    except nx.NetworkXNoPath:
                        st.error("❌ 연결된 도로를 찾을 수 없습니다. (너무 먼 거리거나 경로 없음)")
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
            else:
                st.error("좌표 정보를 찾을 수 없습니다.")
else:
    # 초기 화면 안내
    st.info("👈 왼쪽 사이드바에서 출발지와 도착지를 선택하고 '경로 탐색 시작' 버튼을 눌러주세요.")
    # 기본 지도 표시
    m_default = folium.Map(location=[36.5, 127.5], zoom_start=7)
    st_folium(m_default, width=800, height=400)
