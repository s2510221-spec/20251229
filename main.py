import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="SafeRoad - 안전 경로 탐색")

st.title("🚗 SafeRoad: 데이터 기반 안전 경로 탐색")
st.markdown("데이터 파일 내의 장소를 선택하여 최단 경로와 안전 정보를 확인합니다.")

# ---------------------------------------------------------
# 2. 데이터 로드 및 전처리 (오류 수정 핵심 부분)
# ---------------------------------------------------------
@st.cache_data
def load_data():
    file_path = '20251229road_최종.csv'
    df = pd.DataFrame()
    
    # 1. 파일 읽기 (인코딩 자동 감지 시도)
    try:
        # 한국 공공데이터는 주로 cp949 또는 euc-kr 사용
        df = pd.read_csv(file_path, encoding='cp949')
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except:
            st.error("파일 인코딩 형식을 알 수 없습니다. (cp949, utf-8 실패)")
            return pd.DataFrame()
    except FileNotFoundError:
        st.error(f"'{file_path}' 파일을 찾을 수 없습니다. 폴더에 파일이 있는지 확인해주세요.")
        return pd.DataFrame()

    # 2. 컬럼명 자동 매핑 (핵심 수정 사항)
    # 데이터의 컬럼명이 무엇이든 lat, lon, road_name으로 통일시킴
    column_mapping = {
        '위도': 'lat', 'latitude': 'lat', 'Lat': 'lat', 'LAT': 'lat',
        '경도': 'lon', 'longitude': 'lon', 'Lon': 'lon', 'LON': 'lon',
        '장소명': 'road_name', '도로명': 'road_name', '지점명': 'road_name', '이름': 'road_name',
        '위험도': 'risk_score', '위험지수': 'risk_score'
    }
    
    # 실제 데이터에 있는 컬럼만 rename 적용
    df = df.rename(columns=column_mapping)

    # 3. 필수 데이터 확인
    if 'lat' not in df.columns or 'lon' not in df.columns:
        st.error("🚨 오류: 데이터 파일에서 위도/경도 정보를 찾을 수 없습니다.")
        st.write("현재 파일의 컬럼 목록:", df.columns.tolist())
        st.write("위도/경도 컬럼 이름을 'lat', 'lon' 또는 '위도', '경도'로 변경해주세요.")
        return pd.DataFrame()

    # road_name 없으면 임의 생성
    if 'road_name' not in df.columns:
        df['road_name'] = [f"지점_{i}" for i in range(len(df))]
    
    # risk_score 없으면 임의 생성 (0~100)
    if 'risk_score' not in df.columns:
        import numpy as np
        df['risk_score'] = np.random.randint(1, 100, size=len(df))

    return df

df = load_data()

def get_risk_level(score):
    if score < 30: return "안전", "green"
    elif score < 70: return "주의", "orange"
    else: return "위험", "red"

# ---------------------------------------------------------
# 3. 사이드바 UI
# ---------------------------------------------------------
st.sidebar.header("📍 설정")

if not df.empty:
    # 데이터 미리보기 (디버깅용 - 필요 없으면 주석 처리)
    with st.expander("데이터 원본 보기 (상위 5개)"):
        st.dataframe(df.head())

    mode = st.sidebar.radio("모드 선택", ("🚗 자동차 모드", "🚶 보행자 모드"))
    
    # 장소 목록 (가나다순 정렬)
    # 문자열로 확실히 변환 후 정렬
    location_list = sorted([str(x) for x in df['road_name'].unique()])
    
    start_point_name = st.sidebar.selectbox("출발지", location_list, index=0)
    
    # 도착지 기본값 설정 로직
    default_end_idx = 1 if len(location_list) > 1 else 0
    end_point_name = st.sidebar.selectbox("도착지", location_list, index=default_end_idx)
    
    search_btn = st.sidebar.button("경로 탐색")
else:
    st.stop() # 데이터 없으면 여기서 멈춤

# ---------------------------------------------------------
# 4. 지도 및 분석 로직
# ---------------------------------------------------------
m = folium.Map(location=[36.5, 127.5], zoom_start=7)

if search_btn:
    if start_point_name == end_point_name:
        st.warning("출발지와 도착지가 동일합니다.")
    else:
        # 선택한 장소의 데이터 행 추출
        start_row = df[df['road_name'] == start_point_name].iloc[0]
        end_row = df[df['road_name'] == end_point_name].iloc[0]
        
        start_coords = [start_row['lat'], start_row['lon']]
        end_coords = [end_row['lat'], end_row['lon']]
        
        # 지도 중심 이동
        mid_lat = (start_coords[0] + end_coords[0]) / 2
        mid_lon = (start_coords[1] + end_coords[1]) / 2
        m.location = [mid_lat, mid_lon]
        m.zoom_start = 12

        # 1. 출발/도착 마커
        folium.Marker(start_coords, popup=f"출발: {start_point_name}", icon=folium.Icon(color="blue", icon="play")).add_to(m)
        folium.Marker(end_coords, popup=f"도착: {end_point_name}", icon=folium.Icon(color="red", icon="stop")).add_to(m)
        
        # 2. 경로 선 그리기
        color = "blue" if "자동차" in mode else "green"
        style = None if "자동차" in mode else "10"
        folium.PolyLine([start_coords, end_coords], color=color, weight=5, dash_array=style).add_to(m)
        
        # 3. 위험도 오버레이 (범위 필터링)
        lats = [start_coords[0], end_coords[0]]
        lons = [start_coords[1], end_coords[1]]
        buffer = 0.03
        
        # 지도에 표시될 범위 내의 데이터만 가져옴
        mask = (df['lat'] >= min(lats)-buffer) & (df['lat'] <= max(lats)+buffer) & \
               (df['lon'] >= min(lons)-buffer) & (df['lon'] <= max(lons)+buffer)
        sub_df = df[mask]
        
        count = 0
        for i, row in sub_df.iterrows():
            # 출발/도착지는 이미 마커가 있으므로 제외
            if row['road_name'] in [start_point_name, end_point_name]:
                continue
                
            lvl_text, lvl_color = get_risk_level(row['risk_score'])
            
            if "자동차" in mode:
                # 자동차: 모든 포인트 표시
                folium.CircleMarker(
                    location=[row['lat'], row['lon']], radius=5, color=lvl_color, fill=True, fill_color=lvl_color,
                    popup=f"{row['road_name']}: {lvl_text}"
                ).add_to(m)
            else:
                # 보행자: 위험(Red)만 경고 마커
                if lvl_color == "red":
                    folium.Marker(
                        location=[row['lat'], row['lon']], 
                        icon=folium.Icon(color="red", icon="exclamation-sign"),
                        tooltip=f"위험: {row['road_name']}"
                    ).add_to(m)
                    count += 1
        
        if "보행자" in mode and count > 0:
            st.warning(f"경로 주변에 보행자 위험 구간이 {count}곳 있습니다.")

# 지도 출력
st_folium(m, width="100%", height=600)

# 하단 정보
if search_btn and not df.empty:
    st.markdown("---")
    dist = math.sqrt((start_coords[0]-end_coords[0])**2 + (start_coords[1]-end_coords[1])**2) * 111
    st.metric("예상 거리 (직선)", f"{dist:.2f} km")
