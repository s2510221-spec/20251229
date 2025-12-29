import streamlit as st
import pandas as pd
import osmnx as ox
import networkx as nx
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from scipy.spatial import cKDTree
import os

# ---------------------------------------------------------
# 1. 설정 및 데이터 로드
# ---------------------------------------------------------
st.set_page_config(page_title="안전 경로 네비게이터", layout="wide")

@st.cache_data
def load_data(file_path):
    """
    사용자의 도로 안전 데이터를 로드합니다.
    한글 깨짐 방지 및 컬럼 매핑 로직이 포함되어 있습니다.
    """
    if not os.path.exists(file_path):
        st.error(f"데이터 파일({file_path})을 찾을 수 없습니다.")
        return pd.DataFrame()
    
    df = pd.DataFrame()
    # 1. 인코딩 시도 (한글 CSV는 cp949 또는 euc-kr인 경우가 많음)
    try:
        df = pd.read_csv(file_path, encoding='cp949')
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except Exception as e:
            st.error(f"파일 인코딩 오류: {e}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"데이터 로드 중 알 수 없는 오류: {e}")
        return pd.DataFrame()

    # 2. 컬럼명 공백 제거 (예: ' 노드명 ' -> '노드명')
    df.columns = df.columns.str.strip()

    # 3. 필수 컬럼 확인 및 이름 통일
    # 사용자가 요청한 '노드명'을 'desc'로, '위도'/'경도'를 'lat'/'lon'으로 매핑
    
    # (1) 장소 이름 매핑
    if '노드명' in df.columns:
        df['desc'] = df['노드명']
    elif 'desc' not in df.columns:
        # 노드명이 없으면 첫 번째 문자열 컬럼을 사용하거나 임의 생성
        st.warning("'노드명' 컬럼을 찾을 수 없어 임시 이름을 생성합니다.")
        df['desc'] = df.index.astype(str) + "_지점"

    # (2) 위도 매핑
    if 'lat' not in df.columns:
        if '위도' in df.columns:
            df['lat'] = df['위도']
        else:
            st.error("CSV 파일에 '위도' 또는 'lat' 컬럼이 없습니다.")
            return pd.DataFrame()

    # (3) 경도 매핑
    if 'lon' not in df.columns:
        if '경도' in df.columns:
            df['lon'] = df['경도']
        else:
            st.error("CSV 파일에 '경도' 또는 'lon' 컬럼이 없습니다.")
            return pd.DataFrame()

    # (4) 위험도 매핑 (없으면 0으로 처리)
    if 'risk_score' not in df.columns:
        if '위험도' in df.columns:
            df['risk_score'] = df['위험도']
        else:
            df['risk_score'] = 0 # 기본값

    return df

# 데이터 파일 이름
DATA_FILE = "20251229road_29최종.csv"
risk_data = load_data(DATA_FILE)

# ---------------------------------------------------------
# 2. 유틸리티 함수
# ---------------------------------------------------------
def get_coordinates_from_data(location_name, df):
    """선택한 '노드명'에 해당하는 좌표 반환"""
    if df.empty:
        return None
    
    row = df[df['desc'] == location_name]
    if not row.empty:
        return row.iloc[0]['lat'], row.iloc[0]['lon']
    return None

@st.cache_resource
def get_graph(start_coords, end_coords, mode):
    """도로망 그래프 다운로드 (Bbox)"""
    # 범위 설정
    margin = 0.015
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
    """경로 주변 위험 데이터 매칭"""
    if risk_df.empty or route is None:
        return []

    route_nodes = []
    for node_id in route:
        node = G.nodes[node_id]
        route_nodes.append((node['y'], node['x'])) 

    data_coords = list(zip(risk_df['lat'], risk_df['lon']))
    tree = cKDTree(data_coords)
    
    route_risks = []
    # 반경 약 50m 검색
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
# 3. UI 구성
# ---------------------------------------------------------
st.title("🚗🛡️ 안전 경로 네비게이터 (South Korea)")

# 데이터 로드 상태 확인 (디버깅용)
if risk_data.empty:
    st.error("데이터를 불러오지 못했습니다. CSV 파일을 확인해주세요.")
else:
    # 사이드바 설정
    st.sidebar.header("경로 설정")
    mode = st.sidebar.radio("이동 수단", ["자동차 모드", "보행자 모드"])

    # '노드명' 리스트 추출 (중복 제거)
    location_list = sorted(risk_data['desc'].unique().tolist())
    
    st.sidebar.subheader("출발/도착지 선택")
    
    # 목록이 하나만 뜨는 경우를 대비해 예외 처리
    if len(location_list) < 2:
        st.sidebar.warning("데이터에 등록된 지역(노드명)이 2개 미만입니다.")
        start_select = st.sidebar.selectbox("출발지", location_list)
        end_select = start_select
    else:
        start_select = st.sidebar.selectbox("출발지", location_list, index=0)
        end_select = st.sidebar.selectbox("도착지", location_list, index=1)

    search_btn = st.sidebar.button("경로 탐색 시작")

    # 데이터 미리보기 (제대로 읽혔는지 확인용, 필요 시 주석 처리 가능)
    with st.expander("📊 로드된 데이터 확인하기 (클릭)"):
        st.dataframe(risk_data.head())

    # 경로 탐색 로직
    if search_btn:
        if start_select == end_select:
            st.error("출발지와 도착지가 동일합니다.")
        else:
            with st.spinner('경로를 계산하고 있습니다...'):
                start_coords = get_coordinates_from_data(start_select, risk_data)
                end_coords = get_coordinates_from_data(end_select, risk_data)

                if start_coords and end_coords:
                    G = get_graph(start_coords, end_coords, mode)
                    
                    if G:
                        orig_node = ox.distance.nearest_nodes(G, start_coords[1], start_coords[0])
                        dest_node = ox.distance.nearest_nodes(G, end_coords[1], end_coords[0])

                        try:
                            route = nx.shortest_path(G, orig_node, dest_node, weight='length')
                            route_len = nx.path_weight(G, route, weight='length')
                            matched_risks = match_risk_data(G, route, risk_data)

                            # 지도 생성
                            center_lat = (start_coords[0] + end_coords[0]) / 2
                            center_lon = (start_coords[1] + end_coords[1]) / 2
                            m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

                            # 스타일
                            line_color = 'blue' if mode == '자동차 모드' else 'green'
                            line_style = '10, 10' if mode == '보행자 모드' else None
                            
                            ox.plot_route_folium(G, route, m, color=line_color, weight=5, opacity=0.7, dash_array=line_style)

                            # 마커
                            folium.Marker(start_coords, tooltip=f"출발: {start_select}", icon=folium.Icon(color='green', icon='play')).add_to(m)
                            folium.Marker(end_coords, tooltip=f"도착: {end_select}", icon=folium.Icon(color='red', icon='stop')).add_to(m)

                            # 위험도 오버레이
                            danger_count = 0
                            for info in matched_risks:
                                risk = info['risk']
                                if risk >= 50:
                                    danger_count += 1
                                    color = 'red'
                                    folium.CircleMarker(
                                        location=[info['lat'], info['lon']],
                                        radius=5, color=color, fill=True, fill_color=color,
                                        tooltip=f"{info['desc']} (위험도: {risk})"
                                    ).add_to(m)

                            st.success(f"이동 거리: {route_len/1000:.2f} km")
                            if danger_count > 0:
                                st.warning(f"경로상 위험 구간: {danger_count}곳")
                            
                            st_folium(m, width=800, height=500)

                        except nx.NetworkXNoPath:
                            st.error("경로를 찾을 수 없습니다.")
                        except Exception as e:
                            st.error(f"오류: {e}")
                    else:
                        st.error("지도 데이터를 불러올 수 없습니다.")
