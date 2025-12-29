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
    if not os.path.exists(file_path):
        st.error(f"❌ 파일이 없습니다: {file_path}")
        return pd.DataFrame()
    
    df = pd.DataFrame()
    encodings = ['cp949', 'utf-8', 'euc-kr']
    for enc in encodings:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            break 
        except UnicodeDecodeError:
            continue
        except Exception:
            pass

    if df.empty:
        st.error("❌ 파일을 읽지 못했습니다. 인코딩을 확인해주세요.")
        return pd.DataFrame()

    df.columns = df.columns.str.strip().str.lower()

    def find_column(candidates, columns):
        for col in columns:
            for cand in candidates:
                if cand == col or cand in col:
                    return col
        return None

    # (1) 위도 찾기
    lat_col = find_column(['lat', 'latitude', '위도', 'y'], df.columns)
    if lat_col:
        # 숫자로 강제 변환 (문자열이 섞여 있으면 NaN 처리 후 0으로)
        df['lat'] = pd.to_numeric(df[lat_col], errors='coerce').fillna(0)
    else:
        st.error("❌ '위도' 컬럼을 찾을 수 없습니다.")
        return pd.DataFrame()

    # (2) 경도 찾기
    lon_col = find_column(['lon', 'lng', 'longitude', '경도', 'x'], df.columns)
    if lon_col:
        df['lon'] = pd.to_numeric(df[lon_col], errors='coerce').fillna(0)
    else:
        st.error("❌ '경도' 컬럼을 찾을 수 없습니다.")
        return pd.DataFrame()

    # (3) 노드명 찾기
    desc_col = find_column(['노드명', '장소명', 'name', 'desc', '지점'], df.columns)
    if desc_col:
        df['desc'] = df[desc_col].astype(str)
    else:
        df['desc'] = "지점_" + df.index.astype(str)

    # (4) 위험도 찾기
    risk_col = find_column(['risk', 'score', '위험도', '등급'], df.columns)
    if risk_col:
        df['risk_score'] = pd.to_numeric(df[risk_col], errors='coerce').fillna(0)
    else:
        df['risk_score'] = 0

    return df

DATA_FILE = "20251229road_29최종.csv"
risk_data = load_data(DATA_FILE)

# ---------------------------------------------------------
# 2. 유틸리티 함수
# ---------------------------------------------------------
def get_coordinates_from_data(location_name, df):
    if df.empty: return None
    row = df[df['desc'] == location_name]
    if not row.empty:
        lat = row.iloc[0]['lat']
        lon = row.iloc[0]['lon']
        # 좌표 유효성 검사 (한국 범위 대략적 체크)
        if lat < 33 or lat > 39 or lon < 124 or lon > 132:
            st.toast(f"⚠️ 경고: {location_name}의 좌표({lat}, {lon})가 한국 범위를 벗어난 것 같습니다.")
        return lat, lon
    return None

@st.cache_resource
def get_graph(start_coords, end_coords, mode):
    # 거리 체크 (너무 멀면 서버 다운됨)
    lat_diff = abs(start_coords[0] - end_coords[0])
    lon_diff = abs(start_coords[1] - end_coords[1])
    
    # 대략 0.2도 차이(약 20km) 이상이면 경고 및 차단 가능성
    if lat_diff > 0.5 or lon_diff > 0.5:
        st.error(f"❌ 거리가 너무 멉니다! (위도차: {lat_diff:.2f}, 경도차: {lon_diff:.2f}). 가까운 거리만 탐색 가능합니다.")
        return None

    # BBox 설정 (순서 중요: North, South, East, West)
    margin = 0.01
    north = max(start_coords[0], end_coords[0]) + margin
    south = min(start_coords[0], end_coords[0]) - margin
    east = max(start_coords[1], end_coords[1]) + margin
    west = min(start_coords[1], end_coords[1]) - margin

    network_type = 'drive' if mode == '자동차 모드' else 'walk'
    
    try:
        # 실제 다운로드 시도
        G = ox.graph_from_bbox(north, south, east, west, network_type=network_type, simplify=True)
        return G
    except Exception as e:
        # **핵심 수정: 진짜 에러 메시지를 반환**
        st.error(f"🔍 지도 다운로드 실패 원인: {e}")
        return None

