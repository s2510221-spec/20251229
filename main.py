import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
import numpy as np

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="SafeRoad Simple")
st.title("🚗 SafeRoad: 스마트 경로 탐색")

# 2. 스마트 데이터 로딩 (알아서 찾기)
@st.cache_data
def load_smart_data():
    file_path = '20251229road_최종.csv'
    
    # (1) 파일 읽기 (인코딩 자동 해결)
    df = None
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip() # 공백 제거
            break
        except: continue
            
    if df is None:
        st.error("파일을 읽을 수 없습니다. (인코딩 오류)")
        return pd.DataFrame()

    # (2) 위도/경도 자동 탐지 로직 (컬럼 이름 상관없음)
    # 대한민국 위도 범위(33~39), 경도 범위(124~132)에 맞는 데이터가 들어있는 컬럼을 찾습니다.
    lat_col, lon_col = None, None
    
    # 숫자형 컬럼만 추출
    num_cols = df.select_dtypes(include=[np.number]).columns
    
    for col in num_cols:
        # 데이터의 평균값을 보고 판단
        avg = df[col].mean()
        if 33 <= avg <= 39: # 위도 범위
            lat_col = col
        elif 124 <= avg <= 132: # 경도 범위
            lon_col = col

    # 만약 범위로 못 찾았으면 이름으로 한 번 더 시도
    if not lat_col:
        for col in df.columns:
            if any(k in col.lower() for k in ['lat', '위도', 'y']): lat_col = col; break
    if not lon_col:
        for col in df.columns:
            if any(k in col.lower() for k in ['lon', '경도', 'x']): lon_col = col; break

    if not lat_col or not lon_col:
        st.error("🚨 위도/경도 데이터를 자동으로 찾지 못했습니다. 데이터 파일을 확인해주세요.")
        return pd.DataFrame()

    # (3) 이름/위험도 컬럼 찾기
    name_col = next((c for c in df.columns if df[c].dtype == 'object'), None) # 첫 번째 문자열 컬럼
    risk_col = next((c for c in num_cols if c not in [lat_col, lon_col]), None) # 위경도 뺀 나머지 숫자

    # (4) 표준 이름으로 변경
    df['lat'] = df[lat_col]
    df['lon'] = df[lon_col]
    df['road_name'] = df[name_col].astype(str) if name_col else [f"지점_{i}" for i in range(len(df))]
    df['risk_score'] = df[risk_col] if risk_col else np.random.randint(1, 100, len(df))

    return df

df = load_smart_data()

# 3. 간단해진 UI
if not df.empty:
    st.sidebar.header("경로 설정")
    mode = st.sidebar.radio("이동 모드", ["🚗 자동차", "🚶 보행자"])
    
    places = sorted(df['road_name'].unique())
    start = st.sidebar.selectbox("출발지", places, index=0)
    end = st.sidebar.selectbox("도착지", places, index=1 if len(places)>1 else 0)
    
    if st.sidebar.button("길 찾기"):
        if start == end:
            st.warning("출발지와 도착지가 같습니다.")
        else:
            # 좌표 추출
            s_row = df[df['road_name'] == start].iloc[0]
            e_row = df[df['road_name'] == end].iloc[0]
            s_loc, e_loc = [s_row['lat'], s_row['lon']], [e_row['lat'], e_row['lon']]
            
            # 지도 표시
            mid = [(s_loc[0]+e_loc[0])/2, (s_loc[1]+e_loc[1])/2]
            m = folium.Map(location=mid, zoom_start=12)
            
            # 마커
            folium.Marker(s_loc, icon=folium.Icon(color='blue', icon='play'), tooltip="출발").add_to(m)
            folium.Marker(e_loc, icon=folium.Icon(color='red', icon='stop'), tooltip="도착").add_to(m)
            
            # 선 그리기
            color = 'blue' if "자동차" in mode else 'green'
            style = None if "자동차" in mode else '10'
            folium.PolyLine([s_loc, e_loc], color=color, weight=5, dash_array=style).add_to(m)
            
            # 위험 지역 표시 (범위 내)
            bounds = [min(s_loc[0], e_loc[0])-0.02, max(s_loc[0], e_loc[0])+0.02,
                      min(s_loc[1], e_loc[1])-0.02, max(s_loc[1], e_loc[1])+0.02]
            
            sub = df[(df['lat'].between(bounds[0], bounds[1])) & (df['lon'].between(bounds[2], bounds[3]))]
            
            cnt = 0
            for _, r in sub.iterrows():
                if r['road_name'] in [start, end]: continue
                score = r['risk_score']
                c = 'red' if score >= 70 else ('orange' if score >= 30 else 'green')
                
                if "자동차" in mode:
                    folium.CircleMarker([r['lat'], r['lon']], radius=5, color=c, fill=True, fill_color=c).add_to(m)
                elif c == 'red': # 보행자는 위험한 곳만
                    folium.Marker([r['lat'], r['lon']], icon=folium.Icon(color='red', icon='exclamation-sign')).add_to(m)
                    cnt += 1
            
            st_folium(m, width="100%", height=500)
            
            dist = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111
            st.success(f"거리: {dist:.2f}km | 보행자 위험 구간: {cnt}곳" if "보행자" in mode else f"거리: {dist:.2f}km")
else:
    st.info("데이터 파일을 읽는 중입니다...")
