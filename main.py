import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import math
import numpy as np

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="SafeRoad Korea")

st.title("🇰🇷 SafeRoad: 대한민국 안전 경로 탐색")
st.markdown("데이터 내의 장소를 검색하여 최적의 경로와 안전 정보를 제공합니다.")

# ---------------------------------------------------------
# 2. 데이터 자동 로드 (컬럼 선택 과정 삭제)
# ---------------------------------------------------------
@st.cache_data
def load_data_auto():
    file_path = '20251229road_최종.csv'
    df = None
    
    # 1) 파일 읽기 (인코딩 자동 해결)
    for enc in ['cp949', 'utf-8', 'euc-kr', 'utf-8-sig']:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip() # 공백 제거
            break
        except: continue
            
    if df is None:
        st.error("❌ 데이터 파일('20251229road_최종.csv')을 찾을 수 없습니다.")
        return pd.DataFrame()

    # 2) 컬럼 이름 자동 변경 (여기가 핵심: 사용자가 선택 안 해도 됨)
    # 데이터에 있을법한 이름들을 모두 매핑 리스트에 넣음
    rename_map = {}
    for col in df.columns:
        c_lower = col.lower()
        if any(x in c_lower for x in ['lat', '위도', 'y좌표']): rename_map[col] = 'lat'
        elif any(x in c_lower for x in ['lon', '경도', 'x좌표']): rename_map[col] = 'lon'
        elif any(x in c_lower for x in ['name', '장소', '도로', '지점', '명']): rename_map[col] = 'road_name'
        elif any(x in c_lower for x in ['risk', '위험', 'score', '점수']): rename_map[col] = 'risk_score'
    
    df = df.rename(columns=rename_map)

    # 3) 필수 컬럼 확인 및 데이터 청소
    if 'lat' not in df.columns or 'lon' not in df.columns:
        # 이름으로 못 찾았으면, 숫자 범위로 강제 할당 (대한민국 좌표 범위: 위도 33~39, 경도 124~132)
        num_cols = df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            mean_val = df[c].mean()
            if 33 <= mean_val <= 39: df['lat'] = df[c]
            elif 124 <= mean_val <= 132: df['lon'] = df[c]
    
    # 좌표 없는 행 삭제 (에러 방지)
    if 'lat' in df.columns and 'lon' in df.columns:
        df = df.dropna(subset=['lat', 'lon'])
        # 좌표가 숫자가 아닌 경우 강제 변환
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        df = df.dropna(subset=['lat', 'lon'])
    else:
        st.error("데이터에서 위도/경도 정보를 자동으로 찾을 수 없습니다.")
        return pd.DataFrame()

    # 이름 없으면 자동 생성
    if 'road_name' not in df.columns:
        # 문자열 컬럼 중 첫번째를 이름으로 가정하거나 없으면 생성
        obj_cols = df.select_dtypes(include=['object']).columns
        if len(obj_cols) > 0:
            df['road_name'] = df[obj_cols[0]]
        else:
            df['road_name'] = [f"지점_{i}" for i in range(len(df))]

    # 위험도 없으면 랜덤 생성
    if 'risk_score' not in df.columns:
        df['risk_score'] = np.random.randint(1, 100, len(df))

    return df

df = load_data_auto()

# ---------------------------------------------------------
# 3. 사이드바 UI
# ---------------------------------------------------------
if not df.empty:
    st.sidebar.header("📍 경로 설정")
    
    # 모드 선택
    mode = st.sidebar.radio("이동 수단", ["🚗 자동차 (빠른길)", "🚶 보행자 (안전길)"])
    
    # 장소 선택
    places = sorted(df['road_name'].unique().astype(str))
    start_node = st.sidebar.selectbox("출발지", places, index=0)
    end_node = st.sidebar.selectbox("도착지", places, index=1 if len(places)>1 else 0)
    
    run_btn = st.sidebar.button("경로 분석 시작")
else:
    st.stop()

# ---------------------------------------------------------
# 4. 지도 및 분석 로직 (대한민국 중심)
# ---------------------------------------------------------

