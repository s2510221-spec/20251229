import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
from pyproj import Transformer
import numpy as np
from scipy.spatial import cKDTree

# -----------------------------------------------------------
# 1. 기본 설정 및 세션 초기화
# -----------------------------------------------------------
st.set_page_config(page_title="안전 경로 네비게이터", page_icon="🚗", layout="wide")

# 세션 상태 변수 초기화 (없으면 생성)
if 'route_data' not in st.session_state:
    st.session_state['route_data'] = None
if 'nearby_risks' not in st.session_state:
    st.session_state['nearby_risks'] = pd.DataFrame()
if 'start_point' not in st.session_state:
    st.session_state['start_point'] = None
if 'end_point' not in st.session_state:
    st.session_state['end_point'] = None
if 'final_minutes' not in st.session_state:
    st.session_state['final_minutes'] = 0
if 'view_mode' not in st.session_state:
    st.session_state['view_mode'] = None

st.title("🚗/🚶 안전 최단 경로 탐색기")

# -----------------------------------------------------------
# 2. 데이터 로드
# -----------------------------------------------------------
@st.cache_data
def load_and_process_data(filepath):
    try:
        df = pd.read_csv(filepath)
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
        st.error(f"데이터 오류: {e}")
        return pd.DataFrame()

data_file = "20251229road_29최종.csv"
df_safety = load_and_process_data(data_file)

if df_safety.empty:
    st.warning("데이터 파일이 없습니다.")
    st.stop()

# -----------------------------------------------------------
# 3. 경로 탐색 API
# -----------------------------------------------------------
def get_osrm_route(start_coords, end_coords, mode):
    # OSRM 모드 설정 (자동차: driving, 보행자: foot)
    osrm_mode = 'foot' if mode == 'walking' else 'driving'
    
    base_url = f"http://router.project-osrm.org/route/v1/{osrm_mode}/"
    coords = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    url = f"{base_url}{coords}?overview=full&geometries=geojson"
    
    try:
        r = requests.get(url)
        if r.status_code == 200:
            res = r.json()
            if res.get("code") == "Ok":
                return res["routes"][0]
        return None
    except:
        return None

# -----------------------------------------------------------
# 4. 사이드바 (입력)
# -----------------------------------------------------------
with st.sidebar:
    st.header("🔍 설정")
    
    # 모드 선택
    mode_radio = st.radio("이동 수단", ["자동차 (Car)", "보행자 (Walk)"])
    routing_mode = 'driving' if mode_radio == "자동차 (Car)" else 'walking'
    
    st.markdown("---")
    
    # 출발/도착 선택
    node_list = sorted(df_safety['노드명'].unique())
    idx_start = 0
    idx_end = min(1, len(node_list)-1)
    
    start_node = st.selectbox("출발지", node_list, index=idx_start)
    end_node = st.selectbox("도착지", node_list, index=idx_end)
    
    search_btn = st.button("경로 찾기")

# -----------------------------------------------------------
# 5. 실행 로직 (버튼 클릭 시 계산 및 저장)
# -----------------------------------------------------------
if search_btn:
    if start_node == end_node:
        st.error("출발지와 도착지가 같습니다.")
    else:
        with st.spinner(f"{mode_radio} 모드로 분석 중..."):
            s_row = df_safety[df_safety['노드명'] == start_node].iloc[0]
            e_row = df_safety[df_safety['노드명'] == end_node].iloc[0]
            
            s_loc = (s_row['lat'], s_row['lon'])
            e_loc = (e_row['lat'], e_row['lon'])
            
            # API 호출
            route_data = get_osrm_route(s_loc, e_loc, routing_mode)
            
            if route_data:
                # 1. 기본 데이터 저장
                st.session_state['route_data'] = route_data
                st.session_state['start_point'] = (s_loc[0], s_loc[1], start_node)
                st.session_state['end_point'] = (e_loc[0], e_loc[1], end_node)
                st.session_state['view_mode'] = routing_mode # 현재 모드 박제
                
                # 2. 시간 계산 (여기가 핵심!)
                dist_km = route_data['distance'] / 1000
                if routing_mode == 'walking':
                    # 보행자: 거리 / 4km/h * 60분
                    calc_time = (dist_km / 4) * 60
                else:
                    # 자동차: API 제공 시간 (초) / 60분
                    calc_time = route_data['duration'] / 60
                
                st.session_state['final_minutes'] = calc_time
                
                # 3. 위험도 분석
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

# -----------------------------------------------------------
# 6. 결과 화면 (저장된 데이터 기반)
# -----------------------------------------------------------

# 데이터가 있을 때만 화면 표시
if st.session_state['route_data']:
    # 저장된 변수 불러오기
    r_data = st.session_state['route_data']
    s_pt = st.session_state['start_point']
    e_pt = st.session_state['end_point']
    risks = st.session_state['nearby_risks']
    current_view_mode = st.session_state['view_mode']
    final_time = st.session_state['final_minutes']
    
    # 지도 설정
    m = folium.Map(location=[s_pt[0], s_pt[1]], zoom_start=13)
    
    # 선 스타일 결정 (모드에 따라 다르게)
    if current_view_mode == 'walking':
        line_color = 'blue'
        line_style = '10, 10' # 점선
        tooltip_txt = "보행자 경로 (천천히)"
    else:
        line_color = 'red'
        line_style = None # 실선
        tooltip_txt = "자동차 경로 (빠름)"
    
    # 경로 그리기
    path_coords = r_data['geometry']['coordinates']
    path_latlon = [[p[1], p[0]] for p in path_coords]
    
    folium.PolyLine(
        locations=path_latlon,
        color=line_color,
        weight=6,
        dash_array=line_style,
        opacity=0.8,
        tooltip=tooltip_txt
    ).add_to(m)
    
    # 마커 추가
    folium.Marker([s_pt[0], s_pt[1]], popup=s_pt[2], icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker([e_pt[0], e_pt[1]], popup=e_pt[2], icon=folium.Icon(color='black', icon='stop')).add_to(m)
    
    # 위험 요소 표시
    color_map = {'A': 'blue', 'B': 'green', 'C': 'orange', 'D': 'red', 'E': 'black'}
    for _, row in risks.iterrows():
        grade = row['교차로안전등급']
        # 보행자 모드일 때는 위험한 곳(D, E)만 강조 (선택사항)
        if current_view_mode == 'walking' and grade not in ['C', 'D', 'E']:
            continue
            
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=6, color=color_map.get(grade, 'gray'),
            fill=True, fill_opacity=0.7,
            popup=f"{row['노드명']}({grade})"
        ).add_to(m)

    st_folium(m, width=1000, height=600)
    
    # 통계 출력
    dist_km = r_data['distance'] / 1000
    
    # 시간 포맷팅
    if final_time >= 60:
        time_str = f"{int(final_time // 60)}시간 {int(final_time % 60)}분"
    else:
        time_str = f"{final_time:.0f}분"

    st.subheader(f"📊 분석 결과: {current_view_mode.upper()} 모드")
    c1, c2, c3 = st.columns(3)
    
    c1.metric("이동 거리", f"{dist_km:.2f} km")
    
    # 여기가 중요: 모드에 따라 완전히 다른 시간을 보여줌
    c2.metric("예상 소요 시간", time_str, delta="느림" if current_view_mode == 'walking' else "빠름")
    
    c3.metric("주변 위험 정보", f"{len(risks)} 건")

elif not search_btn:
    # 초기 화면
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11)
    st_folium(m, width=1000, height=500)