def match_risk_data(G, route, risk_df):
    if risk_df.empty or route is None: return []

    route_nodes = []
    for node_id in route:
        node = G.nodes[node_id]
        route_nodes.append((node['y'], node['x'])) 

    data_coords = list(zip(risk_df['lat'], risk_df['lon']))
    tree = cKDTree(data_coords)
    
    route_risks = []
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
st.title("🚗🛡️ 안전 경로 네비게이터 (Debug Ver.)")

if risk_data.empty:
    st.warning("데이터 로드 실패.")
else:
    st.sidebar.header("경로 설정")
    mode = st.sidebar.radio("이동 수단", ["자동차 모드", "보행자 모드"])

    location_list = sorted(risk_data['desc'].unique().tolist())
    
    if len(location_list) < 2:
        st.sidebar.warning("데이터 부족: 장소가 2개 이상이어야 합니다.")
        start_select = st.sidebar.selectbox("출발지", location_list)
        end_select = start_select
    else:
        start_select = st.sidebar.selectbox("출발지", location_list, index=0)
        end_select = st.sidebar.selectbox("도착지", location_list, index=1)

    search_btn = st.sidebar.button("경로 탐색 시작")

    if search_btn:
        if start_select == end_select:
            st.error("출발지와 도착지가 같습니다.")
        else:
            with st.spinner('좌표 확인 및 지도 다운로드 중...'):
                start_coords = get_coordinates_from_data(start_select, risk_data)
                end_coords = get_coordinates_from_data(end_select, risk_data)

                # 디버깅용 좌표 출력
                st.info(f"📍 좌표 확인 | 출발: {start_coords} / 도착: {end_coords}")

                if start_coords and end_coords:
                    # 0,0 좌표 체크
                    if start_coords == (0,0) or end_coords == (0,0):
                        st.error("❌ 좌표가 (0,0)으로 나옵니다. 데이터 파일의 위도/경도 값을 확인해주세요.")
                    else:
                        G = get_graph(start_coords, end_coords, mode)
                        
                        if G:
                            orig_node = ox.distance.nearest_nodes(G, start_coords[1], start_coords[0])
                            dest_node = ox.distance.nearest_nodes(G, end_coords[1], end_coords[0])

                            try:
                                route = nx.shortest_path(G, orig_node, dest_node, weight='length')
                                route_len = nx.path_weight(G, route, weight='length')
                                matched_risks = match_risk_data(G, route, risk_data)

                                center_lat = (start_coords[0] + end_coords[0]) / 2
                                center_lon = (start_coords[1] + end_coords[1]) / 2
                                m = folium.Map(location=[center_lat, center_lon], zoom_start=14)

                                line_color = 'blue' if mode == '자동차 모드' else 'green'
                                line_style = '10, 10' if mode == '보행자 모드' else None
                                
                                ox.plot_route_folium(G, route, m, color=line_color, weight=5, opacity=0.7, dash_array=line_style)

                                folium.Marker(start_coords, tooltip="출발", icon=folium.Icon(color='green', icon='play')).add_to(m)
                                folium.Marker(end_coords, tooltip="도착", icon=folium.Icon(color='red', icon='stop')).add_to(m)

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
                                st_folium(m, width=800, height=500)

                            except nx.NetworkXNoPath:
                                st.error("❌ 경로 없음: 두 지점이 연결되어 있지 않습니다.")
                            except Exception as e:
                                st.error(f"❌ 경로 계산 오류: {e}")
                        else:
                            st.warning("지도를 불러오는 데 실패했습니다. (위의 에러 메시지를 확인하세요)")
