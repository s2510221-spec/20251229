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
st.set_page_config(layout="wide", page_title="SafeRoad Pro")

st.title("🚦 SafeRoad: 맞춤형 안전 경로 시스템")
st.markdown("자동차는 **도로 전체 정보**를, 보행자는 **위험 회피 정보**를 우선적으로 제공합니다.")

# ---------------------------------------------------------
# 2. 데이터 로드 및 "스마트" 전처리
# ---------------------------------------------------------
@st.cache_data
def load_data():
    file_path = '20251229road_최종.csv'
    df = None
    
    # 1) 인코딩 자동 감지하여 읽기
    for enc in ['cp949', 'utf-8', 'euc-kr', 'utf-8-sig']:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip()
            break
        except: continue
    
    if df is None:
        return None

    # 2) 위도/경도 컬럼 찾기 (이름 기반 + 값 범위 기반)
    lat_col, lon_col = None, None
    
    # 이름으로 1차 시도
    for col in df.columns:
        c_low = col.lower()
        if any(x in c_low for x in ['lat', '위도']): lat_col = col
        if any(x in c_low for x in ['lon', '경도']): lon_col = col

    # 못 찾았으면 값 범위(대한민국 좌표)로 2차 시도
    if not lat_col or not lon_col:
        num_cols = df.select_dtypes(include=[np.number]).columns
        for col in num_cols:
            mean_val = df[col].mean()
            if 33 <= mean_val <= 39: lat_col = col
            elif 124 <= mean_val <= 132: lon_col = col

    if not lat_col or not lon_col:
        return pd.DataFrame() # 빈 데이터프레임 반환

    # 3) 데이터 표준화 및 결측치 제거
    df = df.dropna(subset=[lat_col, lon_col]) # 좌표 없는 행 삭제
    
    # 이름 컬럼 찾기
    name_col = next((c for c in df.columns if df[c].dtype == 'object'), None)
    
    # 위험도 컬럼 찾기 (숫자형 중 좌표 제외)
    risk_col = next((c for c in df.select_dtypes(include=[np.number]).columns if c not in [lat_col, lon_col]), None)

    # 최종 정리
    clean_df = pd.DataFrame()
    clean_df['lat'] = df[lat_col]
    clean_df['lon'] = df[lon_col]
    clean_df['road_name'] = df[name_col].astype(str) if name_col else [f"지점_{i}" for i in range(len(df))]
    clean_df['risk_score'] = df[risk_col] if risk_col else np.random.randint(1, 100, len(df))
    
    return clean_df

df = load_data()

# ---------------------------------------------------------
# 3. 사이드바 설정
# ---------------------------------------------------------
st.sidebar.header("🕹️ 모드 설정")

if df is not None and not df.empty:
    # 모드 선택
    mode = st.sidebar.radio("이동 수단 선택", ["🚗 자동차 모드", "🚶 보행자 모드"])
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("경로 지정")
    
    places = sorted(df['road_name'].unique())
    start_point = st.sidebar.selectbox("출발지", places, index=0)
    end_point = st.sidebar.selectbox("도착지", places, index=1 if len(places)>1 else 0)
    
    search_btn = st.sidebar.button("경로 탐색 실행")
else:
    st.error("데이터 파일을 읽을 수 없거나 좌표 정보가 없습니다.")
    st.stop()

# ---------------------------------------------------------
# 4. 지도 및 분석 로직 (핵심 차별화 구간)
# ---------------------------------------------------------

# 기본 좌표 (데이터의 평균 위치로 설정하여 빈 지도 방지)
base_lat = df['lat'].mean()
base_lon = df['lon'].mean()
m = folium.Map(location=[base_lat, base_lon], zoom_start=11)

