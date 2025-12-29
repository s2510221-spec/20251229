import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
from geopy.geocoders import Nominatim
from pyproj import Transformer
import numpy as np
from scipy.spatial import cKDTree

# -----------------------------------------------------------
# 1. 페이지 설정 및 초기화
# -----------------------------------------------------------
st.set_page_config(
    page_title="안전 경로 네비게이터",
    page_icon="🚗",
    layout="wide"
)

st.title("🚗/🚶 안전 최단 경로 탐색기")
st.markdown("""
이 웹앱은 **최단 거리**뿐만 아니라 도로의 **안전 정보**를 함께 제공합니다.
데이터 출처: 도로 안전 데이터 (20251229road_29최종.csv)
""")

# -----------------------------------------------------------
# 2. 데이터 로드 및 전처리 (좌표 변환 포함)
# -----------------------------------------------------------
@st.cache_data
def load_and_process_data(filepath):
    try:
        df = pd.read_csv(filepath)
        
        # 좌표 변환: CSV의 좌표가 TM(EPSG:5174 또는 5186 등)으로 추정됨.
        # 서울 지역 값(X~45만, Y~20만)을 볼 때, EPSG:5174(중부원점 Bessel) 또는 5186일 가능성이 높음.
        # 일반적인 공공데이터 패턴에 따라 변환을 시도합니다.
        
        # 입력 데이터의 컬럼 확인 (y좌표가 20만, x좌표가 45만이면 -> y가 Easting, x가 Northing일 수 있음)
        # 보통 X(Easting)~200,000, Y(Northing)~500,000(또는 450,000)
        # 파일 샘플: y좌표=209659 (Easting 추정), x좌표=449880 (Northing 추정)
        
        source_crs = "epsg:5174" # 한국 중부원점 (오래된 공공데이터 표준)
        target_crs = "epsg:4326" # 위경도 (WGS84)
        
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        
        # 변환 함수
        def transform_coords(row):
            # 파일 컬럼명에 따라 매핑 (y좌표가 Easting, x좌표가 Northing이라고 가정)
            easting = row['y좌표'] 
            northing = row['x좌표']
            lon, lat = transformer.transform(easting, northing)
            return pd.Series({'lat': lat, 'lon': lon})

        # 좌표 변환 적용
        coords = df.apply(transform_coords, axis=1)
        df = pd.concat([df, coords], axis=1)
        
        # 필요한 컬럼만 선택하여 최적화
        cols_to_keep = ['노드명', '노드위치', '교차로안전등급', '교차로위험수준', '사고카운트', 'lat', 'lon']
        return df[cols_to_keep]
    
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

# 데이터 로드
data_file = "20251229road_29최종.csv"
df_safety = load_and_process_data(data_file)

if df_safety.empty:
    st.warning("데이터 파일을 찾을 수 없거나 형식이 잘못되었습니다.")
    st.stop()

# -----------------------------------------------------------
# 3. 유틸리티 함수 (지오코딩, 경로탐색)
# -----------------------------------------------------------

def get_coordinates(address):
    """주소를 위경도로 변환"""
    geolocator = Nominatim(user_agent="safe_route_app_v1")
    try:
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        else:
            return None, None
    except:
        return None, None

def get_osrm_route(start_coords, end_coords, mode):
    """OSRM API를 이용한 경로 탐색"""
    # mode: 'driving' (자동차), 'walking' (보행자)
    base_url = f"http://router.project-osrm.org/route/v1/{mode}/"
    coords = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    url = f"{base_url}{coords}?overview=full&geometries=geojson"
    
    try:
        r = requests.get(url)
        res = r.json()
        if res.get("code") == "Ok":
            route = res["routes"][0]
            return route # geometry, distance, duration 포함
        else:
            return None
    except:
        return None

# -----------------------------------------------------------
# 4. UI 구성 (사이드바 및 입력)
# -----------------------------------------------------------

with st.sidebar:
    st.header("🔍 경로 설정")
    
    # 모드 선택
    mode = st.radio("이동 수단 선택", ["자동차 (Car)", "보행자 (Walk)"])
    routing_mode = 'driving' if mode == "자동차 (Car)" else 'walking'
    
    st.markdown("---")
    start_input = st.text_input("출발지 (예: 서울역)", "서울 광진구 워커힐로 177")
    end_input = st.text_input("도착지 (예: 강남역)", "서울 중랑구 망우로 185")
    
    search_btn = st.button("경로 찾기")

# -----------------------------------------------------------
# 5. 메인 로직 실행
# -----------------------------------------------------------

