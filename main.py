import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
import numpy as np

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="SafeRoad Smart")
st.title("🚗 SafeRoad: 스마트 경로 탐색 (에러 방지 버전)")

# ---------------------------------------------------------
# 2. 데이터 로드 및 전처리 (NaN 에러 해결 로직 추가)
# ---------------------------------------------------------
@st.cache_data
def load_smart_data():
    file_path = '20251229road_최종.csv'
    
    # 1) 파일 읽기 (인코딩 자동 해결)
    df = None
    for enc in ['cp949', 'utf-8', 'euc-kr', 'utf-8-sig']:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip() # 공백 제거
            break
        except: continue
            
    if df is None:
        st.error("❌ 파일을 읽을 수 없습니다. 인코딩 형식을 확인해주세요.")
        return pd.DataFrame()

    # 2) 숫자형 컬럼 찾기 (위도/경도 후보군)
    # 데이터를 숫자로 강제 변환 (문자열이 섞여있으면 NaN 처리)
    for col in df.columns:
        # object 타입이라면 숫자로 변환 시도해봄 (안되면 원본 유지)
        try:
            converted = pd.to_numeric(df[col], errors='coerce')
            # 변환 후 NaN이 너무 많지 않으면(절반 이상이 숫자면) 숫자 컬럼으로 간주
            if converted.notna().sum() > len(df) / 2:
                df[col] = converted
        except:
            pass

    # 3) 위도/경도 컬럼 자동 탐지 로직
    # 대한민국 위도: 33~39, 경도: 124~132
    lat_col, lon_col = None, None
    
    # 숫자형 컬럼만 추출
    num_cols = df.select_dtypes(include=[np.number]).columns
    
    for col in num_cols:
        mean_val = df[col].mean() # NaN 제외하고 평균 계산
        if 33 <= mean_val <= 39:
            lat_col = col
        elif 124 <= mean_val <= 132:
            lon_col = col

    # 범위로 못 찾았으면 이름으로 찾기
    if not lat_col:
        for col in df.columns:
            if any(k in col.lower() for k in ['lat', '위도', 'y']): lat_col = col; break
    if not lon_col:
        for col in df.columns:
            if any(k in col.lower() for k in ['lon', '경도', 'x']): lon_col = col; break

    if not lat_col or not lon_col:
        st.error("🚨 데이터에서 위도/경도 컬럼을 찾지 못했습니다.")
        return pd.DataFrame()

    # 4) [중요] 결측치(NaN) 제거 및 데이터 정리
    # 위도나 경도가 비어있는 행은 지도에 표시 불가하므로 삭제
    df = df.dropna(subset=[lat_col, lon_col])
    
    # 이름/위험도 컬럼 찾기
    name_col = next((c for c in df.columns if df[c].dtype == 'object'), None)
    risk_col = next((c for c in num_cols if c not in [lat_col, lon_col]), None)

    # 표준 컬럼명으로 정리
    clean_df = df.copy()
    clean_df['lat'] = clean_df[lat_col]
    clean_df['lon'] = clean_df[lon_col]
    clean_df['road_name'] = clean_df[name_col].astype(str) if name_col else [f"지점_{i}" for i in range(len(df))]
    
    if risk_col:
        clean_df['risk_score'] = clean_df[risk_col].fillna(50) # 위험도 비었으면 보통(50)으로
    else:
        clean_df['risk_score'] = np.random.randint(1, 100, len(df))

    return clean_df

df = load_smart_data()

# ---------------------------------------------------------
# 3. UI 및 지도 로직
# ---------------------------------------------------------
if not df.empty:
    st.sidebar.header("🗺️ 경로 설정")
    mode = st.sidebar.radio("이동 모드", ["🚗 자동차", "🚶 보행자"])
    
    # 정렬된 장소 목록
    places = sorted(df['road_name'].unique())
    
    start = st.sidebar.selectbox("출발지", places, index=0)
    # 도착지 기본값 로직
    default_end = 1 if len(places) > 1 else 0
    end = st.sidebar.selectbox("도착지", places, index=default_end)
    
    if st.sidebar.button("길 찾기"):
        if start == end:
            st.warning("출발지와 도착지가 같습니다.")
        else:
            # 선택한 장소의 데이터 가져오기
            s_row = df[df['road_name'] == start].iloc[0]
            e_row = df[df['road_name'] == end].iloc[0]
            
            s_loc = [s_row['lat'], s_row['lon']]
            e_loc = [e_row['lat'], e_row['lon']]
            
            # [추가 검증] 좌표가 유효한 숫자인지 마지막 확인
            if pd.isna(s_loc).any() or pd.isna(e_loc).any():
                st.error("선택한 장소의 좌표 정보가 비어있어 지도를 그릴 수 없습니다.")
            else:
                # 지도 중심 계산
                mid_lat = (s_loc[0] + e_loc[0]) / 2
                mid_lon = (s_loc[1] + e_loc[1]) / 2
                
                # 지도 생성
                m = folium.Map(location=[mid_lat, mid_lon], zoom_start=12)
                
                # 마커 추가
                folium.Marker(s_loc, icon=folium.Icon(color='blue', icon='play'), tooltip="출발").add_to(m)
                folium.Marker(e_loc, icon=folium.Icon(color='red', icon='stop'), tooltip="도착").add_to(m)
                
                # 경로 선 그리기
                color = 'blue' if "자동차" in mode else 'green'
                style = None if "자동차" in mode else '10'
                folium.PolyLine([s_loc, e_loc], color=color, weight=5, dash_array=style).add_to(m)
                
                # 주변 위험 지역 탐색 (반경 0.02도 내)
                bounds = [
                    min(s_loc[0], e_loc[0]) - 0.02, max(s_loc[0], e_loc[0]) + 0.02,
                    min(s_loc[1], e_loc[1]) - 0.02, max(s_loc[1], e_loc[1]) + 0.02
                ]
                
                sub = df[
                    (df['lat'] >= bounds[0]) & (df['lat'] <= bounds[1]) &
                    (df['lon'] >= bounds[2]) & (df['lon'] <= bounds[3])
                ]
                
                cnt = 0
                for _, r in sub.iterrows():
                    # 출발/도착지는 제외
                    if r['road_name'] in [start, end]: continue
                    
                    score = r['risk_score']
                    c = 'red' if score >= 70 else ('orange' if score >= 30 else 'green')
                    
                    if "자동차" in mode:
                        folium.CircleMarker([r['lat'], r['lon']], radius=5, color=c, fill=True, fill_color=c, popup=r['road_name']).add_to(m)
                    elif c == 'red': # 보행자는 위험한 곳만
                        folium.Marker([r['lat'], r['lon']], icon=folium.Icon(color='red', icon='exclamation-sign'), tooltip=r['road_name']).add_to(m)
                        cnt += 1
                
                st_folium(m, width="100%", height=500)
                
                # 거리 계산
                dist = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111
                msg = f"거리: 약 {dist:.2f}km"
                if "보행자" in mode and cnt > 0:
                    st.warning(f"{msg} | 경로 주변 보행자 위험 구간: {cnt}곳")
                else:
                    st.success(msg)

else:
    st.info("데이터를 불러오는 중입니다...")
