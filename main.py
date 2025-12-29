import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
from pyproj import Transformer
import numpy as np
from scipy.spatial import cKDTree

# -----------------------------------------------------------
# 1. 페이지 설정 및 세션 상태 초기화
# -----------------------------------------------------------
st.set_page_config(page_title="안전 경로 네비게이터", page_icon="🚗", layout="wide")

# 세션 상태 초기화
if 'route_data' not in st.session_state:
    st.session_state['route_data'] = None
if 'nearby_risks' not in st.session_state:
    st.session_state['nearby_risks'] = pd.DataFrame()
if 'start_point' not in st.session_state:
    st.session_state['start_point'] = None
if 'end_point' not in st.session_state:
    st.session_state['end_point'] = None
if 'current_mode' not in st.session_state: # 현재 모드 저장용 추가
    st.session_state['current_mode'] = None

st.title("🚗/🚶 안전 최단 경로 탐색기")

# -----------------------------------------------------------
# 2. 데이터 로드 및 전처리
# -----------------------------------------------------------
@st.cache_data
def load_and_process_data(filepath):
    try:
        df = pd.read_csv(filepath)
        
        # 좌표 변환 (TM -> WGS84)
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
        df = df.dropna(subset=['노드명', 'lat', 'lon'])
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

data_file = "20251229road_29최종.csv"
df_safety = load_and_process_data(data_file)

if df_safety.empty:
    st.warning("데이터 파일을 찾을 수 없습니다.")
    st.stop()

# -----------------------------------------------------------
# 3. 경로 탐색 API 함수
# -----------------------------------------------------------
def get_osrm_route(start_coords, end_coords, mode):
    # 보행자용 프로필 명칭: 'foot' 사용 (OSRM 표준)
    osrm_mode = 'foot' if mode == 'walking' else 'driving'
    
    base_url = f"http://router.project-osrm.org/route/v1/{osrm_mode}/"
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
# 4. 사이드바 UI
# -----------------------------------------------------------
with st.sidebar:
    st.header("🔍 경로 설정")
    
    mode_selection = st.radio("이동 수단 선택", ["자동차 (Car)", "보행자 (Walk)"])
    routing_mode = 'driving' if mode_selection == "자동차 (Car)" else 'walking'
    
    st.markdown("---")
    
    # 노드명 리스트 (가나다순)
    node_list = sorted(df_safety['노드명'].unique())
    
    # Selectbox
    st.subheader("출발지/도착지 선택")
    idx_start = 0
    idx_end = min(1, len(node_list)-1)
    
    start_node_name = st.selectbox("출발지 (데이터 목록)", node_list, index=idx_start)
    end_node_name = st.selectbox("도착지 (데이터 목록)", node_list, index=idx_end)
    
    search_btn = st.button("경로 찾기")

# -----------------------------------------------------------
# 5. 로직 실행
# -----------------------------------------------------------
if search_btn:
    if start_node_name == end_node_name:
        st.error("출발지와 도착지가 같습니다.")
    else:
        with st.spinner("경로 및 시간 계산 중..."):
            try:
                # 좌표 추출
                start_row = df_safety[df_safety['노드명'] == start_node_name].iloc[0]
                end_row = df_safety[df_safety['노드명'] == end_node_name].iloc[0]
                
                s_lat, s_lon = start_row['lat'], start_row['lon']
                e_lat, e_lon = end_row['lat'], end_row['lon']
                
                # API 호출
                route_data = get_osrm_route((s_lat, s_lon), (e_lat, e_lon), routing_mode)
                
                if route_data:
                    # 데이터 세션 저장
                    st.session_state['route_data'] = route_data
                    st.session_state['start_point'] = (s_lat, s_lon, start_node_name)
                    st.session_state['end_point'] = (e_lat, e_lon, end_node_name)
                    st.session_state['current_mode'] = routing_mode # 현재 모드 저장
                    
                    # 위험도 분석 (KDTree)
                    path_coords = route_data['geometry']['coordinates']
                    path_latlon = [[p[1], p[0]] for p in path_coords]
                    
                    tree = cKDTree(df_safety[['lat', 'lon']].values)
                    path_points = np.array(path_latlon)
                    if len(path_points) > 100: path_points = path_points[::5]
                    
                    indices = tree.query_ball_point(path_points, r=0.003)
                    unique_indices = set().union(*indices)
                    st.session_state['nearby_risks'] = df_safety.iloc[list(unique_indices)]
                else:
                    st.error("경로를 찾을 수 없습니다.")
            except Exception as e:
                st.error(f"오류 발생: {e}")

