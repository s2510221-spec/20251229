import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
from pyproj import Transformer
import numpy as np
from scipy.spatial import cKDTree

# -----------------------------------------------------------
# 1. 페이지 설정 및 세션 상태 초기화 (경로 유지 기능)
# -----------------------------------------------------------
st.set_page_config(page_title="안전 경로 네비게이터", page_icon="🚗", layout="wide")

# 세션 상태 초기화: 버튼을 누르지 않아도 데이터가 남아있도록 함
if 'route_data' not in st.session_state:
    st.session_state['route_data'] = None
if 'nearby_risks' not in st.session_state:
    st.session_state['nearby_risks'] = pd.DataFrame()
if 'start_point' not in st.session_state:
    st.session_state['start_point'] = None
if 'end_point' not in st.session_state:
    st.session_state['end_point'] = None

st.title("🚗/🚶 안전 최단 경로 탐색기")

# -----------------------------------------------------------
# 2. 데이터 로드 및 전처리
# -----------------------------------------------------------
@st.cache_data
def load_and_process_data(filepath):
    try:
        df = pd.read_csv(filepath)
        
        # 좌표 변환 로직 (TM -> WGS84)
        # 데이터가 EPSG:5174 (한국 중부원점) 또는 유사 좌표계로 추정됨
        source_crs = "epsg:5174" 
        target_crs = "epsg:4326"
        
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        
        def transform_coords(row):
            easting = row['y좌표'] 
            northing = row['x좌표']
            lon, lat = transformer.transform(easting, northing)
            return pd.Series({'lat': lat, 'lon': lon})

        coords = df.apply(transform_coords, axis=1)
        df = pd.concat([df, coords], axis=1)
        
        # 노드명이 없거나 좌표가 없는 행 제거
        df = df.dropna(subset=['노드명', 'lat', 'lon'])
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

data_file = "20251229road_29최종.csv"
df_safety = load_and_process_data(data_file)

if df_safety.empty:
    st.warning("데이터 파일을 찾을 수 없습니다. 같은 폴더에 파일을 위치시켜주세요.")
    st.stop()

# -----------------------------------------------------------
# 3. 경로 탐색 API 함수
# -----------------------------------------------------------
def get_osrm_route(start_coords, end_coords, mode):
    base_url = f"http://router.project-osrm.org/route/v1/{mode}/"
    coords = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    url = f"{base_url}{coords}?overview=full&geometries=geojson"
    
    try:
        r = requests.get(url)
        if r.status_code != 200: return None
        res = r.json()
        if res.get("code") == "Ok":
            return res["routes"][0]
        return None
    except:
        return None

# -----------------------------------------------------------
# 4. 사이드바 UI (파일 내 노드명 선택)
# -----------------------------------------------------------
with st.sidebar:
    st.header("🔍 경로 설정")
    
    mode = st.radio("이동 수단 선택", ["자동차 (Car)", "보행자 (Walk)"])
    routing_mode = 'driving' if mode == "자동차 (Car)" else 'walking'
    st.markdown("---")

    # CSV 파일에서 노드명 목록 추출 및 정렬
    node_list = sorted(df_safety['노드명'].unique())
    
    # 텍스트 입력 대신 선택상자(Selectbox) 사용
    st.subheader("출발지/도착지 선택")
    
    # 기본값 설정을 위해 인덱스 지정 (에러 방지용)
    idx_start = 0
    idx_end = min(1, len(node_list)-1)
    
    start_node_name = st.selectbox("출발지 (데이터 목록)", node_list, index=idx_start)
    end_node_name = st.selectbox("도착지 (데이터 목록)", node_list, index=idx_end)
    
    search_btn = st.button("경로 찾기")