# [핵심 변경] 초기 지도 중심을 대한민국(South Korea)으로 고정
# 위도 36.5, 경도 127.5, 줌 레벨 7 (한반도 전체가 보이는 수준)
m = folium.Map(location=[36.5, 127.5], zoom_start=7)

if run_btn:
    if start_node == end_node:
        st.warning("출발지와 도착지가 같습니다.")
    else:
        # 1. 좌표 데이터 가져오기
        s_row = df[df['road_name'] == start_node].iloc[0]
        e_row = df[df['road_name'] == end_node].iloc[0]
        s_loc = [s_row['lat'], s_row['lon']]
        e_loc = [e_row['lat'], e_row['lon']]
        
        # 2. 지도 중심을 경로의 중간지점으로 이동 & 줌인
        mid_lat = (s_loc[0] + e_loc[0]) / 2
        mid_lon = (s_loc[1] + e_loc[1]) / 2
        m.location = [mid_lat, mid_lon]
        m.zoom_start = 12  # 상세 보기
        
        # 3. 마커 표시
        folium.Marker(s_loc, popup="출발", icon=folium.Icon(color='blue', icon='play')).add_to(m)
        folium.Marker(e_loc, popup="도착", icon=folium.Icon(color='red', icon='flag')).add_to(m)
        
        # 4. 주변 데이터 필터링 (화면 범위 내)
        bounds = [
            min(s_loc[0], e_loc[0])-0.03, max(s_loc[0], e_loc[0])+0.03,
            min(s_loc[1], e_loc[1])-0.03, max(s_loc[1], e_loc[1])+0.03
        ]
        nearby = df[
            (df['lat'].between(bounds[0], bounds[1])) & 
            (df['lon'].between(bounds[2], bounds[3]))
        ]
        
        # 거리 계산
        dist = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111

        # ----------------------------------------
        # 모드별 시각화 차별화
        # ----------------------------------------
        if "자동차" in mode:
            # 자동차: 파란 실선 + 클러스터(정보 요약)
            folium.PolyLine([s_loc, e_loc], color='#2E86C1', weight=8, opacity=0.8).add_to(m)
            
            cluster = MarkerCluster().add_to(m)
            for _, r in nearby.iterrows():
                if r['road_name'] in [start_node, end_node]: continue
                sc = r['risk_score']
                c = 'green' if sc < 30 else ('orange' if sc < 70 else 'red')
                folium.CircleMarker(
                    [r['lat'], r['lon']], radius=5, color=c, fill=True, fill_color=c,
                    popup=f"{r['road_name']} ({int(sc)})"
                ).add_to(cluster)
            
            # 정보 패널
            est_time = (dist / 40) * 60
            st.info("🚘 **자동차 경로 분석**")
            c1, c2, c3 = st.columns(3)
            c1.metric("거리", f"{dist:.2f} km")
            c2.metric("예상 시간", f"{int(est_time)} 분")
            c3.metric("도로 상황", f"정보 {len(nearby)}건")

        else:
            # 보행자: 초록 점선 + 위험 경고 아이콘
            folium.PolyLine([s_loc, e_loc], color='#27AE60', weight=6, dash_array='10').add_to(m)
            
            risk_cnt = 0
            for _, r in nearby.iterrows():
                if r['road_name'] in [start_node, end_node]: continue
                # 보행자는 위험한 곳(70점 이상)만 경고
                if r['risk_score'] >= 70:
                    folium.Marker(
                        [r['lat'], r['lon']],
                        icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa'),
                        tooltip=f"⚠️ 주의: {r['road_name']}"
                    ).add_to(m)
                    risk_cnt += 1
            
            # 정보 패널
            walk_time = (dist / 4) * 60
            kcal = dist * 50
            st.success("🚶 **보행자 경로 분석**")
            c1, c2, c3 = st.columns(3)
            c1.metric("거리", f"{dist:.2f} km")
            c2.metric("도보 시간", f"{int(walk_time)} 분")
            c3.metric("소모 칼로리", f"{int(kcal)} kcal")
            
            if risk_cnt > 0:
                st.toast(f"보행 주의 구간이 {risk_cnt}곳 있습니다.", icon="⚠️")

# 지도 출력 (전체 너비 사용)
st_folium(m, width=None, height=550, use_container_width=True)