# -----------------------------------------------------------
# 6. 지도 및 결과 그리기
# -----------------------------------------------------------

if st.session_state['start_point']:
    center_loc = [st.session_state['start_point'][0], st.session_state['start_point'][1]]
    zoom = 13
else:
    center_loc = [37.5665, 126.9780]
    zoom = 11

m = folium.Map(location=center_loc, zoom_start=zoom)

if st.session_state['route_data']:
    r_data = st.session_state['route_data']
    s_pt = st.session_state['start_point']
    e_pt = st.session_state['end_point']
    risks = st.session_state['nearby_risks']
    saved_mode = st.session_state['current_mode']
    
    # -------------------------------------------------------
    # [수정됨] 시간 계산 로직
    # -------------------------------------------------------
    distance_meters = r_data['distance']
    distance_km = distance_meters / 1000
    
    if saved_mode == 'walking':
        # 보행자: 시속 4km 가정 (API 값이 비현실적일 경우를 대비해 직접 계산)
        duration_min = (distance_km / 4) * 60
        line_color = 'blue'
        dash_array = '5, 10' # 점선 효과
        tooltip_txt = "보행자 경로 (도보)"
    else:
        # 자동차: API가 준 시간 사용 (초 단위 -> 분 단위)
        duration_min = r_data['duration'] / 60
        line_color = 'red'
        dash_array = None # 실선
        tooltip_txt = "자동차 경로 (주행)"

    # 경로 그리기
    path_coords = r_data['geometry']['coordinates']
    path_latlon = [[p[1], p[0]] for p in path_coords]
    
    folium.PolyLine(
        locations=path_latlon,
        color=line_color,
        weight=6,
        opacity=0.8,
        dash_array=dash_array, # 점선/실선 적용
        tooltip=tooltip_txt
    ).add_to(m)
    
    # 출발/도착 마커
    folium.Marker([s_pt[0], s_pt[1]], popup=f"출발: {s_pt[2]}", icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker([e_pt[0], e_pt[1]], popup=f"도착: {e_pt[2]}", icon=folium.Icon(color='black', icon='stop')).add_to(m)
    
    # 위험 정보 마커
    color_map = {'A': 'blue', 'B': 'green', 'C': 'orange', 'D': 'red', 'E': 'black'}
    for _, row in risks.iterrows():
        grade = row['교차로안전등급']
        # 보행자 모드일 땐 위험 등급 D, E만 표시하도록 필터링 (선택사항)
        if saved_mode == 'walking' and grade not in ['D', 'E', 'C']:
             continue 
            
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=6,
            color=color_map.get(grade, 'gray'),
            fill=True, fill_opacity=0.7,
            popup=folium.Popup(f"<b>{row['노드명']}</b><br>등급: {grade}", max_width=200)
        ).add_to(m)

st_folium(m, width=1000, height=600)

# 통계 정보 표시
if st.session_state['route_data']:
    # 위에서 계산한 변수들(duration_min 등)은 if문 안에서만 유효할 수 있으므로 다시 정의하거나 가져옴
    dist_km = st.session_state['route_data']['distance'] / 1000
    
    # 시간 재계산 (표시용)
    if st.session_state['current_mode'] == 'walking':
        final_time = (dist_km / 4) * 60 # 시속 4km 기준
        mode_label = "🚶 보행자 모드"
    else:
        final_time = st.session_state['route_data']['duration'] / 60
        mode_label = "🚗 자동차 모드"

    st.subheader(f"📊 분석 결과 ({mode_label})")
    c1, c2, c3 = st.columns(3)
    c1.metric("총 거리", f"{dist_km:.2f} km")
    
    # 시간 표시 포맷팅 (시간/분 구분)
    if final_time >= 60:
        h = int(final_time // 60)
        m = int(final_time % 60)
        time_str = f"{h}시간 {m}분"
    else:
        time_str = f"{final_time:.0f} 분"
        
    c2.metric("예상 소요 시간", time_str)
    c3.metric("경로상 위험 정보", f"{len(st.session_state['nearby_risks'])} 개")