if search_btn:
    with st.spinner("경로와 안전 데이터를 분석 중입니다..."):
        # 1. 주소 -> 좌표 변환
        start_lat, start_lon = get_coordinates(start_input)
        end_lat, end_lon = get_coordinates(end_input)
        
        if not start_lat or not end_lat:
            st.error("출발지 또는 도착지를 찾을 수 없습니다. 정확한 주소를 입력해주세요.")
        else:
            # 2. 경로 탐색 (OSRM)
            route_data = get_osrm_route((start_lat, start_lon), (end_lat, end_lon), routing_mode)
            
            if route_data:
                # 경로 형상 가져오기 (GeoJSON 포맷 -> [[lon, lat], ...])
                path_coords = route_data['geometry']['coordinates']
                # Folium은 [lat, lon] 순서를 씀, OSRM은 [lon, lat]
                path_latlon = [[p[1], p[0]] for p in path_coords]
                
                # 거리 및 시간
                distance_km = route_data['distance'] / 1000
                duration_min = route_data['duration'] / 60
                
                st.success(f"경로 탐색 성공! 거리: {distance_km:.2f}km, 예상 소요시간: {duration_min:.0f}분")

                # -------------------------------------------------------
                # 3. 경로 주변 위험/안전 데이터 필터링
                # -------------------------------------------------------
                # 효율적인 검색을 위해 KDTree 사용 (가까운 노드 찾기)
                # 경로의 모든 점에 대해 반경 X미터 내의 데이터 포인트를 찾음
                
                tree = cKDTree(df_safety[['lat', 'lon']].values)
                
                # 경로상의 포인트들 추출 (너무 많으면 샘플링)
                path_points = np.array(path_latlon)
                if len(path_points) > 100:
                    path_points = path_points[::5] # 5개마다 하나씩 샘플링하여 속도 향상
                
                # 경로 주변 0.005도(약 500m) 내의 인덱스 검색
                indices = tree.query_ball_point(path_points, r=0.003) 
                
                unique_indices = set()
                for idx_list in indices:
                    unique_indices.update(idx_list)
                
                nearby_risks = df_safety.iloc[list(unique_indices)]
                
                # -------------------------------------------------------
                # 4. 지도 시각화
                # -------------------------------------------------------
                m = folium.Map(location=[start_lat, start_lon], zoom_start=13)
                
                # 경로 그리기
                folium.PolyLine(
                    locations=path_latlon,
                    color="blue" if routing_mode == 'walking' else "red",
                    weight=5,
                    opacity=0.7,
                    tooltip="추천 경로"
                ).add_to(m)
                
                # 출발/도착 마커
                folium.Marker([start_lat, start_lon], popup="출발", icon=folium.Icon(color='green', icon='play')).add_to(m)
                folium.Marker([end_lat, end_lon], popup="도착", icon=folium.Icon(color='black', icon='stop')).add_to(m)
                
                # 안전 정보 마커 표시 (자동차 모드일 때 더 강조)
                # 안전 등급에 따른 색상 설정
                color_map = {'A': 'blue', 'B': 'green', 'C': 'orange', 'D': 'red', 'E': 'black'}
                
                for _, row in nearby_risks.iterrows():
                    grade = row['교차로안전등급']
                    risk_score = row['교차로위험수준']
                    color = color_map.get(grade, 'gray')
                    
                    # 보행자 모드일 때는 너무 많은 정보가 방해될 수 있으므로, 위험도가 높은(D, E) 곳만 표시하거나
                    # 자동차 모드일 때는 전체 표시하는 식으로 차별화 가능
                    if routing_mode == 'walking' and grade not in ['D', 'E', 'C']:
                        continue
                        
                    folium.CircleMarker(
                        location=[row['lat'], row['lon']],
                        radius=5,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.7,
                        popup=folium.Popup(f"<b>{row['노드명']}</b><br>등급: {grade}<br>위험도: {risk_score:.2f}", max_width=200)
                    ).add_to(m)

                # 범례 추가 (HTML)
                legend_html = '''
                 <div style="position: fixed; 
                             bottom: 50px; left: 50px; width: 150px; height: 160px; 
                             border:2px solid grey; z-index:9999; font-size:14px;
                             background-color:white; opacity: 0.9;">
                             &nbsp;<b>안전 등급</b> <br>
                             &nbsp;<i class="fa fa-circle" style="color:blue"></i> A (안전)<br>
                             &nbsp;<i class="fa fa-circle" style="color:green"></i> B (양호)<br>
                             &nbsp;<i class="fa fa-circle" style="color:orange"></i> C (주의)<br>
                             &nbsp;<i class="fa fa-circle" style="color:red"></i> D (위험)<br>
                             &nbsp;<i class="fa fa-circle" style="color:black"></i> E (매우위험)<br>
                  </div>
                '''
                m.get_root().html.add_child(folium.Element(legend_html))

                st_folium(m, width=1000, height=600)
                
                # 통계 정보 표시
                st.subheader("📊 경로 상 도로 안전 분석")
                col1, col2, col3 = st.columns(3)
                col1.metric("총 거리", f"{distance_km:.2f} km")
                col2.metric("주변 위험 요소 감지", f"{len(nearby_risks)} 건")
                
                # 가장 위험한 곳 표시
                if not nearby_risks.empty:
                    max_risk = nearby_risks.loc[nearby_risks['교차로위험수준'].idxmax()]
                    col3.metric("최대 위험 지점", f"{max_risk['노드명']} (등급 {max_risk['교차로안전등급']})")
                    
                    with st.expander("⚠️ 경로 주변 상세 위험 정보 확인하기"):
                        st.dataframe(nearby_risks[['노드명', '교차로안전등급', '교차로위험수준', '사고카운트']].sort_values(by='교차로위험수준', ascending=False))
            
            else:
                st.error("경로를 계산할 수 없습니다. (섬 지역이거나 도로 데이터가 없는 구간일 수 있습니다)")
else:
    # 초기 화면 지도 (서울 중심)
    m = folium.Map(location=[37.5665, 126.9780], zoom_start=11)
    st_folium(m, width=1000, height=500)
