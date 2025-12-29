import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="SafeRoad - 데이터 컬럼 매핑")

st.title("🚗 SafeRoad: 데이터 기반 경로 탐색")
st.markdown("데이터 파일을 읽고, **좌측 사이드바에서 컬럼을 맞춰주세요.**")

# ---------------------------------------------------------
# 2. 데이터 로드 (매핑 없이 일단 읽기)
# ---------------------------------------------------------
@st.cache_data
def load_raw_data():
    file_path = '20251229road_최종.csv'
    
    # 인코딩 문제 해결 시도
    encodings = ['cp949', 'utf-8', 'euc-kr', 'utf-8-sig']
    
    for enc in encodings:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            # 컬럼 이름의 앞뒤 공백 제거 (매우 중요)
            df.columns = df.columns.str.strip()
            return df
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            st.error(f"❌ 파일을 찾을 수 없습니다: {file_path}")
            return None
        except Exception as e:
            st.error(f"❌ 파일 읽기 오류: {e}")
            return None
    
    st.error("❌ 모든 인코딩 방식으로도 파일을 읽을 수 없습니다.")
    return None

raw_df = load_raw_data()

# ---------------------------------------------------------
# 3. 사이드바: 컬럼 매핑 (여기가 핵심!)
# ---------------------------------------------------------
st.sidebar.header("📂 데이터 설정")

if raw_df is not None:
    st.sidebar.info("데이터가 로드되었습니다. 아래에서 **알맞은 컬럼**을 선택해주세요.")
    
    # 1. 컬럼 선택 상자
    # 사용자에게 어떤 컬럼이 '위도'인지 물어봅니다.
    cols = raw_df.columns.tolist()
    
    # 기본값 자동 추측 (편의성)
    def find_default(options, keywords):
        for opt in options:
            for kw in keywords:
                if kw in opt.lower():
                    return options.index(opt)
        return 0

    st.sidebar.markdown("---")
    st.sidebar.subheader("1. 컬럼 지정")
    
    lat_col = st.sidebar.selectbox(
        "위도(Latitude) 컬럼은 무엇인가요?", 
        cols, 
        index=find_default(cols, ['lat', '위도', 'y'])
    )
    
    lon_col = st.sidebar.selectbox(
        "경도(Longitude) 컬럼은 무엇인가요?", 
        cols, 
        index=find_default(cols, ['lon', '경도', 'x'])
    )
    
    name_col = st.sidebar.selectbox(
        "장소/도로명 컬럼은 무엇인가요?", 
        cols, 
        index=find_default(cols, ['name', '이름', '명', 'place'])
    )
    
    risk_col = st.sidebar.selectbox(
        "위험도 컬럼은 무엇인가요? (없으면 무시)", 
        ['(없음)'] + cols, 
        index=0
    )

    # 2. 데이터 표준화 (선택한 컬럼으로 새 데이터프레임 생성)
    df = raw_df.copy()
    df['lat'] = df[lat_col]
    df['lon'] = df[lon_col]
    df['road_name'] = df[name_col].astype(str)
    
    if risk_col != '(없음)':
        df['risk_score'] = df[risk_col]
    else:
        # 위험도 없으면 랜덤 생성
        import numpy as np
        df['risk_score'] = np.random.randint(1, 100, size=len(df))

    # 데이터 미리보기 제공 (사용자 확인용)
    with st.expander("✅ 적용된 데이터 확인하기"):
        st.dataframe(df[['road_name', 'lat', 'lon', 'risk_score']].head())

    # -----------------------------------------------------
    # 4. 여기서부터 기존 로직 수행
    # -----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.subheader("2. 경로 탐색")
    
    mode = st.sidebar.radio("모드 선택", ("🚗 자동차 모드", "🚶 보행자 모드"))
    
    location_list = sorted(df['road_name'].unique())
    start_point = st.sidebar.selectbox("출발지", location_list, index=0)
    end_point = st.sidebar.selectbox("도착지", location_list, index=1 if len(location_list)>1 else 0)
    
    search_btn = st.sidebar.button("경로 탐색 시작")
    
    # 지도 그리기
    m = folium.Map(location=[36.5, 127.5], zoom_start=7)
    
    if search_btn:
        if start_point == end_point:
            st.warning("출발지와 도착지가 같습니다.")
        else:
            try:
                # 좌표 가져오기
                s_row = df[df['road_name'] == start_point].iloc[0]
                e_row = df[df['road_name'] == end_point].iloc[0]
                
                start_coords = [s_row['lat'], s_row['lon']]
                end_coords = [e_row['lat'], e_row['lon']]
                
                # 지도 중심 이동
                mid_lat = (start_coords[0] + end_coords[0]) / 2
                mid_lon = (start_coords[1] + end_coords[1]) / 2
                m.location = [mid_lat, mid_lon]
                m.zoom_start = 12
                
                # 마커 및 라인
                folium.Marker(start_coords, popup="출발", icon=folium.Icon(color="blue", icon="play")).add_to(m)
                folium.Marker(end_coords, popup="도착", icon=folium.Icon(color="red", icon="stop")).add_to(m)
                
                color = "blue" if "자동차" in mode else "green"
                folium.PolyLine([start_coords, end_coords], color=color, weight=5).add_to(m)
                
                # 주변 정보 표시
                buffer = 0.03
                mask = (df['lat'] >= min(start_coords[0], end_coords[0])-buffer) & \
                       (df['lat'] <= max(start_coords[0], end_coords[0])+buffer) & \
                       (df['lon'] >= min(start_coords[1], end_coords[1])-buffer) & \
                       (df['lon'] <= max(start_coords[1], end_coords[1])+buffer)
                
                nearby = df[mask]
                
                for _, row in nearby.iterrows():
                    if row['road_name'] in [start_point, end_point]: continue
                    
                    score = row['risk_score']
                    c = "green" if score < 30 else ("orange" if score < 70 else "red")
                    
                    if "자동차" in mode:
                        folium.CircleMarker([row['lat'], row['lon']], radius=5, color=c, fill=True, fill_color=c).add_to(m)
                    elif "보행자" in mode and c == "red":
                        folium.Marker([row['lat'], row['lon']], icon=folium.Icon(color="red", icon="exclamation-sign")).add_to(m)
                
                # 거리 표시
                dist = math.sqrt((start_coords[0]-end_coords[0])**2 + (start_coords[1]-end_coords[1])**2) * 111
                st.success(f"거리: 약 {dist:.2f} km")
                
            except Exception as e:
                st.error(f"좌표 처리 중 오류가 발생했습니다: {e}")

    st_folium(m, width="100%", height=600)

else:
    st.warning("데이터 파일을 불러오지 못했습니다. 파일명(20251229road_최종.csv)을 확인하세요.")
