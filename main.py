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
# 1. 설정 및 데이터 로드 (강력해진 버전)
# ---------------------------------------------------------
st.set_page_config(page_title="안전 경로 네비게이터", layout="wide")

@st.cache_data
def load_data(file_path):
    """
    데이터 로드 및 컬럼 자동 찾기 기능이 포함된 함수
    """
    if not os.path.exists(file_path):
        st.error(f"❌ 파일이 없습니다: {file_path}")
        return pd.DataFrame()
    
    df = pd.DataFrame()
    
    # 1. 인코딩 자동 감지 시도
    encodings = ['cp949', 'utf-8', 'euc-kr']
    for enc in encodings:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            # 성공하면 반복문 탈출
            break 
        except UnicodeDecodeError:
            continue
        except Exception as e:
            st.error(f"파일 읽기 오류 ({enc}): {e}")
            return pd.DataFrame()

    if df.empty:
        st.error("❌ 파일을 읽었으나 데이터가 비어있거나, 인코딩 문제로 읽지 못했습니다.")
        return pd.DataFrame()

    # 2. 컬럼 이름 정리 (공백 제거 및 소문자 변환)
    # 예: ' 위도 ' -> '위도', 'LAT ' -> 'lat'
    df.columns = df.columns.str.strip().str.lower()

    # 디버깅용: 사용자가 컬럼명을 확인할 수 있게 출력 (사이드바)
    with st.sidebar.expander("🛠️ 파일 컬럼명 확인 (디버깅)"):
        st.write("읽어온 파일의 컬럼 목록:")
        st.write(df.columns.tolist())

    # 3. 유연하게 컬럼 찾기 함수
    def find_column(candidates, columns):
        for col in columns:
            for cand in candidates:
                # 정확히 일치하거나, 해당 단어가 포함되어 있으면 선택
                if cand == col or cand in col:
                    return col
        return None

    # (1) 위도 찾기 (lat, latitude, 위도, y 등)
    lat_col = find_column(['lat', 'latitude', '위도', 'y좌표', 'y'], df.columns)
    if lat_col:
        df['lat'] = df[lat_col]
    else:
        st.error(f"❌ '위도' 정보를 찾을 수 없습니다. (현재 컬럼: {df.columns.tolist()})")
        return pd.DataFrame()

    # (2) 경도 찾기 (lon, lng, longitude, 경도, x 등)
    lon_col = find_column(['lon', 'lng', 'longitude', '경도', 'x좌표', 'x'], df.columns)
    if lon_col:
        df['lon'] = df[lon_col]
    else:
        st.error(f"❌ '경도' 정보를 찾을 수 없습니다. (현재 컬럼: {df.columns.tolist()})")
        return pd.DataFrame()

    # (3) 노드명(장소명) 찾기
    desc_col = find_column(['노드명', '장소명', 'name', 'place', 'desc', '지점'], df.columns)
    if desc_col:
        df['desc'] = df[desc_col]
    else:
        # 없으면 인덱스를 사용하여 임시 이름 생성
        df['desc'] = "지점_" + df.index.astype(str)

    # (4) 위험도 찾기
    risk_col = find_column(['risk', 'score', '위험도', '점수', '등급'], df.columns)
    if risk_col:
        df['risk_score'] = df[risk_col].fillna(0) # 결측치는 0으로
    else:
        df['risk_score'] = 0 # 없으면 모두 0점 처리

    return df

# 데이터 파일 이름
DATA_FILE = "20251229road_29최종.csv"
risk_data = load_data(DATA_FILE)

# ---------------------------------------------------------
# 2. 유틸리티 함수
# ---------------------------------------------------------
def get_coordinates_from_data(location_name, df):
    if df.empty: return None
    row = df[df['desc'] == location_name]
    if not row.empty:
        return row.iloc[0]['lat'], row.iloc[0]['lon']
    return None

@st.cache_resource
def get_graph(start_coords, end_coords, mode):
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
    if risk_df.empty or route is None: return []

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

if risk_data.empty:
    st.warning("⚠️ 데이터를 불러오지 못해 앱을 실행할 수 없습니다. 위의 에러 메시지와 왼쪽 사이드바의 컬럼명을 확인해주세요.")
else:
    # 사이드바 설정
    st.sidebar.header("경로 설정")
    mode = st.sidebar.radio("이동 수단", ["자동차 모드", "보행자 모드"])

    # 장소 목록 (가나다순 정렬)
    # 데이터가 모두 문자열인지 확인 후 정렬
    location_list = sorted(risk_data['desc'].astype(str).unique().tolist())
    
    st.sidebar.subheader("출발/도착지 선택")
    
    if len(location_list) < 2:
        st.sidebar.warning(f"장소가 {len(location_list)}개 뿐입니다. 최소 2개가 필요합니다.")
        start_select = st.sidebar.selectbox("출발지", location_list)
        end_select = start_select
    else:
        start_select = st.sidebar.selectbox("출발지", location_list, index=0)
        end_select = st.sidebar.selectbox("도착지", location_list, index=1)

    search_btn = st.sidebar.button("경로 탐색 시작")

    # 데이터 미리보기 (제대로 매핑되었는지 확인)
    with st.expander("📊 로드된 데이터 및 매핑 결과 확인"):
        st.dataframe(risk_data[['desc', 'lat', 'lon', 'risk_score']].head())

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
                            st.error("경로를 찾을 수 없습니다. (도로 연결 끊김)")
                        except Exception as e:
                            st.error(f"지도 처리 오류: {e}")
                    else:
                        st.error("지도 데이터를 불러올 수 없습니다.")