# -----------------------------------------------------------
# 5. 로직 실행 (버튼 클릭 시 Session State 업데이트)
# -----------------------------------------------------------
if search_btn:
    if start_node_name == end_node_name:
        st.error("출발지와 도착지가 같습니다. 다른 곳을 선택해주세요.")
    else:
        with st.spinner("경로를 탐색하고 안전 정보를 분석 중입니다..."):
            # 선택한 노드명의 좌표 가져오기
            try:
                start_row = df_safety[df_safety['노드명'] == start_node_name].iloc[0]
                end_row = df_safety[df_safety['노드명'] == end_node_name].iloc[0]
                
                s_lat, s_lon = start_row['lat'], start_row['lon']
                e_lat, e_lon = end_row['lat'], end_row['lon']
                
                # 경로 탐색 실행
                route_data = get_osrm_route((s_lat, s_lon), (e_lat, e_lon), routing_mode)
                
                if route_data:
                    # 결과를 Session State에 저장 (화면이 깜빡여도 유지됨)
                    st.session_state['route_data'] = route_data
                    st.session_state['start_point'] = (s_lat, s_lon, start_node_name)
                    st.session_state['end_point'] = (e_lat, e_lon, end_node_name)
                    
                    # 주변 위험도 분석
                    path_coords = route_data['geometry']['coordinates']
                    path_latlon = [[p[1], p[0]] for p in path_coords] 
                    
                    # KDTree로 경로 주변 검색
                    tree = cKDTree(df_safety[['lat', 'lon']].values)
                    path_points = np.array(path_latlon)
                    if len(path_points) > 100: path_points = path_points[::5] # 샘플링
                    
                    indices = tree.query_ball_point(path_points, r=0.003) # 반경 검색
                    unique_indices = set().union(*indices)
                    
                    st.session_state['nearby_risks'] = df_safety.iloc[list(unique_indices)]
                else:
                    st.error("경로를 찾을 수 없습니다. (도로 데이터가 없는 구간일 수 있습니다)")
            except Exception as e:
                st.error(f"좌표 처리 중 오류가 발생했습니다: {e}")

# -----------------------------------------------------------
# 6. 지도 및 결과 그리기 (Session State 기반)
# -----------------------------------------------------------

# 1. 지도 중심 설정
if st.session_state['start_point']:
    center_loc = [st.session_state['start_point'][0], st.session_state['start_point'][1]]
    zoom = 13
else:
    center_loc = [37.5665, 126.9780] # 기본값 서울
    zoom = 11

m = folium.Map(location=center_loc, zoom_start=zoom)

# 2. 경로 및 데이터가 있다면 지도에 표시
if st.session_state['route_data']:
    r_data = st.session_state['route_data']
    s_pt = st.session_state['start_point']
    e_pt = st.session_state['end_point']
    risks = st.session_state['nearby_risks']
    
    # 경로 라인
    path_coords = r_data['geometry']['coordinates']
    path_latlon = [[p[1], p[0]] for p in path_coords]
    
    folium.PolyLine(
        locations=path_latlon,
        color="blue" if routing_mode == 'walking' else "red",
        weight=6, opacity=0.8
    ).add_to(m)
    
    # 출발/도착 마커
    folium.Marker([s_pt[0], s_pt[1]], popup=f"출발: {s_pt[2]}", icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker([e_pt[0], e_pt[1]], popup=f"도착: {e_pt[2]}", icon=folium.Icon(color='black', icon='stop')).add_to(m)
    
    # 위험 정보 원형 마커
    color_map = {'A': 'blue', 'B': 'green', 'C': 'orange', 'D': 'red', 'E': 'black'}
    
    for _, row in risks.iterrows():
        grade = row['교차로안전등급']
        # 보행자 모드일 때는 위험한 곳만 보여주기 필터링 예시 (필요시 주석 해제)
        # if routing_mode == 'walking' and grade not in ['D', 'E']: continue
        
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=6,
            color=color_map.get(grade, 'gray'),
            fill=True, fill_opacity=0.7,
            popup=folium.Popup(f"<b>{row['노드명']}</b><br>등급: {grade}", max_width=200)
        ).add_to(m)

# 3. 지도 출력
st_folium(m, width=1000, height=600)

# 4. 통계 정보 (지도가 그려진 후에 아래에 표시)
if st.session_state['route_data']:
    dist = st.session_state['route_data']['distance'] / 1000
    dur = st.session_state['route_data']['duration'] / 60
    risk_count = len(st.session_state['nearby_risks'])
    
    st.subheader("📊 분석 결과")
    c1, c2, c3 = st.columns(3)
    c1.metric("총 거리", f"{dist:.2f} km")
    c2.metric("예상 시간", f"{dur:.0f} 분")
    c3.metric("경로상 안전정보 수", f"{risk_count} 개")