if search_btn:
    if start_point == end_point:
        st.warning("출발지와 도착지가 같습니다.")
    else:
        # 좌표 추출
        s_row = df[df['road_name'] == start_point].iloc[0]
        e_row = df[df['road_name'] == end_point].iloc[0]
        s_loc = [s_row['lat'], s_row['lon']]
        e_loc = [e_row['lat'], e_row['lon']]

        # 1. 지도 중심 재설정
        m.location = [(s_loc[0]+e_loc[0])/2, (s_loc[1]+e_loc[1])/2]
        m.zoom_start = 13

        # 2. 출발/도착 마커
        folium.Marker(s_loc, popup="출발", icon=folium.Icon(color='blue', icon='play')).add_to(m)
        folium.Marker(e_loc, popup="도착", icon=folium.Icon(color='red', icon='flag')).add_to(m)

        # 3. 거리 계산 (직선 거리)
        dist_km = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111

        # 4. 주변 데이터 필터링 (화면 내 범위)
        bounds = [
            min(s_loc[0], e_loc[0])-0.02, max(s_loc[0], e_loc[0])+0.02,
            min(s_loc[1], e_loc[1])-0.02, max(s_loc[1], e_loc[1])+0.02
        ]
        nearby_df = df[
            (df['lat'] >= bounds[0]) & (df['lat'] <= bounds[1]) &
            (df['lon'] >= bounds[2]) & (df['lon'] <= bounds[3])
        ]
        
        # =================================================
        # [핵심] 모드별 차별화 로직
        # =================================================
        
        if "자동차" in mode:
            # ---------------------------------------------
            # 🚗 자동차 모드: '전체 흐름'과 '빠른 이동' 중심
            # ---------------------------------------------
            
            # (1) 경로 스타일: 굵고 진한 실선 (고속도로 느낌)
            folium.PolyLine([s_loc, e_loc], color='#2E86C1', weight=8, opacity=0.8, tooltip="주행 경로").add_to(m)
            
            # (2) 정보 표시: MarkerCluster 사용
            # 자동차는 정보가 너무 많으면 산만하므로, 뭉쳐서 보여주다가 확대하면 퍼지게 함
            marker_cluster = MarkerCluster().add_to(m)
            
            for _, row in nearby_df.iterrows():
                if row['road_name'] in [start_point, end_point]: continue
                
                # 색상 결정
                score = row['risk_score']
                color = 'green' if score < 30 else ('orange' if score < 70 else 'red')
                
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=5,
                    color=color, fill=True, fill_color=color,
                    popup=f"{row['road_name']} (위험도: {score})"
                ).add_to(marker_cluster) # 클러스터에 추가

            # (3) 결과 메트릭 (자동차 기준)
            est_time = (dist_km / 40) * 60 # 평균 시속 40km 가정
            
            st.success(f"🚘 자동차 모드 분석 완료")
            c1, c2, c3 = st.columns(3)
            c1.metric("총 거리", f"{dist_km:.2f} km")
            c2.metric("예상 주행 시간", f"{int(est_time)} 분")
            c3.metric("도로 위험 지점", f"{len(nearby_df)} 곳 감지됨")
            
        else:
            # ---------------------------------------------
            # 🚶 보행자 모드: '안전'과 '건강' 중심
            # ---------------------------------------------
            
            # (1) 경로 스타일: 점선 (산책로 느낌)
            folium.PolyLine([s_loc, e_loc], color='#27AE60', weight=5, dash_array='10, 10', opacity=0.9, tooltip="보행 경로").add_to(m)
            
            # (2) 정보 표시: 위험한 곳(Red Zone)만 경고 아이콘
            danger_count = 0
            for _, row in nearby_df.iterrows():
                if row['road_name'] in [start_point, end_point]: continue
                
                if row['risk_score'] >= 70: # 70점 이상 위험 지역만 표시
                    folium.Marker(
                        location=[row['lat'], row['lon']],
                        icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa'),
                        tooltip=f"⚠️ 주의: {row['road_name']}"
                    ).add_to(m)
                    danger_count += 1
                elif row['risk_score'] < 30: # 아주 안전한 곳은 쉼터 아이콘 (선택사항)
                    folium.CircleMarker(
                        location=[row['lat'], row['lon']], radius=3, color='green', fill=True, popup="안전 구역"
                    ).add_to(m)

            # (3) 결과 메트릭 (보행자 기준)
            walk_time = (dist_km / 4) * 60 # 평균 시속 4km 가정
            calories = dist_km * 50 # 1km당 50kcal 소모 가정
            
            st.success(f"🏃 보행자 모드 분석 완료")
            c1, c2, c3 = st.columns(3)
            c1.metric("총 거리", f"{dist_km:.2f} km")
            c2.metric("예상 도보 시간", f"{int(walk_time)} 분")
            c3.metric("예상 소모 칼로리", f"{int(calories)} kcal")
            
            if danger_count > 0:
                st.error(f"🚨 경로상에 보행자 주의 구간이 {danger_count}곳 있습니다! 우회하거나 주의하세요.")
            else:
                st.info("🌳 안전한 산책 경로입니다.")

# 지도 출력 (컨테이너 너비 사용)
st_folium(m, width=None, height=500, use_container_width=True)
